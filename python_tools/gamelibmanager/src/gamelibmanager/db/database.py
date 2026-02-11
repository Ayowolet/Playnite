"""SQLite-backed game database with full CRUD, transactions, and savepoints."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Type, TypeVar

from ..models.base import DatabaseObject
from ..models.game import Game
from ..models.game_action import GameAction, GameActionType, TrackingMode
from ..models.game_rom import GameRom
from ..models.link import Link
from ..models.lookup_tables import (
    AgeRating, Category, Company, CompletionStatus, GameFeature,
    GameSource, Genre, Platform, Region, Series, Tag,
)
from ..models.release_date import ReleaseDate
from .schema import SCHEMA_VERSION, get_all_ddl

T = TypeVar("T", bound=DatabaseObject)

_EMPTY_UUID = uuid.UUID(int=0)


# ------------------------------------------------------------------ #
# Serialisation helpers
# ------------------------------------------------------------------ #

def _uuid_list_to_json(ids: list[uuid.UUID] | None) -> str | None:
    if ids is None:
        return None
    return json.dumps([str(u) for u in ids])


def _json_to_uuid_list(raw: str | None) -> list[uuid.UUID] | None:
    if raw is None:
        return None
    return [uuid.UUID(s) for s in json.loads(raw)]


def _links_to_json(links: list[Link] | None) -> str | None:
    if links is None:
        return None
    return json.dumps([{"name": lk.name, "url": lk.url} for lk in links])


def _json_to_links(raw: str | None) -> list[Link] | None:
    if raw is None:
        return None
    return [Link(name=d.get("name", ""), url=d.get("url", "")) for d in json.loads(raw)]


def _actions_to_json(actions: list[GameAction] | None) -> str | None:
    if actions is None:
        return None
    out = []
    for a in actions:
        out.append({
            "type": int(a.type), "name": a.name, "path": a.path,
            "working_dir": a.working_dir, "arguments": a.arguments,
            "additional_arguments": a.additional_arguments,
            "override_default_args": a.override_default_args,
            "is_play_action": a.is_play_action,
            "emulator_id": str(a.emulator_id),
            "emulator_profile_id": a.emulator_profile_id,
            "tracking_mode": int(a.tracking_mode),
            "tracking_path": a.tracking_path, "script": a.script,
            "initial_tracking_delay": a.initial_tracking_delay,
            "tracking_frequency": a.tracking_frequency,
        })
    return json.dumps(out)


def _json_to_actions(raw: str | None) -> list[GameAction] | None:
    if raw is None:
        return None
    result = []
    for d in json.loads(raw):
        result.append(GameAction(
            type=GameActionType(d.get("type", 0)),
            name=d.get("name", ""),
            path=d.get("path", ""),
            working_dir=d.get("working_dir", ""),
            arguments=d.get("arguments", ""),
            additional_arguments=d.get("additional_arguments", ""),
            override_default_args=d.get("override_default_args", False),
            is_play_action=d.get("is_play_action", False),
            emulator_id=uuid.UUID(d["emulator_id"]) if d.get("emulator_id") else _EMPTY_UUID,
            emulator_profile_id=d.get("emulator_profile_id", ""),
            tracking_mode=TrackingMode(d.get("tracking_mode", 0)),
            tracking_path=d.get("tracking_path", ""),
            script=d.get("script", ""),
            initial_tracking_delay=d.get("initial_tracking_delay", 0),
            tracking_frequency=d.get("tracking_frequency", 2000),
        ))
    return result


def _roms_to_json(roms: list[GameRom] | None) -> str | None:
    if roms is None:
        return None
    return json.dumps([{"name": r.name, "path": r.path} for r in roms])


def _json_to_roms(raw: str | None) -> list[GameRom] | None:
    if raw is None:
        return None
    return [GameRom(name=d.get("name", ""), path=d.get("path", "")) for d in json.loads(raw)]


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    return datetime.fromisoformat(raw)


def _uuid_to_str(u: uuid.UUID) -> str:
    return str(u)


def _str_to_uuid(s: str | None) -> uuid.UUID:
    if s is None:
        return _EMPTY_UUID
    return uuid.UUID(s)


def _bool_to_int(b: bool) -> int:
    return 1 if b else 0


def _int_to_bool(i: Any) -> bool:
    return bool(i)


# ------------------------------------------------------------------ #
# Column order for the games table
# ------------------------------------------------------------------ #

_GAME_COLUMNS = [
    "id", "name", "game_id", "plugin_id", "sorting_name", "description",
    "notes", "hidden", "favorite", "is_installed", "is_installing",
    "is_uninstalling", "is_launching", "is_running", "override_install_state",
    "include_library_plugin_action", "enable_system_hdr",
    "platform_ids", "developer_ids", "publisher_ids", "genre_ids",
    "category_ids", "tag_ids", "feature_ids", "series_ids",
    "age_rating_ids", "region_ids", "source_id", "completion_status_id",
    "release_date", "last_activity", "added", "modified",
    "last_size_scan_date", "playtime", "play_count", "install_size",
    "user_score", "critic_score", "community_score",
    "icon", "cover_image", "background_image", "install_directory",
    "version", "manual", "pre_script", "post_script",
    "game_started_script", "use_global_pre_script", "use_global_post_script",
    "use_global_game_started_script", "links", "game_actions", "roms",
    "_normalized_name",
]

_GAME_PLACEHOLDERS = ", ".join(["?"] * len(_GAME_COLUMNS))
_GAME_COLUMN_LIST = ", ".join(_GAME_COLUMNS)


class GameDatabase:
    """SQLite-backed game database."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def open(
        self,
        busy_timeout_ms: int = 30_000,
        connect_timeout: float = 10.0,
    ) -> None:
        """Open the database connection.

        Args:
            busy_timeout_ms: SQLite busy_timeout in milliseconds.  When
                another process holds a lock, SQLite retries internally
                for up to this long before raising OperationalError.
            connect_timeout: Python sqlite3 module lock-wait timeout in
                seconds passed to ``sqlite3.connect()``.
        """
        self.conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            timeout=connect_timeout,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        self._ensure_schema()

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> GameDatabase:
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def check_write_access(self, timeout_ms: int = 3000) -> None:
        """Verify that a write lock can be acquired on the database.

        Attempts to start and immediately roll back an ``IMMEDIATE``
        transaction.  If another process holds a lock that cannot be
        released within *timeout_ms*, raises
        :class:`~gamelibmanager.db.concurrency.DatabaseLockedError`.

        Call this before a long-running merge so the user gets immediate
        feedback rather than failing mid-operation.
        """
        from .concurrency import DatabaseLockedError, is_lock_error

        assert self.conn is not None
        old_timeout: int = 0
        try:
            row = self.conn.execute("PRAGMA busy_timeout").fetchone()
            old_timeout = row[0] if row else 0
            self.conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute("ROLLBACK")
        except sqlite3.OperationalError as exc:
            # Make sure we leave the connection in a clean state.
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            if is_lock_error(exc):
                raise DatabaseLockedError("pre-flight lock check", 1, exc)
            raise
        finally:
            self.conn.execute(f"PRAGMA busy_timeout={old_timeout}")

    def sqlite_backup(self, dest_path: str | Path) -> None:
        """Create a consistent database copy using SQLite's backup API.

        Produces a valid snapshot even when another process is writing
        concurrently (WAL mode captures a point-in-time snapshot).
        """
        assert self.conn is not None
        dest = sqlite3.connect(str(dest_path))
        try:
            self.conn.backup(dest)
        finally:
            dest.close()

    def _ensure_schema(self) -> None:
        assert self.conn is not None
        for stmt in get_all_ddl():
            self.conn.execute(stmt)

        row = self.conn.execute(
            "SELECT value FROM _schema_meta WHERE key = 'version'"
        ).fetchone()
        current_version = int(row["value"]) if row else 0

        if current_version < 2:
            self.rebuild_normalized_names()

        self.conn.execute(
            "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES (?, ?)",
            ("version", str(SCHEMA_VERSION)),
        )

    def rebuild_normalized_names(self) -> int:
        """Re-compute _normalized_name for all games. Returns count updated."""
        from ..duplicates.normalizer import TitleNormalizer
        assert self.conn is not None
        rows = self.conn.execute("SELECT id, name FROM games").fetchall()
        count = 0
        for row in rows:
            new_norm = TitleNormalizer.normalize(row["name"] or "")
            self.conn.execute(
                "UPDATE games SET _normalized_name = ? WHERE id = ?",
                (new_norm, row["id"]),
            )
            count += 1
        return count

    # ------------------------------------------------------------------ #
    # Transaction helpers
    # ------------------------------------------------------------------ #

    def begin_transaction(self) -> None:
        assert self.conn is not None
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        assert self.conn is not None
        self.conn.commit()

    def rollback(self) -> None:
        assert self.conn is not None
        self.conn.rollback()

    def savepoint(self, name: str) -> None:
        assert self.conn is not None
        self.conn.execute(f"SAVEPOINT {name}")

    def release_savepoint(self, name: str) -> None:
        assert self.conn is not None
        self.conn.execute(f"RELEASE SAVEPOINT {name}")

    def rollback_to_savepoint(self, name: str) -> None:
        assert self.conn is not None
        self.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")

    # ------------------------------------------------------------------ #
    # Game CRUD
    # ------------------------------------------------------------------ #

    def _game_to_row(self, game: Game) -> tuple:
        from ..duplicates.normalizer import TitleNormalizer
        return (
            _uuid_to_str(game.id),
            game.name,
            game.game_id,
            _uuid_to_str(game.plugin_id),
            game.sorting_name,
            game.description,
            game.notes,
            _bool_to_int(game.hidden),
            _bool_to_int(game.favorite),
            _bool_to_int(game.is_installed),
            _bool_to_int(game.is_installing),
            _bool_to_int(game.is_uninstalling),
            _bool_to_int(game.is_launching),
            _bool_to_int(game.is_running),
            _bool_to_int(game.override_install_state),
            _bool_to_int(game.include_library_plugin_action),
            _bool_to_int(game.enable_system_hdr),
            _uuid_list_to_json(game.platform_ids),
            _uuid_list_to_json(game.developer_ids),
            _uuid_list_to_json(game.publisher_ids),
            _uuid_list_to_json(game.genre_ids),
            _uuid_list_to_json(game.category_ids),
            _uuid_list_to_json(game.tag_ids),
            _uuid_list_to_json(game.feature_ids),
            _uuid_list_to_json(game.series_ids),
            _uuid_list_to_json(game.age_rating_ids),
            _uuid_list_to_json(game.region_ids),
            _uuid_to_str(game.source_id),
            _uuid_to_str(game.completion_status_id),
            game.release_date.serialize() if game.release_date else None,
            _dt_to_str(game.last_activity),
            _dt_to_str(game.added),
            _dt_to_str(game.modified),
            _dt_to_str(game.last_size_scan_date),
            game.playtime,
            game.play_count,
            game.install_size,
            game.user_score,
            game.critic_score,
            game.community_score,
            game.icon,
            game.cover_image,
            game.background_image,
            game.install_directory,
            game.version,
            game.manual,
            game.pre_script,
            game.post_script,
            game.game_started_script,
            _bool_to_int(game.use_global_pre_script),
            _bool_to_int(game.use_global_post_script),
            _bool_to_int(game.use_global_game_started_script),
            _links_to_json(game.links),
            _actions_to_json(game.game_actions),
            _roms_to_json(game.roms),
            TitleNormalizer.normalize(game.name),
        )

    def _row_to_game(self, row: sqlite3.Row) -> Game:
        rd_raw = row["release_date"]
        release_date = ReleaseDate.deserialize(rd_raw) if rd_raw else None
        return Game(
            id=_str_to_uuid(row["id"]),
            name=row["name"] or "",
            game_id=row["game_id"] or "",
            plugin_id=_str_to_uuid(row["plugin_id"]),
            sorting_name=row["sorting_name"],
            description=row["description"] or "",
            notes=row["notes"] or "",
            hidden=_int_to_bool(row["hidden"]),
            favorite=_int_to_bool(row["favorite"]),
            is_installed=_int_to_bool(row["is_installed"]),
            is_installing=_int_to_bool(row["is_installing"]),
            is_uninstalling=_int_to_bool(row["is_uninstalling"]),
            is_launching=_int_to_bool(row["is_launching"]),
            is_running=_int_to_bool(row["is_running"]),
            override_install_state=_int_to_bool(row["override_install_state"]),
            include_library_plugin_action=_int_to_bool(row["include_library_plugin_action"]),
            enable_system_hdr=_int_to_bool(row["enable_system_hdr"]),
            platform_ids=_json_to_uuid_list(row["platform_ids"]),
            developer_ids=_json_to_uuid_list(row["developer_ids"]),
            publisher_ids=_json_to_uuid_list(row["publisher_ids"]),
            genre_ids=_json_to_uuid_list(row["genre_ids"]),
            category_ids=_json_to_uuid_list(row["category_ids"]),
            tag_ids=_json_to_uuid_list(row["tag_ids"]),
            feature_ids=_json_to_uuid_list(row["feature_ids"]),
            series_ids=_json_to_uuid_list(row["series_ids"]),
            age_rating_ids=_json_to_uuid_list(row["age_rating_ids"]),
            region_ids=_json_to_uuid_list(row["region_ids"]),
            source_id=_str_to_uuid(row["source_id"]),
            completion_status_id=_str_to_uuid(row["completion_status_id"]),
            release_date=release_date,
            last_activity=_str_to_dt(row["last_activity"]),
            added=_str_to_dt(row["added"]),
            modified=_str_to_dt(row["modified"]),
            last_size_scan_date=_str_to_dt(row["last_size_scan_date"]),
            playtime=row["playtime"] or 0,
            play_count=row["play_count"] or 0,
            install_size=row["install_size"],
            user_score=row["user_score"],
            critic_score=row["critic_score"],
            community_score=row["community_score"],
            icon=row["icon"],
            cover_image=row["cover_image"],
            background_image=row["background_image"],
            install_directory=row["install_directory"],
            version=row["version"],
            manual=row["manual"] or "",
            pre_script=row["pre_script"] or "",
            post_script=row["post_script"] or "",
            game_started_script=row["game_started_script"] or "",
            use_global_pre_script=_int_to_bool(row["use_global_pre_script"]),
            use_global_post_script=_int_to_bool(row["use_global_post_script"]),
            use_global_game_started_script=_int_to_bool(row["use_global_game_started_script"]),
            links=_json_to_links(row["links"]),
            game_actions=_json_to_actions(row["game_actions"]),
            roms=_json_to_roms(row["roms"]),
        )

    def add_game(self, game: Game) -> None:
        assert self.conn is not None
        self.conn.execute(
            f"INSERT INTO games ({_GAME_COLUMN_LIST}) VALUES ({_GAME_PLACEHOLDERS})",
            self._game_to_row(game),
        )

    def add_games_batch(self, games: list[Game]) -> None:
        assert self.conn is not None
        rows = [self._game_to_row(g) for g in games]
        wrap = not self.conn.in_transaction
        if wrap:
            self.conn.execute("BEGIN")
        self.conn.executemany(
            f"INSERT INTO games ({_GAME_COLUMN_LIST}) VALUES ({_GAME_PLACEHOLDERS})",
            rows,
        )
        if wrap:
            self.conn.commit()

    def get_game(self, game_id: uuid.UUID) -> Game | None:
        assert self.conn is not None
        row = self.conn.execute(
            "SELECT * FROM games WHERE id = ?", (_uuid_to_str(game_id),)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_game(row)

    def get_all_games(self) -> list[Game]:
        assert self.conn is not None
        rows = self.conn.execute("SELECT * FROM games").fetchall()
        return [self._row_to_game(r) for r in rows]

    def update_game(self, game: Game) -> None:
        assert self.conn is not None
        row = self._game_to_row(game)
        set_clause = ", ".join(f"{col} = ?" for col in _GAME_COLUMNS if col != "id")
        values = row[1:] + (row[0],)  # skip id, append id for WHERE
        self.conn.execute(f"UPDATE games SET {set_clause} WHERE id = ?", values)

    def delete_game(self, game_id: uuid.UUID) -> None:
        assert self.conn is not None
        self.conn.execute("DELETE FROM games WHERE id = ?", (_uuid_to_str(game_id),))

    def game_count(self) -> int:
        assert self.conn is not None
        row = self.conn.execute("SELECT COUNT(*) FROM games").fetchone()
        return row[0]

    # ------------------------------------------------------------------ #
    # Lookup table CRUD (generic)
    # ------------------------------------------------------------------ #

    _LOOKUP_TABLE_MAP: dict[type, str] = {
        Platform: "platforms",
        Genre: "genres",
        Company: "companies",
        Tag: "tags",
        Category: "categories",
        GameFeature: "features",
        GameSource: "sources",
        Series: "series",
        AgeRating: "age_ratings",
        Region: "regions",
        CompletionStatus: "completion_statuses",
    }

    def _get_lookup_table(self, cls: type) -> str:
        tbl = self._LOOKUP_TABLE_MAP.get(cls)
        if tbl is None:
            raise ValueError(f"Unknown lookup type: {cls}")
        return tbl

    def add_lookup(self, obj: DatabaseObject) -> None:
        assert self.conn is not None
        tbl = self._get_lookup_table(type(obj))
        if isinstance(obj, Platform):
            self.conn.execute(
                f"INSERT OR REPLACE INTO {tbl} (id, name, specification_id, icon, cover, background) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                (str(obj.id), obj.name, obj.specification_id, obj.icon, obj.cover, obj.background),
            )
        else:
            self.conn.execute(
                f"INSERT OR REPLACE INTO {tbl} (id, name) VALUES (?, ?)",
                (str(obj.id), obj.name),
            )

    def get_lookup(self, cls: Type[T], obj_id: uuid.UUID) -> T | None:
        assert self.conn is not None
        tbl = self._get_lookup_table(cls)
        row = self.conn.execute(
            f"SELECT * FROM {tbl} WHERE id = ?", (str(obj_id),)
        ).fetchone()
        if row is None:
            return None
        if cls is Platform:
            return Platform(  # type: ignore[return-value]
                id=uuid.UUID(row["id"]),
                name=row["name"],
                specification_id=row["specification_id"] or "",
                icon=row["icon"] or "",
                cover=row["cover"] or "",
                background=row["background"] or "",
            )
        return cls(id=uuid.UUID(row["id"]), name=row["name"])  # type: ignore[return-value]

    def get_all_lookup(self, cls: Type[T]) -> list[T]:
        assert self.conn is not None
        tbl = self._get_lookup_table(cls)
        rows = self.conn.execute(f"SELECT * FROM {tbl}").fetchall()
        results: list[T] = []
        for row in rows:
            if cls is Platform:
                results.append(Platform(  # type: ignore[arg-type]
                    id=uuid.UUID(row["id"]),
                    name=row["name"],
                    specification_id=row["specification_id"] or "",
                    icon=row["icon"] or "",
                    cover=row["cover"] or "",
                    background=row["background"] or "",
                ))
            else:
                results.append(cls(id=uuid.UUID(row["id"]), name=row["name"]))  # type: ignore[arg-type]
        return results

    def find_lookup_by_name(self, cls: Type[T], name: str) -> T | None:
        assert self.conn is not None
        tbl = self._get_lookup_table(cls)
        row = self.conn.execute(
            f"SELECT * FROM {tbl} WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        if cls is Platform:
            return Platform(  # type: ignore[return-value]
                id=uuid.UUID(row["id"]),
                name=row["name"],
                specification_id=row["specification_id"] or "",
                icon=row["icon"] or "",
                cover=row["cover"] or "",
                background=row["background"] or "",
            )
        return cls(id=uuid.UUID(row["id"]), name=row["name"])  # type: ignore[return-value]

    def delete_lookup(self, cls: Type[T], obj_id: uuid.UUID) -> None:
        assert self.conn is not None
        tbl = self._get_lookup_table(cls)
        self.conn.execute(f"DELETE FROM {tbl} WHERE id = ?", (str(obj_id),))

    # ------------------------------------------------------------------ #
    # Convenience accessors for common lookups
    # ------------------------------------------------------------------ #

    def get_platform(self, obj_id: uuid.UUID) -> Platform | None:
        return self.get_lookup(Platform, obj_id)

    def get_source(self, obj_id: uuid.UUID) -> GameSource | None:
        return self.get_lookup(GameSource, obj_id)

    def get_company(self, obj_id: uuid.UUID) -> Company | None:
        return self.get_lookup(Company, obj_id)

    # ------------------------------------------------------------------ #
    # Bulk helpers
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Slim query for duplicate detection (memory-optimised)
    # ------------------------------------------------------------------ #

    _DETECTION_COLUMNS = (
        "id, name, game_id, plugin_id, hidden, is_installed, source_id, "
        "platform_ids, developer_ids, publisher_ids, genre_ids, "
        "release_date, modified, "
        "CASE WHEN description IS NOT NULL AND description != '' THEN 'Y' ELSE '' END AS description, "
        "cover_image, background_image, icon, "
        "critic_score, community_score, "
        "_normalized_name"
    )

    def _row_to_game_slim(self, row: sqlite3.Row) -> tuple[Game, str]:
        """Build a Game with only detection-relevant fields populated.

        Returns ``(game, normalized_name)``."""
        rd_raw = row["release_date"]
        release_date = ReleaseDate.deserialize(rd_raw) if rd_raw else None
        game = Game(
            id=_str_to_uuid(row["id"]),
            name=row["name"] or "",
            game_id=row["game_id"] or "",
            plugin_id=_str_to_uuid(row["plugin_id"]),
            hidden=_int_to_bool(row["hidden"]),
            is_installed=_int_to_bool(row["is_installed"]),
            source_id=_str_to_uuid(row["source_id"]),
            platform_ids=_json_to_uuid_list(row["platform_ids"]),
            developer_ids=_json_to_uuid_list(row["developer_ids"]),
            publisher_ids=_json_to_uuid_list(row["publisher_ids"]),
            genre_ids=_json_to_uuid_list(row["genre_ids"]),
            release_date=release_date,
            modified=_str_to_dt(row["modified"]),
            description=row["description"] or "",
            cover_image=row["cover_image"],
            background_image=row["background_image"],
            icon=row["icon"],
            critic_score=row["critic_score"],
            community_score=row["community_score"],
        )
        norm = row["_normalized_name"] or ""
        return game, norm

    def get_games_for_detection(self) -> tuple[list[Game], list[str]]:
        """Load games with only the columns needed for duplicate detection.

        Returns ``(games, normalized_names)``."""
        assert self.conn is not None
        cursor = self.conn.execute(
            f"SELECT {self._DETECTION_COLUMNS} FROM games"
        )
        games: list[Game] = []
        norms: list[str] = []
        for r in cursor:
            g, n = self._row_to_game_slim(r)
            games.append(g)
            norms.append(n)
        return games, norms

    def get_games_by_ids(self, game_ids: list[uuid.UUID]) -> list[Game]:
        assert self.conn is not None
        if not game_ids:
            return []
        placeholders = ", ".join(["?"] * len(game_ids))
        rows = self.conn.execute(
            f"SELECT * FROM games WHERE id IN ({placeholders})",
            [str(gid) for gid in game_ids],
        ).fetchall()
        return [self._row_to_game(r) for r in rows]
