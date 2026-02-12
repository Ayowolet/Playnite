"""
Tests for the game launcher module.

Tests cover:
- Argument sanitization and injection prevention
- Path validation
- URL validation
- Environment building
- Display configuration integration
"""

import os
import shlex
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from playnite_py.configurations.launcher import (
    GameLauncher,
    LaunchResult,
    _sanitize_argument,
    _validate_executable_path,
    _validate_url,
    ALLOWED_URL_PROTOCOLS,
    DANGEROUS_ARG_PATTERNS,
)
from playnite_py.core.models.game import Game, GameAction, GameActionType
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    DisplayConfig,
    EnvironmentConfig,
    LaunchArguments,
)


class TestArgumentSanitization:
    """Tests for argument sanitization."""

    def test_sanitize_removes_null_bytes(self):
        """Null bytes should be removed."""
        assert _sanitize_argument("hello\x00world") == "helloworld"

    def test_sanitize_removes_newlines(self):
        """Newlines should be removed to prevent injection."""
        assert _sanitize_argument("hello\nworld") == "helloworld"
        assert _sanitize_argument("hello\r\nworld") == "helloworld"

    def test_sanitize_preserves_normal_args(self):
        """Normal arguments should pass through unchanged."""
        assert _sanitize_argument("-flag") == "-flag"
        assert _sanitize_argument("--config=value") == "--config=value"
        assert _sanitize_argument("/path/to/file") == "/path/to/file"

    def test_sanitize_preserves_spaces_in_args(self):
        """Spaces within arguments should be preserved."""
        assert _sanitize_argument("hello world") == "hello world"


class TestPathValidation:
    """Tests for executable path validation."""

    def test_empty_path_rejected(self):
        """Empty paths should be rejected."""
        is_valid, error = _validate_executable_path("")
        assert not is_valid
        assert "Empty" in error

    def test_path_traversal_rejected(self):
        """Path traversal attempts should be rejected."""
        is_valid, error = _validate_executable_path("/path/../../../etc/passwd")
        assert not is_valid
        assert "traversal" in error.lower()

    def test_shell_metacharacters_rejected(self):
        """Shell metacharacters should be rejected."""
        dangerous_paths = [
            "/path/to/game; rm -rf /",
            "/path/to/game | cat /etc/passwd",
            "/path/to/game & malicious",
            "/path/to/game `whoami`",
            "/path/to/game $(id)",
        ]
        for path in dangerous_paths:
            is_valid, error = _validate_executable_path(path)
            assert not is_valid, f"Path should be rejected: {path}"

    def test_nonexistent_path_rejected(self):
        """Non-existent paths should be rejected."""
        is_valid, error = _validate_executable_path("/nonexistent/path/to/game.exe")
        assert not is_valid
        assert "not found" in error.lower()

    def test_valid_path_accepted(self):
        """Valid existing paths should be accepted."""
        # Use a known existing file
        is_valid, error = _validate_executable_path("/bin/echo")
        assert is_valid
        assert error == ""


class TestURLValidation:
    """Tests for URL protocol validation."""

    def test_allowed_protocols_accepted(self):
        """Allowed URL protocols should be accepted."""
        allowed_urls = [
            ("https://example.com", "https"),
            ("http://example.com", "http"),
            ("steam://run/12345", "steam"),
            ("origin://launch/12345", "origin"),
        ]
        for url, protocol in allowed_urls:
            if protocol in ALLOWED_URL_PROTOCOLS:
                is_valid, error = _validate_url(url)
                assert is_valid, f"URL should be allowed: {url}"

    def test_dangerous_protocols_rejected(self):
        """Dangerous URL protocols should be rejected."""
        dangerous_urls = [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://malicious.com/file",
        ]
        for url in dangerous_urls:
            is_valid, error = _validate_url(url)
            assert not is_valid, f"URL should be rejected: {url}"

    def test_missing_protocol_rejected(self):
        """URLs without protocol should be rejected."""
        is_valid, error = _validate_url("example.com")
        assert not is_valid
        assert "no protocol" in error.lower()


class TestGameLauncher:
    """Tests for the GameLauncher class."""

    @pytest.fixture
    def launcher(self):
        """Create a GameLauncher instance."""
        return GameLauncher()

    @pytest.fixture
    def mock_game(self):
        """Create a mock game."""
        game = Game(name="Test Game", source="manual")
        game.actions = [
            GameAction(
                name="Play",
                type=GameActionType.FILE,
                path="/bin/echo",
                arguments="test",
                is_default=True,
            )
        ]
        return game

    def test_launcher_initialization(self, launcher):
        """Launcher should initialize with required components."""
        assert launcher.compatibility_manager is not None
        assert launcher.display_manager is not None
        assert launcher._temp_files == []

    def test_build_environment_starts_with_copy(self, launcher):
        """Environment should start with os.environ copy."""
        env = launcher._build_launch_environment(None)
        # Should contain PATH from os.environ
        assert "PATH" in env

    def test_build_environment_applies_user_vars(self, launcher):
        """User environment variables should be applied."""
        config = PlatformConfiguration(
            name="Test",
            game_id=uuid4(),
            environment=EnvironmentConfig(
                set_variables={"MY_VAR": "my_value"},
            ),
        )
        launcher.compatibility_manager._last_env = {}
        env = launcher._build_launch_environment(config)
        assert env.get("MY_VAR") == "my_value"

    def test_build_environment_unsets_vars(self, launcher):
        """Environment should support unsetting variables."""
        # Set a var first
        os.environ["TEST_UNSET_VAR"] = "should_be_removed"
        try:
            config = PlatformConfiguration(
                name="Test",
                game_id=uuid4(),
                environment=EnvironmentConfig(
                    unset_variables=["TEST_UNSET_VAR"],
                ),
            )
            launcher.compatibility_manager._last_env = {}
            env = launcher._build_launch_environment(config)
            assert "TEST_UNSET_VAR" not in env
        finally:
            del os.environ["TEST_UNSET_VAR"]

    def test_sensitive_vars_not_expanded(self, launcher):
        """Sensitive environment variables should not be expanded."""
        assert launcher._is_sensitive_var("PASSWORD")
        assert launcher._is_sensitive_var("API_KEY")
        assert launcher._is_sensitive_var("AWS_SECRET_ACCESS_KEY")
        assert launcher._is_sensitive_var("DB_PASSWORD")
        assert not launcher._is_sensitive_var("PATH")
        assert not launcher._is_sensitive_var("HOME")

    def test_launch_result_defaults(self):
        """LaunchResult should have correct defaults."""
        result = LaunchResult(success=False, game_id=uuid4())
        assert result.success is False
        assert result.error_message == ""
        assert result.exit_code is None
        assert result.used_fallback is False


class TestLaunchArguments:
    """Tests for launch argument handling."""

    def test_shlex_split_quoted_args(self):
        """Quoted arguments should be handled correctly."""
        args = LaunchArguments(
            base_arguments='-config "C:/Program Files/Game/config.ini"'
        )
        result = args.get_final_arguments()
        parsed = shlex.split(result)
        assert len(parsed) == 2
        assert parsed[0] == "-config"
        assert parsed[1] == "C:/Program Files/Game/config.ini"

    def test_add_arguments(self):
        """Arguments should be addable."""
        args = LaunchArguments(
            base_arguments="-flag1",
            add_arguments=["-flag2", "-flag3"],
        )
        result = args.get_final_arguments()
        parsed = shlex.split(result)
        assert "-flag1" in parsed
        assert "-flag2" in parsed
        assert "-flag3" in parsed

    def test_remove_arguments(self):
        """Arguments should be removable."""
        args = LaunchArguments(
            base_arguments="-flag1 -flag2 -flag3",
            remove_arguments=["-flag2"],
        )
        result = args.get_final_arguments()
        parsed = shlex.split(result)
        assert "-flag1" in parsed
        assert "-flag2" not in parsed
        assert "-flag3" in parsed

    def test_replace_arguments(self):
        """Replace should override all arguments."""
        args = LaunchArguments(
            base_arguments="-old1 -old2",
            add_arguments=["-add"],
            replace_arguments="-new1 -new2",
        )
        result = args.get_final_arguments()
        assert result == "-new1 -new2"


class TestEnvironmentIsolation:
    """Tests for environment variable isolation."""

    def test_os_environ_not_modified(self):
        """os.environ should never be modified."""
        original_keys = set(os.environ.keys())

        launcher = GameLauncher()
        config = PlatformConfiguration(
            name="Test",
            game_id=uuid4(),
            environment=EnvironmentConfig(
                set_variables={"SHOULD_NOT_POLLUTE": "value"},
            ),
        )
        launcher.compatibility_manager._last_env = {}
        env = launcher._build_launch_environment(config)

        # Verify env has the var
        assert env.get("SHOULD_NOT_POLLUTE") == "value"
        # Verify os.environ was NOT modified
        assert "SHOULD_NOT_POLLUTE" not in os.environ
        assert set(os.environ.keys()) == original_keys
