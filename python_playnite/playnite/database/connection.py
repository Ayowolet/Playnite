"""Database session factory and initialisation helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from playnite.database.models import Base

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Engine


def _enable_wal_mode(dbapi_conn, _connection_record) -> None:
    """Enable WAL journal mode for better concurrent read performance."""
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


class DatabaseManager:
    """Manages the SQLAlchemy engine and session factory."""

    def __init__(self, database_path: str) -> None:
        self._path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine: Engine = create_engine(
            f"sqlite:///{database_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        event.listen(self._engine, "connect", _enable_wal_mode)
        self._SessionFactory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            # Prevent attribute expiry after commit so ORM objects remain readable
            # inside the same 'with get_session()' block.
            expire_on_commit=False,
        )

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create all tables if they don't exist yet."""
        Base.metadata.create_all(self._engine)

    def drop_all(self) -> None:
        """Drop all tables (use only in tests)."""
        Base.metadata.drop_all(self._engine)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Provide a transactional session scope."""
        session: Session = self._SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def database_path(self) -> str:
        return self._path
