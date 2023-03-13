import logging
import os
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from typing import Any, List, Optional

import cv2
import numpy as np
from PIL import Image
from tensorflow.keras.models import load_model
from tensorflow import convert_to_tensor, stack

from app.async_utils import load
from app.clients import MyImgurClient, MyWallhavenClient, RedditClient
from app.config import config, is_windows
from app.db import (
    Wallpaper,
    all_local_wallpapers,
    bulk_insert_colors,
    bulk_insert_tags,
    bulk_insert_wallpapers,
    bulk_update_wallpapers,
    create_session,
)

logger = logging.getLogger(__name__)


def to_hex(red: int, green: int, blue: int) -> str:
    """Convert 0-255 RGB values to a hex color string"""
    return int(f"{int(red):02x}{int(green):02x}{int(blue):02x}", 16)


def dhash(image: np.array, hashSize: int = 8) -> int:
    """
    Creates a perceptual hash known as 'dhash' for a given image as an array
    Reference: http://www.hackerfactor.com/blog/index.php?/archives/529-Kind-of-Like-That.html
    The hash size will determine the bits to be compared, by default 64(8x8) is used.
    """
    resized = cv2.resize(image, (hashSize + 1, hashSize))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2**i for (i, v) in enumerate(diff.flatten()) if v])


# TODO: Dear god this hurts to look at
def common_colors(image: np.array, n_colors: int = 5) -> List[str]:
    """Gather an ordered list of the most common colors in an image array"""
    pixels = np.float32(image.reshape(-1, 3))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
    flags = cv2.KMEANS_RANDOM_CENTERS
    _, labels, palette = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)
    _, counts = np.unique(labels, return_counts=True)
    return list(
        zip(*sorted(zip(palette.astype(int), counts), key=lambda x: x[1], reverse=True))
    )[0]


# TODO: Would be nice to be able to package this with the model
#   some models do it with a inference prediction api but I don't have that
def load_label_names():
    with open(config.label_loc, "r") as fobj:
        label_names = fobj.read().split("\n")
    return label_names


def image_labels(image, model, labels):
    image = image.resize((224, 224)).convert("RGB")
    input_tensor = convert_to_tensor(image)
    # Direct model calls expect a batch of tensors
    # so we make one, my hacky way for single image inference
    # but I should run these as a batch run instead 
    input_tensor = stack([input_tensor])
    pred = model(input_tensor, training=False)
    ix = pred[0].numpy().argmax()
    return [labels[ix]]


def analyze_image(image, model, label_names):
    """
    Gather information on an image for search organization.
    :param PIL.Image image: image to analyze.
    :param int image_size: File size of the image, this is inaccurate to calculate from
                           the PIL.Image itself, should be gathered from the file itself.
    :return dict: Dictionary of analysis data.
    """

    width, height = image.size
    # TODO: Random values but thumbnail resizes with respect to aspect ratio
    #       what is the best size for speed vs accuracy tho?
    image.thumbnail((480, 270), Image.ANTIALIAS)
    image_array = np.asarray(image)
    image.convert("L")
    gray_image_array = np.asarray(image)
    colors = common_colors(image_array, 10)
    colors = [to_hex(*color) for color in colors]
    tags = image_labels(image, model, label_names)

    return {
        "dhash": str(dhash(gray_image_array)),
        "width": width,
        "height": height,
        "analyzed": True,
    }, colors, tags


def scan_local_images():
    """Check local source for file changes and add/remove as needed"""
    # Get all known local entries and group by their dirs
    stored_sets = defaultdict(set)
    for wallpaper in all_local_wallpapers(2000):
        stored_sets[wallpaper.source_uri].add(
            (wallpaper.filename, wallpaper.file_ctime)
        )

    # Scan filesystem for images and group by their dirs
    found_sets = defaultdict(set)
    for image_dir in config.core.image_dirs:
        for file in os.listdir(image_dir):
            fullpath = os.path.join(image_dir, file)
            if os.path.isfile(fullpath):  # TODO: and is an image
                stat = os.stat(fullpath)
                filename, ext = os.path.splitext(file)
                found_sets[image_dir].add((f"{filename}{ext}", int(stat.st_ctime)))

    for image_dir in config.core.image_dirs:
        added = found_sets[image_dir] - stored_sets[image_dir]
        removed = stored_sets[image_dir] - found_sets[image_dir]

        to_add = []
        for file in added:
            file, ctime = file
            filename, ext = os.path.splitext(file)
            to_add.append(
                {
                    "source_uri": image_dir,
                    "source_id": filename,
                    "source_type": "local",
                    "image_type": ext[1:],
                    "analyzed": False,
                    "file_ctime": ctime,
                }
            )
        if to_add:
            bulk_insert_wallpapers(to_add)

        # TODO: This will not scale great, make a bulk routine?
        for file in removed:
            file, ctime = file
            with create_session() as session:
                session.query(Wallpaper).filter(
                    Wallpaper.source_type == "local"
                    and Wallpaper.source_id == file
                    and Wallpaper.file_ctime == ctime
                ).delete(synchronize_session=False)
                session.commit()

    return len(to_add)


class Crawler:
    def __init__(self):
        self.clients = (RedditClient, MyImgurClient, MyWallhavenClient)
        self.client = self.clients[0]
        self._cancel = False

    def cancel(self):
        self.client.cancel = True
        self._cancel = True
        logger.info(f"Canceling Crawler run")

    @staticmethod
    def client_enabled(client) -> bool:
        return getattr(getattr(config, client.source_type), "enabled")

    def __call__(self, limit: int) -> int:
        new_images = 0
        new_images += scan_local_images()
        for client_cls in self.clients:
            if self._cancel:
                break
            if not self.client_enabled(client_cls):
                continue
            self.client = client_cls()
            data = [entry for entry in self.client.fetch(limit)]
            bulk_insert_wallpapers(data)
            new_images += len(data)
        return new_images


class Inspector:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True
        logger.info(f"Canceling Inspector run")

    # TODO: step_callback was originally used with a progressbar ui
    #   not used now but maybe it would look nice
    def __call__(
        self, limit: int = 20, batch: int = 100, step_callback: Optional[Any] = None
    ):
        number_of_full_runs = limit // batch
        leftover = limit % batch
        processes = cpu_count()

        model = load_model(config.core.model_loc)
        labels = load_label_names()

        def analyze_set(num: int):
            with create_session() as session:
                to_analyze = (
                    session.query(Wallpaper)
                    .filter(Wallpaper.analyzed == False)
                    .limit(num)
                    .all()
                )
            uris = []
            _ids = []
            for obj in to_analyze:
                uris.append(obj.src_path)
                _ids.append(obj.id)

            if self._cancel:
                return

            image_data, err = load(uris, timeout=60)
            images = []
            ids = []
            for ix, data in enumerate(image_data):
                # An image failed to load so we must account for the ids
                if data is None:
                    pass
                else:
                    ids.append(_ids[ix])
                    images.append(data.convert("RGB"))

            # TODO: Running tf with a process pool locks up the computer it seems
            # For some reason the process pool spawns a bunch
            # of ui windows on windows os so lets not get fancy
            # if is_windows():
            data = map(analyze_image, images, [model] * len(images), [labels] * len(images))
            # else:
            #     with Pool(processes=processes) as pool:
            #         data = pool.map(analyze_image, images)

            to_update = []
            wallpaper_to_colors = {}
            wallpaper_to_tags = {}
            for id, obj in zip(ids, data):
                entry, colors, tags = obj
                to_update.append({"id": id, **entry})
                wallpaper_to_colors[id] = colors
                wallpaper_to_tags[id] = tags

            bulk_update_wallpapers(to_update)
            bulk_insert_colors(wallpaper_to_colors)
            bulk_insert_tags(wallpaper_to_tags)

        if number_of_full_runs > 0:
            for i in range(number_of_full_runs):
                if self._cancel:
                    return
                logger.info(f"Inspecting set of {batch} images")
                analyze_set(batch)
                if step_callback is not None:
                    step_callback((i / number_of_full_runs) * 100)

        if self._cancel:
            return
        logger.info(f"Inspecting set of {leftover} images")
        analyze_set(leftover)
