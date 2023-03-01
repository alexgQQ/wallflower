import logging
from collections import defaultdict
from functools import cached_property
from math import sqrt
from typing import Dict, List, Optional, Tuple

import vptree
from colormath.color_conversions import convert_color
from colormath.color_objects import LabColor, sRGBColor
from sqlalchemy.orm import Query

from app.db import (
    QueryDict,
    Wallpaper,
    WallpaperQuery,
    all_colors,
    create_session,
    wallpaper_by_id,
)

logger = logging.getLogger(__name__)


class ColorSearch:
    """
    Find the closest n colors to a given color in the database
    An interesting process of using the LAB colorspace and a vantage
    point tree for fast and accurate distance searching.
    """

    def __init__(self) -> None:
        colors = [self.hex_to_lab(val) for val in self.known_colors]
        self.vptree = vptree.VPTree(colors, self.euclidean)

    # TODO: This could potentially get very large and
    # may need to be updated if new images are added
    @cached_property
    def known_colors(self) -> List[int]:
        return tuple(color[0] for color in all_colors())

    @staticmethod
    def hex_to_lab(hex_value: int) -> Tuple[float, float, float]:
        """Convert a hex color to a lab colorspace"""
        red, green, blue = (
            (hex_value >> 16) & 0xFF,
            (hex_value >> 8) & 0xFF,
            hex_value & 0xFF,
        )
        color = sRGBColor(red, green, blue, is_upscaled=True)
        return convert_color(color, LabColor).get_value_tuple()

    @staticmethod
    def lab_to_hex(lab_values: Tuple[float, float, float]) -> int:
        """Convert lab values to a friendly hex string of the form #AABBCC"""
        # Incoming sRGBColor values had a default illumination of `d65`
        # https://python-colormath.readthedocs.io/en/latest/color_objects.html#colormath.color_objects.sRGBColor.native_illuminant
        l, a, b = lab_values
        color = convert_color(LabColor(l, a, b, illuminant="d65"), sRGBColor)
        r, g, b = color.get_upscaled_value_tuple()
        return r << 16 | g << 8 | b

    @staticmethod
    def euclidean(p1: Tuple[float], p2: Tuple[float]) -> float:
        return sqrt(sum(((v2 - v1) ** 2) for v1, v2 in zip(p1, p2)))

    def __call__(self, color: str, n_colors: int = 20) -> List[int]:
        """Find the n closest colors in the db to a given color"""
        color = self.hex_to_lab(int(color.strip("#"), 16))
        # First return value are the search scores and are not needed
        _, labs = zip(*self.vptree.get_n_nearest_neighbors(color, n_colors))
        return [self.lab_to_hex(lab) for lab in labs]


class DuplicateSearch:
    """
    Find duplicate images in the database.
    A process of using a interesting perceptual hash (dhash)
    and a vantage point tree. Scale invariant!
    """

    @staticmethod
    def hamming(a: int, b: int) -> int:
        """Find the hamming distance between two integers"""
        return bin(int(a) ^ int(b)).count("1")

    @property
    def id_to_dhash(self) -> dict:
        with create_session() as session:
            query = (
                session.query(Wallpaper.id, Wallpaper.dhash)
                .filter(Wallpaper.dhash != None)
                .all()
            )
        return {_id: _dhash for _id, _dhash in query}

    def similar(self, _id: int) -> List[int]:
        """Find images that are similar to a given image id"""

        # TODO: I'm not terribly sure how great this works.
        # By observation it kinda works but there are other ways
        # comparisons could be done like with histograms.
        # Would be interesting to investigate it a bit

        dhash = wallpaper_by_id(_id).dhash
        dhash_to_id = {}
        duplicates = defaultdict(list)

        for _id, _dhash in self.id_to_dhash.items():
            if _dhash in dhash_to_id:
                duplicates[dhash_to_id[_dhash]].append(_id)
            else:
                dhash_to_id[_dhash] = _id

        search_tree = vptree.VPTree(list(dhash_to_id.keys()), self.hamming)

        results = search_tree.get_n_nearest_neighbors(dhash, 20)
        results = sorted(results)
        ids = []
        for _, _hash in results:
            ids.append(dhash_to_id.get(_hash))
        return ids

    def duplicates(self) -> Dict[int, List[int]]:
        """Find duplicated images in the database"""
        # Build a mapping of ids to image hashes for searching and
        # find early duplicates by matching the hash exactly
        dhash_to_id = {}
        duplicates = defaultdict(list)

        for _id, _dhash in self.id_to_dhash.items():
            if _dhash in dhash_to_id:
                duplicates[dhash_to_id[_dhash]].append(_id)
            else:
                dhash_to_id[_dhash] = _id

        # Load a vantage point tree with a hamming distance search indexer
        search_tree = vptree.VPTree(list(dhash_to_id.keys()), self.hamming)

        # Find similar hashes for each image
        for search_hash, search_id in dhash_to_id.items():
            results = search_tree.get_all_in_range(search_hash, 1)
            results = sorted(results)
            similar_ids = [
                dhash_to_id.get(_hash)
                for distance, _hash in results
                if _hash != search_hash
            ]

            if similar_ids:
                duplicates[search_id].extend(similar_ids)

        # Mark single images as duplicates
        to_mark = []
        check = {}
        for found_duplicate, related_duplicates in duplicates.items():
            if found_duplicate not in to_mark:
                to_mark += related_duplicates
                check[found_duplicate] = related_duplicates

        return check


class Search:
    """Handles processing search input from the ui and parses the results"""

    limit = 20
    query_data = QueryDict()

    def __init__(self) -> None:
        self.color_search = ColorSearch()

    def parse_query(self, query: Query) -> Tuple[Tuple[int, str, str], List[str]]:
        """Evaluate a query and split the results into metadata and image sources"""
        table_results = []
        image_srcs = []
        for image in query:
            table_results.append((image.id, image.filename, image.source_type))
            image_srcs.append(image.src_path)
        logger.info(
            f"Search listing query found {len(table_results)} results with {self.query_data}"
        )
        return table_results, image_srcs

    @property
    def ids(self) -> Optional[List[int]]:
        return self.query_data.get("ids")

    @ids.setter
    def ids(self, value: Optional[List[int]]):
        self.query_data["ids"] = value

    @property
    def colors(self) -> Optional[List[int]]:
        return self.query_data.get("colors")

    @colors.setter
    def colors(self, value: Optional[str]):
        if value is not None:
            value = self.color_search(value)
        self.query_data["colors"] = value

    @property
    def source_types(self) -> Optional[List[int]]:
        return self.query_data.get("source_types")

    @source_types.setter
    def source_types(self, value: Optional[List[int]]):
        self.query_data["source_types"] = value

    @property
    def aspect_ratio(self) -> Optional[float]:
        return self.query_data.get("aspect_ratio")

    @aspect_ratio.setter
    def aspect_ratio(self, value: Optional[float]):
        self.query_data["aspect_ratio"] = value

    def clear(self):
        """Clear search params"""
        self.ids = None
        self.colors = None
        self.source_types = None
        self.aspect_ratio = None

    def find(self) -> Tuple[Tuple[int, str, str], List[str]]:
        """Return search results"""
        query = WallpaperQuery(self.query_data)
        table, srcs = self.parse_query(query(limit=self.limit))
        # Hack to fix where the color values are cleared after search
        # since its value isn't accumulated on each search call
        _colors = self.colors
        self.clear()
        self.query_data["colors"] = _colors
        return table, srcs
