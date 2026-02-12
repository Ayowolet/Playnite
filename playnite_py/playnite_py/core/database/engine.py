"""
Database engine and session management for Playnite-Py.

This module provides database connection management, session handling,
and utilities for creating profile-isolated databases.

Example:
    >>> from playnite_py.core.database.engine import DatabaseEngine
    >>> engine = DatabaseEngine.create_for_profile("/path/to/profile")
    >>> with engine.session() as session:
    ...     # perform database operations
    ...     pass
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from sqlalchemy import Engine

from playnite_py.core.database.models import Base

logger = logging.getLogger(__name__)


def get_database_url(profile_path: Path, db_name: str = "library.db") -> str:
    """
    Generate a SQLite database URL for a profile.

    Args:
        profile_path: Path to the profile's data directory
        db_name: Name of the database file

    Returns:
        SQLite connection URL string

    Example:
        >>> url = get_database_url(Path("/data/profile1"))
        >>> url
        'sqlite:////data/profile1/library.db'
    """
    db_path = profile_path / db_name
    return f"sqlite:///{db_path}"


def create_engine_for_profile(
    profile_path: Path,
    db_name: str = "library.db",
    echo: bool = False,
    in_memory: bool = False,
) -> "Engine":
    """
    Create a SQLAlchemy engine for a profile's database.

    Creates the database file and parent directories if they don't exist.
    Configures SQLite for optimal performance with WAL mode and
    appropriate pragmas.

    Args:
        profile_path: Path to the profile's data directory
        db_name: Name of the database file
        echo: Whether to log SQL statements
        in_memory: Use in-memory database (for testing)

    Returns:
        Configured SQLAlchemy Engine

    Example:
        >>> engine = create_engine_for_profile(Path("/data/profile1"))
        >>> Base.metadata.create_all(engine)
    """
    if in_memory:
        # In-memory database for testing
        url = "sqlite:///:memory:"
        engine = create_engine(
            url,
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # Ensure directory exists
        profile_path.mkdir(parents=True, exist_ok=True)

        url = get_database_url(profile_path, db_name)
        engine = create_engine(
            url,
            echo=echo,
            connect_args={"check_same_thread": False},
        )

    # Configure SQLite pragmas for performance
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Configure SQLite pragmas on connection."""
        cursor = dbapi_connection.cursor()
        # Enable WAL mode for better concurrent access
        cursor.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        # Set synchronous to NORMAL for better performance
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Increase cache size (negative value = KiB)
        cursor.execute("PRAGMA cache_size=-64000")
        # Enable memory-mapped I/O
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.close()

    return engine


class DatabaseEngine:
    """
    Database engine wrapper with session management.

    Provides a high-level interface for database operations with
    automatic session management and transaction handling.

    Attributes:
        engine: SQLAlchemy engine instance
        _session_factory: Session factory for creating sessions

    Example:
        >>> db = DatabaseEngine.create_for_profile(Path("/data/profile"))
        >>> with db.session() as session:
        ...     games = session.query(GameModel).all()
    """

    def __init__(self, engine: "Engine") -> None:
        """
        Initialize the database engine wrapper.

        Args:
            engine: SQLAlchemy engine to wrap
        """
        self.engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @classmethod
    def create_for_profile(
        cls,
        profile_path: Path,
        db_name: str = "library.db",
        echo: bool = False,
        in_memory: bool = False,
    ) -> "DatabaseEngine":
        """
        Create a DatabaseEngine for a profile.

        Creates the database schema if it doesn't exist.

        Args:
            profile_path: Path to the profile's data directory
            db_name: Name of the database file
            echo: Whether to log SQL statements
            in_memory: Use in-memory database (for testing)

        Returns:
            Configured DatabaseEngine instance

        Example:
            >>> db = DatabaseEngine.create_for_profile(Path("/data/profile1"))
        """
        engine = create_engine_for_profile(profile_path, db_name, echo, in_memory)
        Base.metadata.create_all(engine)
        return cls(engine)

    @classmethod
    def create_in_memory(cls, echo: bool = False) -> "DatabaseEngine":
        """
        Create an in-memory DatabaseEngine for testing.

        Args:
            echo: Whether to log SQL statements

        Returns:
            In-memory DatabaseEngine instance
        """
        return cls.create_for_profile(
            Path("/tmp"), db_name="test.db", echo=echo, in_memory=True
        )

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Create a database session context manager.

        Automatically commits on success and rolls back on error.

        Yields:
            SQLAlchemy Session instance

        Example:
            >>> with db.session() as session:
            ...     game = GameModel(name="Test")
            ...     session.add(game)
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error, rolling back: {e}")
            raise
        finally:
            session.close()

    def create_session(self) -> Session:
        """
        Create a new session without context manager.

        The caller is responsible for committing/rolling back
        and closing the session.

        Returns:
            New Session instance
        """
        return self._session_factory()

    def execute_raw(self, sql: str) -> None:
        """
        Execute raw SQL statement.

        Args:
            sql: SQL statement to execute

        Example:
            >>> db.execute_raw("VACUUM")
        """
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()

    def get_database_size(self) -> int:
        """
        Get the size of the database file in bytes.

        Returns:
            Database file size in bytes, or 0 for in-memory databases
        """
        url = str(self.engine.url)
        if ":memory:" in url:
            return 0

        # Extract path from sqlite URL
        db_path = url.replace("sqlite:///", "")
        path = Path(db_path)
        if path.exists():
            return path.stat().st_size
        return 0

    def vacuum(self) -> None:
        """
        Run VACUUM to optimize database.

        Reclaims unused space and defragments the database file.
        """
        self.execute_raw("VACUUM")

    def backup(self, backup_path: Path) -> None:
        """
        Create a backup of the database.

        Uses SQLite's backup API for a consistent snapshot.

        Args:
            backup_path: Path for the backup file

        Example:
            >>> db.backup(Path("/backups/library_backup.db"))
        """
        import sqlite3

        url = str(self.engine.url)
        if ":memory:" in url:
            raise ValueError("Cannot backup in-memory database")

        db_path = url.replace("sqlite:///", "")

        # Ensure backup directory exists
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        # Use SQLite backup API
        source = sqlite3.connect(db_path)
        dest = sqlite3.connect(str(backup_path))
        source.backup(dest)
        dest.close()
        source.close()

        logger.info(f"Database backed up to {backup_path}")

    def close(self) -> None:
        """Close the database engine and all connections."""
        self.engine.dispose()
