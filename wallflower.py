# import click
# import logging

# from app.clients.reddit import RedditClient
# from app.clients.imgur import MyImgurClient
# from app.clients.wallhaven import MyWallhavenClient
# from app.search import find_nearest_colors
# from app.db import create_session, all_colors, wallpapers_by_color, all as all_wallpapers
# from app.utils import load
# from time import time


# def get_all_from_clients():
#     clients = (
#         MyWallhavenClient, MyImgurClient, RedditClient
#     )
#     data = []
#     for client in clients:
#         client = client()
#         data += [obj for obj in client.fetch()]
#     return data


# @click.group()
# @click.option('-v', '--verbose', is_flag=True, default=False)
# @click.pass_context
# def cli(ctx, verbose):
#     ctx.ensure_object(dict)
#     ctx.obj['VERBOSE'] = verbose
#     if verbose:
#         logging.basicConfig(level=logging.INFO)


# @cli.command()
# @click.option(
#     '--limit', default=5, show_default=True,
#     help='The number of images to pull.'
#     )
# @click.option(
#     '--source', type=click.Choice(['reddit', 'imgur', 'all'], case_sensitive=False),
#     help='Where to pull new images from.', show_default=True, default='all'
#     )
# @click.pass_context
# def pull(ctx, limit, source):
#     '''
#     Pull image files from sources and download them.
#     '''
#     # source_type_map = {
#     #     'imgur': MyImgurClient,
#     #     'reddit': RedditClient,
#     # }

#     # client_kwargs = {
#     #     'after': latest_from_reddit(),
#     # }

#     # if not only_download:
#     #     if source == 'all':
#     #         source_types = list(source_type_map.keys())
#     #     else:
#     #         source_types = [source]

#     #     for source_type in source_types:
#     #         click.secho(f'Pulling images from {source_type}...')
#     #         serializer = ClientSerializer(
#     #             source_type_map[source_type], limit=limit, # client_kwargs=client_kwargs
#     #         )
#     #         serializer.save()

#     # if download or only_download:
#     #     click.secho(f'Downloading {limit} images...')
#     #     num_dowloaded, errored =_download(limit=limit, location=image_dir)
#     #     click.secho(f'Successfully downloaded {num_dowloaded} images')

#     #     # TODO: I should make custom exceptions to get gathered by the download
#     #     # routine to track the urls that failed or mark the related entries as bad
#     #     if errored:
#     #         click.secho(f'Error downloading {len(errored)} images')

#     click.secho('Done!')


# @cli.command()
# @click.option(
#     '--image', default=None,
#     show_default=True, help='A specific file to look at.',
#     )
# @click.option(
#     '--reset/--no-reset', default=False,
#     help='Reanalyze all the current files.', show_default=True,
#     )
# @click.option(
#     '--duplicates', default=False, is_flag=True,
#     help='Find duplicate images.', show_default=True,
#     )
# @click.option(
#     '--limit', default=5, type=int,
#     show_default=True, help='Number of images to inspect',
#     )
# @click.option(
#     '--bulk', default=False, is_flag=True,
#     help='Use Vision bulk service', show_default=True,
#     )
# @click.pass_context
# def inspect(ctx, image, reset, duplicates, limit, bulk):
#     '''
#     Analyze current set of images.
#     '''
#     # if image:
#     #     analyze_image(image, image_dir)
#     #     return

#     # if duplicates:
#     #     query = MGWallpaper.objects(active=True, dhash__ne=None).only('dhash', 'guid')
#     #     guid_to_hash = {obj.guid: int(obj.dhash) for obj in query}
#     #     duplicate_guids = find_duplicates(guid_to_hash)
#     #     return

#     # if reset:
#     #     MGWallpaper.objects.update(analyzed=False)
#     #     return

#     # click.secho(f'Analyzing {limit} files...')
#     # if bulk:
#     #     bulk_analyze_images(limit=limit)
#     # else:
#     #     analyze(limit=limit)
#     click.secho(f'Done!')


# @cli.command()
# @click.option(
#     '--label', type=str, default=None,
#     help='Label keyword to search. TODO: Currently unsupported', show_default=True,
#     )
# @click.option(
#     '--color', type=str, default=None,
#     help='Hex color value to search.', show_default=True,
#     )
# @click.pass_context
# def search(ctx, label, color):
#     '''
#     Search images with given query
#     '''
#     # if color is not None:
#     session = create_session()
#     wallpapers = all_wallpapers(session, 10)
#     urls = [wallpaper.source_url for wallpaper in wallpapers]
#     now = time()
#     images = load(urls)
#     print(time() - now)
#     now = time()
#     images = load(urls)
#     print(time() - now)
#     now = time()
#     images = load(urls)
#     print(time() - now)


# if __name__ == '__main__':
#     cli()

from PyQt5 import QtWidgets
from app.gui.main_window import Ui_MainWindow
import os
import sys

if __name__ == "__main__":
    # opencv has a built in qt binary that it attempts to load on import
    # removing the plugin path for opencv fixes the issue
    # https://stackoverflow.com/a/67863156
    os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH")
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
