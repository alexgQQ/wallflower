import click
import os
import uuid
import time
import numpy as np
import vptree

from PIL import Image

from app.reddit import RedditClient
from app.db import Wallpaper
from app.elastic import upload_data, search_color
from app.utils import (
    download as async_download,
    media_path,
    get_labels,
    common_colors,
    hex_to_lab,
    to_hex,
    dhash,
    convert_hash,
    hamming,
)


def find_duplicates():
    query = (Wallpaper
                .select(Wallpaper.dhash, Wallpaper.guid)
                .where(Wallpaper.dhash != None and Wallpaper.duplicate == False)
                .namedtuples()
                )
    hashes = []
    hash_to_guid = {}

    for entry in query:
        _hash = convert_hash(entry.dhash)
        hash_to_guid[_hash] = entry.guid
        hashes.append(_hash)

    search_tree = vptree.VPTree(hashes, hamming)
    duplicates = {}

    for search_hash, search_guid in hash_to_guid.items():
        results = search_tree.get_all_in_range(search_hash, 4)
        results = sorted(results)
        similar_guids = []
        for (distance, _hash) in results:
            found_guid = hash_to_guid.get(_hash)
            if found_guid != search_guid:
                similar_guids.append(found_guid)
        if similar_guids:
            duplicates[search_guid] = similar_guids

    to_mark = []
    for found_duplicate, related_duplicates in duplicates.items():
        if found_duplicate not in to_mark:
            to_mark += related_duplicates 

    update = Wallpaper.update(duplicate=True).where(Wallpaper.guid.in_(to_mark))
    update.execute()


def analyze_image(guid, image_loc):
    try:
        wallpaper = Wallpaper.get(guid=guid)
    except Wallpaper.DoesNotExist:
        click.secho('Image not found!', fg='red')
        return None
    filename = media_path(wallpaper.guid, wallpaper.extension, cdn_host=image_loc)
    image = Image.open(filename)
    orig_image_array = np.asarray(image)
    _dhash = dhash(orig_image_array)
    # image = image.resize((200, 200))
    image.thumbnail((200, 200), Image.ANTIALIAS)
    image_array = np.asarray(image)
    colors = common_colors(image_array, 5)
    top_colors = sorted(zip(colors[1], colors[0]), reverse=True)
    try:
        colors = [to_hex(*val[:3]) for _, val in top_colors]
    except:
        colors = []
    # labels = get_labels(filename, top_num=5)
    labels = []
    wallpaper.dhash = _dhash
    wallpaper.top_colors = ','.join(colors)
    wallpaper.top_labels = ','.join(labels)
    wallpaper.analyzed = True
    wallpaper.save()


def analyze(image_loc, limit=20):

    for wallpaper in Wallpaper.select().where(
        Wallpaper.downloaded == True and Wallpaper.analyzed == False):
        filename = media_path(wallpaper.guid, wallpaper.extension, cdn_host=image_loc)
        image = Image.open(filename)
        orig_image_array = np.asarray(image)
        _dhash = dhash(orig_image_array)
        # image = image.resize((200, 200))
        image.thumbnail((200, 200), Image.ANTIALIAS)
        image_array = np.asarray(image)
        colors = common_colors(image_array, 5)
        top_colors = sorted(zip(colors[1], colors[0]), reverse=True)
        try:
            colors = [to_hex(*val[:3]) for _, val in top_colors]
        except:
            colors = []
            continue
        # labels = get_labels(filename, top_num=5)
        labels = []
        wallpaper.dhash = _dhash
        wallpaper.top_colors = ','.join(colors)
        wallpaper.top_labels = ','.join(labels)
        wallpaper.analyzed = True
        wallpaper.save()


def from_reddit(limit=20):
    '''
    Gather all images from saved reddit posts and load them into the database.
    :param int limit: The number of reddit posts to pull.
    '''
    client = RedditClient()
    for obj in client.saved_wallpapers(limit=limit):
        # TODO: Should explore other algorithms like batch pulls
        # may be inefficient to check each one individually
        try:
            Wallpaper.get(reddit_id=obj.id)
        except Wallpaper.DoesNotExist:
            create_params = {
                'guid': str(uuid.uuid4()),
                'url': obj.url,
                'reddit_id': obj.id,
                'downloaded': False,
                'extension': obj.url.split('.')[-1],
                'analyzed': False,
                'source_type': 'reddit',
            }
            Wallpaper.create(**create_params)


def _download(limit=500, location=''):
    '''
    Download all images from the database that are not downloaded.
    :param int limit: The number of images to download.
    '''
    urls = []
    filenames = []
    for wallpaper in Wallpaper.select().where(Wallpaper.downloaded == False).limit(limit):
        filename = media_path(wallpaper.guid, wallpaper.extension, cdn_host=location)
        filenames.append(filename)
        urls.append(wallpaper.url)
        wallpaper.downloaded = True
        wallpaper.save()
    async_download(urls, filenames)


def validate_files(file_location):
    '''
    Check download locations for ingested images. Will update the database if the status does
    not match
    :param string file_location: The directory path for the fils to validate.
    :return int broken: The number of fixed files.
    '''
    broken = 0
    for obj in Wallpaper.select():
        filename = media_path(obj.guid, obj.extension, cdn_host=file_location)
        exists = os.path.isfile(filename)
        if exists != obj.downloaded:
            broken += 1
            obj.downloaded = exists
            obj.save()
    return broken


@click.group()
@click.option('--debug/--no-debug', default=False)
@click.pass_context
def cli(ctx, debug):
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug


@cli.command()
@click.option(
    '--limit', default=5, show_default=True,
    help='The number of images to pull.'
    )
@click.option(
    '--image-dir', envvar='IMAGE_DIRECTORY',
    show_envvar=True, help='The root directory for the image files.',
    )
@click.option(
    '--download/--no-download', default=True,
    help='Enable or disable downloading.', show_default=True,
    )
@click.option(
    '--only-download', is_flag=True, default=False,
    help='Only downlaod files currently known.', show_default=True,
    )
@click.pass_context
def pull(
    ctx, limit, image_dir, download, only_download):
    '''
    Pull image files from sources and download them.
    '''
    if not only_download:
        click.secho('Pulling images from Reddit...')
        from_reddit(limit=limit)
    if download or only_download:
        click.secho('Downloading images...')
        _download(limit=limit, location=image_dir)
    click.secho('Done!')


@cli.command()
@click.option(
    '--image-dir', envvar='IMAGE_DIRECTORY',
    show_envvar=True, help='The root directory of the image files',
    )
@click.option(
    '--image', default=None,
    show_default=True, help='A specific file to look at.',
    )
@click.option(
    '--reset/--no-reset', default=False,
    help='Reanalyze all the current files.', show_default=True,
    )
@click.option(
    '--duplicates', default=False, is_flag=True,
    help='Find duplicate images.', show_default=True,
    )
@click.pass_context
def inspect(ctx, image_dir, image, reset, duplicates):
    '''
    Analyze current set of images.
    '''
    if image:
        analyze_image(image, image_dir)
        return None

    if duplicates:
        find_duplicates()
        return None

    if reset:
        for obj in Wallpaper.select():
            obj.analyzed = False
            obj.save()
    total = Wallpaper.select().where(Wallpaper.analyzed == False).count()
    click.secho(f'Analyzing {total} files...')
    analyze(image_dir)
    click.secho(f'Done!')


@cli.command()
@click.option(
    '--image-dir', envvar='IMAGE_DIRECTORY',
    show_envvar=True, help='The root directory of the image files',
    )
@click.option(
    '--image', multiple=True, default=[],
    show_default=True, help='A specific file to look at.',
    )
@click.option(
    '--validate', is_flag=True, default=False,
    help='Validate if downloaded files are downloaded', show_default=True,
    )
@click.option(
    '--check-source', is_flag=True, default=False,
    help='Check if new files are available on sources', show_default=True,
    )
@click.pass_context
def info(ctx, image_dir, image, validate, check_source):
    '''
    Report information on current files.
    '''

    if validate:
        total = len(Wallpaper)
        click.secho(f'Checking {total} files...')
        broken = validate_files(image_dir)
        if broken:
            click.secho(f'Fixed {broken} files...')
        click.secho(u'\u2728 All Clean \u2728')

    if check_source:
        client = RedditClient()
        from_reddit = Wallpaper.select().where(Wallpaper.source_type == 'reddit').count()
        in_reddit = client.check_status()
        click.secho('- Reddit Info -', bold=True, fg='red')
        click.secho(f'In Sync: {in_reddit == from_reddit}')

    if image:
        try:
            image = Wallpaper.get(guid=image)
            filename = media_path(image.guid, image.extension, cdn_host=image_dir)
            click.secho(filename)
        except Wallpaper.DoesNotExist:
            click.secho('Image not found!', fg='red')
        return None

    total = len(Wallpaper)
    downloaded = Wallpaper.select().where(Wallpaper.downloaded == True).count()
    analyzed = Wallpaper.select().where(Wallpaper.analyzed == True).count()
    click.secho('- Database Info -', bold=True)
    click.secho(f'Total: {total}, Downloaded: {downloaded}, Analyzed: {analyzed}')


@cli.command()
@click.argument(
    'color', required=False, default=None
    )
@click.option(
    '--upload', is_flag=True, default=False,
    help='Upload elasticsearch models.', show_default=True,
    )
@click.pass_context
def search(ctx, color, upload):
    '''
    Search elasticsearch instance with given info.
    '''
    if upload:
        click.secho('Seeding elasticsearch...')
        upload_data()
        click.secho('Done!')
        return

    if color is not None:
        value = hex_to_lab(color)
        image_dir = os.environ.get('IMAGE_DIRECTORY')
        results = search_color(value[0,0,:])
        for item in results:
            click.secho(os.path.join(image_dir, media_path(item['guid'], item['extension'])))
