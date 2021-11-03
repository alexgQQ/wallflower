from uuid import uuid4

from app.config import get_config
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, create_engine
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()
config = get_config()

def _create_engine():
    db_file = config["Core"]["DatabaseLocation"]
    return create_engine(f"sqlite:///{db_file}")


def create_session():
    engine = _create_engine()
    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()


def create_tables():
    engine = _create_engine()
    Base.metadata.create_all(engine)


def default_uuid():
    return str(uuid4())


class WallpaperColor(Base):
    __tablename__ = "wallpaper_color"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    wallpaper_id = Column("wallpaper_id", Integer, ForeignKey("wallpapers.id"), nullable=False)
    color_value = Column(String, nullable=False)
    rank = Column("rank", Integer, nullable=False)
    wallpaper = relationship("Wallpaper", back_populates="colors")


class Wallpaper(Base):
    __tablename__ = "wallpapers"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    source_url = Column(String, nullable=False)
    dhash = Column(String, nullable=True)
    guid = Column(String, default=default_uuid, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    image_type = Column(String, nullable=False)
    analyzed = Column(Boolean, nullable=False)
    colors = relationship("WallpaperColor", back_populates="wallpaper")

    @property
    def filename(self):
        return f'{self.guid}.{self.image_type}'


def all_wallpapers(session, limit):
    return [color for color in session.query(Wallpaper).limit(limit).all()]


def wallpapers_by_color(session, colors):
    return session.query(Wallpaper).join(Wallpaper.colors).filter(WallpaperColor.color_value.in_(colors)).order_by(WallpaperColor.rank)


def all_colors(session):
    return [color.color_value for color in session.query(WallpaperColor).all()]


def bulk_update_wallpapers(session, mappings):
    session.bulk_update_mappings(Wallpaper, mappings)
    session.commit()


def bulk_insert_wallpapers(session, mappings):
    session.bulk_insert_mappings(Wallpaper, mappings)
    session.commit()


def bulk_insert_colors(session, wallpaper_to_colors):
    mappings = []
    for wallpaper_id, colors in wallpaper_to_colors.items():
        for rank, color_value in enumerate(colors):
            mappings.append({
                "color_value": color_value,
                "rank": rank,
                "wallpaper_id": wallpaper_id,
            })
    session.bulk_insert_mappings(WallpaperColor, mappings)
    session.commit()


def create_wallpaper(session, data, colors=None):
    wallpaper = Wallpaper(**data)
    if colors:
        for i, value in enumerate(colors):
            join = WallpaperColor(rank=i, color_value=value)
            wallpaper.colors.append(join)
    session.add(wallpaper)
    session.commit()
    return wallpaper
