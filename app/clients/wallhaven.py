"""
application code for interacting with the Wallhaven API
"""

import logging
import time
from functools import cached_property

import requests

from app.clients.base import Client
from app.config import config
from app.db import source_ids_by_type

logger = logging.getLogger(__name__)


class MyWallhavenClient(Client):
    """
    Class for client interaction with the Wallhaven API https://wallhaven.cc/help/api
    """

    source_type = "wallhaven"

    def __init__(self, *args, **kwargs):
        self.api_key = config.wallhaven.api_key
        self.username = config.wallhaven.username

        assert self.api_key is not None, "A ApiKey must be provided"
        assert self.username is not None, "A Username must be provided"
        logger.info("Starting client")

    @cached_property
    def saved_ids(self):
        return source_ids_by_type(self.source_type)

    # TODO: might be good to wrap this a bit better for errors
    def make_request(self, url, params={}):
        params["apikey"] = self.api_key
        response = requests.get(url, params=params)
        if response.status_code == 429:
            logger.warning("Rate limit encountered, waiting for 60 seconds")
            time.sleep(60)
            response = requests.get(url, params=params)
        response_data = response.json()
        data = response_data["data"]

        try:
            last_page = response_data["meta"]["last_page"]
        except KeyError:
            last_page = 1

        for page in range(2, last_page + 1):
            params["page"] = page
            response = requests.get(url, params=params)
            if response.status_code == 429:
                logger.warning("Rate limit encountered, waiting for 60 seconds")
                time.sleep(60)
                response = requests.get(url, params=params)
            response_data = response.json()
            page_data = response_data["data"]
            data += page_data

        return data

    @cached_property
    def default_collection_id(self):
        collections = self.make_request("https://wallhaven.cc/api/v1/collections")
        default_collection = [c for c in collections if c["label"] == "Default"][0]
        return default_collection["id"]

    def images(self):
        url = f"https://wallhaven.cc/api/v1/collections/{self.username}/{self.default_collection_id}"
        wallpapers = self.make_request(url)
        for obj in wallpapers:
            if obj["id"] in self.saved_ids:
                continue
            yield obj

    @staticmethod
    def to_db(obj):
        ext = obj["file_type"].split("/")[-1]

        return {
            "source_uri": obj["path"],
            "source_id": obj["id"],
            "source_type": MyWallhavenClient.source_type,
            "image_type": ext,
            "analyzed": False,
        }
