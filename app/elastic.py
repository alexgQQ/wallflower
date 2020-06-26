import ndjson

from app.db import Wallpaper
from elasticsearch import Elasticsearch

es = Elasticsearch()


def upload_data(file_path=None, index='image'):
    '''
    Convert db entries to a index files to be understood by elasticsearch.
    Reference: https://www.elastic.co/guide/en/elasticsearch/reference/current/getting-started-index.html#getting-started-batch-processing
    Note: File needs to be JSON with newline separator known as NDJSON
    '''
    bulk_indices = []
    for obj in Wallpaper.select():
        _id, data = obj.elastic_model()
        bulk_indices.append({'index': _id})
        bulk_indices.append(data)

    if isinstance(file_path, str):
        with open(file_path, 'w') as file_obj:
            ndjson.dump(bulk_indices, file_obj)
            file_obj.write('\n')
    else:
        es.bulk(bulk_indices, index=index)
        es.indices.refresh(index=index)


def search_color(lab_colors):
    query = {
        "query": {
            "script_score": {
                "query" : {
                    "bool" : {
                        "filter" : {
                            "term" : {
                                "searchable" : "true",
                            }
                        }
                    }
                },
                "script": {
                    "source": "1 / (1 + l2norm(params.queryVector, 'top_color_0'))",
                    "params": {
                        "queryVector": lab_colors,
                    }
                },
                "script": {
                    "source": "1 / (1 + l2norm(params.queryVector, 'top_color_1'))",
                    "params": {
                        "queryVector": lab_colors,
                    }
                },
                "script": {
                    "source": "1 / (1 + l2norm(params.queryVector, 'top_color_2'))",
                    "params": {
                        "queryVector": lab_colors,
                    }
                },
            }
        }
    }

    results = es.search(index='image', body=query)
    return [hit['_source'] for hit in results['hits']['hits']]
