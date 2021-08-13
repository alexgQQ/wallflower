import click
import os
import uuid
import time
import numpy as np
import requests
import tempfile
import json
from typing import Optional
import aiohttp
import io
import logging

from collections import defaultdict
from PIL import Image
from datetime import datetime
from multiprocessing import Pool, cpu_count

from app.clients.reddit import RedditClient
from app.clients.vision import bulk_analyze, vision_image_properties
from app.clients.imgur import MyImgurClient

from app.utils import (
    download as async_download,
    media_path,
    common_colors,
    hex_to_lab,
    to_hex,
    dhash,
    hex_to_lab,
    hamming,
    load_image,
    upload as async_upload,
    generate_download_signed_url_v4,
    list_blobs_with_prefix,
    json_annotation_blobs,
    bulk_delete_from_bucket,
    load as async_load,
    find_duplicates,
)
from app.mongo import Wallpaper as MGWallpaper, connect, color_search, bulk_update


supported_formats = (
    'jpeg', 'jpg', 'png',
)


def latest_from_reddit():
    return MGWallpaper.objects(source_type=RedditClient.source_type) \
                      .order_by('-created_date').first()


def earliest_from_reddit():
    return MGWallpaper.objects(source_type=RedditClient.source_type) \
                      .order_by('+created_date').first()


class ClientSerializer:

    def __init__(self, client, client_kwargs={}, limit=10):
        self.client = client(**client_kwargs)
        self.limit = limit

    def from_client(self, exclude_ids=[]):
        to_create = []

        for data in self.client.fetch(limit=self.limit):
            if exclude_ids and data['source_id'] in exclude_ids:
                continue
            else:
                data['guid'] = str(uuid.uuid4())
                data['created_date'] = datetime.now()
                data['updated_date'] = datetime.now()
                to_create.append(MGWallpaper(**data))

        logging.info(
            f'Found {len(to_create)} images from {self.client.__class__}'
        )
        return to_create

    def save(self):
        existing_query = MGWallpaper.objects(source_type=self.client.source_type).only('source_id')
        existing_ids = [obj.source_id for obj in existing_query]
        doc_data = self.from_client(exclude_ids=existing_ids)
        documents = MGWallpaper.objects().insert(doc_data)
        logging.info(
            f'Inserted {len(documents)} documents'
        )


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
        # if for_vision and wallpaper.size_in_bytes >= 10485760:
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


def analyze_image(image):
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
    # image.thumbnail((454, 256), Image.ANTIALIAS)
    # image_array = np.asarray(image)
    results = vision_image_properties(image)
    image.convert("L")
    gray_image_array = np.asarray(image)
    _dhash = dhash(gray_image_array)
    # colors, counts = common_colors(image_array, 5)

    data = {}
    analyzed = True
    # try:
    #     top_hex_colors = [to_hex(*color) for color in colors[:, :3]]
    # except Exception as err:
    #     logging.info(
    #         f'Error converting colors to hex strings -- {err}'
    #     )
    #     top_hex_colors = None

    # if top_hex_colors and len(top_hex_colors) >= 5:
    #     try:
    #         for n in range(5):
    #             data[f'lab_color_{n}'] = list(hex_to_lab(top_hex_colors[n]))
    #         analyzed = True
    #     except Exception as err:
    #         logging.info(
    #             f'Error converting hex colors to lab -- {err}'
    #         )
    #         data[f'lab_color_{n}'] = None

    # results = vision_image_properties(image)
    data['top_labels'] = ','.join((obj.description for obj in results.label_annotations))
    top_hex_colors = [
        to_hex(int(color.color.red), int(color.color.green), int(color.color.blue))
        for color in results.image_properties_annotation.dominant_colors.colors
        ]
    return {
        'dhash': str(_dhash),
        'top_colors': top_hex_colors[:5],
        'analyzed': analyzed,
        **data,
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
    models_to_analyze = MGWallpaper.objects(active=True, analyzed=False).limit(limit)
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

    # MGWallpaper.objects(guid__in=annotation_data.keys()).all()


    # Load image data from urls to calculate the dhash
    # TODO: Should unify this with the download routine to limit loads
    guids = []
    source_urls = []
    for model in models_to_analyze:
        guids.append(model.guid)
        source_urls.append(model.url)

    loaded, err = async_load(source_urls)
    for guid, data in zip(guids, loaded):
        image_array = np.asarray(Image.open(io.BytesIO(data)))
        annotation_data[guid].update({
                'dhash': dhash(image_array),
            })

    # Cleanup files in buckets
    click.secho('Removing bucket assets...')
    bulk_delete_from_bucket(bucket_name, upload_dir)
    bulk_delete_from_bucket(bucket_name, result_dir)


def analyze(limit: int = 20, batch: int = 100):

    to_analyze = MGWallpaper.objects(active=True, analyzed=False) \
                            .only('guid', 'url').limit(limit)
    guids = []
    results = []
    for obj in to_analyze:
        guids.append(obj.guid)
        results.append(analyze_image(load_image(obj.url)))

    to_write = dict(zip(guids, results))
    bulk_update(to_write)
    # number_of_full_runs = limit // batch
    # leftover = limit % batch
    # processes = cpu_count()

    # def analyze_set(num):
    #     to_analyze = MGWallpaper.objects(active=True, analyzed=False) \
    #                             .only('guid', 'url').limit(num)
    #     urls = []
    #     guids = []
    #     for obj in to_analyze:
    #         urls.append(obj.url)
    #         guids.append(obj.guid)

    #     images, err = async_load(urls)
    #     images = [Image.open(io.BytesIO(data)) for data in images]
    #     with Pool(processes=processes) as pool:
    #         data = pool.map(analyze_image, images)
    #     to_write = dict(zip(guids, data))
    #     bulk_update(to_write)

    # if number_of_full_runs > 0:
    #     for n in range(number_of_full_runs):
    #         analyze_set(limit)

    # analyze_set(leftover)


def _download(limit=500, location=''):
    '''
    Download all images from the database that are not downloaded.
    :param int limit: The number of images to download.
    '''
    urls = []
    filenames = []

    for wallpaper in MGWallpaper.objects(active=True, downloaded=False).limit(limit):
        filename = media_path(wallpaper.guid, wallpaper.extension, cdn_host=location, nested=False)
        filenames.append(filename)
        urls.append(wallpaper.url)

    download_count, errors = async_download(urls, filenames)


def validate_files(file_location):
    '''
    Check download locations for ingested images. Will update the database if the status does
    not match
    :param string file_location: The directory path for the fils to validate.
    :return int broken: The number of fixed files.
    '''
    broken = 0
    for obj in MGWallpaper.objects.all():
        filename = media_path(obj.guid, obj.extension, cdn_host=file_location)
        exists = os.path.isfile(filename)
        if exists != obj.downloaded:
            broken += 1
            obj.downloaded = exists
            obj.save()
    return broken


@click.group()
@click.option('-v', '--verbose', is_flag=True, default=False)
@click.pass_context
def cli(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose
    if verbose:
        logging.basicConfig(level=logging.INFO)


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
@click.option(
    '--source', type=click.Choice(['reddit', 'imgur', 'all'], case_sensitive=False),
    help='Where to pull new images from.', show_default=True, default='all'
    )
@click.pass_context
def pull(
    ctx, limit, image_dir, download, only_download, source):
    '''
    Pull image files from sources and download them.
    '''
    source_type_map = {
        'imgur': MyImgurClient,
        'reddit': RedditClient,
    }

    client_kwargs = {
        'after': latest_from_reddit(),
    }

    if not only_download:
        if source == 'all':
            source_types = list(source_type_map.keys())
        else:
            source_types = [source]

        for source_type in source_types:
            click.secho(f'Pulling images from {source_type}...')
            serializer = ClientSerializer(
                source_type_map[source_type], limit=limit, # client_kwargs=client_kwargs
            )
            serializer.save()

    if download or only_download:
        click.secho(f'Downloading {limit} images...')
        num_dowloaded, errored =_download(limit=limit, location=image_dir)
        click.secho(f'Successfully downloaded {num_dowloaded} images')

        # TODO: I should make custom exceptions to get gathered by the download
        # routine to track the urls that failed or mark the related entries as bad
        if errored:
            click.secho(f'Error downloading {len(errored)} images')

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
    '--limit', default=5, type=int,
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
        query = MGWallpaper.objects(active=True, dhash__ne=None).only('dhash', 'guid')
        guid_to_hash = {obj.guid: int(obj.dhash) for obj in query}
        duplicate_guids = find_duplicates(guid_to_hash)
        return

    if reset:
        MGWallpaper.objects.update(analyzed=False)
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
        total = MGWallpaper.objects.count()
        click.secho(f'Checking {total} files...')
        broken = validate_files(image_dir)
        if broken:
            click.secho(f'Fixed {broken} files...')
        click.secho(u'\u2728 All Clean \u2728')

    if check_source:
        client = RedditClient()
        from_reddit = MGWallpaper.objects(source_type='reddit').count()
        in_reddit = client.check_status()
        click.secho('- Reddit Info -', bold=True, fg='red')
        click.secho(f'In Sync: {in_reddit == from_reddit}')

    if image:
        try:
            image = MGWallpaper.objects.get(guid=image)
            filename = media_path(image.guid, image.extension, cdn_host=image_dir)
            click.secho(filename)
        except MGWallpaper.DoesNotExist:
            click.secho('Image not found!', fg='red')
        return None

    total = MGWallpaper.objects(active=True).count()
    click.secho('- Database Info -', bold=True)
    click.secho(f'Total: {total}')


@cli.command()
@click.option(
    '--label', type=str, default=None,
    help='Label keyword to search.', show_default=True,
    )
@click.option(
    '--color', type=str, default=None,
    help='Hex color value to search.', show_default=True,
    )
@click.pass_context
def search(ctx, label, color):
    '''
    Search mongodb instance with given info.
    '''
    if color is not None:
        guids = color_search(color)
        query = MGWallpaper.objects(guid__in=guids).only('url')
        print([obj.url for obj in query])
        # value = hex_to_lab(color)
        # color = value[0,0,:]

    # results = _search(lab_colors=color, label_keyword=label)

    # for result in results['hits']['hits']:
    #     click.secho(str(result['_source']['url']))


@cli.command()
def foobar():
    
    pass


if __name__ == '__main__':
    cli()
