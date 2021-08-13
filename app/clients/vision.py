"""
application code for interacting with the Google Vision API
"""

import io
from typing import Type
from PIL import Image

from google.cloud.vision import Image as GImage, ImageAnnotatorClient
from google.cloud.vision import Feature

from app.utils import to_hex


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
