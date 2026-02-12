"""
Tests for the compatibility layer module.

Tests cover:
- Path normalization and conversion
- Wine/Proton environment setup
- Layer detection
- Windows executable validation
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from playnite_py.configurations.compatibility import (
    CompatibilityManager,
    _normalize_path,
    _convert_unix_to_wine_path,
    _is_windows_executable,
    WINDOWS_EXECUTABLE_EXTENSIONS,
)
from playnite_py.core.models.configuration import CompatibilityConfig


class TestPathNormalization:
    """Tests for path normalization."""

    def test_normalize_expands_home(self):
        """Home directory should be expanded."""
        result = _normalize_path("~/games/game.exe")
        assert "~" not in str(result)
        assert result.is_absolute()

    def test_normalize_resolves_dotdot(self):
        """.. should be resolved."""
        result = _normalize_path("/home/user/../user/games/game.exe")
        assert ".." not in str(result)

    def test_normalize_resolves_dot(self):
        """Single . should be resolved."""
        result = _normalize_path("/home/user/./games/game.exe")
        assert "/./" not in str(result)

    def test_normalize_returns_absolute(self):
        """Result should always be absolute."""
        result = _normalize_path("relative/path/game.exe")
        assert result.is_absolute()


class TestUnixToWinePathConversion:
    """Tests for Unix to Wine path conversion."""

    def test_path_in_prefix_converted_to_c_drive(self):
        """Paths inside Wine prefix should be converted to C: drive."""
        prefix = Path("/home/user/.wine")
        unix_path = "/home/user/.wine/drive_c/Program Files/Game/game.exe"

        result = _convert_unix_to_wine_path(unix_path, prefix)

        assert result.startswith("C:")
        assert "Program Files" in result
        assert "Game" in result

    def test_path_outside_prefix_unchanged(self):
        """Paths outside Wine prefix should use Z: drive (passed as-is)."""
        prefix = Path("/home/user/.wine")
        unix_path = "/home/user/external/games/game.exe"

        result = _convert_unix_to_wine_path(unix_path, prefix)

        # Should not be a C: path
        assert not result.startswith("C:")

    def test_path_without_prefix(self):
        """Paths without prefix specified should pass through."""
        unix_path = "/home/user/games/game.exe"

        result = _convert_unix_to_wine_path(unix_path, None)

        assert "game.exe" in result


class TestWindowsExecutableDetection:
    """Tests for Windows executable detection."""

    def test_exe_detected(self):
        """EXE files should be detected."""
        assert _is_windows_executable("game.exe")
        assert _is_windows_executable("GAME.EXE")
        assert _is_windows_executable("/path/to/game.exe")

    def test_msi_detected(self):
        """MSI files should be detected."""
        assert _is_windows_executable("setup.msi")

    def test_bat_detected(self):
        """BAT files should be detected."""
        assert _is_windows_executable("script.bat")
        assert _is_windows_executable("script.cmd")

    def test_non_windows_not_detected(self):
        """Non-Windows executables should not be detected."""
        assert not _is_windows_executable("game.app")
        assert not _is_windows_executable("game.sh")
        assert not _is_windows_executable("game")
        assert not _is_windows_executable("game.bin")


class TestCompatibilityManager:
    """Tests for CompatibilityManager."""

    @pytest.fixture
    def manager(self):
        """Create a CompatibilityManager instance."""
        return CompatibilityManager()

    def test_initialization(self, manager):
        """Manager should initialize correctly."""
        assert manager._wine_path is None
        assert manager._proton_path is None
        assert manager._last_env == {}

    def test_wine_environment_setup(self, manager):
        """Wine environment should be set up correctly."""
        config = CompatibilityConfig(
            use_compatibility_layer=True,
            layer_type="wine",
            prefix_path=Path("/tmp/wine_prefix"),
            esync_enabled=True,
            fsync_enabled=True,
            dxvk_enabled=True,
        )

        env = manager._setup_wine_environment(config)

        assert env["WINEPREFIX"] == "/tmp/wine_prefix"
        assert env["WINEARCH"] == "win64"
        assert env["WINEESYNC"] == "1"
        assert env["WINEFSYNC"] == "1"
        assert env["DXVK_LOG_LEVEL"] == "none"

    def test_proton_environment_setup(self, manager):
        """Proton environment should be set up correctly."""
        config = CompatibilityConfig(
            use_compatibility_layer=True,
            layer_type="proton",
            prefix_path=Path("/tmp/proton_prefix"),
            esync_enabled=True,
            fsync_enabled=False,
        )

        env = manager._setup_proton_environment(config, Path("/opt/proton"))

        assert env["STEAM_COMPAT_DATA_PATH"] == "/tmp/proton_prefix"
        assert env["PROTON_NO_ESYNC"] == "0"  # Enabled means NO_ESYNC=0
        assert env["PROTON_NO_FSYNC"] == "1"  # Disabled means NO_FSYNC=1

    def test_dll_overrides(self, manager):
        """DLL overrides should be formatted correctly."""
        config = CompatibilityConfig(
            use_compatibility_layer=True,
            layer_type="wine",
            dll_overrides={"d3d11": "native", "dxgi": "native,builtin"},
        )

        env = manager._setup_wine_environment(config)

        assert "WINEDLLOVERRIDES" in env
        assert "d3d11=native" in env["WINEDLLOVERRIDES"]
        assert "dxgi=native,builtin" in env["WINEDLLOVERRIDES"]

    def test_get_launch_environment_returns_copy(self, manager):
        """get_launch_environment should return a copy."""
        manager._last_env = {"TEST": "value"}

        env1 = manager.get_launch_environment()
        env1["NEW_KEY"] = "new_value"
        env2 = manager.get_launch_environment()

        assert "NEW_KEY" not in env2

    def test_windows_returns_none(self, manager):
        """On Windows, get_launch_command should return None."""
        config = CompatibilityConfig(use_compatibility_layer=True, layer_type="wine")

        with patch("platform.system", return_value="Windows"):
            result = manager.get_launch_command("/path/to/game.exe", config)
            assert result is None

    def test_disabled_layer_returns_none(self, manager):
        """Disabled compatibility layer should return None."""
        config = CompatibilityConfig(use_compatibility_layer=False)

        result = manager.get_launch_command("/path/to/game.exe", config)
        assert result is None

    def test_validate_configuration_valid(self, manager):
        """Valid configuration should pass validation."""
        config = CompatibilityConfig(
            use_compatibility_layer=True,
            layer_type="wine",
        )

        is_valid, errors = manager.validate_configuration(config)
        assert is_valid
        assert errors == []

    def test_validate_configuration_invalid_type(self, manager):
        """Invalid layer type should fail validation at construction."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            CompatibilityConfig(
                use_compatibility_layer=True,
                layer_type="invalid_layer",
            )

        assert "layer_type" in str(exc_info.value)


class TestEnvironmentIsolation:
    """Tests for environment variable isolation."""

    def test_setup_wine_does_not_pollute_environ(self):
        """_setup_wine_environment should not modify os.environ."""
        original_keys = set(os.environ.keys())

        manager = CompatibilityManager()
        config = CompatibilityConfig(
            use_compatibility_layer=True,
            layer_type="wine",
            prefix_path=Path("/tmp/test_prefix"),
        )

        env = manager._setup_wine_environment(config)

        # Verify env has the vars
        assert "WINEPREFIX" in env
        # Verify os.environ was NOT modified
        assert "WINEPREFIX" not in os.environ or os.environ.get("WINEPREFIX") != "/tmp/test_prefix"
        final_keys = set(os.environ.keys())
        # No new keys should be added
        new_keys = final_keys - original_keys
        wine_keys = {k for k in new_keys if "WINE" in k}
        assert not wine_keys, f"os.environ polluted with: {wine_keys}"
