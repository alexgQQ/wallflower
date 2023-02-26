import logging
import os

from app.config import config, debug_mode, app_name
from app.db import create_tables
from app.gui.main_window import main_window

from platformdirs import user_config_dir, user_data_dir


if __name__ == "__main__":

    config_dir = user_config_dir(app_name)
    if not debug_mode() and not os.path.exists(config_dir):
        os.makedirs(config_dir)

    data_dir = user_data_dir(app_name)
    if not debug_mode() and not os.path.exists(data_dir):
        os.makedirs(data_dir)

    config.load()
    filename = None if not config.core.logs_loc else config.core.logs_loc
    logging.basicConfig(filename=filename, level=getattr(logging, config.core.logs_level))

    if not os.path.exists(config.core.db_loc):
        logging.warning(f"Database not found, creating one at {config.core.db_loc}")
        create_tables()
    
    if debug_mode():
        logging.info('Application started in debug mode!')
    else:
        logging.info('Application started!')
    main_window()
