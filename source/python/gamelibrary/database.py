"""SQLite database management for game library."""

import json
import logging
import sqlite3
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".gamelibrary" / "gamelibrary.db"

SCHEMA_VERSION = 2

SCHEMA_SQL = """
-- Platform configurations
CREATE TABLE IF NOT EXISTS platforms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    api_type TEXT NOT NULL,
    credentials TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Games from each platform
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id INTEGER NOT NULL,
    external_game_id TEXT NOT NULL,
    name TEXT NOT NULL,
    total_achievements INTEGER DEFAULT 0,
    icon_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (platform_id) REFERENCES platforms(id),
    UNIQUE(platform_id, external_game_id)
);

-- Achievement definitions
CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    external_achievement_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    icon_url TEXT,
    locked_icon_url TEXT,
    global_completion_pct REAL DEFAULT 0.0,
    difficulty_score REAL DEFAULT 0.0,
    is_hidden INTEGER DEFAULT 0,
    max_progress INTEGER DEFAULT 0,
    category TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    UNIQUE(game_id, external_achievement_id)
);

-- Achievement unlock status per user
CREATE TABLE IF NOT EXISTS achievement_unlocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    achievement_id INTEGER NOT NULL,
    unlocked INTEGER DEFAULT 0,
    unlock_date TEXT,
    current_progress INTEGER DEFAULT 0,
    source TEXT DEFAULT 'api',
    synced_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (achievement_id) REFERENCES achievements(id) ON DELETE CASCADE,
    UNIQUE(achievement_id)
);

-- Sync history log
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id INTEGER,
    sync_type TEXT DEFAULT 'full',
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    achievements_found INTEGER DEFAULT 0,
    new_unlocks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

-- Achievement milestones
CREATE TABLE IF NOT EXISTS achievement_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_type TEXT NOT NULL,
    milestone_value TEXT NOT NULL,
    reached_at TEXT DEFAULT (datetime('now')),
    details TEXT DEFAULT '{}'
);

-- Notification log
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);

-- Backup records
CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    backup_type TEXT DEFAULT 'full',
    file_path TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    size_bytes INTEGER DEFAULT 0,
    compressed_size INTEGER DEFAULT 0,
    is_encrypted INTEGER DEFAULT 0,
    destination TEXT DEFAULT 'local',
    checksum TEXT,
    parent_backup_id INTEGER,
    status TEXT DEFAULT 'completed',
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (profile_id) REFERENCES backup_profiles(id),
    FOREIGN KEY (parent_backup_id) REFERENCES backups(id)
);

-- Backup profiles
CREATE TABLE IF NOT EXISTS backup_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    schedule_cron TEXT,
    retention_days INTEGER DEFAULT 30,
    max_backups INTEGER DEFAULT 10,
    destinations TEXT DEFAULT '["local"]',
    include_patterns TEXT DEFAULT '["*"]',
    exclude_patterns TEXT DEFAULT '[]',
    encrypt INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Backup items (what's in each backup)
CREATE TABLE IF NOT EXISTS backup_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id INTEGER NOT NULL,
    item_path TEXT NOT NULL,
    item_type TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    checksum TEXT,
    modified_at TEXT,
    FOREIGN KEY (backup_id) REFERENCES backups(id) ON DELETE CASCADE
);

-- Backup destinations
CREATE TABLE IF NOT EXISTS backup_destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    dest_type TEXT NOT NULL,
    config TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Restore history
CREATE TABLE IF NOT EXISTS restore_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id INTEGER NOT NULL,
    restored_at TEXT DEFAULT (datetime('now')),
    items_restored INTEGER DEFAULT 0,
    components TEXT DEFAULT '[]',
    status TEXT DEFAULT 'completed',
    error_message TEXT,
    FOREIGN KEY (backup_id) REFERENCES backups(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_games_platform ON games(platform_id);
CREATE INDEX IF NOT EXISTS idx_achievements_game ON achievements(game_id);
CREATE INDEX IF NOT EXISTS idx_achievement_unlocks_achievement ON achievement_unlocks(achievement_id);
CREATE INDEX IF NOT EXISTS idx_achievements_global_pct ON achievements(global_completion_pct);
CREATE INDEX IF NOT EXISTS idx_achievement_unlocks_date ON achievement_unlocks(unlock_date);
CREATE INDEX IF NOT EXISTS idx_sync_history_platform ON sync_history(platform_id);
CREATE INDEX IF NOT EXISTS idx_backups_profile ON backups(profile_id);
CREATE INDEX IF NOT EXISTS idx_backup_items_backup ON backup_items(backup_id);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT DEFAULT (datetime('now'))
);
"""


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._apply_migrations(conn)

    def _apply_migrations(self, conn: sqlite3.Connection):
        """Apply any pending schema migrations."""
        cursor = conn.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        current_version = row[0] if row and row[0] is not None else 0

        if current_version < SCHEMA_VERSION:
            logger.info(
                "Upgrading schema from version %d to %d",
                current_version,
                SCHEMA_VERSION,
            )
            if current_version < 2:
                self._migrate_v2_encrypt_credentials(conn)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )

    def _migrate_v2_encrypt_credentials(self, conn: sqlite3.Connection):
        """Encrypt any plain-text credentials in the platforms table."""
        from .achievements.credential_store import encrypt_credentials, is_encrypted

        rows = conn.execute("SELECT id, credentials FROM platforms").fetchall()
        for row in rows:
            creds_value = row["credentials"] if isinstance(row, sqlite3.Row) else row[1]
            row_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            if creds_value and not is_encrypted(creds_value):
                try:
                    creds = json.loads(creds_value)
                    encrypted = encrypt_credentials(creds)
                    conn.execute(
                        "UPDATE platforms SET credentials = ? WHERE id = ?",
                        (encrypted, row_id),
                    )
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(
                        "Could not migrate credentials for platform %s: %s",
                        row_id, e,
                    )

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Database transaction failed, rolled back")
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    def execute_insert(self, sql: str, params: tuple = ()) -> int:
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid

    def execute_many(self, sql: str, params_list: list[tuple]):
        with self.connect() as conn:
            conn.executemany(sql, params_list)

    def get_db_path(self) -> Path:
        return self.db_path
