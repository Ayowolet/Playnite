"""Tests for concurrency utilities (retry-on-lock, DatabaseLockedError)."""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from gamelibmanager.db.concurrency import (
    DatabaseLockedError,
    execute_with_retry,
    is_lock_error,
    retry_on_lock,
)


# ------------------------------------------------------------------ #
# is_lock_error
# ------------------------------------------------------------------ #

class TestIsLockError:
    def test_true_for_database_is_locked(self):
        exc = sqlite3.OperationalError("database is locked")
        assert is_lock_error(exc) is True

    def test_true_for_database_table_is_locked(self):
        exc = sqlite3.OperationalError("database table is locked")
        assert is_lock_error(exc) is True

    def test_false_for_other_operational_error(self):
        exc = sqlite3.OperationalError("no such table: foo")
        assert is_lock_error(exc) is False

    def test_false_for_non_operational_error(self):
        exc = ValueError("database is locked")
        assert is_lock_error(exc) is False

    def test_false_for_integrity_error(self):
        exc = sqlite3.IntegrityError("UNIQUE constraint failed")
        assert is_lock_error(exc) is False


# ------------------------------------------------------------------ #
# retry_on_lock decorator
# ------------------------------------------------------------------ #

class TestRetryOnLock:
    def test_succeeds_on_first_attempt(self):
        @retry_on_lock("test")
        def always_ok():
            return 42

        assert always_ok() == 42

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_retries_then_succeeds(self, mock_sleep):
        call_count = 0

        @retry_on_lock("test op", max_retries=3, base_delay=0.1)
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        assert fail_twice() == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        @retry_on_lock("test op", max_retries=2, base_delay=0.01)
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(DatabaseLockedError) as exc_info:
            always_locked()
        assert exc_info.value.attempts == 3  # 1 initial + 2 retries
        assert "test op" in str(exc_info.value)

    def test_does_not_retry_non_lock_operational_error(self):
        @retry_on_lock("test", max_retries=3)
        def schema_error():
            raise sqlite3.OperationalError("no such table: foo")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            schema_error()

    def test_does_not_retry_other_exception(self):
        @retry_on_lock("test", max_retries=3)
        def type_error():
            raise TypeError("bad type")

        with pytest.raises(TypeError):
            type_error()

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_respects_max_retries(self, mock_sleep):
        attempts = 0

        @retry_on_lock("test", max_retries=1, base_delay=0.01)
        def fail():
            nonlocal attempts
            attempts += 1
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(DatabaseLockedError):
            fail()
        assert attempts == 2  # 1 initial + 1 retry

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_backoff_increases(self, mock_sleep):
        @retry_on_lock("test", max_retries=3, base_delay=0.1, backoff_factor=2.0)
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(DatabaseLockedError):
            always_locked()
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert delays[0] == pytest.approx(0.1)
        assert delays[1] == pytest.approx(0.2)
        assert delays[2] == pytest.approx(0.4)

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_delay_capped_at_max(self, mock_sleep):
        @retry_on_lock("test", max_retries=5, base_delay=1.0, max_delay=2.0, backoff_factor=3.0)
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(DatabaseLockedError):
            always_locked()
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert all(d <= 2.0 for d in delays)


# ------------------------------------------------------------------ #
# execute_with_retry
# ------------------------------------------------------------------ #

class TestExecuteWithRetry:
    def test_executes_sql_successfully(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("CREATE TABLE t (x INTEGER)")
        cursor = execute_with_retry(conn, "INSERT INTO t VALUES (?)", (1,))
        assert cursor.rowcount == 1
        conn.close()

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_retries_on_lock_then_succeeds(self, mock_sleep):
        call_count = 0

        mock_conn = MagicMock()

        def side_effect(sql, params=()):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise sqlite3.OperationalError("database is locked")
            return MagicMock(rowcount=1)

        mock_conn.execute.side_effect = side_effect
        execute_with_retry(mock_conn, "INSERT INTO t VALUES (?)", (1,))
        assert call_count == 2

    @patch("gamelibmanager.db.concurrency.time.sleep")
    def test_raises_after_exhausted_retries(self, mock_sleep):
        conn = MagicMock()
        conn.execute.side_effect = sqlite3.OperationalError("database is locked")

        with pytest.raises(DatabaseLockedError):
            execute_with_retry(conn, "SELECT 1", max_retries=2, base_delay=0.01)


# ------------------------------------------------------------------ #
# DatabaseLockedError
# ------------------------------------------------------------------ #

class TestDatabaseLockedError:
    def test_message_includes_operation(self):
        orig = sqlite3.OperationalError("database is locked")
        err = DatabaseLockedError("merge game", 3, orig)
        assert "merge game" in str(err)

    def test_message_includes_attempt_count(self):
        orig = sqlite3.OperationalError("database is locked")
        err = DatabaseLockedError("op", 5, orig)
        assert "5 attempt" in str(err)

    def test_preserves_original_exception(self):
        orig = sqlite3.OperationalError("database is locked")
        err = DatabaseLockedError("op", 1, orig)
        assert err.original is orig
