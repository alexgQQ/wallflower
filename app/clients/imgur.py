"""
application code for interacting with the Imgur API
"""

import requests
import logging

from imgurpython import ImgurClient
from app.config import get_config


class MyImgurClient:
    '''
    Class for client interaction with the Imgur API.
    This makes use of the python client library: https://github.com/Imgur/imgurpython
    '''

    source_type = 'imgur'

    def __init__(self, *args, **kwargs):

        config = get_config()
        self.client_id = config.get('Imgur', 'clientid')
        self.client_secret = config.get('Imgur', 'clientsecret')
        self.access_token = config.get('Imgur', 'accesstoken')
        self.refresh_token = config.get('Imgur', 'refreshtoken')

        assert self.client_id is not None, 'A ClientID must be provided'
        assert self.client_secret is not None, 'A ClientSecret must be provided'
        assert self.access_token is not None, 'A AccessToken must be provided'
        assert self.refresh_token is not None, 'A RefreshToken must be provided'

        # Note since access tokens expire after an hour,
        # only the refresh token is required (library handles autorefresh)
        self.client = ImgurClient(
            self.client_id, self.client_secret, self.access_token, self.refresh_token)

    def favorited_galleries(self, limit=20):
        '''
        Generator to return images from favorited imgur albums.
        This is done in a synchronous manner by grabbing each albums detail data
        and yielding all the images from each.
        Imgur API References:
        - https://apidocs.imgur.com/?version=latest#a432a8e6-2ece-4544-bc7a-2999eb586f06
        - https://apidocs.imgur.com/?version=latest#f64e44be-8bf3-47bb-90d5-d1bf39c5e417
        '''
        count = 0
        for item in self.client.get_account_favorites('me'):
            logging.info(f'Pulling image gallery - {item.id}')
            url = f'https://api.imgur.com/3/gallery/album/{item.id}'
            response = requests.get(
                url, headers={'Authorization': f'Client-ID {self.client_id}'})
            data = response.json()
            image_data = data['data']['images']
            logging.info(f'{len(image_data)} images found in gallery')
            for image in image_data:
                count += 1
                yield image

    @staticmethod
    def to_db(obj):
        ext = obj['type'].split('/')[-1]
        return {
            'source_url': obj['link'],
            'source_id': obj['id'],
            'source_type': MyImgurClient.source_type,
            'image_type': ext,
            'analyzed': False,
        }

    def fetch(self, limit: int = 20):
        for wallpaper in self.favorited_galleries(limit=limit):
            yield self.to_db(wallpaper)
