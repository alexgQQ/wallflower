from typing import Dict, List, Optional, Tuple, TypedDict

from sqlalchemy import REAL, Boolean, Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Query, relationship, sessionmaker
from sqlalchemy.sql.expression import cast

from app.config import config

Base = declarative_base()


def _create_engine():
    return create_engine(f"sqlite:///{config.core.db_loc}")


def create_session():
    engine = _create_engine()
    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()


def create_tables():
    engine = _create_engine()
    Base.metadata.create_all(engine)


class WallpaperColor(Base):
    __tablename__ = "wallpaper_color"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    wallpaper_id = Column(
        "wallpaper_id", Integer, ForeignKey("wallpapers.id"), nullable=False
    )
    color_value = Column(Integer, nullable=False)
    rank = Column("rank", Integer, nullable=False)
    wallpaper = relationship("Wallpaper", back_populates="colors")


class WallpaperTag(Base):
    __tablename__ = "wallpaper_tags"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    wallpaper_id = Column(
        "wallpaper_id", Integer, ForeignKey("wallpapers.id"), nullable=False
    )
    tag = Column(String, nullable=False)
    wallpaper = relationship("Wallpaper", back_populates="tags")


# TODO: Should I make the type fields enums or choice fields?
class Wallpaper(Base):
    __tablename__ = "wallpapers"
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    source_uri = Column(String, nullable=False)
    dhash = Column(String, nullable=True)
    file_ctime = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    image_type = Column(String, nullable=False)
    analyzed = Column(Boolean, nullable=False)
    duplicate = Column(Boolean, nullable=False, default=False)
    colors = relationship("WallpaperColor", back_populates="wallpaper")
    tags = relationship("WallpaperTag", back_populates="wallpaper")

    @property
    def filename(self) -> str:
        return f"{self.source_id}.{self.image_type}"

    @property
    def src_path(self) -> str:
        if self.source_type == "local":
            return f"{self.source_uri}/{self.filename}"
        else:
            return self.source_uri

    @property
    def download_path(self) -> str:
        return f"{config.core.download_loc}/{self.filename}"


class QueryDict(TypedDict):
    # TODO: Update python ver to allow | syntax!
    # Also its unclear if order matters with the query calls
    # especially with the join on color search
    #  OrderedDict ¯\_(ツ)_/¯
    ids: Optional[List[int]]
    colors: Optional[List[int]]
    source_types: Optional[List[str]]
    aspect_ratio: Optional[float]
    tags: Optional[List[str]]


class WallpaperQuery:
    """Helper class to handle varying combinations of queries"""

    def __init__(self, query_data: QueryDict):
        self.query = Query([Wallpaper])

        for key, value in query_data.items():
            if value is None:
                continue
            func = getattr(self, f"by_{key}")
            self.query = func(value)

    def by_colors(self, colors: List[int]) -> Query:
        return (
            self.query.join(Wallpaper.colors)
            .filter(WallpaperColor.color_value.in_(colors))
            .order_by(WallpaperColor.rank)
        )

    def by_ids(self, ids: List[int]) -> Query:
        return self.query.filter(Wallpaper.id.in_(ids))

    def by_source_types(self, source_types: List[str]) -> Query:
        return self.query.filter(Wallpaper.source_type.in_(source_types))

    def by_aspect_ratio(self, aspect_ratio: float) -> Query:
        # Cast one value to promote filter to a float type
        # TODO: this may cause precision issues as 16:9 = 1.77777777777
        # and depending on rounding something like 1.78 may get missed
        return self.query.filter(
            (cast(Wallpaper.width, REAL) / Wallpaper.height) == aspect_ratio
        )

    def by_tags(self, tags: List[str]) -> Query:
        return (
            self.query.join(Wallpaper.tags)
            .filter(WallpaperTag.tag.in_(tags))
        )

    def __call__(self, limit: int = 10) -> List[Wallpaper]:
        with create_session() as session:
            return (
                self.query.with_session(session)
                .filter(Wallpaper.duplicate == False)
                .limit(limit)
                .all()
            )


def all_local_wallpapers(limit: int) -> List[Wallpaper]:
    with create_session() as session:
        query = (
            session.query(Wallpaper)
            .filter(Wallpaper.source_type == "local")
            .limit(limit)
            .all()
        )
    return query


# TODO: I'd like some way to handle client paging instead
# of gathering source ids to check against when pulling images.
# This is tricky because each api has its own rules/paradigms for paging
# but possibly I could store a `cursor` value to track where each source is?
def source_ids_by_type(source_type: str) -> Tuple[str]:
    with create_session() as session:
        query = (
            session.query(Wallpaper.source_id)
            .filter(Wallpaper.source_type == source_type)
            .all()
        )
    return tuple(entry[0] for entry in query)


def wallpaper_by_id(_id: int) -> Wallpaper:
    with create_session() as session:
        query = session.query(Wallpaper).filter(Wallpaper.id == _id)
    return query.one()


# TODO: Query limits exist, I'm not sure what it would be here
# but if the colors get large enough it may fail
def all_colors() -> List[Tuple[int]]:
    with create_session() as session:
        query = session.query(WallpaperColor.color_value).distinct().all()
    return query


class InsertMapping(TypedDict):
    source_type: str
    source_id: str
    source_uri: str
    image_type: str
    analyzed: bool


class UpdateMapping(TypedDict):
    id: int
    dhash: str
    width: int
    height: int
    analyzed: bool


def bulk_insert_wallpapers(mappings: List[InsertMapping]):
    with create_session() as session:
        session.bulk_insert_mappings(Wallpaper, mappings)
        session.commit()


def bulk_update_wallpapers(mappings: List[UpdateMapping]):
    with create_session() as session:
        session.bulk_update_mappings(Wallpaper, mappings)
        session.commit()


def bulk_insert_colors(wallpaper_to_colors: Dict[int, List[int]]):
    with create_session() as session:
        mappings = []
        for wallpaper_id, colors in wallpaper_to_colors.items():
            for rank, color_value in enumerate(colors):
                mappings.append(
                    {
                        "color_value": color_value,
                        "rank": rank,
                        "wallpaper_id": wallpaper_id,
                    }
                )
        session.bulk_insert_mappings(WallpaperColor, mappings)
        session.commit()


def bulk_insert_tags(wallpaper_to_tags: Dict[int, List[str]]):
    with create_session() as session:
        mappings = []
        for wallpaper_id, tags in wallpaper_to_tags.items():
            for tag in tags:
                mappings.append(
                    {
                        "tag": tag,
                        "wallpaper_id": wallpaper_id,
                    }
                )
        session.bulk_insert_mappings(WallpaperTag, mappings)
        session.commit()


def set_duplicate(ids: List[int]):
    with create_session() as session:
        session.query(Wallpaper).filter(Wallpaper.id.in_(ids)).update(
            {Wallpaper.duplicate: True}
        )
        session.commit()


# TODO: This is only used in tests, remove?
def create_wallpaper(data, colors=None):
    with create_session() as session:
        wallpaper = Wallpaper(**data)
        if colors:
            for i, value in enumerate(colors):
                join = WallpaperColor(rank=i, color_value=value)
                wallpaper.colors.append(join)
        session.add(wallpaper)
        session.commit()
    return wallpaper
