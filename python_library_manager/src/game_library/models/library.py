"""
Library model: a named collection of games plus all reference entities
(platforms, companies, genres, etc.) needed to resolve relationship IDs.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .game import Game
from ..utils.text_utils import nfc_lower


@dataclass(slots=True)
class NamedEntity:
    """Generic named entity (platform, company, genre, tag, source, …)."""

    Id: str = field(default_factory=lambda: str(uuid.uuid4()))
    Name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"Id": self.Id, "Name": self.Name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NamedEntity":
        return cls(Id=data.get("Id", str(uuid.uuid4())), Name=data.get("Name", ""))


@dataclass(slots=True)
class LibrarySource:
    """Metadata about the origin of a library (e.g. one Playnite instance)."""

    name: str
    path: str = ""
    priority: int = 99  # lower = higher priority in duplicate resolution


@dataclass
class Library:
    """
    In-memory game library.

    Stores games plus all reference lookup tables so that relationship IDs can
    be resolved to human-readable names.
    """

    source: LibrarySource = field(default_factory=lambda: LibrarySource(name="default"))
    games: dict[str, Game] = field(default_factory=dict)  # keyed by Game.Id

    # Reference lookup tables
    platforms: dict[str, NamedEntity] = field(default_factory=dict)
    companies: dict[str, NamedEntity] = field(default_factory=dict)
    genres: dict[str, NamedEntity] = field(default_factory=dict)
    categories: dict[str, NamedEntity] = field(default_factory=dict)
    tags: dict[str, NamedEntity] = field(default_factory=dict)
    series: dict[str, NamedEntity] = field(default_factory=dict)
    sources: dict[str, NamedEntity] = field(default_factory=dict)
    age_ratings: dict[str, NamedEntity] = field(default_factory=dict)
    regions: dict[str, NamedEntity] = field(default_factory=dict)
    completion_statuses: dict[str, NamedEntity] = field(default_factory=dict)

    # ── Mutation helpers ─────────────────────────────────────────────────────

    def add_game(self, game: Game) -> None:
        self.resolve_game(game)
        self.games[game.Id] = game

    def remove_game(self, game_id: str) -> Optional[Game]:
        return self.games.pop(game_id, None)

    def get_game(self, game_id: str) -> Optional[Game]:
        return self.games.get(game_id)

    def all_games(self) -> list[Game]:
        return list(self.games.values())

    # ── Reference resolution ─────────────────────────────────────────────────

    def resolve_game(self, game: Game) -> None:
        """Populate a game's ``_resolved_*`` attributes from lookup tables."""
        game._source_name = self.sources.get(game.SourceId, NamedEntity()).Name if game.SourceId else ""
        game._platform_names = [self.platforms[pid].Name for pid in game.PlatformIds if pid in self.platforms]
        game._developer_names = [self.companies[did].Name for did in game.DeveloperIds if did in self.companies]
        game._publisher_names = [self.companies[pid].Name for pid in game.PublisherIds if pid in self.companies]
        game._genre_names = [self.genres[gid].Name for gid in game.GenreIds if gid in self.genres]
        game._category_names = [self.categories[cid].Name for cid in game.CategoryIds if cid in self.categories]
        game._tag_names = [self.tags[tid].Name for tid in game.TagIds if tid in self.tags]

    def resolve_all(self) -> None:
        for game in self.games.values():
            self.resolve_game(game)

    # ── Lookup helpers ───────────────────────────────────────────────────────

    def _get_or_create_entity(self, table: dict[str, NamedEntity], name: str) -> str:
        """Return existing entity ID by name or create and return a new one."""
        for eid, entity in table.items():
            if nfc_lower(entity.Name) == nfc_lower(name):
                return eid
        new_id = str(uuid.uuid4())
        table[new_id] = NamedEntity(Id=new_id, Name=name)
        return new_id

    def get_or_create_platform(self, name: str) -> str:
        return self._get_or_create_entity(self.platforms, name)

    def get_or_create_company(self, name: str) -> str:
        return self._get_or_create_entity(self.companies, name)

    def get_or_create_genre(self, name: str) -> str:
        return self._get_or_create_entity(self.genres, name)

    def get_or_create_category(self, name: str) -> str:
        return self._get_or_create_entity(self.categories, name)

    def get_or_create_source(self, name: str) -> str:
        return self._get_or_create_entity(self.sources, name)

    # ── Statistics ───────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        games = self.all_games()
        return {
            "total_games": len(games),
            "installed": sum(1 for g in games if g.IsInstalled),
            "hidden": sum(1 for g in games if g.Hidden),
            "favorites": sum(1 for g in games if g.Favorite),
            "total_playtime_hours": round(sum(g.Playtime for g in games) / 3600, 1),
            "platforms": len(self.platforms),
            "sources": len(self.sources),
        }
