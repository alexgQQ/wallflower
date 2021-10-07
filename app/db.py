from uuid import uuid4

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, create_engine
from sqlalchemy.orm import relationship, sessionmaker, case
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


def create_session():
    engine = create_engine(f"sqlite://")
    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()


def default_uuid():
    return str(uuid4())


class WallpaperColor(Base):
    __tablename__ = "wallpaper_color"
    wallpaper_id = Column("wallpaper_id", Integer, ForeignKey("wallpapers.id"), primary_key=True, nullable=False)
    color_id = Column("color_id", Integer, ForeignKey("colors.id"), primary_key=True, nullable=False)
    rank = Column("rank", Integer, nullable=False)
    color = relationship("Color", back_populates="wallpapers")
    wallpaper = relationship("Wallpaper", back_populates="colors")


class Wallpaper(Base):
    __tablename__ = "wallpapers"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    guid = Column(String, default=default_uuid, nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    image_type = Column(String, nullable=False)
    dhash = Column(String)
    analyzed = Column(Boolean)
    colors = relationship("WallpaperColor", back_populates="wallpaper")

    @property
    def filename(self):
        return f'{self.guid}.{self.image_type}'


class Color(Base):
    __tablename__ = "colors"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    value = Column(String, nullable=False)
    wallpapers = relationship("WallpaperColor", back_populates="color")


def wallpapers_by_color(session, colors):
    return session.query(Wallpaper).join(Wallpaper.colors, WallpaperColor.color).filter(Color.value.in_(colors)).order_by(WallpaperColor.rank)


def all_colors(session):
    return [color.value for color in session.query(Color).all()]


def create_wallpaper(session, data, colors):
    wallpaper = Wallpaper(**data)
    for i, value in enumerate(colors):
        join = WallpaperColor(rank=i)
        color = Color(value=value)
        join.color = color
        wallpaper.colors.append(join)
        session.add(color)
    session.add(wallpaper)
    session.commit()
    return wallpaper
