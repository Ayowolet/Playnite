"""Global action profiles: apply the same set of actions to games matching criteria."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from playnite_py.models.action import GameAction
from playnite_py.models.game import Game
from playnite_py.models.database import GameDatabase


@dataclass
class ProfileCriteria:
    """Criteria for matching games to a profile."""
    platform_ids: list[str] = field(default_factory=list)
    genre_ids: list[str] = field(default_factory=list)
    tag_ids: list[str] = field(default_factory=list)
    category_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    name_pattern: str = ""
    is_installed: bool | None = None

    def matches(self, game: Game) -> bool:
        """Check whether a game matches all specified criteria."""
        if self.platform_ids:
            if not any(pid in game.platform_ids for pid in self.platform_ids):
                return False
        if self.genre_ids:
            if not any(gid in game.genre_ids for gid in self.genre_ids):
                return False
        if self.tag_ids:
            if not any(tid in game.tag_ids for tid in self.tag_ids):
                return False
        if self.category_ids:
            if not any(cid in game.category_ids for cid in self.category_ids):
                return False
        if self.sources:
            if game.source not in self.sources:
                return False
        if self.name_pattern:
            import re
            if not re.search(self.name_pattern, game.name, re.IGNORECASE):
                return False
        if self.is_installed is not None:
            if game.is_installed != self.is_installed:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        d: dict[str, Any] = {}
        if self.platform_ids:
            d["platform_ids"] = self.platform_ids
        if self.genre_ids:
            d["genre_ids"] = self.genre_ids
        if self.tag_ids:
            d["tag_ids"] = self.tag_ids
        if self.category_ids:
            d["category_ids"] = self.category_ids
        if self.sources:
            d["sources"] = self.sources
        if self.name_pattern:
            d["name_pattern"] = self.name_pattern
        if self.is_installed is not None:
            d["is_installed"] = self.is_installed
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileCriteria:
        """Deserialize from a dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ActionProfile:
    """A profile that applies a set of actions to all games matching criteria."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    criteria: ProfileCriteria = field(default_factory=ProfileCriteria)
    action_templates: list[dict[str, Any]] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "criteria": self.criteria.to_dict(),
            "action_templates": self.action_templates,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionProfile:
        """Deserialize from a dictionary."""
        d = dict(data)
        if "criteria" in d:
            d["criteria"] = ProfileCriteria.from_dict(d["criteria"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ProfileManager:
    """Manages action profiles and applies them to matching games."""

    def __init__(self, database: GameDatabase):
        self._db = database
        self._profiles: dict[str, ActionProfile] = {}

    def create_profile(
        self,
        name: str,
        criteria: dict[str, Any],
        action_templates: list[dict[str, Any]],
        description: str = "",
    ) -> ActionProfile:
        """Create and register a new action profile."""
        profile = ActionProfile(
            name=name,
            description=description,
            criteria=ProfileCriteria.from_dict(criteria),
            action_templates=action_templates,
        )
        self._profiles[profile.id] = profile
        return profile

    def remove_profile(self, profile_id: str) -> bool:
        """Remove a profile by ID and return whether it existed."""
        return self._profiles.pop(profile_id, None) is not None

    def get_profile(self, profile_id: str) -> ActionProfile | None:
        """Return a profile by ID, or None if not found."""
        return self._profiles.get(profile_id)

    def get_all_profiles(self) -> list[dict[str, Any]]:
        """Return all registered profiles as dictionaries."""
        return [p.to_dict() for p in self._profiles.values()]

    def apply_profiles(self, game: Game) -> list[GameAction]:
        """Find profiles matching a game and inject their actions."""
        injected: list[GameAction] = []
        for profile in self._profiles.values():
            if not profile.enabled:
                continue
            if not profile.criteria.matches(game):
                continue
            for tmpl in profile.action_templates:
                action = GameAction.from_dict({
                    **tmpl,
                    "game_id": game.id,
                    "source_script_id": f"profile:{profile.id}",
                })
                self._db.add_action(action)
                injected.append(action)
        return injected

    def get_matching_games(self, profile_id: str) -> list[dict[str, Any]]:
        """List all games that match a profile's criteria."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return []
        return [
            g.to_dict()
            for g in self._db.get_all_games()
            if profile.criteria.matches(g)
        ]
