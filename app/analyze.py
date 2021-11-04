from typing import List
import scipy
import cv2
import numpy as np

from io import BytesIO
from PIL import Image, UnidentifiedImageError
from app.async_utils import load
from app.db import (
    create_session, bulk_insert_colors, Wallpaper, bulk_update_wallpapers,
)
from multiprocessing import Pool, cpu_count


def to_hex(red: int, green: int, blue: int) -> str:
    """ Convert 0-255 RGB values to a hex color string """
    return f'{int(red):02x}{int(green):02x}{int(blue):02x}'


def dhash(image: np.array, hashSize: int = 8) -> int:
    """
    Creates a perceptual hash known as 'dhash' for a given image as an array
    Reference: http://www.hackerfactor.com/blog/index.php?/archives/529-Kind-of-Like-That.html
    The hash size will determine the bits to be compared, by default 64(8x8) is used.
    """
    resized = cv2.resize(image, (hashSize + 1, hashSize))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])


def common_colors(image: np.array, num_of_clusters: int = 5) -> List[str]:
    """
    param image: np.array of colored image data, should be at least 3 dimensions
    param num_of_clusters: integer for the number of colors to find
    return dict: dictionary of color counts keyed from the color value
    """
    width, height, channels = image.shape
    image = image.reshape(
        scipy.product((width, height)), channels).astype(float)
    codes, _ = scipy.cluster.vq.kmeans(image, num_of_clusters)
    vecs, _ = scipy.cluster.vq.vq(image, codes)
    counts, _ = scipy.histogram(vecs, len(codes))
    return list(zip(*sorted(zip(codes, counts), key=lambda x: x[1], reverse=True)))[0]


def analyze_image(image):
    """
    Gather information on an image for search organization.
    :param PIL.Image image: image to analyze.
    :param int image_size: File size of the image, this is inaccurate to calculate from
                           the PIL.Image itself, should be gathered from the file itself.
    :return dict: Dictionary of analysis data.
    """

    width, height = image.size
    image.thumbnail((1920, 1080), Image.ANTIALIAS)
    image_array = np.asarray(image)
    image.convert("L")
    gray_image_array = np.asarray(image)
    colors = common_colors(image_array, 10)
    colors = [to_hex(*color) for color in colors]

    return {
        'dhash': str(dhash(gray_image_array)),
        'width': width,
        'height': height,
        "analyzed": True,
    }, colors


def analyze(limit: int = 20, batch: int = 100, step_callback=None):
    number_of_full_runs = limit // batch
    leftover = limit % batch
    processes = cpu_count()
    session = create_session()

    def analyze_set(num):
        to_analyze = session.query(Wallpaper).filter(Wallpaper.analyzed == False).limit(num).all()
        urls = []
        ids = []
        for obj in to_analyze:
            urls.append(obj.source_url)
            ids.append(obj.id)

        images, err = load(urls)
        images = []
        for data in images:
            try:
                images.append(Image.open(BytesIO(data)).convert('RGB'))
            except UnidentifiedImageError:
                pass
        with Pool(processes=processes) as pool:
            data = pool.map(analyze_image, images)
        to_update = []
        wallpaper_to_colors = {}
        for id, obj in zip(ids, data):
            entry = obj[0]
            colors = obj[1]
            to_update.append({ "id": id, **entry })
            wallpaper_to_colors[id] = colors
        bulk_update_wallpapers(session, to_update)
        bulk_insert_colors(session, wallpaper_to_colors)

    if number_of_full_runs > 0:
        for i in range(number_of_full_runs):
            analyze_set(limit)
            if step_callback is not None:
                step_callback((i / number_of_full_runs) * 100)

    analyze_set(leftover)
