"""
application code for interacting with the Google Vision API
"""

import io
from typing import Type
from PIL import Image

from google.cloud.vision import types, ImageAnnotatorClient

from app.utils import to_hex


def image_content_to_type(image: Type[Image]) -> types.Image:
    ''' Load image data as bytestream into an understandable google client data type '''
    image_content = io.BytesIO()
    image.save(image_content, format=image.format)
    return types.Image(content=image_content.getvalue())


def labels(client: Type[ImageAnnotatorClient], image: Type[types.Image]) -> list:
    ''' Gather label annotations from the Google Vision API '''
    label_response = client.label_detection(image=image)
    return [
        label.description
        for label in sorted(label_response.label_annotations, key=lambda x: x.score, reverse=True)
        ]


def colors(client: Type[ImageAnnotatorClient], image: Type[types.Image]) -> list:
    ''' Gather prominent colors as hex strings from the Google Vision API '''
    property_response = client.image_properties(image=image)
    colors = property_response.image_properties_annotation.dominant_colors.colors
    return [
        to_hex(color.color.red, color.color.green, color.color.blue)
        for color in sorted(colors, key=lambda x: x.score, reverse=True)
        ]


def vision_image_properties(image: Type[Image]) -> dict:
    ''' Gather image properties from the Google Vision API '''
    client = ImageAnnotatorClient()
    image_data = image_content_to_type(image)
    return {
        'colors': colors(client, image_data),
        'labels': labels(client, image_data),
    }
