"""Database engine and session management."""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from pathlib import Path
import logging

from ..models.base import Base
from ..config import SMART_COLLECTION_AUTO_UPDATE
from ..validation import ValidationError

logger = logging.getLogger(__name__)


class DatabaseEngine:
    """Manages database connections and sessions."""

    def __init__(self, db_path=None):
        """
        Initialize database engine with path validation.

        Args:
            db_path: Path to SQLite database file. If None, uses in-memory database.

        Raises:
            ValidationError: If db_path contains dangerous patterns or is invalid
        """
        if db_path is None:
            db_url = "sqlite:///:memory:"
        else:
            # Validate and sanitize the database path
            db_path = self._validate_db_path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"

        self.engine = create_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False}  # For SQLite
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)

    def _validate_db_path(self, db_path) -> Path:
        """
        Validate database path to prevent path traversal attacks.

        Args:
            db_path: Database path to validate

        Returns:
            Validated Path object

        Raises:
            ValidationError: If path is invalid or dangerous
        """
        try:
            # Convert to Path object
            db_path = Path(db_path)

            # Resolve to absolute path to detect traversal attempts
            resolved_path = db_path.resolve()

            # Check for null bytes (common in path traversal attacks)
            if '\x00' in str(db_path):
                raise ValidationError("Database path contains null bytes")

            # Ensure the file extension is .db (optional but good practice)
            if resolved_path.suffix and resolved_path.suffix.lower() not in ['.db', '.sqlite', '.sqlite3']:
                logger.warning(f"Database path has unusual extension: {resolved_path.suffix}")

            # Check if path is trying to escape current directory using ../
            path_parts = db_path.parts
            if '..' in path_parts:
                raise ValidationError("Database path cannot contain '..' (parent directory references)")

            logger.info(f"Validated database path: {resolved_path}")
            return resolved_path

        except (OSError, ValueError) as e:
            raise ValidationError(f"Invalid database path: {e}")

    def create_tables(self, register_events=True):
        """
        Create all database tables.

        Args:
            register_events: Whether to register smart collection event listeners
        """
        Base.metadata.create_all(self.engine)

        if register_events and SMART_COLLECTION_AUTO_UPDATE:
            from .events import register_smart_collection_events
            session = self.get_session()
            register_smart_collection_events(session, enabled=True)

    def drop_tables(self):
        """Drop all database tables."""
        Base.metadata.drop_all(self.engine)

    def get_session(self):
        """Get a new database session."""
        return self.Session()

    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope for database operations.

        Usage:
            with engine.session_scope() as session:
                # Do work
                session.add(obj)
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class DatabaseManager:
    """
    Thread-safe singleton manager for database engine lifecycle.

    Provides a testable, dependency-injectable alternative to global state.
    """

    _instance = None
    _lock = None

    def __new__(cls):
        """Ensure only one instance exists (thread-safe singleton)."""
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()

        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._engine = None
                cls._instance._initialized = False

        return cls._instance

    def initialize(self, db_path=None, auto_update_collections=True):
        """
        Initialize the database engine.

        Args:
            db_path: Path to database file (None for in-memory)
            auto_update_collections: Whether to enable automatic smart collection updates

        Returns:
            DatabaseEngine instance

        Raises:
            RuntimeError: If already initialized
        """
        if self._initialized:
            logger.warning("Database already initialized. Use reset() to reinitialize.")
            return self._engine

        self._engine = DatabaseEngine(db_path)
        self._engine.create_tables(register_events=auto_update_collections)
        self._initialized = True
        logger.info("Database initialized successfully")
        return self._engine

    def get_engine(self):
        """
        Get the database engine instance.

        Returns:
            DatabaseEngine instance

        Raises:
            RuntimeError: If not initialized
        """
        if not self._initialized or self._engine is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._engine

    def get_session(self):
        """
        Get a new database session.

        Returns:
            SQLAlchemy session
        """
        return self.get_engine().get_session()

    def reset(self):
        """
        Reset the database manager (useful for testing).

        Closes all sessions and drops the engine.
        """
        if self._engine is not None:
            # Close all sessions
            self._engine.Session.remove()
            # Dispose of engine connections
            self._engine.engine.dispose()
            logger.info("Database manager reset")

        self._engine = None
        self._initialized = False

    @classmethod
    def reset_instance(cls):
        """
        Reset the singleton instance (for testing).

        Warning: This is intended for testing only.
        """
        if cls._lock is not None:
            with cls._lock:
                if cls._instance is not None:
                    cls._instance.reset()
                cls._instance = None


# Convenience functions for backward compatibility
def init_database(db_path=None, auto_update_collections=True):
    """
    Initialize the database (convenience function).

    Args:
        db_path: Path to database file (None for in-memory)
        auto_update_collections: Whether to enable automatic smart collection updates

    Returns:
        DatabaseEngine instance
    """
    manager = DatabaseManager()
    return manager.initialize(db_path, auto_update_collections)


def get_engine():
    """
    Get the database engine (convenience function).

    Returns:
        DatabaseEngine instance

    Raises:
        RuntimeError: If not initialized
    """
    manager = DatabaseManager()
    return manager.get_engine()


def get_session():
    """
    Get a new database session (convenience function).

    Returns:
        SQLAlchemy session
    """
    manager = DatabaseManager()
    return manager.get_session()
