"""
application code for interacting with the Google Vision API
"""

import io
import datetime
import tempfile
import os
import json
import click
import numpy as np
from typing import Type
from PIL import Image

from google.cloud.vision import Image as GImage, ImageAnnotatorClient
from google.cloud.vision import Feature
from google.cloud import storage

from app.utils import to_hex, download, upload, load, bulk_download_wallpapers, media_path
from app.db import Wallpaper, create_session
from app.analyze import dhash


def list_blobs_with_prefix(bucket_name, prefix):
    """
    Gather json files under a specific bloc path in a bucket
    """

    storage_client = storage.Client()

    return storage_client.list_blobs(bucket_name, prefix=prefix)


def json_annotation_blobs(bucket_name, prefix):
    """
    Gather json files under a specific blob path in a bucket
    """

    storage_client = storage.Client()

    blobs = storage_client.list_blobs(bucket_name, prefix=prefix)
    
    return [blob.name for blob in blobs if blob.name.endswith('.json')]


def bulk_delete_from_bucket(bucket_name: str, blob_prefix: str):

    storage_client = storage.Client()

    blobs_to_delete = list_blobs_with_prefix(bucket_name, blob_prefix)
    blobs_to_delete = [blob for blob in blobs_to_delete]

    try:
        with storage_client.batch():
            for blob in blobs_to_delete:
                blob.delete()
    # For some reason the constructor exiting raises a ValueError
    except ValueError:
        pass


def generate_download_signed_url_v4(bucket_name, blob_name):
    """Generates a v4 signed URL for downloading a blob.

    Note that this method requires a service account key file. You can not use
    this if you are using Application Default Credentials from Google Compute
    Engine or from the Google Cloud SDK.
    """

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="GET",
    )

    return url


def image_content_to_type(image):
    ''' Load image data as bytestream into an understandable google client data type '''
    image_content = io.BytesIO()
    image.save(image_content, format=image.format)
    return GImage(content=image_content.getvalue())


def labels(client: Type[ImageAnnotatorClient], image: Type[GImage]) -> list:
    ''' Gather label annotations from the Google Vision API '''
    label_response = client.label_detection(image=image)
    return [
        label.description
        for label in sorted(label_response.label_annotations, key=lambda x: x.score, reverse=True)
        ]


def colors(client: Type[ImageAnnotatorClient], image: Type[GImage]) -> list:
    ''' Gather prominent colors as hex strings from the Google Vision API '''
    property_response = client.image_properties(image=image)
    colors = property_response.image_properties_annotation.dominant_colors.colors
    return [
        to_hex(int(color.color.red), int(color.color.green), int(color.color.blue))
        for color in sorted(colors, key=lambda x: x.score, reverse=True)
        ]


def vision_image_properties(image) -> dict:
    ''' Gather image properties from the Google Vision API '''
    # client = ImageAnnotatorClient()
    # image_data = image_content_to_type(image)
    # return {
    #     'colors': colors(client, image_data),
    #     'labels': labels(client, image_data),
    # }
    client = ImageAnnotatorClient()
    response = client.annotate_image(
        {
            'image': image_content_to_type(image),
            'features': [{'type_': Feature.Type.LABEL_DETECTION},
                         {'type_': Feature.Type.IMAGE_PROPERTIES}],
        }
    )
    return response


def bulk_analyze(image_data: list, output_dir: str, bucket: str):
    ''' Perform async batch image annotation. '''
    client = ImageAnnotatorClient()
    output_uri = f'gs://{bucket}/{output_dir}/'
    gcs_destination = {'uri': output_uri}
    features = [
        {'type_': Feature.Type.LABEL_DETECTION},
        {'type_': Feature.Type.IMAGE_PROPERTIES},
    ]
    batch_size = 5
    output_config = {"gcs_destination": gcs_destination,
                     "batch_size": batch_size}

    requests = []
    for each in image_data:
        source = {"image_uri": f'gs://{bucket}/{each}'}
        image = {'source': source}
        requests.append({'image': image, 'features': features})

    operation = client.async_batch_annotate_images(requests, output_config=output_config)
    operation.result()


def read_bulk_annotations(download_urls: list) -> dict:
    '''
    Gather response information from batch annotation files in google cloud buckets.
    '''

    # Download annotation files to a temp location for easy cleanup
    with tempfile.TemporaryDirectory() as tmpdirname:
        local_files = [os.path.join(tmpdirname, f'batch_{batch}') for batch in range(len(download_urls))]
        download(download_urls, local_files)

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
    session = create_session()
    models_to_analyze = session.query(Wallpaper).filter(Wallpaper.active == True, Wallpaper.analyzed == False).limit(limit).all()
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
        results = upload(downloaded_files, blob_locations, bucket_name)

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

    loaded, err = load(source_urls)
    for guid, data in zip(guids, loaded):
        image_array = np.asarray(Image.open(io.BytesIO(data)))
        annotation_data[guid].update({
                'dhash': dhash(image_array),
            })

    # Cleanup files in buckets
    click.secho('Removing bucket assets...')
    bulk_delete_from_bucket(bucket_name, upload_dir)
    bulk_delete_from_bucket(bucket_name, result_dir)
