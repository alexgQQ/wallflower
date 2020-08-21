import os
from playhouse.migrate import SqliteMigrator, migrate
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

from .utils import hex_to_lab


database_loc = os.environ.get('DATABASE_LOCATION')
database = SqliteDatabase(database_loc)


def handle_migration():
    '''
    Define migration operations to apply to the database
    PeeWee Reference: http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#schema-migrations
    '''
    migrator = SqliteMigrator(database)
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
        database = database

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
            'extension': self.extension,
        }
        colors = [] if not self.top_colors else self.top_colors.split(',')
        i = -1
        for i, color in enumerate(colors):
            data.update({f'top_color_{i}': list(hex_to_lab(color)[0,0,:])})
        while i < 9:
            i += 1
            data.update({f'top_color_{i}': [0.0, 0.0, 0.0]})

        return index, data


database.create_tables([Wallpaper])


def bulk_update_db_entries(
    models_to_update: list, update_data: dict, batch_size: int = 50, key_field: str = 'id'):
    '''
    Update Wallpaper db entries in a bulk fashion. Provide a list of model instances to update and a dict of
    data to match using the 'key_field' to match between models.
    '''

    assert len(models_to_update) == len(update_data), 'models_to_update and update_data must be the same length'
    fields_to_update = update_data[list(update_data.keys())[0]].keys()
    for model in models_to_update:
        values = update_data[getattr(model, key_field)]
        for attr in fields_to_update:
            setattr(model, attr, values.get(attr))
    Wallpaper.bulk_update(models_to_update, fields=fields_to_update, batch_size=batch_size)
