import os
import io
import cv2
import requests
from PIL import Image
from typing import List


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

    # download(source_urls, local_filepaths)

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
