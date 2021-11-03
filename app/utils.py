import os
import io
import cv2
import requests
import asyncio
import aiohttp
import aiofiles
from gcloud.aio.storage import Storage
from PIL import Image
from typing import List, Tuple
from functools import lru_cache


async def download_file(url: str, dst: str):
    '''
    Async download routine for an image url to a given file location, will create parent paths.
    Returns url and file location on success and throws exceptions on network errors to be accumulated.
    '''
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        response = await session.get(url)            
        assert response.status == 200
        data = await response.read()

    parent_dirs = os.path.dirname(dst)
    if not os.path.exists(parent_dirs):
        os.makedirs(parent_dirs)

    async with aiofiles.open(dst, 'wb') as outfile:
        await outfile.write(data)
    return url, dst


async def gather_download_routines(urls: List[str], file_names: List[str]):
    '''
    Assemble a list of async download routines for execution. Accumulates exceptions.
    '''
    download_futures = [download_file(url, dst) for url, dst in zip(urls, file_names)]
    return await asyncio.gather(*download_futures, return_exceptions=True)


def download(urls: List[str], filenames: List[str], retry: int = 2) -> Tuple[int, List]:
    '''
    Bulk download a list of urls to their respective filename. Executes async routines for better performance.
    Will retry any failed downloads a set number of times. Return failed download locations otherwise.
    '''
    results = asyncio.run(gather_download_routines(urls, filenames))
    success = set()
    for item in results:
        if isinstance(item, Exception):
            continue
        success.add(item)

    failed = set(zip(urls, filenames)) - success
    
    if failed and retry > 0:
        urls, dsts = tuple(zip(*failed))
        failed = download(urls, dsts, retry=retry - 1)

    return failed


# @lru_cache(maxsize=None)
# async def load_file(url: str):
#     '''
#     Async load routine for an image url.
#     '''
#     if url.startswith('http'):
#         async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
#             response = await session.get(url)
#             assert response.status == 200
#             return await response.read()
#     else:
#         async with aiofiles.open(url, mode='rb') as afp:
#             return await afp.read()


# async def gather_load_routines(urls: List[str]):
#     '''
#     Assemble a list of async load routines for execution.
#     '''
#     load_futures = [load_file(url) for url in urls]
#     return await asyncio.gather(*load_futures, return_exceptions=True)


# def load(urls: List[str]):
#     '''
#     Bulk load a list of urls to their respective filename. Executes async routines for better performance.
#     '''
#     data = asyncio.run(gather_load_routines(urls))
#     errors = []
#     success = []
#     for item in data:
#         if isinstance(item, Exception):
#             errors.append(item)
#         else:
#             success.append(item)
#     return success, errors


async def upload_file(src: str, dst: str, bucket: str):
    ''' Async upload routine for uploading an image to a google bucket. '''

    async with aiofiles.open(src, mode='rb') as afp:
        fobj = await afp.read()

        async with aiohttp.ClientSession() as session:
            storage = Storage(session=session)
            status = await storage.upload(bucket, dst, fobj)
            return src, dst


async def gather_upload_routines(
    file_names: List[str], destinations: List[str], bucket: str
    ):
    '''
    Gather coroutines for async execution, returns an exception in case of network errors.
    '''
    upload_futures = [upload_file(src, dst, bucket) for src, dst in zip(file_names, destinations)]
    return await asyncio.gather(*upload_futures, return_exceptions=True)


def upload(
    file_names: List[str], destinations: List[str], bucket: str
    ):
    '''
    Bulk upload a list of files to a bucket. Executes async routines for better performance.
    '''
    return asyncio.run(gather_upload_routines(file_names, destinations, bucket))


def bulk_download_wallpapers(
    list_of_wallpapers: list, directory: str, for_vision: bool = False
    ) -> list:
    '''
    Asyncronously download a set of Wallpaper models from their source url under the
    given directory with their guid path. If `for_vision` is enabled, images that exceed
    the Google Vision API image size will be resized.
    '''

    local_filepaths = []
    source_urls = []
    to_resize = []

    for wallpaper in list_of_wallpapers:
        # Build local filepath to save to
        guid_path = media_path(wallpaper.guid, wallpaper.extension)
        local_filepath = os.path.join(directory, guid_path)

        # Save files that are too large to be resized after download
        # if for_vision and wallpaper.size_in_bytes >= 10485760:
        # to_resize.append(local_filepath)

        local_filepaths.append(local_filepath)
        source_urls.append(wallpaper.url)

    download(source_urls, local_filepaths)

    # TODO: See if there is a way to do this in memory with async
    for each in to_resize:
        image = load_image(each)
        image.thumbnail((1920, 1080), Image.ANTIALIAS)
        image.save(each)
    
    return local_filepaths


# def upload(image, loc, bucket_name)
#     storageClient = storage.Client()
#     bucket = storageClient.get_bucket(bucket_name)
#     blob = bucket.blob(loc)

#     imageByteArray = io.BytesIO()
#     image.save(imageByteArray, format=image.format)

#     blob.upload_from_string(imageByteArray.getvalue())


def media_path(guid: str, extension: str, cdn_host: str = '', nested: bool = True) -> str:
    ''' Return the file path for the provided guid and host. '''
    if nested:
        file_path = f'{guid[0]}/{guid[1]}/{guid[2]}/{guid}.{extension}'
    else:
        file_path = f'{guid}.{extension}'
    return os.path.join(cdn_host, file_path)


def image_dimensions(image):
    """
    param image: np.array of image data, should be at 2 or 3 dimensions
    return width: integer value of the image width
    return height: integer value of the image height
    return channels: integer value of the number of color channels
    """
    try:
        width, height, channels = image.shape
    except ValueError:
        width, height = image.shape
        channels = 1
    return width, height, channels


def histogram(image, bins):
    """
    param image: np.array of image data, minimum of 2 dimensions
    param bins: integer value for groups of each channel in histogram
    return hist: np.array of normalized histogram data
    """
    widht, height, channels = image_dimensions(image)

    # Color range and bins for each channel
    color_range = [0, 256] * channels
    bins = [bins] * channels

    channels = [channel for channel in range(channels)]
    hist = cv2.calcHist([image], channels, None, bins, color_range)
    hist = cv2.normalize(hist, hist).flatten()
    return hist


def pixelate(image, size=(32, 32)):
    """
    param image: np.array of image data, minimum of 2 dimensions
    param size: tuple of integer values for the pixelation sized
    return pixelated_image: np.array representing the pixelated image
    """
    width, height, channels = image_dimensions(image)
    temp = cv2.resize(image, size, interpolation=cv2.INTER_LINEAR)
    pixelated_image = cv2.resize(temp, (width, height), interpolation=cv2.INTER_NEAREST)
    return pixelated_image


def load_image(image_location: str) -> Image:
    """ Load image data into memory from a url or local file """
    if image_location.startswith('http'):
        response = requests.get(image_location)
        image = Image.open(io.BytesIO(response.content))
    else:
        image = Image.open(image_location)
    return image
