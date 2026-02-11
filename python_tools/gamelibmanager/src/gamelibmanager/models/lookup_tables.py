"""Lookup table entities mirroring C# Playnite SDK models.

In Playnite, Company, Genre, Tag, Category, etc. are all simple
``{Id, Name}`` entities inheriting from ``DatabaseObject``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import DatabaseObject


@dataclass(slots=True)
class Platform(DatabaseObject):
    specification_id: str = ""
    icon: str = ""
    cover: str = ""
    background: str = ""


@dataclass(slots=True)
class Genre(DatabaseObject):
    pass


@dataclass(slots=True)
class Company(DatabaseObject):
    pass


@dataclass(slots=True)
class Tag(DatabaseObject):
    pass


@dataclass(slots=True)
class Category(DatabaseObject):
    pass


@dataclass(slots=True)
class GameFeature(DatabaseObject):
    pass


@dataclass(slots=True)
class GameSource(DatabaseObject):
    pass


@dataclass(slots=True)
class Series(DatabaseObject):
    pass


@dataclass(slots=True)
class AgeRating(DatabaseObject):
    pass


@dataclass(slots=True)
class Region(DatabaseObject):
    pass


@dataclass(slots=True)
class CompletionStatus(DatabaseObject):
    pass
