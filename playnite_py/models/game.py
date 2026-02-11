"""Core game data models mirroring Playnite's game database schema."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class CompletionStatus(Enum):
    NOT_PLAYED = "not_played"
    PLAYING = "playing"
    BEATEN = "beaten"
    COMPLETED = "completed"
    SHELVED = "shelved"
    ABANDONED = "abandoned"


def _new_id() -> str:
    return str(uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Metadata entity types
# ---------------------------------------------------------------------------

@dataclass
class Platform:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Platform:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Genre:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Genre:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Developer:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Developer:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Publisher:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Publisher:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Tag:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Tag:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Category:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Category:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Feature:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Feature:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Series:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Series:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class AgeRating:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> AgeRating:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Region:
    id: str = field(default_factory=_new_id)
    name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> Region:
        """Deserialize from a dictionary."""
        return cls(id=data.get("id", _new_id()), name=data.get("name", ""))


@dataclass
class Link:
    name: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {"name": self.name, "url": self.url}

    @classmethod
    def from_dict(cls, data: dict) -> Link:
        """Deserialize from a dictionary."""
        return cls(name=data.get("name", ""), url=data.get("url", ""))


# ---------------------------------------------------------------------------
# Main Game model
# ---------------------------------------------------------------------------

@dataclass
class Game:
    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    platform_ids: list[str] = field(default_factory=list)
    genre_ids: list[str] = field(default_factory=list)
    developer_ids: list[str] = field(default_factory=list)
    publisher_ids: list[str] = field(default_factory=list)
    tag_ids: list[str] = field(default_factory=list)
    category_ids: list[str] = field(default_factory=list)
    feature_ids: list[str] = field(default_factory=list)
    series_ids: list[str] = field(default_factory=list)
    release_date: str | None = None
    links: list[Link] = field(default_factory=list)
    is_installed: bool = False
    install_directory: str = ""
    source: str = ""
    completion_status: CompletionStatus = CompletionStatus.NOT_PLAYED
    playtime: int = 0  # seconds
    play_count: int = 0
    last_activity: str | None = None
    added: str = field(default_factory=_now_iso)
    modified: str = field(default_factory=_now_iso)
    version: str = ""
    user_score: int | None = None
    critic_score: int | None = None
    community_score: int | None = None
    cover_image: str = ""
    background_image: str = ""
    icon: str = ""
    notes: str = ""
    hidden: bool = False
    favorite: bool = False
    # Script-injected actions stored by ID reference
    action_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "platform_ids": list(self.platform_ids),
            "genre_ids": list(self.genre_ids),
            "developer_ids": list(self.developer_ids),
            "publisher_ids": list(self.publisher_ids),
            "tag_ids": list(self.tag_ids),
            "category_ids": list(self.category_ids),
            "feature_ids": list(self.feature_ids),
            "series_ids": list(self.series_ids),
            "release_date": self.release_date,
            "links": [link.to_dict() for link in self.links],
            "is_installed": self.is_installed,
            "install_directory": self.install_directory,
            "source": self.source,
            "completion_status": self.completion_status.value,
            "playtime": self.playtime,
            "play_count": self.play_count,
            "last_activity": self.last_activity,
            "added": self.added,
            "modified": self.modified,
            "version": self.version,
            "user_score": self.user_score,
            "critic_score": self.critic_score,
            "community_score": self.community_score,
            "cover_image": self.cover_image,
            "background_image": self.background_image,
            "icon": self.icon,
            "notes": self.notes,
            "hidden": self.hidden,
            "favorite": self.favorite,
            "action_ids": list(self.action_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Game:
        """Deserialize from a dictionary."""
        d = dict(data)
        d["links"] = [Link.from_dict(l) for l in d.get("links", [])]
        status = d.get("completion_status", "not_played")
        if isinstance(status, str):
            d["completion_status"] = CompletionStatus(status)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def clone(self) -> Game:
        """Return a deep copy."""
        return copy.deepcopy(self)
