import datetime

from mongoengine import (
    Document, StringField, DateTimeField, LongField,
    connect, ListField, URLField, BooleanField
)
from pymongo import UpdateOne
from bson.code import Code
from collections import defaultdict

from .utils import hex_to_lab

connection_url = f'mongodb+srv://dbUser:pSJeeK9egBHdoKzc@maincluster.kqhjh.mongodb.net/default?retryWrites=true&w=majority'

connect('wallflower', host=connection_url)

class Wallpaper(Document):
    guid = StringField(required=True)
    url = URLField(null=True)
    source_id = StringField(null=True)
    downloaded = BooleanField(default=False)
    top_colors = ListField(field=StringField(), max_length=10, null=True)
    top_labels = StringField(null=True)
    extension = StringField(required=True, null=True)
    analyzed = BooleanField(default=False)
    source_type = StringField(null=True)
    # Maximum value for a dhash algorithm on a (9, 8) image
    dhash = StringField(null=True)
    duplicate = BooleanField(default=False)
    created_date = DateTimeField(required=True)
    updated_date = DateTimeField(required=True)
    lab_color_0 = ListField(required=False, null=True)
    lab_color_1 = ListField(required=False, null=True)
    lab_color_2 = ListField(required=False, null=True)
    lab_color_3 = ListField(required=False, null=True)
    lab_color_4 = ListField(required=False, null=True)
    active = BooleanField(default=False)
    # size_in_bytes = IntegerField(null=True)

    meta = {'allow_inheritance': True, 'collection': 'wallflower'}


def bulk_update(update_data):
    bulk_operations = []

    for guid, data in update_data.items():
        bulk_operations.append(
            UpdateOne({'guid': guid}, {'$set': data})
        )

    if bulk_operations:
        collection = Wallpaper._get_collection().bulk_write(bulk_operations, ordered=False)


def color_search(hex_color: str, num_of_colors: int = 5, score_threshold: float = 5.0):

    result = []
    target_lab_color = list(hex_to_lab(hex_color))

    for color in range(num_of_colors):

        map_func = Code( "function () {                                                  "
                         "  var i;                                                       "
                        f"  if (this.lab_color_{color}) {{                               "
                        f"    for (i = 0; i < this.lab_color_{color}.length; i++) {{     "
                        f"      emit(this.guid, this.lab_color_{color}[i] - target[i]);  "
                         "    }                                                          "
                         "  }                                                            "
                         "}                                                              "
        )

        reduce_func = Code( "function (key, values) {                   "
                            "  var total = 0;                           "
                            "  var i = 0;                               "
                            "  for (i = 0; i < values.length; i++) {    "
                            "    total = total + Math.pow(values[i],2); "
                            "  }                                        "
                            "  return Math.sqrt(total);                 "
                            "}                                          "
        )

        data = Wallpaper._get_collection() \
            .map_reduce(map_func, reduce_func, "myresults", scope={"target": target_lab_color})

        for entry in data.find({"value": {"$lt": score_threshold}}):
            result.append(entry['_id'])

    return result
