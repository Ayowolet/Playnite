"""Filtering system for the game library."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session, Query

from ..database.models import Game, Tag, Category, Genre, Platform


def _like_escape(s: str) -> str:
    """Escape SQL LIKE wildcard characters in user-supplied strings."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


COMPLETION_STATUSES = [
    "not_played",
    "playing",
    "completed",
    "dropped",
    "plan_to_play",
    "on_hold",
]

SORT_FIELDS = [
    "name",
    "release_year",
    "playtime",
    "play_count",
    "added",
    "last_played",
    "user_score",
    "developer",
    "publisher",
    "completion_status",
]


@dataclass
class FilterSpec:
    """Specification for filtering games. All fields are optional."""

    platforms: Optional[List[str]] = None
    genres: Optional[List[str]] = None
    tags: Optional[List[str]] = None  # any of these tags (OR semantics)
    categories: Optional[List[str]] = None
    release_year_min: Optional[int] = None
    release_year_max: Optional[int] = None
    playtime_min: Optional[int] = None  # seconds
    playtime_max: Optional[int] = None  # seconds
    completion_statuses: Optional[List[str]] = None
    rating_min: Optional[int] = None  # 0-100
    rating_max: Optional[int] = None
    is_favorite: Optional[bool] = None
    is_hidden: Optional[bool] = None
    is_installed: Optional[bool] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "FilterSpec":
        valid = {k for k in cls.__dataclass_fields__}
        unknown = set(data) - valid
        if unknown:
            warnings.warn(
                f"FilterSpec.from_dict() ignoring unknown fields: {sorted(unknown)}",
                stacklevel=2,
            )
        return cls(**{k: v for k, v in data.items() if k in valid})


class FilterEngine:
    """Applies a FilterSpec to a SQLAlchemy Session query."""

    def build_query(self, session: Session, spec: FilterSpec, include_hidden: bool = False) -> Query:
        """Return a SQLAlchemy Query with all filters applied (does NOT execute)."""
        query = session.query(Game)

        if not include_hidden and spec.is_hidden is None:
            query = query.filter(Game.is_hidden == False)  # noqa: E712

        if spec.platforms:
            query = query.filter(Game.platforms.any(Platform.name.in_(spec.platforms)))

        if spec.genres:
            query = query.filter(Game.genres.any(Genre.name.in_(spec.genres)))

        if spec.tags:
            query = query.filter(Game.tags.any(Tag.name.in_(spec.tags)))

        if spec.categories:
            query = query.filter(Game.categories.any(Category.name.in_(spec.categories)))

        if spec.release_year_min is not None:
            query = query.filter(Game.release_year >= spec.release_year_min)

        if spec.release_year_max is not None:
            query = query.filter(Game.release_year <= spec.release_year_max)

        if spec.playtime_min is not None:
            query = query.filter(Game.playtime >= spec.playtime_min)

        if spec.playtime_max is not None:
            query = query.filter(Game.playtime <= spec.playtime_max)

        if spec.completion_statuses:
            query = query.filter(Game.completion_status.in_(spec.completion_statuses))

        if spec.rating_min is not None:
            query = query.filter(Game.user_score >= spec.rating_min)

        if spec.rating_max is not None:
            query = query.filter(Game.user_score <= spec.rating_max)

        if spec.is_favorite is not None:
            query = query.filter(Game.is_favorite == spec.is_favorite)

        if spec.is_hidden is not None:
            query = query.filter(Game.is_hidden == spec.is_hidden)

        if spec.is_installed is not None:
            query = query.filter(Game.is_installed == spec.is_installed)

        if spec.developer:
            query = query.filter(
                Game.developer.ilike(f"%{_like_escape(spec.developer)}%", escape="\\")
            )

        if spec.publisher:
            query = query.filter(
                Game.publisher.ilike(f"%{_like_escape(spec.publisher)}%", escape="\\")
            )

        return query

    def apply(self, session: Session, spec: FilterSpec, include_hidden: bool = False) -> List[Game]:
        """Return games matching *spec*. Kept for backward compatibility."""
        return self.build_query(session, spec, include_hidden=include_hidden).all()
