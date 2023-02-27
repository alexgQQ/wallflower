import asyncio
import io
import logging
import os
import platform
import shutil
import subprocess
import threading
from collections import UserList
from queue import SimpleQueue
from random import choices
from string import ascii_lowercase, ascii_uppercase, digits
from typing import List, Optional, Set, Tuple

import aiofiles
import aiohttp
import PySimpleGUI as sg
from PIL import Image

from app.async_utils import download as async_download
from app.config import user_agent
from app.db import Wallpaper, create_session

logger = logging.getLogger(__name__)


def open_location(path: str):
    """Open an image file  in the system's browser"""
    plat = platform.system()
    if plat == "Linux":
        subprocess.Popen(["xdg-open", path])
    elif plat == "Windows":
        os.startfile(path)
    elif plat == "Darwin":
        subprocess.Popen(["open", path])


def random_uuid4():
    chars = ascii_lowercase + ascii_uppercase + digits
    return "".join(choices(chars, k=8))


def download_files(ids: List[int]) -> Tuple[int, Set[Tuple[str, str]]]:
    """
    Download images to the download location by their ids.
    Intended to run on a background thread. Returns the thread id and
    any failed download src/dst pairs.
    """
    dst = []
    urls = []

    with create_session() as session:
        query = session.query(Wallpaper).filter(Wallpaper.id.in_(ids)).all()

    for image in query:
        if image.source_type == "local":
            shutil.copyfile(image.src_path, image.download_path)
        else:
            dst.append(image.download_path)
            urls.append(image.source_uri)

    failed = async_download(urls, dst)
    return threading.get_ident(), failed


# TODO: Does this have to be global?
#       It's only used for being threadsafe
#       but I'm not sure if making it a cls var
#       compromises that
image_queue = SimpleQueue()


class ImageList(UserList):
    """
    Acts as list for images to show and a buffer for loading images
    in the background. Provides the standard list capabilities but
    should be set with `load_images`. This opens a background thread
    and loads images asynchronously. Make sure to call `clear` before
    each `load_images` call and `from_queue` in the main event loop.
    """

    # The `window` arg is actually not optional as it is needed for
    # thread dispatching. It is listed as a keyword arg with None
    # because `UserList` subclasses need constructors with 0 or 1
    # positional List args
    def __init__(self, seq: List, window: Optional[sg.Window] = None):
        super().__init__(seq)
        self.window = window

    def clear(self):
        """Clear the array and queue and cancel any current image loading"""
        self.run_id = None
        self.data = []
        while not image_queue.empty():
            image_queue.get()

    # TODO: I may want to introduce chunking functionality
    def load_images(self, image_srcs: List[str]):
        """
        Start a background thread and load the provided image paths or urls.
        """
        # Since image will load in async, we need to maintain order
        # by guaranteeing each index position is available
        self.data = [None] * len(image_srcs)
        # Track each run with a specific value so they can be stopped
        self.run_id = random_uuid4()
        thread = self.window.start_thread(
            lambda: self._load(image_srcs),
            "-LOAD_THREAD-",
        )
        logger.info(f"Thread {thread.ident} started for image loading")

    def from_queue(self):
        """Load the image array with images from the queue"""
        while not image_queue.empty():
            ix, image = image_queue.get()
            self.data[ix] = image

    @staticmethod
    def process_image(image: Image, max_width: int = 500):
        """Resize and convert the image for loading"""
        width, height = image.size
        ar = width / height
        image = image.resize((max_width, int(max_width / ar))).convert("RGB")
        return image

    async def _load_source(self, index: int, source: str, run_id: str, retry: int = 0):
        """Load an image source into the queue"""
        try:
            if source.startswith("http"):
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=False),
                    timeout=timeout,
                    headers={"User-Agent": user_agent},
                ) as session:
                    response = await session.get(source)
                    assert response.status == 200
                    data = await response.read()
                    image = Image.open(io.BytesIO(data))
            else:
                async with aiofiles.open(source, mode="rb") as afp:
                    data = await afp.read()
                    image = Image.open(io.BytesIO(data))
            image = self.process_image(image)

        # Image failures should be represented as `None`
        except aiohttp.ClientError as err:
            if retry < 3:
                retry += 1
                logger.info(f"Retry load #{retry} for {source}")
                await self._load_source(index, source, run_id, retry=retry)
            else:
                logger.warning(f"Retries exceeded to load image from {source} - {err}")
                image = None
        except Exception as err:
            logger.warning(f"Unable to load image from {source} - {err}")
            image = None

        # Acts as a sort of cancel flag. If a new image set is called to
        # load while one is still loading, the old results need to be ignored
        if run_id == self.run_id:
            image_queue.put((index, image))
        else:
            logger.info(f"Cancel loading for run: {run_id}")

    async def _gather_load_routines(self, sources: List[str]):
        load_futures = [
            self._load_source(index, sources, self.run_id)
            for index, sources in enumerate(sources)
        ]
        await asyncio.gather(*load_futures)

    def _load(self, sources: List[str]):
        asyncio.run(self._gather_load_routines(sources))
        logger.info(f"Thread {threading.get_ident()} completed for image loading")
