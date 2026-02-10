"""
SQLite-backed persistence layer.

All domain objects are stored as JSON blobs plus indexed scalar columns so
queries can filter on common fields without deserialising everything.

Schema
------
games               — game records
user_profiles       — user profiles
play_sessions       — individual play sessions
recommendation_feedback — user feedback on recommendations
recommendation_history  — exported batches of recommendations
capture_records     — metadata about captured media files
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

log = logging.getLogger(__name__)

from ..models.game import Game
from ..models.user_profile import PlaySession, RecommendationFeedback, UserProfile


SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    source          TEXT,
    is_installed    INTEGER NOT NULL DEFAULT 0,
    is_owned        INTEGER NOT NULL DEFAULT 1,
    in_wishlist     INTEGER NOT NULL DEFAULT 0,
    is_played       INTEGER NOT NULL DEFAULT 0,
    play_count      INTEGER NOT NULL DEFAULT 0,
    playtime_seconds INTEGER NOT NULL DEFAULT 0,
    last_played     TEXT,
    hidden          INTEGER NOT NULL DEFAULT 0,
    favorite        INTEGER NOT NULL DEFAULT 0,
    added           TEXT,
    modified        TEXT,
    data            TEXT NOT NULL   -- full JSON blob
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL,
    current_mood    TEXT,
    updated_at      TEXT,
    data            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS play_sessions (
    id              TEXT PRIMARY KEY,
    game_id         TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    start_time      TEXT NOT NULL,
    end_time        TEXT,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recommendation_feedback (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    game_id         TEXT NOT NULL,
    action          TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    data            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_history (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    generated_at    TEXT NOT NULL,
    mood            TEXT,
    data            TEXT NOT NULL   -- JSON list of recommendation dicts
);

CREATE TABLE IF NOT EXISTS capture_records (
    id              TEXT PRIMARY KEY,
    game_id         TEXT,
    game_name       TEXT,
    capture_type    TEXT NOT NULL,  -- screenshot | video | replay
    file_path       TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    captured_at     TEXT NOT NULL,
    tags            TEXT,           -- JSON list
    metadata        TEXT            -- JSON dict
);

CREATE INDEX IF NOT EXISTS idx_games_source ON games(source);
CREATE INDEX IF NOT EXISTS idx_games_played ON games(is_played);
CREATE INDEX IF NOT EXISTS idx_play_sessions_game ON play_sessions(game_id);
CREATE INDEX IF NOT EXISTS idx_play_sessions_user ON play_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON recommendation_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_captures_game ON capture_records(game_id);
CREATE INDEX IF NOT EXISTS idx_captures_type ON capture_records(capture_type);
"""


# Migration dispatch table: (from_version, to_version) → callable(conn)
# Add entries here when the schema needs to evolve.
_MIGRATIONS: Dict[Tuple[int, int], Any] = {
    # Example entry (uncomment and implement when bumping SCHEMA_VERSION):
    # (1, 2): _migrate_1_to_2,
}


def _dt_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        from dateutil.parser import parse as parse_dt
        return parse_dt(s)
    except Exception:
        log.warning("Failed to parse datetime string %r — stored value will be lost", s, exc_info=True)
        return None


class GameDatabase:
    """
    Thin wrapper around a SQLite connection.
    All public methods accept / return domain objects.

    Thread safety: a single connection is shared across threads, protected by
    an ``RLock``.  All reads and writes acquire the lock so concurrent callers
    from background threads (e.g. buffer/hotkey threads) are safe.
    """

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            # Write schema version if not already present; otherwise migrate if needed
            row = self._conn.execute("SELECT version FROM schema_version").fetchone()
            if not row:
                self._conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
                )
                self._conn.commit()
            else:
                stored = int(row[0])
                if stored < SCHEMA_VERSION:
                    self._run_migrations(stored)

    def _run_migrations(self, current_version: int) -> None:
        """Apply all pending migrations from current_version up to SCHEMA_VERSION."""
        version = current_version
        while version < SCHEMA_VERSION:
            next_version = version + 1
            migration_fn = _MIGRATIONS.get((version, next_version))
            if migration_fn is None:
                log.warning(
                    "No migration found from schema version %d to %d; skipping",
                    version, next_version,
                )
                break
            log.info("Applying database migration %d → %d", version, next_version)
            migration_fn(self._conn)
            self._conn.execute(
                "UPDATE schema_version SET version = ?", (next_version,)
            )
            self._conn.commit()
            version = next_version

    def get_schema_version(self) -> int:
        """Return the stored schema version, or 0 if unset."""
        row = self._execute_one("SELECT version FROM schema_version")
        return int(row[0]) if row else 0

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Cursor, None, None]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def _execute(self, sql: str, params: Any = ()) -> List[sqlite3.Row]:
        """Execute a read-only query under the lock and return all rows."""
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _execute_one(self, sql: str, params: Any = ()) -> Optional[sqlite3.Row]:
        """Execute a read-only query under the lock and return the first row."""
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ================================================================== #
    # Games                                                                #
    # ================================================================== #

    def upsert_game(self, game: Game) -> None:
        log.debug("upsert_game: id=%s name=%r", game.id, game.name)
        with self._tx() as cur:
            cur.execute(
                """
                INSERT INTO games
                    (id, name, source, is_installed, is_owned, in_wishlist,
                     is_played, play_count, playtime_seconds, last_played,
                     hidden, favorite, added, modified, data)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    source=excluded.source,
                    is_installed=excluded.is_installed,
                    is_owned=excluded.is_owned,
                    in_wishlist=excluded.in_wishlist,
                    is_played=excluded.is_played,
                    play_count=excluded.play_count,
                    playtime_seconds=excluded.playtime_seconds,
                    last_played=excluded.last_played,
                    hidden=excluded.hidden,
                    favorite=excluded.favorite,
                    modified=excluded.modified,
                    data=excluded.data
                """,
                (
                    game.id, game.name, game.source,
                    int(game.is_installed), int(game.is_owned),
                    int(game.in_wishlist), int(game.is_played),
                    game.play_count, game.playtime_seconds,
                    _dt_str(game.last_played),
                    int(game.hidden), int(game.favorite),
                    _dt_str(game.added), _dt_str(game.modified),
                    json.dumps(game.to_dict()),
                ),
            )

    def get_game(self, game_id: str) -> Optional[Game]:
        log.debug("get_game: id=%s", game_id)
        row = self._execute_one("SELECT data FROM games WHERE id=?", (game_id,))
        return Game.from_dict(json.loads(row["data"])) if row else None

    def delete_game(self, game_id: str) -> bool:
        with self._tx() as cur:
            cur.execute("DELETE FROM games WHERE id=?", (game_id,))
            return cur.rowcount > 0

    def list_games(
        self,
        *,
        owned_only: bool = False,
        installed_only: bool = False,
        played_only: bool = False,
        unplayed_only: bool = False,
        in_wishlist: Optional[bool] = None,
        source: Optional[str] = None,
        hidden: bool = False,
    ) -> List[Game]:
        clauses: List[str] = []
        params: List[Any] = []

        if owned_only:
            clauses.append("is_owned=1")
        if installed_only:
            clauses.append("is_installed=1")
        if played_only:
            clauses.append("is_played=1")
        if unplayed_only:
            clauses.append("is_played=0")
        if in_wishlist is not None:
            clauses.append("in_wishlist=?")
            params.append(int(in_wishlist))
        if source is not None:
            clauses.append("source=?")
            params.append(source)
        if not hidden:
            clauses.append("hidden=0")

        sql = "SELECT data FROM games"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        rows = self._execute(sql, params)
        return [Game.from_dict(json.loads(r["data"])) for r in rows]

    def get_game_count(self) -> int:
        row = self._execute_one("SELECT COUNT(*) FROM games WHERE hidden=0")
        return int(row[0]) if row else 0

    # ================================================================== #
    # User Profiles                                                        #
    # ================================================================== #

    def upsert_user_profile(self, profile: UserProfile) -> None:
        with self._tx() as cur:
            cur.execute(
                """
                INSERT INTO user_profiles (id, username, current_mood, updated_at, data)
                VALUES (?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    current_mood=excluded.current_mood,
                    updated_at=excluded.updated_at,
                    data=excluded.data
                """,
                (
                    profile.id, profile.username, profile.current_mood,
                    _dt_str(profile.updated_at), json.dumps(profile.to_dict()),
                ),
            )

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        row = self._execute_one("SELECT data FROM user_profiles WHERE id=?", (user_id,))
        return UserProfile.from_dict(json.loads(row["data"])) if row else None

    def get_default_profile(self) -> Optional[UserProfile]:
        row = self._execute_one(
            "SELECT data FROM user_profiles ORDER BY updated_at DESC LIMIT 1"
        )
        return UserProfile.from_dict(json.loads(row["data"])) if row else None

    def list_user_profiles(self) -> List[UserProfile]:
        rows = self._execute("SELECT data FROM user_profiles")
        return [UserProfile.from_dict(json.loads(r["data"])) for r in rows]

    # ================================================================== #
    # Play Sessions                                                        #
    # ================================================================== #

    def save_play_session(self, session: PlaySession) -> None:
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO play_sessions
                    (id, game_id, user_id, start_time, end_time, duration_seconds)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    session.id, session.game_id, session.user_id,
                    _dt_str(session.start_time), _dt_str(session.end_time),
                    session.duration_seconds,
                ),
            )

    def get_play_sessions(
        self, *, game_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> List[PlaySession]:
        clauses: List[str] = []
        params: List[Any] = []
        if game_id:
            clauses.append("game_id=?")
            params.append(game_id)
        if user_id:
            clauses.append("user_id=?")
            params.append(user_id)
        sql = "SELECT * FROM play_sessions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY start_time DESC"
        rows = self._execute(sql, params)
        return [
            PlaySession(
                id=r["id"],
                game_id=r["game_id"],
                user_id=r["user_id"],
                start_time=_parse_dt(r["start_time"]) or datetime.utcnow(),
                end_time=_parse_dt(r["end_time"]),
                duration_seconds=r["duration_seconds"],
            )
            for r in rows
        ]

    # ================================================================== #
    # Recommendation Feedback                                              #
    # ================================================================== #

    def save_feedback(self, fb: RecommendationFeedback) -> None:
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO recommendation_feedback
                    (id, user_id, recommendation_id, game_id, action, timestamp, data)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    fb.id, fb.user_id, fb.recommendation_id, fb.game_id,
                    fb.action, _dt_str(fb.timestamp), json.dumps(fb.to_dict()),
                ),
            )

    def get_feedback(self, user_id: str) -> List[RecommendationFeedback]:
        rows = self._execute(
            "SELECT data FROM recommendation_feedback WHERE user_id=? ORDER BY timestamp DESC",
            (user_id,),
        )
        return [RecommendationFeedback.from_dict(json.loads(r["data"])) for r in rows]

    # ================================================================== #
    # Recommendation History                                               #
    # ================================================================== #

    def save_recommendation_batch(
        self,
        rec_id: str,
        user_id: str,
        recommendations: List[Dict[str, Any]],
        mood: Optional[str] = None,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO recommendation_history
                    (id, user_id, generated_at, mood, data)
                VALUES (?,?,?,?,?)
                """,
                (
                    rec_id, user_id, datetime.utcnow().isoformat(),
                    mood, json.dumps(recommendations),
                ),
            )

    def get_recommendation_history(
        self, user_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        rows = self._execute(
            """
            SELECT id, generated_at, mood, data FROM recommendation_history
            WHERE user_id=? ORDER BY generated_at DESC LIMIT ?
            """,
            (user_id, limit),
        )
        result = []
        for r in rows:
            result.append(
                {
                    "id": r["id"],
                    "generated_at": r["generated_at"],
                    "mood": r["mood"],
                    "recommendations": json.loads(r["data"]),
                }
            )
        return result

    # ================================================================== #
    # Capture Records                                                      #
    # ================================================================== #

    def save_capture_record(
        self,
        record_id: str,
        game_id: Optional[str],
        game_name: Optional[str],
        capture_type: str,
        file_path: str,
        file_size_bytes: int,
        captured_at: datetime,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        log.debug("save_capture_record: id=%s type=%s game=%r", record_id, capture_type, game_name)
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO capture_records
                    (id, game_id, game_name, capture_type, file_path,
                     file_size_bytes, captured_at, tags, metadata)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    record_id, game_id, game_name, capture_type, file_path,
                    file_size_bytes, _dt_str(captured_at),
                    json.dumps(tags or []), json.dumps(metadata or {}),
                ),
            )

    def list_capture_records(
        self,
        *,
        game_id: Optional[str] = None,
        capture_type: Optional[str] = None,
        tag: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        log.debug("list_capture_records: game_id=%s type=%s limit=%d", game_id, capture_type, limit)
        clauses: List[str] = []
        params: List[Any] = []
        if game_id:
            clauses.append("game_id=?")
            params.append(game_id)
        if capture_type:
            clauses.append("capture_type=?")
            params.append(capture_type)
        if tag:
            clauses.append("EXISTS (SELECT 1 FROM json_each(tags) WHERE value=?)")
            params.append(tag)
        if since:
            clauses.append("captured_at >= ?")
            params.append(_dt_str(since))
        if until:
            clauses.append("captured_at <= ?")
            params.append(_dt_str(until))
        sql = "SELECT * FROM capture_records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._execute(sql, params)
        return [
            {
                "id": r["id"],
                "game_id": r["game_id"],
                "game_name": r["game_name"],
                "capture_type": r["capture_type"],
                "file_path": r["file_path"],
                "file_size_bytes": r["file_size_bytes"],
                "captured_at": r["captured_at"],
                "tags": json.loads(r["tags"] or "[]"),
                "metadata": json.loads(r["metadata"] or "{}"),
            }
            for r in rows
        ]

    def delete_capture_record(self, record_id: str) -> bool:
        with self._tx() as cur:
            cur.execute("DELETE FROM capture_records WHERE id=?", (record_id,))
            return cur.rowcount > 0

    def get_total_capture_size_bytes(self) -> int:
        row = self._execute_one(
            "SELECT COALESCE(SUM(file_size_bytes), 0) as total FROM capture_records"
        )
        return int(row["total"]) if row else 0

    # ================================================================== #
    # Statistics                                                           #
    # ================================================================== #

    def get_library_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats: Dict[str, Any] = {}
            stats["total_games"] = self._conn.execute(
                "SELECT COUNT(*) FROM games WHERE hidden=0"
            ).fetchone()[0]
            stats["owned_games"] = self._conn.execute(
                "SELECT COUNT(*) FROM games WHERE is_owned=1 AND hidden=0"
            ).fetchone()[0]
            stats["played_games"] = self._conn.execute(
                "SELECT COUNT(*) FROM games WHERE is_played=1 AND hidden=0"
            ).fetchone()[0]
            stats["total_playtime_hours"] = round(
                (
                    self._conn.execute(
                        "SELECT COALESCE(SUM(playtime_seconds),0) FROM games WHERE hidden=0"
                    ).fetchone()[0]
                )
                / 3600,
                1,
            )
            stats["wishlist_count"] = self._conn.execute(
                "SELECT COUNT(*) FROM games WHERE in_wishlist=1"
            ).fetchone()[0]
        return stats
