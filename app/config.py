import os
import platform
from configparser import ConfigParser

from platformdirs import user_config_dir, user_data_dir

from app import __version__

app_name = "wallflower"
user_agent = f"{platform.system()}:{app_name}:v{__version__}"


def is_windows() -> bool:
    return platform.system() == "Windows"


def debug_mode() -> bool:
    return bool(os.getenv("WALLFLOWER_DEBUG", False))


class ConfigObject:
    """
    Functions as a interface for accessing the dict-like structure of
    `ConfigParser` as an object
    """

    def __init__(self, config: ConfigParser, section: str):
        # When overriding setattr this has to be done to avoid an endless loop
        super().__setattr__("config", config)
        super().__setattr__("section", section)

    def __getattr__(self, attr):
        if attr == "image_dirs":
            return self.config.getlist(self.section, attr)
        elif attr == "enabled":
            return self.config.getboolean(self.section, attr.lower())
        else:
            return self.config.get(self.section, attr)

    def __setattr__(self, attr, value):
        if attr == "image_dirs":
            value = ",".join(value)
        self.config.set(self.section, attr, value)


class Config:
    """
    A class to accumulate application config values and it's actions.
    The main motivation for this was to use `ConfigParser` but with object
    like accessors.
    """

    def __init__(self):
        self.config = ConfigParser(
            converters={"list": lambda x: [i.strip() for i in x.split(",")]}
        )

    def default(self):
        """Fill the config defaults for installed or development versions"""
        if debug_mode():
            db_loc = os.path.join(os.getcwd(), "data.db")
            logs_loc = ""
            logs_level = "DEBUG"
            image_dirs = os.path.join(os.getcwd(), "images")
            download_loc = os.path.join(os.getcwd(), "images/downloads")
        else:
            db_loc = os.path.join(user_data_dir(app_name), "data.db")
            logs_loc = os.path.join(user_data_dir(app_name), "app.log")
            logs_level = "WARN"
            image_dirs = ""
            download_loc = ""

        return {
            "core": {
                "image_dirs": image_dirs,
                "db_loc": db_loc,
                "download_loc": download_loc,
                "logs_loc": logs_loc,
                "logs_level": logs_level,
            },
            "reddit": {
                "enabled": "False",
                "client_id": "",
                "client_secret": "",
                "username": "",
                "password": "",
            },
            "imgur": {
                "enabled": "False",
                "client_id": "",
                "client_secret": "",
                "access_token": "",
                "refresh_token": "",
            },
            "wallhaven": {
                "enabled": "False",
                "api_key": "",
                "username": "",
            },
        }

    def load(self):
        """Create/Load values from the config file"""

        if debug_mode():
            config_file = os.path.join(os.getcwd(), "config.ini")
        else:
            config_file = os.path.join(user_config_dir(app_name), "config.ini")
        self.file_loc = config_file

        if os.path.exists(self.file_loc):
            self.config.read(self.file_loc)
        else:
            self.config.read_dict(self.default())
            with open(self.file_loc, "w") as config_file:
                self.config.write(config_file)

        for section in self.config.sections():
            obj = ConfigObject(self.config, section)
            setattr(self, section, obj)

    def update(self):
        """Write current values to the config file"""
        with open(self.file_loc, "w") as config_file:
            self.config.write(config_file)


# Gifs are a bit of an outlier but sometimes show up
# from reddit posts. They can be used as a wallpapers but
# they only use the first frame
supported_formats = (
    "jpeg",
    "jpg",
    "png",
    "gif",
)


config = Config()
