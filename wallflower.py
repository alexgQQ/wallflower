import click
import os
import uuid
import time
import numpy as np
import vptree
import requests
import tempfile
import json
from typing import Optional
import aiohttp
import io

from collections import defaultdict
from PIL import Image

from app.clients import RedditClient, bulk_analyze, vision_image_properties
from app.db import Wallpaper, bulk_update_db_entries
from app.elastic import upload_data, search as _search, put_mappings
from app.utils import (
    download as async_download,
    media_path,
    common_colors,
    hex_to_lab,
    to_hex,
    dhash,
    convert_hash,
    hamming,
    load_image,
    upload as async_upload,
    generate_download_signed_url_v4,
    list_blobs_with_prefix,
    json_annotation_blobs,
    bulk_delete_from_bucket,
    load as async_load,
)


def find_duplicates():

    # Build a mapping of guids to image hashes for searching
    query = Wallpaper.select(Wallpaper.dhash, Wallpaper.guid) \
                     .where(Wallpaper.dhash != None) \
                     .namedtuples()
    hash_to_guid = {}
    duplicates = {}

    for entry in query:
        image_hash = convert_hash(entry.dhash)
        if image_hash in hash_to_guid:
            duplicates[hash_to_guid[image_hash]] = [entry.guid]
        else:
            hash_to_guid[image_hash] = entry.guid
    print(duplicates)
    # Load a vantage point tree with a hamming distance search indexer
    search_tree = vptree.VPTree(list(hash_to_guid.keys()), hamming)
    duplicates = {}

    # Find similar hashes for each image
    for search_hash, search_guid in hash_to_guid.items():
        results = search_tree.get_all_in_range(search_hash, 4)
        results = sorted(results)
        similar_guids = [hash_to_guid.get(_hash) for distance, _hash in results if _hash != search_hash]

        if similar_guids:
            duplicates[search_guid] = similar_guids

    # Mark single images as duplicates
    to_mark = []
    check = {}
    for found_duplicate, related_duplicates in duplicates.items():
        if found_duplicate not in to_mark:
            to_mark += related_duplicates
            check[Wallpaper.get(guid=found_duplicate).url] = [obj.url for obj in Wallpaper.select().where(Wallpaper.guid.in_(related_duplicates))]

    # update = Wallpaper.update(duplicate=True).where(Wallpaper.guid.in_(to_mark))
    # update.execute()
    return check


def select_to_analyze(limit: int = 5):
    query = Wallpaper.select().where(Wallpaper.analyzed == False).limit(limit)
    return [entry for entry in query]


def bulk_download_wallpapers(
    list_of_wallpapers: list, directory: str, for_vision: bool = False
    ) -> list:
    '''
    Asyncronously download a set of Wallpaper models from their source url under the
    given directory with their guid path. If `for_vision` is enabled, images that exceed
    the Google Vision API image size will be resized.
    '''

    local_filepaths = []
    source_urls = []
    to_resize = []

    for wallpaper in list_of_wallpapers:
        # Build local filepath to save to
        guid_path = media_path(wallpaper.guid, wallpaper.extension)
        local_filepath = os.path.join(directory, guid_path)

        # Save files that are too large to be resized after download
        if for_vision and wallpaper.size_in_bytes >= 10485760:
            to_resize.append(local_filepath)

        local_filepaths.append(local_filepath)
        source_urls.append(wallpaper.url)

    async_download(source_urls, local_filepaths)

    # TODO: See if there is a way to do this in memory with async
    for each in to_resize:
        image = load_image(each)
        image.thumbnail((1920, 1080), Image.ANTIALIAS)
        image.save(each)
    
    return local_filepaths


def analyze_image(image, image_size):
    '''
    Gather information on an image for search organization.
    :param PIL.Image image: image to analyze.
    :param int image_size: File size of the image, this is inaccurate to calculate from
                           the PIL.Image itself, should be gathered from the file itself.
    :return dict: Dictionary of analysis data.
    '''

    # Google vision api limits image sizes to 10MB
    # if image_size >= 10485760:
    #     image.thumbnail((1920, 1080), Image.ANTIALIAS)

    image.thumbnail((1920, 1080), Image.ANTIALIAS)
    image_array = np.asarray(image)
    _dhash = dhash(image_array)
    properties = vision_image_properties(image)

    return {
        'dhash': _dhash,
        'top_colors': ','.join(properties['colors']),
        'top_labels': ','.join(properties['labels']),
        'analyzed': True,
    }


def read_bulk_annotations(download_urls: list) -> dict:
    '''
    Gather response information from batch annotation files in google cloud buckets.
    '''

    # Download annotation files to a temp location for easy cleanup
    with tempfile.TemporaryDirectory() as tmpdirname:
        local_files = [os.path.join(tmpdirname, f'batch_{batch}') for batch in range(len(download_urls))]
        async_download(download_urls, local_files)

        # Build a dictionary mapping the annotation results to image guids with corresponding db fields
        results = {}
        for file_name in local_files:
            with open(file_name, 'r') as fobj:
                data = json.load(fobj)
                for entry in data.get('responses', []):
                    label_annotations = entry.get('labelAnnotations', [])
                    dominant_colors = entry.get('imagePropertiesAnnotation', {}) \
                                           .get('dominantColors', {}) \
                                           .get('colors', {})
                    labels = [annotation.get('description', '') for annotation in label_annotations]
                    colors = [
                        to_hex(
                            color.get('color', {}).get('red', 0),
                            color.get('color', {}).get('green', 0),
                            color.get('color', {}).get('blue', 0)
                            )
                        for color in dominant_colors
                        ]
                    # Get the guid from the url path in from the source bucket path
                    # TODO: should find a better way to link these entries, but only the source path is available in the context
                    guid = entry.get('context', {}).get('uri', '').split('/')[-1].split('.')[0]
                    results[guid] = {
                        'analyzed': True,
                        'top_labels': ','.join(labels),
                        'top_colors': ','.join(colors),
                    }
    return results


def bulk_analyze_images(limit: int = 20):

    bucket_name = 'pixelpopart-test'
    upload_dir = 'uploads'
    result_dir = 'batch_annotations'
    models_to_analyze = select_to_analyze(limit=limit)
    number_of_models = len(models_to_analyze)

    if number_of_models == 0:
        click.secho('No models found for analyzing')
        return

    # Download images so they can be resized, and upload them to the given bucket.
    click.secho(
        f'Uploading {number_of_models} images to gs://{bucket_name}/{upload_dir}')
    with tempfile.TemporaryDirectory() as tmpdirname:
        downloaded_files = bulk_download_wallpapers(models_to_analyze, tmpdirname, for_vision=True)
        blob_locations = [
            media_path(model.guid, model.extension, cdn_host=upload_dir)
            for model in models_to_analyze
        ]
        results = async_upload(downloaded_files, blob_locations, bucket_name)

    # Wait until batch jobs are done
    click.secho('Awaiting Google Vision annotation results...')
    bulk_analyze(blob_locations, result_dir, bucket_name)

    # Gather result annotation files from the batch job
    click.secho('Reading annotation data...')
    result_blobs = json_annotation_blobs(bucket_name, result_dir)
    download_urls = [
        generate_download_signed_url_v4(bucket_name, blob)
        for blob in result_blobs
    ]
    annotation_data = read_bulk_annotations(download_urls)
    bulk_update_db_entries(models_to_analyze, annotation_data, key_field='guid')

    # Load image data from urls to calculate the dhash
    # TODO: Should unify this with the download routine to limit loads
    guids = []
    source_urls = []
    for model in models_to_analyze:
        guids.append(model.guid)
        source_urls.append(model.url)

    for guid, data in zip(guids, async_load(source_urls)):
        image_array = np.asarray(Image.open(io.BytesIO(data)))
        annotation_data[guid].update({
                'dhash': dhash(image_array),
            })

    # Cleanup files in buckets
    click.secho('Removing bucket assets...')
    bulk_delete_from_bucket(bucket_name, upload_dir)
    bulk_delete_from_bucket(bucket_name, result_dir)


def analyze(limit: int = 20):

    to_update = {}
    models_to_analyze = select_to_analyze(limit=limit)

    with click.progressbar(models_to_analyze) as models:
        for model in models:
            try:
                image = load_image(model.url)
                to_update[model.id] = analyze_image(image, model.size_in_bytes)
            except requests.exceptions.RequestException:
                pass

    bulk_update_db_entries(models_to_analyze, to_update)


def from_reddit(limit=20):
    '''
    Gather all images from saved reddit posts and load them into the database.
    :param int limit: The number of reddit posts to pull.
    '''
    to_create = []
    client = RedditClient()
    for obj in client.saved_wallpapers(limit=limit):
        try:
            Wallpaper.get(reddit_id=obj.id)
        except Wallpaper.DoesNotExist:
            create_params = {
                'guid': str(uuid.uuid4()),
                'url': obj.url,
                'source_id': obj.id,
                'downloaded': False,
                'extension': obj.url.split('.')[-1],
                'analyzed': False,
                'source_type': 'reddit',
                'size_in_bytes': int(requests.head(obj.url).headers['Content-Length']),
            }
            to_create.append(create_params)
    Wallpaper.insert_many(to_create).execute()


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
@click.option(
    '--limit', default=0, type=int,
    show_default=True, help='Number of images to inspect',
    )
@click.option(
    '--bulk', default=False, is_flag=True,
    help='Use Vision bulk service', show_default=True,
    )
@click.pass_context
def inspect(ctx, image_dir, image, reset, duplicates, limit, bulk):
    '''
    Analyze current set of images.
    '''
    if image:
        analyze_image(image, image_dir)
        return

    if duplicates:
        values = find_duplicates()
        return

    if reset:
        Wallpaper.update({'analyzed': False}).execute()
        return

    click.secho(f'Analyzing {limit} files...')
    if bulk:
        bulk_analyze_images(limit=limit)
    else:
        analyze(limit=limit)
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
@click.option(
    '--label', type=str, default=None,
    help='Label keyword to search.', show_default=True,
    )
@click.option(
    '--color', type=str, default=None,
    help='Hex color value to search.', show_default=True,
    )
@click.option(
    '--upload', is_flag=True, default=False,
    help='Upload elasticsearch models.', show_default=True,
    )
@click.option(
    '--mappings', is_flag=True, default=False,
    help='Upload elasticsearch field mappings.', show_default=True,
    )
@click.pass_context
def search(ctx, label, color, upload, mappings):
    '''
    Search elasticsearch instance with given info.
    '''
    if upload:
        click.secho('Seeding elasticsearch...')
        upload_data()
        click.secho('Done!')
        return

    if mappings:
        click.secho('Mapping elasticsearch fields...')
        put_mappings()
        click.secho('Done!')
        return

    if color is not None:
        value = hex_to_lab(color)
        color = value[0,0,:]

    results = _search(lab_colors=color, label_keyword=label)

    for result in results['hits']['hits']:
        click.secho(str(result['_source']['url']))
