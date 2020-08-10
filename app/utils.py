import os
import io
import scipy
import scipy.cluster
import cv2
import sys
import numpy as np
import requests

import asyncio
import aiohttp
import aiofiles
from gcloud.aio.storage import Storage
from skimage import color
from PIL import Image

from google.cloud import vision
from google.cloud.vision import types



async def download_file(url, dst):
    '''
    Async download routine for an image url.
    :param string url: Url location of the file to download
    :param string dst: File destination for the file
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


async def gather_download_routines(urls, file_names):
    '''
    Assemble a list of async download routines for execution.
    :param list urls: List of string url locations, should match the length of filenames given.
    :param list file_names: List of string file locations, should match the length of urls given.
    '''
    download_futures = [download_file(url, dst) for url, dst in zip(urls, file_names)]
    return await asyncio.gather(*download_futures)


def download(urls, filenames):
    '''
    Bulk download a list of urls to their respective filename. Executes async routines for better performance.
    :param list urls: List of string url locations, should match the length of filenames given.
    :param list file_names: List of string file locations, should match the length of urls given.
    '''
    asyncio.run(gather_download_routines(urls, filenames))


async def upload_file(src, dst, bucket):
    '''
    Async upload routine for uploading an image to a google bucket.
    :param string src: File location of the source file.
    :param string dst: Bucket destination of the file.
    '''
    async with aiohttp.ClientSession() as session:
        client = Storage(session=session)

        async with open(src, mode='r') as f:
            await client.upload(bucket, dst, f.read())


async def gather_upload_routines(file_names, destinations, bucket):
    '''
    Assemble a list of async upload routines for execution.
    :param list file_names: List of string file locations, should match the length of destinations given.
    :param list destinations: List of string file locations to save to a bucket, should match the length of file_names given.
    :param string bucket: Name of the bucket to upload to.
    '''
    upload_futures = [upload_file(src, dst, bucket) for src, dst in zip(file_names, destinations)]
    return await asyncio.gather(*upload_futures)


def upload(file_names, destinations, bucket):
    '''
    Bulk upload a list of files to a bucket. Executes async routines for better performance.
    :param list file_names: List of string file locations, should match the length of destinations given.
    :param list destinations: List of string file locations to save to a bucket, should match the length of file_names given.
    :param string bucket: Name of the bucket to upload to.
    '''
    asyncio.run(gather_upload_routines(file_names, destinations), bucket)


# def upload(image, loc, bucket_name)
#     storageClient = storage.Client()
#     bucket = storageClient.get_bucket(bucket_name)
#     blob = bucket.blob(loc)

#     imageByteArray = io.BytesIO()
#     image.save(imageByteArray, format=image.format)

#     blob.upload_from_string(imageByteArray.getvalue())


def media_path(guid, extension, cdn_host=''):
    '''
    Return the file path for the provided file.
    :param string guid: The global identifier for the file.
    :param string extension: The file extension.
    '''
    file_path = f'{guid[0]}/{guid[1]}/{guid[2]}/{guid}.{extension}'
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


def dhash(image, hashSize=8):
    """
    param image: np.array of image data, should be at least 2 dimensions
    param hashSize: integer for the size to shrink the image down to
    return int: hash of image representing pixel differences
    """
    resized = cv2.resize(image, (hashSize + 1, hashSize))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])


def convert_hash(h):
    return int(np.array(h, dtype="float64"))


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


def get_labels(image, top_num=5):
    client = vision.ImageAnnotatorClient()

    # Load image as bytes stream for GCP request
    image_content = io.BytesIO()
    image.save(image_content, format=image.format)
    image = types.Image(content=image_content.getvalue())

    label_response = client.label_detection(image=image)
    return [label.description for label in label_response.label_annotations[:]]


def get_colors(image, top_num=5):
    client = vision.ImageAnnotatorClient()

    # Load image as bytes stream for GCP request
    image_content = io.BytesIO()
    image.save(image_content, format=image.format)
    image = types.Image(content=image_content.getvalue())

    property_response = client.image_properties(image=image)
    return [color for color in property_response.image_properties_annotation.dominant_colors.colors[:]]


def get_labels_and_colors(image):
    client = vision.ImageAnnotatorClient()

    # Load image as bytes stream for GCP request
    image_content = io.BytesIO()
    image.save(image_content, format=image.format)
    image = types.Image(content=image_content.getvalue())

    property_response = client.image_properties(image=image)
    label_response = client.label_detection(image=image)

    labels = [
        label.description 
        for label in sorted(label_response.label_annotations, key=lambda x: x.score, reverse=True)
        ]
    colors = [
        to_hex(color.color.red, color.color.green, color.color.blue)
        for color in sorted(property_response.image_properties_annotation.dominant_colors.colors, key=lambda x: x.score, reverse=True)
        ]

    return labels, colors


def to_hex(red, green, blue):
    red, green, blue = int(red), int(green), int(blue)
    return f'{red:02x}{green:02x}{blue:02x}'


def hex_to_lab(hex):
    r = np.asarray(int(hex[0:2], 16), np.uint8)
    g = np.asarray(int(hex[2:4], 16), np.uint8)
    b = np.asarray(int(hex[4:6], 16), np.uint8)
    return color.rgb2lab(np.dstack((r, g, b)))


def hamming(a, b):
	return bin(int(a) ^ int(b)).count('1')


def approx_image_bytesize(image):
    with tempfile.TemporaryDirectory() as tmpdirname:
        filename = f'temp_image.{image.format.lower()}'
        file_path = os.path.join(tmpdirname, filename)
        image.save(file_path)
        sys_size = os.stat(file_path).st_size

    return sys_size


def load_image(image_location):
    """
    param image_location: string of filepath or url of image to load
    return image: pillow image object
    """
    if image_location.startswith('http'):
        response = requests.get(image_location)
        image = Image.open(io.BytesIO(response.content))
    else:
        image = Image.open(image_location)

    return image
