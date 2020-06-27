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
        migrator.add_column('wallpaper', 'duplicate', BooleanField(default=False))
    )


class Wallpaper(Model):
    guid = CharField()
    url = CharField(null=True)
    reddit_id = IntegerField(null=True)
    downloaded = BooleanField()
    top_colors = TextField(null=True)
    top_labels = TextField(null=True)
    extension = CharField()
    analyzed = BooleanField()
    source_type = CharField(null=True)
    dhash = CharField(null=True)
    duplicate = BooleanField(default=False)

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
            'top_color_0': list(hex_to_lab(self.top_colors.split(',')[0])[0,0,:]) if self.top_colors else '',
            'top_color_1': list(hex_to_lab(self.top_colors.split(',')[1])[0,0,:]) if self.top_colors else '',
            'top_color_2': list(hex_to_lab(self.top_colors.split(',')[2])[0,0,:]) if self.top_colors else '',
            'top_labels': self.top_labels,
            'searchable': True,
            'guid': self.guid,
            'extension': self.extension,
        }
        return index, data


db.create_tables([Wallpaper])
