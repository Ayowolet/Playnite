"""
SQLite-backed game database.

Each entity type (Game, Platform, Genre, …) is stored in its own table with
``id TEXT PRIMARY KEY`` and ``data TEXT`` (JSON-serialised object).  This
mirrors the LiteDB document-store approach used in the original C# Playnite.

Usage
-----
>>> db = GameDatabase("library.db")
>>> db.open()
>>> game = Game(name="Half-Life 2")
>>> db.games.add(game)
>>> all_games = db.games.all()
>>> db.close()
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import (
    Any, Callable, Dict, Generic, Iterator, List, Optional, Type, TypeVar,
)

from ..models.game import (
    AgeRating, Category, Company, CompletionStatus, Game, GameFeature,
    GameSource, Genre, NamedObject, Platform, Region, Series, Tag,
)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Connection wrapper — deferred-commit support
# ---------------------------------------------------------------------------

class _ConnectionWrapper:
    """
    Thin proxy around :class:`sqlite3.Connection` that supports deferred
    commits.

    ``sqlite3.Connection.commit`` is read-only on Python 3.11+ and cannot be
    monkey-patched.  This wrapper intercepts ``commit()`` calls: when
    ``_buffering > 0`` they become no-ops; only :meth:`force_commit` writes
    through unconditionally.

    Increment ``_buffering`` to enter a buffered block; decrement and call
    :meth:`force_commit` to flush.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._buffering: int = 0
        self._buf_lock = threading.Lock()

    def execute(self, sql: str, parameters: Any = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_params: Any) -> sqlite3.Cursor:
        return self._conn.executemany(sql, seq_of_params)

    def commit(self) -> None:
        if self._buffering == 0:
            self._conn.commit()

    def force_commit(self) -> None:
        """Commit unconditionally, regardless of the buffering counter."""
        self._conn.commit()

    @contextmanager
    def buffered(self) -> Iterator[None]:
        """
        Context manager that defers commits for the duration of the block.

        Thread-safe: uses a lock to guard the buffering counter so that
        nested or concurrent ``buffered()`` calls compose correctly.

        Nested calls are safe — only the outermost exit triggers the actual
        commit::

            with conn.buffered():        # depth → 1
                with conn.buffered():    # depth → 2
                    conn.commit()        # no-op (buffering active)
                # depth back to 1 → no commit yet
            # depth back to 0 → force_commit() fires here
        """
        with self._buf_lock:
            self._buffering += 1
        try:
            yield
        finally:
            with self._buf_lock:
                self._buffering -= 1
                should_commit = self._buffering == 0
            if should_commit:
                self.force_commit()

    def close(self) -> None:
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


# ---------------------------------------------------------------------------
# Generic document collection
# ---------------------------------------------------------------------------

class Collection(Generic[T]):
    """
    A typed collection backed by a single SQLite table.

    The table schema is::

        CREATE TABLE IF NOT EXISTS <name> (
            id   TEXT PRIMARY KEY,
            name TEXT,
            data TEXT NOT NULL
        )

    ``name`` is kept as a separate column for efficient name lookups without
    deserialising every row.
    """

    def __init__(
        self,
        conn: _ConnectionWrapper,
        table_name: str,
        model_class: Type[T],
        lock: threading.Lock,
    ) -> None:
        self._conn = conn
        self._table = table_name
        self._cls = model_class
        self._lock = lock
        self._ensure_table()

        # Subscribers for change notifications (item_added, item_updated, item_removed)
        self._on_item_updated: List[Callable[[T], None]] = []
        self._on_item_added: List[Callable[[T], None]] = []
        self._on_item_removed: List[Callable[[str], None]] = []

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id   TEXT PRIMARY KEY,
                    name TEXT,
                    data TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_name ON {self._table}(name)"
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, item: T) -> T:
        """Insert *item*; raises ``sqlite3.IntegrityError`` if the ID already exists."""
        d = item.to_dict()  # type: ignore[attr-defined]
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {self._table}(id, name, data) VALUES(?,?,?)",
                (d["id"], d.get("name", ""), json.dumps(d)),
            )
            self._conn.commit()
            callbacks = list(self._on_item_added)
        for cb in callbacks:
            cb(item)
        return item

    def update(self, item: T) -> None:
        """Update an existing item; no-op if not found."""
        d = item.to_dict()  # type: ignore[attr-defined]
        if isinstance(item, Game):
            item.touch()  # type: ignore[attr-defined]
            d = item.to_dict()  # type: ignore[attr-defined]
        with self._lock:
            self._conn.execute(
                f"UPDATE {self._table} SET name=?, data=? WHERE id=?",
                (d.get("name", ""), json.dumps(d), d["id"]),
            )
            self._conn.commit()
            callbacks = list(self._on_item_updated)
        for cb in callbacks:
            cb(item)

    def add_or_update(self, item: T) -> T:
        """Upsert: insert if new, update if existing."""
        d = item.to_dict()  # type: ignore[attr-defined]
        existing = self.get(d["id"])
        if existing is None:
            return self.add(item)
        self.update(item)
        return item

    def remove(self, item_id: str) -> None:
        """Delete by ID.  Silently succeeds if not found."""
        with self._lock:
            self._conn.execute(
                f"DELETE FROM {self._table} WHERE id=?", (item_id,)
            )
            self._conn.commit()
            callbacks = list(self._on_item_removed)
        for cb in callbacks:
            cb(item_id)

    def get(self, item_id: str) -> Optional[T]:
        """Return item by ID or *None*."""
        with self._lock:
            cur = self._conn.execute(
                f"SELECT data FROM {self._table} WHERE id=?", (item_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._cls.from_dict(json.loads(row[0]))  # type: ignore[attr-defined]

    def get_by_name(self, name: str) -> Optional[T]:
        """Return the first item matching *name* (case-sensitive)."""
        with self._lock:
            cur = self._conn.execute(
                f"SELECT data FROM {self._table} WHERE name=?", (name,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._cls.from_dict(json.loads(row[0]))  # type: ignore[attr-defined]

    def all(self) -> List[T]:
        """Return all items in the collection."""
        with self._lock:
            cur = self._conn.execute(f"SELECT data FROM {self._table}")
            rows = cur.fetchall()
        return [self._cls.from_dict(json.loads(r[0])) for r in rows]  # type: ignore[attr-defined]

    def filter(self, predicate: Callable[[T], bool]) -> List[T]:
        """Return items matching *predicate* (evaluated in Python, not SQL)."""
        return [item for item in self.all() if predicate(item)]

    def count(self) -> int:
        with self._lock:
            cur = self._conn.execute(f"SELECT COUNT(*) FROM {self._table}")
            return cur.fetchone()[0]

    def clear(self) -> None:
        """Remove all items from the collection."""
        with self._lock:
            self._conn.execute(f"DELETE FROM {self._table}")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    @contextmanager
    def buffered_update(self) -> Iterator[None]:
        """
        Context manager that defers commits until the block exits.

        Use this when adding/updating many items at once to avoid a SQLite
        commit per row::

            with db.games.buffered_update():
                for game in big_list:
                    db.games.add(game)
        """
        with self._conn.buffered():
            yield

    # ------------------------------------------------------------------
    # Change event subscriptions
    # ------------------------------------------------------------------

    def on_item_added(self, callback: Callable[[T], None]) -> None:
        self._on_item_added.append(callback)

    def on_item_updated(self, callback: Callable[[T], None]) -> None:
        self._on_item_updated.append(callback)

    def on_item_removed(self, callback: Callable[[str], None]) -> None:
        self._on_item_removed.append(callback)


# ---------------------------------------------------------------------------
# Specialised Game collection with search helpers
# ---------------------------------------------------------------------------

class GamesCollection(Collection[Game]):
    """Extends ``Collection[Game]`` with game-specific query methods."""

    def get_installed(self) -> List[Game]:
        return self.filter(lambda g: g.is_installed)

    def get_by_platform(self, platform_id: str) -> List[Game]:
        return self.filter(lambda g: platform_id in g.platform_ids)

    def get_by_tag(self, tag_id: str) -> List[Game]:
        return self.filter(lambda g: tag_id in g.tag_ids)

    def search(self, query: str) -> List[Game]:
        """Case-insensitive substring search across ``name``, ``description``, and ``notes``."""
        q = query.lower()
        return self.filter(
            lambda g: q in g.name.lower()
            or q in g.description.lower()
            or q in g.notes.lower()
        )

    def get_recently_played(self, limit: int = 10) -> List[Game]:
        played = [g for g in self.all() if g.last_activity is not None]
        played.sort(key=lambda g: g.last_activity, reverse=True)  # type: ignore[arg-type]
        return played[:limit]

    def get_favorites(self) -> List[Game]:
        return self.filter(lambda g: g.is_favorite)

    def get_hidden(self) -> List[Game]:
        return self.filter(lambda g: g.is_hidden)


# ---------------------------------------------------------------------------
# Main database class
# ---------------------------------------------------------------------------

class GameDatabase:
    """
    Top-level database facade.

    Holds one :class:`Collection` (or :class:`GamesCollection`) per entity
    type.  All collections share the same SQLite connection and a
    :class:`threading.Lock` for thread safety.

    Example
    -------
    >>> db = GameDatabase("/path/to/library.db")
    >>> db.open()
    >>> db.games.add(Game(name="Celeste"))
    >>> db.close()
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._conn: Optional[_ConnectionWrapper] = None
        self._lock = threading.Lock()
        self._cm_lock = threading.Lock()   # guards _enter_depth
        self._enter_depth: int = 0         # tracks nested with-block depth

        # Collections — populated in open()
        self.games: GamesCollection
        self.platforms: Collection[Platform]
        self.genres: Collection[Genre]
        self.companies: Collection[Company]
        self.tags: Collection[Tag]
        self.categories: Collection[Category]
        self.series: Collection[Series]
        self.age_ratings: Collection[AgeRating]
        self.regions: Collection[Region]
        self.features: Collection[GameFeature]
        self.sources: Collection[GameSource]
        self.completion_statuses: Collection[CompletionStatus]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database and initialise all collections."""
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = _ConnectionWrapper(sqlite3.connect(
            self._path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we control transactions ourselves
        ))
        # Enable WAL mode for better concurrent read performance
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self.games = GamesCollection(self._conn, "games", Game, self._lock)
        self.platforms = Collection(self._conn, "platforms", Platform, self._lock)
        self.genres = Collection(self._conn, "genres", Genre, self._lock)
        self.companies = Collection(self._conn, "companies", Company, self._lock)
        self.tags = Collection(self._conn, "tags", Tag, self._lock)
        self.categories = Collection(self._conn, "categories", Category, self._lock)
        self.series = Collection(self._conn, "series", Series, self._lock)
        self.age_ratings = Collection(self._conn, "age_ratings", AgeRating, self._lock)
        self.regions = Collection(self._conn, "regions", Region, self._lock)
        self.features = Collection(self._conn, "features", GameFeature, self._lock)
        self.sources = Collection(self._conn, "sources", GameSource, self._lock)
        self.completion_statuses = Collection(
            self._conn, "completion_statuses", CompletionStatus, self._lock
        )

    def close(self) -> None:
        """Flush and close the underlying connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def is_open(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def resolve_names(self, game: Game) -> Dict[str, Any]:
        """
        Return a dict mapping field names to human-readable strings for
        a given *game* (resolves ID references to names).

        The returned dict always contains all eight keys: ``platforms``,
        ``genres``, ``developers``, ``publishers``, ``tags``,
        ``categories``, ``features``, and ``series``.  IDs that have no
        matching row in the corresponding collection are silently omitted
        from each list; the value is an empty list when none of the IDs
        resolve.
        """
        def _names(ids: List[str], col: Collection) -> List[str]:
            return [obj.name for obj in [col.get(i) for i in ids] if obj]

        return {
            "platforms": _names(game.platform_ids, self.platforms),
            "genres": _names(game.genre_ids, self.genres),
            "developers": _names(game.developer_ids, self.companies),
            "publishers": _names(game.publisher_ids, self.companies),
            "tags": _names(game.tag_ids, self.tags),
            "categories": _names(game.category_ids, self.categories),
            "features": _names(game.feature_ids, self.features),
            "series": _names(game.series_ids, self.series),
        }

    def export_json(self, path: str) -> None:
        """Export the entire game list to a JSON file."""
        games = [g.to_dict() for g in self.games.all()]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(games, fh, indent=2, default=str)

    def import_json(self, path: str) -> int:
        """
        Import games from a JSON file.

        Returns the number of games imported.
        """
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        count = 0
        with self.games.buffered_update():
            for d in raw:
                self.games.add_or_update(Game.from_dict(d))
                count += 1
        return count

    @contextmanager
    def buffered_update(self) -> Iterator[None]:
        """
        Defer all commits until the block exits.

        Since all :class:`Collection` instances share the same SQLite connection
        wrapper, a single buffered block suspends commits for every collection —
        safe to use for bulk multi-collection operations::

            with db.buffered_update():
                db.games.add(game)
                db.tags.add(tag)
        """
        if self._conn is None:
            raise RuntimeError("Database is not open.")
        with self._conn.buffered():
            yield

    def get_stats(self) -> Dict[str, int]:
        """Return high-level library statistics."""
        all_games = self.games.all()
        total_playtime = sum(g.play_time for g in all_games)
        return {
            "total_games": self.games.count(),
            "installed": len([g for g in all_games if g.is_installed]),
            "favorites": len([g for g in all_games if g.is_favorite]),
            "hidden": len([g for g in all_games if g.is_hidden]),
            "total_playtime_seconds": total_playtime,
            "platforms": self.platforms.count(),
            "genres": self.genres.count(),
            "tags": self.tags.count(),
        }

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "GameDatabase":
        with self._cm_lock:
            if not self.is_open():
                self.open()
            self._enter_depth += 1
        return self

    def __exit__(self, *_: Any) -> None:
        with self._cm_lock:
            self._enter_depth = max(0, self._enter_depth - 1)
            should_close = self._enter_depth == 0
        if should_close:
            self.close()
