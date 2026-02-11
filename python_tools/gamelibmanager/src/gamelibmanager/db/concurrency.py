"""Retry utilities for transient SQLite lock errors."""

from __future__ import annotations

import logging
import sqlite3
import time
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 0.1  # seconds
DEFAULT_MAX_DELAY = 5.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


class DatabaseLockedError(Exception):
    """Raised when all retry attempts are exhausted for a locked database."""

    def __init__(
        self,
        operation: str,
        attempts: int,
        original: sqlite3.OperationalError,
    ):
        self.operation = operation
        self.attempts = attempts
        self.original = original
        super().__init__(
            f"Database is locked after {attempts} attempt(s) during "
            f"'{operation}'. Another application (e.g. Playnite) may have "
            f"the database open. Close it and retry."
        )


def is_lock_error(exc: Exception) -> bool:
    """Return True if *exc* is a transient SQLite lock error."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg


def retry_on_lock(
    operation_name: str = "database operation",
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
) -> Callable:
    """Decorator that retries a function on transient SQLite lock errors.

    Uses exponential backoff:
        delay = min(base_delay * backoff_factor ** attempt, max_delay)
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: sqlite3.OperationalError | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    if not is_lock_error(exc):
                        raise
                    last_exc = exc
                    if attempt < max_retries:
                        delay = min(
                            base_delay * (backoff_factor ** attempt),
                            max_delay,
                        )
                        logger.warning(
                            "Database locked during %s (attempt %d/%d), "
                            "retrying in %.2fs...",
                            operation_name,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
            assert last_exc is not None
            raise DatabaseLockedError(operation_name, max_retries + 1, last_exc)

        return wrapper

    return decorator


def execute_with_retry(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    operation_name: str = "SQL execute",
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> sqlite3.Cursor:
    """Execute a single SQL statement with retry-on-lock."""

    @retry_on_lock(operation_name, max_retries, base_delay)
    def _do() -> sqlite3.Cursor:
        return conn.execute(sql, params)

    return _do()
