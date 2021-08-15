"""
application code for interacting with the Wallhaven API
"""

import os
import requests
import logging
import time

from functools import cached_property

from app.config import supported_formats


class MyWallhavenClient:
    '''
    Class for client interaction with the Wallhaven API https://wallhaven.cc/help/api
    '''

    source_type = 'wallhaven'

    def __init__(self, *args, **kwargs):
        self.api_key = os.getenv('WALLHAVEN_API_KEY')
        self.username = os.getenv('WALLHAVEN_USERNAME')

    def make_request(self, url, params={}):
        params['apikey'] = self.api_key
        response = requests.get(url, params=params)
        if response.status_code == 429:
            time.sleep(60)
            response = requests.get(url, params=params)
        response_data = response.json()
        data = response_data['data']
        try:
            last_page = response_data['meta']['last_page']
        except KeyError:
            last_page = 1

        for page in range(2, last_page + 1):
            params['page'] = page
            response = requests.get(url, params=params)
            if response.status_code == 429:
                time.sleep(60)
                response = requests.get(url, params=params)
            response_data = response.json()
            data += response_data['data']

        return data

    @cached_property
    def default_collection_id(self):
        collections = self.make_request('https://wallhaven.cc/api/v1/collections')
        default_collection = [c for c in collections if c['label'] == 'Default'][0]
        return default_collection['id']

    def wallpapers(self):
        url = f'https://wallhaven.cc/api/v1/collections/{self.username}/{self.default_collection_id}'
        wallpapers = self.make_request(url)
        for obj in wallpapers:
            yield obj

    @staticmethod
    def to_db(obj):
        ext = obj['file_type'].split('/')[-1]

        return {
            'url': obj['path'],
            'source_id': obj['id'],
            'extension': ext,
            'source_type': MyWallhavenClient.source_type,
            'active': ext in supported_formats,
        }

    def fetch(self, limit: int = 20):
        for wallpaper in self.wallpapers():
            yield self.to_db(wallpaper)
