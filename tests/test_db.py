import pytest

from random import choice, randint
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from app.db import Base, wallpapers_by_color, create_wallpaper


fake = Faker()


@pytest.fixture(scope="session")
def connection():
    return create_engine(f"sqlite://").connect()


@pytest.fixture(scope="session")
def setup_database(connection):
    Base.metadata.bind = connection
    Base.metadata.create_all()
    
    yield

    Base.metadata.drop_all()


@pytest.fixture
def db_session(setup_database, connection):
    transaction = connection.begin()
    yield scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=connection)
    )
    transaction.rollback()


def mock_wallpaper_data():
    return {
        "source_type": fake.word(),
        "source_id": fake.md5(),
        "source_url": fake.image_url(),
        "width": fake.random_int(),
        "height": fake.random_int(),
        "dhash": fake.md5(),
        "image_type": choice(('png', 'jpg', 'jpeg')),
    }


def test_create_wallpaper(db_session):
    """
    Test creation of a wallpaper entry and associated colors
    """
    data = mock_wallpaper_data()
    colors = tuple(fake.color() for color in range(10))
    wallpaper = create_wallpaper(db_session, data, colors)
    assert wallpaper.guid
    for expected, created in zip(colors, (obj.color.value for obj in wallpaper.colors)):
        assert expected == created


def test_wallpapers_by_color(db_session):
    """
    Test for querying a set of wallpapers by their related colors ordered by the color rank
    """

    num_of_colors = 10
    test_colors = []
    test_ranks = []
    test_guids = []

    for i in range(5):
        colors = tuple(fake.color() for _ in range(num_of_colors))
        while (rank := randint(0, num_of_colors - 1)) in test_ranks:
            pass
        test_ranks.append(rank)
        test_colors.append(colors[rank])
        wallpaper = mock_wallpaper_data()
        wallpaper = create_wallpaper(db_session, wallpaper, colors)
        test_guids.append(wallpaper.guid)

    for _ in range(2):
        index = randint(0, len(test_ranks) - 1)
        test_ranks.pop(index)
        test_colors.pop(index) 
        test_guids.pop(index) 

    ordered_guids = tuple(zip(*sorted(zip(test_guids, test_ranks), key=lambda x: x[1])))[0]

    results = wallpapers_by_color(db_session, test_colors)

    for entry, guid in zip(results.all(), ordered_guids):
        assert entry.guid == guid


def test_all_colors(db_session):
    pass
