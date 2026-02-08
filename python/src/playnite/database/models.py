"""SQLAlchemy ORM models for the Playnite game library."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# Association tables for many-to-many relationships
game_tags = Table(
    "game_tags",
    Base.metadata,
    Column("game_id", String(36), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

game_categories = Table(
    "game_categories",
    Base.metadata,
    Column("game_id", String(36), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", String(36), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)

game_genres = Table(
    "game_genres",
    Base.metadata,
    Column("game_id", String(36), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", String(36), ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)

game_platforms = Table(
    "game_platforms",
    Base.metadata,
    Column("game_id", String(36), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("platform_id", String(36), ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True),
)


class Game(Base):
    """Represents a game in the library."""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "completion_status IN ('not_played','playing','completed','dropped','plan_to_play','on_hold')",
            name="ck_game_completion_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(500), nullable=False, index=True)
    description = Column(Text)
    release_year = Column(Integer, index=True)
    developer = Column(String(200), index=True)
    publisher = Column(String(200))
    playtime = Column(Integer, default=0, index=True)  # seconds
    play_count = Column(Integer, default=0)
    last_played = Column(DateTime)
    added = Column(DateTime, default=lambda: datetime.now())
    modified = Column(DateTime, default=lambda: datetime.now())
    user_score = Column(Integer, index=True)  # 0-100
    community_score = Column(Integer)
    critic_score = Column(Integer)
    completion_status = Column(String(50), default="not_played", index=True)
    is_favorite = Column(Boolean, default=False, index=True)
    is_hidden = Column(Boolean, default=False, index=True)
    is_installed = Column(Boolean, default=False)
    notes = Column(Text)
    cover_image = Column(String(500))
    sort_name = Column(String(500), index=True)  # override for custom sort order

    tags = relationship("Tag", secondary=game_tags, back_populates="games")
    categories = relationship("Category", secondary=game_categories, back_populates="games")
    genres = relationship("Genre", secondary=game_genres, back_populates="games")
    platforms = relationship("Platform", secondary=game_platforms, back_populates="games")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "release_year": self.release_year,
            "developer": self.developer,
            "publisher": self.publisher,
            "playtime": self.playtime,
            "play_count": self.play_count,
            "last_played": self.last_played.isoformat() if self.last_played is not None else None,
            "added": self.added.isoformat() if self.added is not None else None,
            "modified": self.modified.isoformat() if self.modified is not None else None,
            "user_score": self.user_score,
            "community_score": self.community_score,
            "critic_score": self.critic_score,
            "completion_status": self.completion_status,
            "is_favorite": self.is_favorite,
            "is_hidden": self.is_hidden,
            "is_installed": self.is_installed,
            "notes": self.notes,
            "cover_image": self.cover_image,
            "tags": [t.name for t in self.tags],
            "categories": [c.name for c in self.categories],
            "genres": [g.name for g in self.genres],
            "platforms": [p.name for p in self.platforms],
        }


class Tag(Base):
    __tablename__ = "tags"

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(200), unique=True, nullable=False, index=True)
    games = relationship("Game", secondary=game_tags, back_populates="tags")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


class Category(Base):
    __tablename__ = "categories"

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(200), unique=True, nullable=False, index=True)
    games = relationship("Game", secondary=game_categories, back_populates="categories")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


class Genre(Base):
    __tablename__ = "genres"

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(200), unique=True, nullable=False, index=True)
    games = relationship("Game", secondary=game_genres, back_populates="genres")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(200), unique=True, nullable=False, index=True)
    games = relationship("Game", secondary=game_platforms, back_populates="platforms")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


class SmartCollection(Base):
    """A collection whose membership is determined by rules evaluated at query time.

    ``rules`` is a JSON list of rule dicts with keys:

    - ``field``: one of tag_names, genre_names, platform_names, category_names,
      name, release_year, playtime, completion_status, developer, publisher, user_score
    - ``operator``: equals, not_equals, contains, not_contains, gt, lt, gte, lte,
      in, not_in, is_true, is_false
    - ``value``: the comparison value

    Example::

        [{"field": "genre_names", "operator": "contains", "value": "RPG"},
         {"field": "playtime", "operator": "gte", "value": 3600}]
    """

    __tablename__ = "smart_collections"
    __table_args__ = (
        CheckConstraint("logic IN ('AND','OR')", name="ck_smartcollection_logic"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(200), unique=True, nullable=False, index=True)
    rules = Column(JSON, nullable=False, default=lambda: [])
    logic = Column(String(3), default="AND")  # AND | OR
    description = Column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "rules": self.rules,
            "logic": self.logic,
            "description": self.description,
        }


class ViewPreset(Base):
    """A named, saved view configuration (sort, group, filter, layout)."""

    __tablename__ = "view_presets"
    __table_args__ = (
        CheckConstraint("sort_order IN ('asc','desc')", name="ck_viewpreset_sort_order"),
        CheckConstraint("view_type IN ('list','grid')", name="ck_viewpreset_view_type"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    name = Column(String(200), unique=True, nullable=False, index=True)
    sort_by = Column(String(100), default="name")
    sort_order = Column(String(4), default="asc")
    group_by = Column(String(100))
    view_type = Column(String(10), default="list")  # list | grid
    filters = Column(JSON, default=lambda: {})
    columns = Column(JSON, default=lambda: [])  # ordered list of visible column names

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "group_by": self.group_by,
            "view_type": self.view_type,
            "filters": self.filters,
            "columns": self.columns,
        }
