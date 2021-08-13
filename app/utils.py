import os
import io
import scipy
import scipy.cluster
import cv2
import sys
import numpy as np
import requests
import vptree
import asyncio
import aiohttp
import aiofiles
import logging
from gcloud.aio.storage import Storage
from skimage import color
from PIL import Image
from typing import Type, List, Tuple
import datetime
from collections import defaultdict

from google.cloud import vision, storage


async def download_file(url: str, dst: str):
    '''
    Async download routine for an image url.
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


async def gather_download_routines(urls: List[str], file_names: List[str]):
    '''
    Assemble a list of async download routines for execution.
    '''
    download_futures = [download_file(url, dst) for url, dst in zip(urls, file_names)]
    return await asyncio.gather(*download_futures, return_exceptions=True)


def download(urls: List[str], filenames: List[str]) -> Tuple[int, List]:
    '''
    Bulk download a list of urls to their respective filename. Executes async routines for better performance.
    '''
    results = asyncio.run(gather_download_routines(urls, filenames))
    errors = [err for err in results if isinstance(err, Exception)]
    return results.count(None), errors


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
        else:
            success.append(item)
    return success, errors


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


def common_colors(image, num_of_clusters):
    """
    param image: np.array of colored image data, should be at least 3 dimensions
    param num_of_clusters: integer for the number of colors to find
    return dict: dictionary of color counts keyed from the color value
    """
    width, height, channels = image_dimensions(image)
    image = image.reshape(
        scipy.product((width, height)), channels).astype(float)
    codes, dist = scipy.cluster.vq.kmeans(image, num_of_clusters)
    vecs, dist = scipy.cluster.vq.vq(image, codes)
    counts, bins = scipy.histogram(vecs, len(codes))
    return codes.astype(int), counts


def dhash(image: np.array, hashSize: int = 8) -> int:
    """
    Creates a perceptual hash known as 'dhash' for a given image as an array
    Reference: http://www.hackerfactor.com/blog/index.php?/archives/529-Kind-of-Like-That.html
    The hash size will determine the bits to be compared, by default 64(8x8) is used.
    """
    resized = cv2.resize(image, (hashSize + 1, hashSize))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])


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


def to_hex(red: int, green: int, blue: int) -> str:
    """ Convert 0-255 RGB values to a hex color string """
    return f'{red:02x}{green:02x}{blue:02x}'


def hex_to_lab(hex_value: str) -> Type[np.array]:
    """
    Convert a string hex color to a lab colorspace as an numpy array.
    This is intended to work for a single color and should return a (,3) array.
    """
    red = np.asarray(int(hex_value[0:2], 16), np.uint8)
    green = np.asarray(int(hex_value[2:4], 16), np.uint8)
    blue = np.asarray(int(hex_value[4:6], 16), np.uint8)
    return color.rgb2lab(np.dstack((red, green, blue)))[0,0,:]


def hamming(a: int, b: int) -> int:
    """ Find the hamming distance between two integers """
    return bin(int(a) ^ int(b)).count('1')


def load_image(image_location: str) -> Image:
    """ Load image data into memory from a url or local file """
    if image_location.startswith('http'):
        response = requests.get(image_location)
        image = Image.open(io.BytesIO(response.content))
    else:
        image = Image.open(image_location)
    return image


def generate_download_signed_url_v4(bucket_name, blob_name):
    """Generates a v4 signed URL for downloading a blob.

    Note that this method requires a service account key file. You can not use
    this if you are using Application Default Credentials from Google Compute
    Engine or from the Google Cloud SDK.
    """

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="GET",
    )

    return url


def list_blobs_with_prefix(bucket_name, prefix):
    """
    Gather json files under a specific bloc path in a bucket
    """

    storage_client = storage.Client()

    return storage_client.list_blobs(bucket_name, prefix=prefix)


def json_annotation_blobs(bucket_name, prefix):
    """
    Gather json files under a specific blob path in a bucket
    """

    storage_client = storage.Client()

    blobs = storage_client.list_blobs(bucket_name, prefix=prefix)
    
    return [blob.name for blob in blobs if blob.name.endswith('.json')]


def bulk_delete_from_bucket(bucket_name: str, blob_prefix: str):

    storage_client = storage.Client()

    blobs_to_delete = list_blobs_with_prefix(bucket_name, blob_prefix)
    blobs_to_delete = [blob for blob in blobs_to_delete]

    try:
        with storage_client.batch():
            for blob in blobs_to_delete:
                blob.delete()
    # For some reason the constructor exiting raises a ValueError
    except ValueError:
        pass


def find_duplicates(guid_to_hash: dict):

    # Build a mapping of guids to image hashes for searching and
    # find early duplicates by matching the hash exactly
    hash_to_guid = {}
    duplicates = defaultdict(list)

    for guid, image_hash in guid_to_hash.items():
        if image_hash in hash_to_guid:
            duplicates[hash_to_guid[image_hash]].append(guid)
        else:
            hash_to_guid[image_hash] = guid

    # Load a vantage point tree with a hamming distance search indexer
    search_tree = vptree.VPTree(list(hash_to_guid.keys()), hamming)

    # Find similar hashes for each image
    for search_hash, search_guid in hash_to_guid.items():
        results = search_tree.get_all_in_range(search_hash, 4)
        results = sorted(results)
        similar_guids = [hash_to_guid.get(_hash) for distance, _hash in results if _hash != search_hash]

        if similar_guids:
            duplicates[search_guid] += similar_guids

    # Mark single images as duplicates
    to_mark = []
    check = {}
    for found_duplicate, related_duplicates in duplicates.items():
        if found_duplicate not in to_mark:
            to_mark += related_duplicates
            check[found_duplicate] = related_duplicates

    return check
