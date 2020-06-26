import praw
import os


class RedditClient:
    """
    Save wallpaper images saved from my reddit account to `save_dir`
    """

    def __init__(self, *args, **kwargs):

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

    def saved_wallpapers(self, limit=500):
        """
        Returns a generator of reddit Submissions for saved posts from r/wallpaper/
        """
        for item in self.reddit.user.me().saved(limit=limit):
            if isinstance(item, praw.models.Submission) and item.subreddit.display_name == 'wallpaper':
                yield item

    def check_status(self):
        return len(list(self.saved_wallpapers(limit=None)))
