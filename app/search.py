import vptree
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from collections import defaultdict
from typing import Type, List, Tuple
from colormath.color_objects import LabColor, sRGBColor
from colormath.color_conversions import convert_color

from app.db import Wallpaper, create_session
from app.utils import load
from app.analyze import to_hex


def hamming(a: int, b: int) -> int:
    """ Find the hamming distance between two integers """
    return bin(int(a) ^ int(b)).count('1')


def hex_to_lab(hex_value: str) -> Tuple[float]:
    """
    Convert a string hex color to a lab colorspace.
    """
    hex_value = hex_value[1:] if hex_value.startswith('#') else hex_value
    red = np.asarray(int(hex_value[0:2], 16), np.uint8)
    green = np.asarray(int(hex_value[2:4], 16), np.uint8)
    blue = np.asarray(int(hex_value[4:6], 16), np.uint8)
    return convert_color(sRGBColor(red, green, blue), LabColor).get_value_tuple()


def lab_to_hex(lab_values: Tuple[float]) -> str:
    """
    Convert lab values to a freindly hex string of the form #AABBCC
    """
    # The `sRGBColor` class method `get_rgb_hex` gives a rather large hex value, maybe an error?
    return to_hex(*convert_color(LabColor(*lab_values), sRGBColor).get_value_tuple())


def find_nearest_colors(query_color: str, colors: List[str], n: int = 10) -> List[str]:
    
    def euclidean(p1, p2):
        return np.sqrt(np.sum(np.power(p2 - p1, 2)))

    colors = [hex_to_lab(val) for val in colors]
    query_color = hex_to_lab(query_color)
    
    search_tree = vptree.VPTree(np.array(colors), euclidean)
    _, labs = zip(*search_tree.get_n_nearest_neighbors(query_color, n))
    return [lab_to_hex(lab) for lab in labs]


def dhash(image: np.array, hashSize: int = 8) -> int:
    """
    Creates a perceptual hash known as 'dhash' for a given image as an array
    Reference: http://www.hackerfactor.com/blog/index.php?/archives/529-Kind-of-Like-That.html
    The hash size will determine the bits to be compared, by default 64(8x8) is used.
    """
    resized = cv2.resize(image, (hashSize + 1, hashSize))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])


def get_dhashes():
    session = create_session()
    urls = session.query(Wallpaper.source_url).all()
    urls = [url[0] for url in urls]
    images, _ = load(urls)
    images = [np.asarray(Image.open(BytesIO(data)).convert('L')) for data in images]


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
