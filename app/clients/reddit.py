"""
application code for interacting with the Reddit API
"""

import os
import praw


class RedditClient:
    '''
    Class for client interaction with the Reddit API.
    This makes use of the python client library: https://praw.readthedocs.io/en/latest/
    '''

    def __init__(self):

        client_id = os.getenv('REDDIT_CLIENT_ID')
        client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        username = os.getenv('REDDIT_USERNAME')
        password = os.getenv('REDDIT_PASSWORD')
        user_agent = 'osx:wall-flower:v0.0.1 (by /u/PocketBananna)'

        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent
            )

    def saved_wallpapers(self, limit: int = 500):
        '''
        Returns a generator of reddit Submissions for saved posts from r/wallpaper/
        can provide a limit of images to grab at once.
        TODO: Reddit recently allowed multiple images on a post,
              need to see how compatability plays out.
        '''
        for item in self.reddit.user.me().saved(limit=limit):
            if isinstance(item, praw.models.Submission) \
                and item.subreddit.display_name == 'wallpaper':
                yield item

    def check_status(self):
        ''' Return the number of saved wallpaper posts '''
        return len(list(self.saved_wallpapers(limit=None)))
