import os
from collections import defaultdict
from configparser import ConfigParser

# TODO: Should make a standardized location for this at some point
config_file = 'wallflower.ini'

supported_formats = (
    'jpeg', 'jpg', 'png',
)

def update_config(config_obj):
    with open(config_file, "w") as _file:
        config_obj.write(_file)


def get_config():
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
    return config
