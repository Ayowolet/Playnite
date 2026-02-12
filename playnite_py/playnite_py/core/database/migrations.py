"""
Database migration system for Playnite-Py.

Provides schema versioning and automatic migrations for SQLite databases.
Migrations are applied automatically when the database is opened.

Example:
    >>> from playnite_py.core.database.migrations import MigrationManager
    >>> manager = MigrationManager(engine)
    >>> manager.apply_migrations()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# Current schema version
CURRENT_VERSION = 1


@dataclass
class Migration:
    """Represents a database migration."""
    version: int
    description: str
    up: Callable[[Session], None]
    down: Callable[[Session], None] | None = None


class MigrationManager:
    """
    Manages database schema migrations.

    Tracks applied migrations in a _migrations table and applies
    pending migrations automatically.

    Attributes:
        engine: SQLAlchemy engine
        migrations: List of available migrations
    """

    def __init__(self, engine: "Engine") -> None:
        self.engine = engine
        self.migrations: list[Migration] = []
        self._register_builtin_migrations()

    def _register_builtin_migrations(self) -> None:
        """Register built-in migrations."""
        # Migration 1: Initial schema (handled by SQLAlchemy create_all)
        self.register(Migration(
            version=1,
            description="Initial schema",
            up=self._migration_1_up,
        ))

    def register(self, migration: Migration) -> None:
        """Register a migration."""
        self.migrations.append(migration)
        self.migrations.sort(key=lambda m: m.version)

    def get_current_version(self) -> int:
        """Get the current database schema version."""
        with Session(self.engine) as session:
            # Check if migrations table exists
            result = session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
            ))
            if not result.fetchone():
                return 0

            # Get max applied version
            result = session.execute(text(
                "SELECT MAX(version) FROM _migrations"
            ))
            row = result.fetchone()
            return row[0] if row and row[0] else 0

    def apply_migrations(self) -> list[int]:
        """
        Apply all pending migrations.

        Returns:
            List of applied migration versions
        """
        current = self.get_current_version()
        applied = []

        for migration in self.migrations:
            if migration.version > current:
                self._apply_migration(migration)
                applied.append(migration.version)

        if applied:
            logger.info(f"Applied migrations: {applied}")
        else:
            logger.debug(f"Database at version {current}, no migrations needed")

        return applied

    def _apply_migration(self, migration: Migration) -> None:
        """Apply a single migration."""
        logger.info(f"Applying migration {migration.version}: {migration.description}")

        with Session(self.engine) as session:
            # Ensure migrations table exists
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """))

            # Run the migration
            migration.up(session)

            # Record the migration
            session.execute(text("""
                INSERT INTO _migrations (version, description, applied_at)
                VALUES (:version, :description, :applied_at)
            """), {
                "version": migration.version,
                "description": migration.description,
                "applied_at": datetime.utcnow().isoformat(),
            })

            session.commit()

    def rollback(self, target_version: int) -> list[int]:
        """
        Rollback migrations to a target version.

        Args:
            target_version: Version to rollback to

        Returns:
            List of rolled back migration versions

        Raises:
            ValueError: If rollback not supported for a migration
        """
        current = self.get_current_version()
        rolled_back = []

        for migration in reversed(self.migrations):
            if migration.version > target_version and migration.version <= current:
                if migration.down is None:
                    raise ValueError(
                        f"Migration {migration.version} does not support rollback"
                    )
                self._rollback_migration(migration)
                rolled_back.append(migration.version)

        if rolled_back:
            logger.info(f"Rolled back migrations: {rolled_back}")

        return rolled_back

    def _rollback_migration(self, migration: Migration) -> None:
        """Rollback a single migration."""
        logger.info(f"Rolling back migration {migration.version}: {migration.description}")

        with Session(self.engine) as session:
            # Run the rollback
            if migration.down:
                migration.down(session)

            # Remove migration record
            session.execute(text(
                "DELETE FROM _migrations WHERE version = :version"
            ), {"version": migration.version})

            session.commit()

    # Built-in migrations
    @staticmethod
    def _migration_1_up(session: Session) -> None:
        """Initial schema migration - tables are created by SQLAlchemy."""
        # The initial schema is handled by Base.metadata.create_all()
        # This migration just marks the initial version
        pass


def apply_migrations_for_engine(engine: "Engine") -> list[int]:
    """
    Apply all pending migrations to an engine.

    Convenience function for automatic migration on database open.

    Args:
        engine: SQLAlchemy engine

    Returns:
        List of applied migration versions
    """
    manager = MigrationManager(engine)
    return manager.apply_migrations()
