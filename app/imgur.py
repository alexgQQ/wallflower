import os
import requests

from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError


class MyImgurClient:

    def __init__(self, *args, **kwargs):

        self.client_id = os.getenv('IMGUR_CLIENT_ID')
        self.client_secret = os.getenv('IMGUR_CLIENT_SECRET')
        self.access_token = os.getenv('IMGUR_ACCESS_TOKEN')
        self.refresh_token = os.getenv('IMGUR_REFRESH_TOKEN')

        # Note since access tokens expire after an hour,
        # only the refresh token is required (library handles autorefresh)
        self.client = ImgurClient(
            self.client_id, self.client_secret, self.access_token, self.refresh_token)

    def favorited_galleries(self):
        for item in self.client.get_account_favorites('me'):
            url = f'https://api.imgur.com/3/gallery/album/{item.id}'
            response = requests.get(
                url, headers={'Authorization': f'Client-ID {self.client_id}'})
            data = response.json()
            for image in data['data']['images']:
                yield image
