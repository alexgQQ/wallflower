from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QListView
from PyQt5.QtGui import QIcon, QPixmap, QImage
from PyQt5.QtCore import QSize, QTimer
import io
from PIL import Image

import asyncio
import aiohttp
import aiofiles
from PIL import Image
from typing import List
from functools import lru_cache


# TODO: For some reason importiung this from utils make the app crash
# should try to fix and make this a util import as it is used in other spots
@lru_cache(maxsize=None)
async def load_file(url: str):
    '''
    Async load routine for an image url.
    '''
    if url.startswith('http'):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            response = await session.get(url)
            assert response.status == 200
            return await response.read()
    else:
        async with aiofiles.open(url, mode='rb') as afp:
            return await afp.read()


async def gather_load_routines(urls: List[str]):
    '''
    Assemble a list of async load routines for execution.
    '''
    load_futures = [load_file(url) for url in urls]
    return await asyncio.gather(*load_futures, return_exceptions=True)


def load(urls: List[str]):
    '''
    Bulk load a list of urls to their respective filename. Executes async routines for better performance.
    '''
    data = asyncio.run(gather_load_routines(urls))
    errors = []
    success = []
    for item in data:
        if isinstance(item, Exception):
            errors.append(item)
            success.append(None)
        else:
            success.append(item)
    return success, errors


def create_icon(image_data):
    icon = QIcon()
    image = Image.open(io.BytesIO(image_data)).resize((128, 128)).convert('RGBA')
    image_data = image.tobytes("raw", "RGBA")
    qim = QImage(image_data, image.size[0], image.size[1], QImage.Format_RGBA8888)
    icon.addPixmap(QPixmap(qim))
    return icon


class ImageList(QListWidget):

    unloaded_items = []

    def setup_ui(self):
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(128, 128))
    #     self.timer = QTimer(self)
    #     self.timer.timeout.connect(self.foobar)
    #     self.timer.start(5000)
    #     self.verticalScrollBar().valueChanged.connect(self.load_batch) 

    # def foobar(self):
    #     print('Here')
    #     item = self.item(1)
    #     icon = QIcon()
    #     icon.addPixmap(QPixmap("/home/agent/dev/repos/wallflower/wall-flower-cli/tmp/1a422cc2-4acc-4e2c-9d98-25088cac48d4.jpg"))
    #     item.setHidden(True)
    #     item.setIcon(icon)
    #     item.setHidden(False)

    def load_batch(self):
        self.add_images(12)

    def add_images(self, num):
        urls = []
        guids = []
        for wallpaper in self.unloaded_items[:num]:
            urls.append(wallpaper.source_url)
            guids.append(wallpaper.guid)
        images, errors = load(urls)
        for guid, image_data in zip(guids, images):
            icon = QIcon()
            icon.addPixmap(QPixmap("/home/agent/dev/repos/wallflower/wall-flower-cli/tmp/no_image.png"))
            # if image_data is None:
            #     icon = QIcon()
            #     icon.addPixmap(QPixmap("/home/agent/dev/repos/wallflower/wall-flower-cli/tmp/no_image.png"))
            # else:
            #     icon = create_icon(image_data)
            item = QListWidgetItem(icon, guid)
            self.addItem(item)
        self.unloaded_items = self.unloaded_items[:num]
