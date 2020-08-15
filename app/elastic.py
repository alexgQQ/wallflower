import ndjson
from typing import Optional

from app.db import Wallpaper
from elasticsearch import Elasticsearch

elastic_client = Elasticsearch()


def upload_data(file_path: Optional[str] = None, index: str = 'image'):
    '''
    Upload database entries to elasticsearch to the provided index.
    Optionally the database entries can be written to a njson file to be uploaded to elasticsearch
    Note: File needs to be JSON with newline separator known as NDJSON
    Reference: https://www.elastic.co/guide/en/elasticsearch/reference/current/getting-started-index.html#getting-started-batch-processing
    '''
    bulk_indices = []
    for obj in Wallpaper.select().where(Wallpaper.analyzed == True):
        _id, data = obj.elastic_model()
        bulk_indices.append({'index': _id})
        bulk_indices.append(data)

    if isinstance(file_path, str):
        with open(file_path, 'w') as file_obj:
            ndjson.dump(bulk_indices, file_obj)
            file_obj.write('\n')
    else:
        elastic_client.bulk(bulk_indices, index=index)
        elastic_client.indices.refresh(index=index)


def put_mappings(index: str = 'image'):
    '''
    Set field mappings for a given index for elasticsearch documents based on database models.
    '''
    def color_field(number: int):
        return {
            f'top_color_{number}': {
                'type': 'dense_vector',
                'dims': 3,
            }
        }

    properties = {
        'searchable': {'type': 'boolean'},
        'top_labels': {
            'fields': {
                'keyword': {
                    'ignore_above': 256,
                    'type': 'keyword'
                }
            },
            'type': 'text'
        },
        'url': {
            'fields': {
                'keyword': {
                    'ignore_above': 256,
                    'type': 'keyword'
                }
            },
            'type': 'text'
        },
        'extension': {
            'fields': {
                'keyword': {
                    'ignore_above': 256,
                    'type': 'keyword'
                }
            },
            'type': 'text'
        },
    }
    for number in range(10):
        field = color_field(number)
        properties.update(field)

    elastic_client.indices.create(index, ignore=[400])
    elastic_client.indices.put_mapping({'properties': properties}, index=index)


# TODO: Since the api is set up, does this need to be here?
def search(lab_colors=None, label_keyword=None):

    if lab_colors is None and label_keyword is None:
        return []

    def color_field_search(number):
        source = "((1 / (1 + l2norm(params.queryVector, 'top_color_0'))) + (1 / (1 + l2norm(params.queryVector, 'top_color_1'))) + (1 / (1 + l2norm(params.queryVector, 'top_color_2')))) / 3"

        return {
                "source": source,
                "params": {
                    "queryVector": lab_colors,
                }
            }

    base_query = {
        "query" : {
            "bool" : {
                "filter" : {
                    "term" : {
                        "searchable" : "true",
                    }
                }
            }
        }
    }

    if label_keyword:
        del base_query['query']['bool']
        base_query['query']['match'] = {
            "top_labels": label_keyword,
        }

    if lab_colors is not None:
        base_query = {
            'query': {
                'script_score': base_query,
            },
        }
        base_query['query']['script_score']['script'] = color_field_search(0)
        base_query['query']['script_score']['min_score'] = 0.01
    results = elastic_client.search(index='image', body=base_query, params={'size': 20})

    return results
