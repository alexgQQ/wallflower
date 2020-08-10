import os
from peewee import (
    SqliteDatabase,
    Model,
    CharField,
    DateField,
    FloatField,
    IntegerField,
    BooleanField,
    TextField,
)
from playhouse.migrate import SqliteMigrator, migrate

from .utils import hex_to_lab


db_loc = os.environ.get('DATABASE_LOCATION')
db = SqliteDatabase(db_loc)


def handle_migration():
    migrator = SqliteMigrator(db)
    migrate(
        migrator.rename_column('wallpaper', 'reddit_id', 'source_id')
    )


class Wallpaper(Model):

    guid = CharField()
    url = CharField(null=True)
    source_id = IntegerField(null=True)
    downloaded = BooleanField()
    top_colors = TextField(null=True)
    top_labels = TextField(null=True)
    extension = CharField()
    analyzed = BooleanField()
    source_type = CharField(null=True)
    dhash = CharField(null=True)
    duplicate = BooleanField(default=False)
    size_in_bytes = IntegerField(null=True)

    class Meta:
        database = db

    def elastic_model(self):
        '''
        Create a data model for this database entry to be uploaded to elasticsearch.
        '''
        index = {
            '_id': self.id,
        }
        data = {
            'top_labels': self.top_labels,
            'searchable': True,
            'url': self.url,
        }
        colors = [] if not self.top_colors else self.top_colors.split(',')
        i = -1
        for i, color in enumerate(colors):
            data.update({f'top_color_{i}': list(hex_to_lab(color)[0,0,:])})
        while i < 9:
            i += 1
            data.update({f'top_color_{i}': [0.0, 0.0, 0.0]})

        return index, data


db.create_tables([Wallpaper])
