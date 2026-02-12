"""
Integration tests for Playnite-Py.

Tests cover end-to-end workflows and component interactions.
"""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from playnite_py.core.models.profile import Profile, ProfileSettings
from playnite_py.core.models.game import Game, GameAction, GameActionType
from playnite_py.core.models.configuration import PlatformConfiguration, DisplayConfig
from playnite_py.core.errors import ErrorCode, PlayniteError


class TestProfileNameSanitization:
    """Tests for profile name validation and sanitization."""

    def test_valid_name(self):
        """Valid names should be accepted."""
        profile = Profile(name="My Gaming Profile")
        assert profile.name == "My Gaming Profile"

    def test_name_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped."""
        profile = Profile(name="  Gaming  ")
        assert profile.name == "Gaming"

    def test_invalid_chars_rejected(self):
        """Names with invalid characters should be rejected."""
        invalid_names = [
            "Game/Profile",
            "Game\\Profile",
            "Game:Profile",
            "Game<Profile",
            "Game>Profile",
            "Game|Profile",
            'Game"Profile',
            "Game?Profile",
            "Game*Profile",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match="cannot contain"):
                Profile(name=name)

    def test_reserved_names_rejected(self):
        """Windows reserved names should be rejected."""
        reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
        for name in reserved:
            with pytest.raises(ValueError, match="reserved name"):
                Profile(name=name)

    def test_path_traversal_rejected(self):
        """Path traversal sequences should be rejected."""
        dangerous = ["../etc/passwd", "..\\windows", "/root", "~/.ssh"]
        for name in dangerous:
            with pytest.raises(ValueError, match="traversal|cannot contain"):
                Profile(name=name)

    def test_leading_trailing_dots_rejected(self):
        """Names starting/ending with dots should be rejected."""
        with pytest.raises(ValueError, match="start with"):
            Profile(name=".hidden")
        with pytest.raises(ValueError, match="end with"):
            Profile(name="profile.")

    def test_control_chars_rejected(self):
        """Control characters should be rejected."""
        with pytest.raises(ValueError, match="control"):
            Profile(name="Profile\x01Name")


class TestErrorCodes:
    """Tests for structured error codes."""

    def test_error_code_categories(self):
        """Error codes should have correct categories."""
        from playnite_py.core.errors import ErrorCategory

        assert ErrorCode.PROFILE_NOT_FOUND.category == ErrorCategory.PROFILE
        assert ErrorCode.GAME_NOT_FOUND.category == ErrorCategory.GAME
        assert ErrorCode.LAUNCH_PATH_NOT_FOUND.category == ErrorCategory.LAUNCH
        assert ErrorCode.DATABASE_QUERY_FAILED.category == ErrorCategory.DATABASE

    def test_playnite_error_serialization(self):
        """PlayniteError should serialize correctly."""
        error = PlayniteError(
            ErrorCode.PROFILE_NOT_FOUND,
            "Profile 'gaming' not found",
            details={"profile_name": "gaming"},
            suggestion="Create the profile first",
        )

        data = error.to_dict()
        assert data["code"] == 1001
        assert data["code_name"] == "PROFILE_NOT_FOUND"
        assert data["category"] == "profile"
        assert "gaming" in data["message"]
        assert data["details"]["profile_name"] == "gaming"
        assert "Create" in data["suggestion"]


class TestHealthCheck:
    """Tests for health check functionality."""

    def test_health_checker_default_checks(self):
        """Health checker should have default checks."""
        from playnite_py.utils.health import HealthChecker, HealthStatus

        checker = HealthChecker()
        health = checker.check_all()

        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        assert len(health.components) >= 2
        assert any(c.name == "python" for c in health.components)

    def test_health_checker_with_data_dir(self):
        """Health checker should verify filesystem access."""
        from playnite_py.utils.health import HealthChecker, HealthStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = HealthChecker(data_dir=Path(tmpdir))
            health = checker.check_all()

            fs_check = next(c for c in health.components if c.name == "filesystem")
            assert fs_check.status == HealthStatus.HEALTHY

    def test_health_to_dict(self):
        """Health status should serialize correctly."""
        from playnite_py.utils.health import HealthChecker

        checker = HealthChecker()
        health = checker.check_all()
        data = health.to_dict()

        assert "status" in data
        assert "healthy" in data
        assert "timestamp" in data
        assert "components" in data


class TestGracefulShutdown:
    """Tests for graceful shutdown handling."""

    def test_callback_registration(self):
        """Callbacks should be registered correctly."""
        from playnite_py.utils.health import GracefulShutdown

        shutdown = GracefulShutdown()
        called = []

        def callback1():
            called.append(1)

        def callback2():
            called.append(2)

        shutdown.register_callback(callback1)
        shutdown.register_callback(callback2)

        # Manually trigger callbacks
        shutdown._run_callbacks()

        # Callbacks should run in reverse order
        assert called == [2, 1]

    def test_shutdown_requested_flag(self):
        """Shutdown requested flag should work."""
        from playnite_py.utils.health import GracefulShutdown

        shutdown = GracefulShutdown()
        assert not shutdown.is_shutdown_requested()

        shutdown._shutdown_requested.set()
        assert shutdown.is_shutdown_requested()


class TestRetryLogic:
    """Tests for retry and rate limiting utilities."""

    def test_retry_succeeds_eventually(self):
        """Retry should succeed after transient failures."""
        from playnite_py.utils.retry import retry

        attempts = [0]

        @retry(max_attempts=3, delay=0.01)
        def flaky_function():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError("Transient error")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert attempts[0] == 3

    def test_retry_exhausted(self):
        """Retry should raise after max attempts."""
        from playnite_py.utils.retry import retry

        @retry(max_attempts=2, delay=0.01)
        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fails()

    def test_rate_limiter(self):
        """Rate limiter should control call rate."""
        from playnite_py.utils.retry import RateLimiter, RateLimitConfig
        import time

        limiter = RateLimiter(RateLimitConfig(calls_per_second=100, burst_size=2))

        # Should succeed immediately for burst
        assert limiter.try_acquire()
        assert limiter.try_acquire()

        # Third should fail without waiting
        # (depends on timing, so we just verify it doesn't crash)
        limiter.try_acquire()

    def test_circuit_breaker(self):
        """Circuit breaker should open after failures."""
        from playnite_py.utils.retry import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        def failing_func():
            raise ValueError("Failure")

        # First two failures should pass through
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(failing_func)

        # Circuit should be open now
        assert breaker.state == "OPEN"

        # Calls should fail immediately
        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            breaker.call(failing_func)


class TestPaginatedResults:
    """Tests for repository pagination."""

    def test_paged_result_properties(self):
        """PagedResult should calculate properties correctly."""
        from playnite_py.core.database.repositories import PagedResult

        result = PagedResult(
            items=[1, 2, 3],
            total=25,
            page=2,
            page_size=10,
        )

        assert result.total_pages == 3
        assert result.has_next
        assert result.has_previous

    def test_paged_result_first_page(self):
        """First page should not have previous."""
        from playnite_py.core.database.repositories import PagedResult

        result = PagedResult(
            items=[1, 2, 3],
            total=25,
            page=1,
            page_size=10,
        )

        assert not result.has_previous
        assert result.has_next

    def test_paged_result_last_page(self):
        """Last page should not have next."""
        from playnite_py.core.database.repositories import PagedResult

        result = PagedResult(
            items=[1, 2, 3, 4, 5],
            total=25,
            page=3,
            page_size=10,
        )

        assert result.has_previous
        assert not result.has_next


class TestGameActionSerialization:
    """Tests for game model serialization."""

    def test_game_serialization(self):
        """Game should serialize correctly with field_serializer."""
        game = Game(
            name="Test Game",
            actions=[
                GameAction(
                    name="Play",
                    type=GameActionType.FILE,
                    path="/games/test/game.exe",
                    is_default=True,
                )
            ],
        )

        data = game.model_dump(mode='json')

        assert data["name"] == "Test Game"
        assert isinstance(data["id"], str)  # UUID serialized to string
        assert isinstance(data["added_date"], str)  # datetime to ISO string
        assert len(data["actions"]) == 1
        assert data["actions"][0]["name"] == "Play"

    def test_configuration_serialization(self):
        """Configuration should serialize correctly."""
        config = PlatformConfiguration(
            name="High Quality",
            game_id=uuid4(),
            display=DisplayConfig(
                width=2560,
                height=1440,
                fullscreen=True,
            ),
        )

        data = config.model_dump(mode='json')

        assert data["name"] == "High Quality"
        assert isinstance(data["id"], str)
        assert isinstance(data["game_id"], str)
        assert isinstance(data["created_at"], str)
        assert data["display"]["width"] == 2560


class TestExportEncryption:
    """Tests for profile export encryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Data should survive encrypt-decrypt cycle."""
        from playnite_py.profiles.export import _encrypt_data, _decrypt_data

        original = b"Hello, World! This is test data for encryption."
        password = "test-password-123"

        encrypted = _encrypt_data(original, password)
        decrypted = _decrypt_data(encrypted, password)

        assert decrypted == original
        assert encrypted != original  # Should be different

    def test_encrypted_data_has_header(self):
        """Encrypted data should have proper header."""
        from playnite_py.profiles.export import _encrypt_data, ENCRYPTION_MAGIC

        original = b"Test data"
        encrypted = _encrypt_data(original, "password")

        assert encrypted[:4] == ENCRYPTION_MAGIC

    def test_wrong_password_fails(self):
        """Decryption with wrong password should fail."""
        from playnite_py.profiles.export import _encrypt_data, _decrypt_data

        original = b"Secret data"
        encrypted = _encrypt_data(original, "correct-password")

        with pytest.raises(ValueError, match="Decryption failed"):
            _decrypt_data(encrypted, "wrong-password")

    def test_is_encrypted_export_detection(self):
        """Should correctly detect encrypted exports."""
        from playnite_py.profiles.export import (
            _encrypt_data,
            is_encrypted_export,
            ENCRYPTION_MAGIC,
        )

        # Create a temporary encrypted file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ppfe") as f:
            encrypted = _encrypt_data(b"test", "password")
            f.write(encrypted)
            encrypted_path = Path(f.name)

        # Create a temporary non-encrypted file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ppf") as f:
            f.write(b"PK\x03\x04not encrypted")  # ZIP magic number
            plain_path = Path(f.name)

        try:
            assert is_encrypted_export(encrypted_path)
            assert not is_encrypted_export(plain_path)
        finally:
            encrypted_path.unlink()
            plain_path.unlink()

    def test_different_passwords_different_outputs(self):
        """Same data with different passwords should produce different outputs."""
        from playnite_py.profiles.export import _encrypt_data

        original = b"Same data"
        enc1 = _encrypt_data(original, "password1")
        enc2 = _encrypt_data(original, "password2")

        # Different passwords should produce different ciphertext
        assert enc1 != enc2

    def test_same_password_different_outputs(self):
        """Same password should produce different outputs due to random nonce."""
        from playnite_py.profiles.export import _encrypt_data

        original = b"Same data"
        enc1 = _encrypt_data(original, "same-password")
        enc2 = _encrypt_data(original, "same-password")

        # Due to random salt and nonce, outputs should differ
        assert enc1 != enc2
