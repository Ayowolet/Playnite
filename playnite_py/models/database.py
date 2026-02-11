"""In-memory game database with JSON file persistence and event callbacks."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from playnite_py.models.game import (
    AgeRating, Category, Developer, Feature, Game, Genre,
    Link, Platform, Publisher, Region, Series, Tag,
)
from playnite_py.models.action import GameAction


class GameDatabase:
    """Central game database with CRUD, querying, persistence, and events."""

    def __init__(self, path: str | None = None):
        self._path = path
        self._lock = threading.RLock()

        # Primary collections
        self._games: dict[str, Game] = {}
        self._actions: dict[str, GameAction] = {}

        # Metadata collections
        self._platforms: dict[str, Platform] = {}
        self._genres: dict[str, Genre] = {}
        self._developers: dict[str, Developer] = {}
        self._publishers: dict[str, Publisher] = {}
        self._tags: dict[str, Tag] = {}
        self._categories: dict[str, Category] = {}
        self._features: dict[str, Feature] = {}
        self._series: dict[str, Series] = {}
        self._age_ratings: dict[str, AgeRating] = {}
        self._regions: dict[str, Region] = {}

        # Event callbacks
        self.on_game_added: list[Callable[[Game], None]] = []
        self.on_game_updated: list[Callable[[Game, Game], None]] = []
        self.on_game_removed: list[Callable[[Game], None]] = []
        self.on_action_added: list[Callable[[GameAction], None]] = []
        self.on_action_removed: list[Callable[[GameAction], None]] = []

        if self._path and os.path.exists(self._path):
            self.load()

    # ------------------------------------------------------------------
    # Game CRUD
    # ------------------------------------------------------------------

    def add_game(self, game: Game) -> Game:
        """Add a game to the database and fire the game-added event."""
        with self._lock:
            self._games[game.id] = game
            self._fire_event(self.on_game_added, game)
            return game

    def get_game(self, game_id: str) -> Game | None:
        """Return the game with the given ID, or None if not found."""
        with self._lock:
            return self._games.get(game_id)

    def update_game(self, game: Game) -> None:
        """Replace an existing game and fire the game-updated event."""
        with self._lock:
            old = self._games.get(game.id)
            self._games[game.id] = game
            self._fire_event(self.on_game_updated, old, game)

    def remove_game(self, game_id: str) -> bool:
        """Remove a game by ID and return whether it existed."""
        with self._lock:
            game = self._games.pop(game_id, None)
            if game:
                self._fire_event(self.on_game_removed, game)
                return True
            return False

    def get_all_games(self) -> list[Game]:
        """Return a list of all games in the database."""
        with self._lock:
            return list(self._games.values())

    def query_games(self, **filters: Any) -> list[Game]:
        """Filter games by field values.

        Supported filters: name, source, is_installed, hidden, favorite,
        completion_status, platform_id (in platform_ids), genre_id (in genre_ids),
        tag_id (in tag_ids), developer_id, publisher_id, category_id, feature_id.
        """
        with self._lock:
            results = list(self._games.values())

        for key, value in filters.items():
            filtered = []
            for game in results:
                if key == "name" and value.lower() in game.name.lower():
                    filtered.append(game)
                elif key == "source" and game.source == value:
                    filtered.append(game)
                elif key == "is_installed" and game.is_installed == value:
                    filtered.append(game)
                elif key == "hidden" and game.hidden == value:
                    filtered.append(game)
                elif key == "favorite" and game.favorite == value:
                    filtered.append(game)
                elif key == "completion_status" and game.completion_status.value == value:
                    filtered.append(game)
                elif key == "platform_id" and value in game.platform_ids:
                    filtered.append(game)
                elif key == "genre_id" and value in game.genre_ids:
                    filtered.append(game)
                elif key == "tag_id" and value in game.tag_ids:
                    filtered.append(game)
                elif key == "developer_id" and value in game.developer_ids:
                    filtered.append(game)
                elif key == "publisher_id" and value in game.publisher_ids:
                    filtered.append(game)
                elif key == "category_id" and value in game.category_ids:
                    filtered.append(game)
                elif key == "feature_id" and value in game.feature_ids:
                    filtered.append(game)
            results = filtered
        return results

    # ------------------------------------------------------------------
    # Action CRUD
    # ------------------------------------------------------------------

    def add_action(self, action: GameAction) -> GameAction:
        """Add an action and link it to its game if applicable."""
        with self._lock:
            self._actions[action.id] = action
            if action.game_id:
                game = self._games.get(action.game_id)
                if game and action.id not in game.action_ids:
                    game.action_ids.append(action.id)
            self._fire_event(self.on_action_added, action)
            return action

    def get_action(self, action_id: str) -> GameAction | None:
        """Return the action with the given ID, or None if not found."""
        with self._lock:
            return self._actions.get(action_id)

    def remove_action(self, action_id: str) -> bool:
        """Remove an action by ID and unlink it from its game."""
        with self._lock:
            action = self._actions.pop(action_id, None)
            if action:
                if action.game_id:
                    game = self._games.get(action.game_id)
                    if game and action_id in game.action_ids:
                        game.action_ids.remove(action_id)
                self._fire_event(self.on_action_removed, action)
                return True
            return False

    def get_actions_for_game(
        self, game_id: str | None = None, phase: str | None = None
    ) -> list[GameAction]:
        """Return enabled actions for a game and phase, sorted by priority."""
        with self._lock:
            results = []
            for action in self._actions.values():
                if not action.enabled:
                    continue
                if game_id is not None:
                    if action.game_id is not None and action.game_id != game_id:
                        continue
                if phase is not None and action.phase.value != phase:
                    continue
                results.append(action)
            results.sort(key=lambda a: a.priority, reverse=True)
            return results

    def get_all_actions(self) -> list[GameAction]:
        """Return a list of all actions in the database."""
        with self._lock:
            return list(self._actions.values())

    # ------------------------------------------------------------------
    # Metadata CRUD (generic helper + typed accessors)
    # ------------------------------------------------------------------

    def _add_metadata(self, collection: dict, item: Any) -> Any:
        with self._lock:
            collection[item.id] = item
            return item

    def _get_metadata(self, collection: dict) -> list:
        with self._lock:
            return list(collection.values())

    def _remove_metadata(self, collection: dict, item_id: str) -> bool:
        with self._lock:
            return collection.pop(item_id, None) is not None

    def add_platform(self, p: Platform) -> Platform:
        """Add a platform to the database."""
        return self._add_metadata(self._platforms, p)

    def get_platforms(self) -> list[Platform]:
        """Return all platforms."""
        return self._get_metadata(self._platforms)

    def remove_platform(self, pid: str) -> bool:
        """Remove a platform by ID."""
        return self._remove_metadata(self._platforms, pid)

    def add_genre(self, g: Genre) -> Genre:
        """Add a genre to the database."""
        return self._add_metadata(self._genres, g)

    def get_genres(self) -> list[Genre]:
        """Return all genres."""
        return self._get_metadata(self._genres)

    def remove_genre(self, gid: str) -> bool:
        """Remove a genre by ID."""
        return self._remove_metadata(self._genres, gid)

    def add_developer(self, d: Developer) -> Developer:
        """Add a developer to the database."""
        return self._add_metadata(self._developers, d)

    def get_developers(self) -> list[Developer]:
        """Return all developers."""
        return self._get_metadata(self._developers)

    def add_publisher(self, p: Publisher) -> Publisher:
        """Add a publisher to the database."""
        return self._add_metadata(self._publishers, p)

    def get_publishers(self) -> list[Publisher]:
        """Return all publishers."""
        return self._get_metadata(self._publishers)

    def add_tag(self, t: Tag) -> Tag:
        """Add a tag to the database."""
        return self._add_metadata(self._tags, t)

    def get_tags(self) -> list[Tag]:
        """Return all tags."""
        return self._get_metadata(self._tags)

    def remove_tag(self, tid: str) -> bool:
        """Remove a tag by ID."""
        return self._remove_metadata(self._tags, tid)

    def add_category(self, c: Category) -> Category:
        """Add a category to the database."""
        return self._add_metadata(self._categories, c)

    def get_categories(self) -> list[Category]:
        """Return all categories."""
        return self._get_metadata(self._categories)

    def add_feature(self, f: Feature) -> Feature:
        """Add a feature to the database."""
        return self._add_metadata(self._features, f)

    def get_features(self) -> list[Feature]:
        """Return all features."""
        return self._get_metadata(self._features)

    def add_series(self, s: Series) -> Series:
        """Add a series to the database."""
        return self._add_metadata(self._series, s)

    def get_series_list(self) -> list[Series]:
        """Return all series."""
        return self._get_metadata(self._series)

    def add_age_rating(self, a: AgeRating) -> AgeRating:
        """Add an age rating to the database."""
        return self._add_metadata(self._age_ratings, a)

    def get_age_ratings(self) -> list[AgeRating]:
        """Return all age ratings."""
        return self._get_metadata(self._age_ratings)

    def add_region(self, r: Region) -> Region:
        """Add a region to the database."""
        return self._add_metadata(self._regions, r)

    def get_regions(self) -> list[Region]:
        """Return all regions."""
        return self._get_metadata(self._regions)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the database."""
        with self._lock:
            games = list(self._games.values())
        total = len(games)
        installed = sum(1 for g in games if g.is_installed)
        total_playtime = sum(g.playtime for g in games)
        by_status: dict[str, int] = {}
        for g in games:
            key = g.completion_status.value
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "total_games": total,
            "installed_games": installed,
            "total_playtime_seconds": total_playtime,
            "total_actions": len(self._actions),
            "by_completion_status": by_status,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        with self._lock:
            return {
                "games": {gid: g.to_dict() for gid, g in self._games.items()},
                "actions": {aid: a.to_dict() for aid, a in self._actions.items()},
                "platforms": {pid: p.to_dict() for pid, p in self._platforms.items()},
                "genres": {gid: g.to_dict() for gid, g in self._genres.items()},
                "developers": {did: d.to_dict() for did, d in self._developers.items()},
                "publishers": {pid: p.to_dict() for pid, p in self._publishers.items()},
                "tags": {tid: t.to_dict() for tid, t in self._tags.items()},
                "categories": {cid: c.to_dict() for cid, c in self._categories.items()},
                "features": {fid: f.to_dict() for fid, f in self._features.items()},
                "series": {sid: s.to_dict() for sid, s in self._series.items()},
                "age_ratings": {aid: a.to_dict() for aid, a in self._age_ratings.items()},
                "regions": {rid: r.to_dict() for rid, r in self._regions.items()},
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: str | None = None) -> GameDatabase:
        """Deserialize from a dictionary."""
        db = cls.__new__(cls)
        db.__init__(path=None)  # type: ignore[misc]
        for gid, gdata in data.get("games", {}).items():
            db._games[gid] = Game.from_dict(gdata)
        for aid, adata in data.get("actions", {}).items():
            db._actions[aid] = GameAction.from_dict(adata)
        for pid, pdata in data.get("platforms", {}).items():
            db._platforms[pid] = Platform.from_dict(pdata)
        for gid, gdata in data.get("genres", {}).items():
            db._genres[gid] = Genre.from_dict(gdata)
        for did, ddata in data.get("developers", {}).items():
            db._developers[did] = Developer.from_dict(ddata)
        for pid, pdata in data.get("publishers", {}).items():
            db._publishers[pid] = Publisher.from_dict(pdata)
        for tid, tdata in data.get("tags", {}).items():
            db._tags[tid] = Tag.from_dict(tdata)
        for cid, cdata in data.get("categories", {}).items():
            db._categories[cid] = Category.from_dict(cdata)
        for fid, fdata in data.get("features", {}).items():
            db._features[fid] = Feature.from_dict(fdata)
        for sid, sdata in data.get("series", {}).items():
            db._series[sid] = Series.from_dict(sdata)
        for aid, adata in data.get("age_ratings", {}).items():
            db._age_ratings[aid] = AgeRating.from_dict(adata)
        for rid, rdata in data.get("regions", {}).items():
            db._regions[rid] = Region.from_dict(rdata)
        if path:
            db._path = path
        return db

    def save(self) -> None:
        """Persist the database to the configured JSON file."""
        if not self._path:
            raise ValueError("No database path configured")
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(path))

    def load(self) -> None:
        """Load database contents from the configured JSON file."""
        if not self._path or not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return
        data = json.loads(content)
        loaded = GameDatabase.from_dict(data)
        with self._lock:
            self._games = loaded._games
            self._actions = loaded._actions
            self._platforms = loaded._platforms
            self._genres = loaded._genres
            self._developers = loaded._developers
            self._publishers = loaded._publishers
            self._tags = loaded._tags
            self._categories = loaded._categories
            self._features = loaded._features
            self._series = loaded._series
            self._age_ratings = loaded._age_ratings
            self._regions = loaded._regions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def remove_listener(self, callback: Callable) -> None:
        """Remove a callback from all event handler lists."""
        for handlers in (
            self.on_game_added,
            self.on_game_updated,
            self.on_game_removed,
            self.on_action_added,
            self.on_action_removed,
        ):
            try:
                handlers.remove(callback)
            except ValueError:
                pass

    def clear_listeners(self) -> None:
        """Remove all registered event listeners."""
        self.on_game_added.clear()
        self.on_game_updated.clear()
        self.on_game_removed.clear()
        self.on_action_added.clear()
        self.on_action_removed.clear()

    @staticmethod
    def _fire_event(handlers: list[Callable], *args: Any) -> None:
        for handler in handlers:
            try:
                handler(*args)
            except Exception:
                pass  # Event handlers must not crash the database
