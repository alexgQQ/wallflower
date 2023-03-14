"""
application code for interacting with the Reddit API
"""

import logging

import praw
import requests
from funcy import cached_property

from app.clients.base import Client
from app.config import config, supported_formats, user_agent
from app.db import source_ids_by_type

logger = logging.getLogger(__name__)


class RedditClient(Client):
    """
    Class for client interaction with the Reddit API.
    This makes use of the python client library: https://praw.readthedocs.io/en/latest/
    """

    source_type = "reddit"

    def __init__(self, *args, **kwargs):
        client_id = config.reddit.client_id
        client_secret = config.reddit.client_secret
        username = config.reddit.username
        password = config.reddit.password

        assert client_id is not None, "A ClientID must be provided"
        assert client_secret is not None, "A ClientSecret must be provided"
        assert username is not None, "A Username must be provided"
        assert password is not None, "A Password must be provided"

        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent,
        )
        logger.info("Starting client")

    @cached_property
    def saved_ids(self):
        return source_ids_by_type(self.source_type)

    def images(self):
        """
        Returns a generator of reddit Submissions for saved posts from r/wallpaper/
        can provide a limit of images to grab at once.
        """
        for item in self.reddit.user.me().saved(limit=1000):
            # TODO: Test with image galleries to see if it works
            if (
                isinstance(item, praw.models.Submission)
                and item.subreddit.display_name == "wallpaper"
                and item.removal_reason is None
                and item.id not in self.saved_ids
                and not getattr(item, "is_gallery", False)
            ):
                yield item

    @staticmethod
    def to_db(obj):
        # Reddit posts that are image links (common in this app)
        # do not store the image type directly like Imgur/Wallhaven.
        # We basically approximate it by the image link or the
        # content type of the link.
        try:
            ext = obj.url.split(".")[-1].strip()
            assert ext in supported_formats
        except (AssertionError, IndexError):
            resp = requests.head(obj.url)
            resp.raise_for_status()
            content = resp.headers.get("Content-Type")
            if content.startswith("image/"):
                _, ext = content.split("/")
                if ext in supported_formats:
                    pass
                else:
                    logger.warning(f"Failed to identify image type - {obj.url}")
                    return None
            else:
                logger.warning(f"Failed to identify image type - {obj.url}")
                return None
        except requests.exceptions.RequestException:
            logger.warning(f"Failed to identify image type - {obj.url}")
            return None

        return {
            "source_uri": obj.url,
            "source_id": obj.id,
            "source_type": RedditClient.source_type,
            "image_type": ext,
            "analyzed": False,
        }
