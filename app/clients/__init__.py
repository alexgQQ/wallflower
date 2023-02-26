# Some general notes on the client code
# TODO: My method for finding new images is a bit greedy
#   in that each client class gets all the saved source ids
#   for it's type and then as many images that it can from
#   whatever api and checks each source id against the saved.
#   This is slow and would be worth looking at alternatives
#   like cursoring or something.
# TODO: It would be worth migrating some of the auth handlers
#   to full login integrations. Most apis support this in some capacity
#   and would be a bit more secure than just having creds on file.

from app.clients.imgur import MyImgurClient
from app.clients.reddit import RedditClient
from app.clients.wallhaven import MyWallhavenClient
