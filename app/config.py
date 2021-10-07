import os
from collections import defaultdict
from configparser import ConfigParser

# TODO: Should make a standardized location for this at some point
config_file = 'wallflower.ini'
config = ConfigParser()


if os.path.exists(config_file):
    config.read(config_file)
else:
    config['Core'] = defaultdict(None)
    config['Reddit'] = defaultdict(None)
    config['Imgur'] = defaultdict(None)
    config['Wallhaven'] = defaultdict(None)
    with open(config_file, 'w') as configfile:
        config.write(configfile)
