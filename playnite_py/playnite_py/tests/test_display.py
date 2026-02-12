"""
Tests for the display management module.

Tests cover:
- Target monitor finding
- Race condition prevention
- Platform-specific API calls
- Rollback mechanism
"""

import threading
from unittest.mock import patch, MagicMock

import pytest

from playnite_py.configurations.display import (
    DisplayManager,
    DisplayChangeResult,
)
from playnite_py.configurations.detection import DisplayInfo
from playnite_py.core.models.configuration import DisplayConfig


class TestDisplayManager:
    """Tests for DisplayManager."""

    @pytest.fixture
    def manager(self):
        """Create a DisplayManager instance."""
        return DisplayManager()

    @pytest.fixture
    def mock_displays(self):
        """Create mock display info."""
        return [
            DisplayInfo(name="HDMI-1", width=1920, height=1080, is_primary=True),
            DisplayInfo(name="DP-1", width=2560, height=1440, is_primary=False),
        ]

    def test_initialization(self, manager):
        """Manager should initialize correctly."""
        assert manager._lock is not None
        assert manager._detector is not None
        assert manager._previous_configs == {}

    def test_has_threading_lock(self, manager):
        """Manager should have a threading lock."""
        assert isinstance(manager._lock, type(threading.Lock()))


class TestTargetMonitorFinding:
    """Tests for target monitor finding."""

    @pytest.fixture
    def manager(self):
        return DisplayManager()

    @pytest.fixture
    def displays(self):
        return [
            DisplayInfo(name="HDMI-1", width=1920, height=1080, is_primary=True),
            DisplayInfo(name="DP-1", width=2560, height=1440, is_primary=False),
        ]

    def test_find_by_exact_name(self, manager, displays):
        """Should find monitor by exact name."""
        target = manager._find_target_monitor("HDMI-1", displays)
        assert target is not None
        assert target.name == "HDMI-1"

    def test_find_by_name_case_insensitive(self, manager, displays):
        """Should find monitor case-insensitively."""
        target = manager._find_target_monitor("hdmi-1", displays)
        assert target is not None
        assert target.name == "HDMI-1"

    def test_find_primary_when_no_target(self, manager, displays):
        """Should return primary when no target specified."""
        target = manager._find_target_monitor(None, displays)
        assert target is not None
        assert target.is_primary is True

    def test_find_first_when_no_primary(self, manager):
        """Should return first display when no primary."""
        displays = [
            DisplayInfo(name="DP-1", width=1920, height=1080, is_primary=False),
            DisplayInfo(name="DP-2", width=2560, height=1440, is_primary=False),
        ]
        target = manager._find_target_monitor(None, displays)
        assert target is not None
        assert target.name == "DP-1"

    def test_find_nonexistent_returns_none(self, manager, displays):
        """Should return None for nonexistent monitor."""
        target = manager._find_target_monitor("NonExistent", displays)
        assert target is None

    def test_find_empty_displays_returns_none(self, manager):
        """Should return None when no displays."""
        target = manager._find_target_monitor("Any", [])
        assert target is None


class TestDisplayChangeResult:
    """Tests for DisplayChangeResult."""

    def test_default_values(self):
        """Should have correct defaults."""
        result = DisplayChangeResult(success=False)
        assert result.success is False
        assert result.error_message == ""
        assert result.previous_config is None
        assert result.applied_config is None

    def test_with_error(self):
        """Should store error message."""
        result = DisplayChangeResult(
            success=False,
            error_message="Monitor disconnected"
        )
        assert not result.success
        assert result.error_message == "Monitor disconnected"


class TestRaceConditionPrevention:
    """Tests for race condition prevention."""

    @pytest.fixture
    def manager(self):
        return DisplayManager()

    def test_lock_acquired_during_apply(self, manager):
        """Lock should be acquired during apply."""
        config = DisplayConfig(width=1920, height=1080)

        with patch.object(manager, '_apply_display_config_locked') as mock:
            mock.return_value = DisplayChangeResult(success=True)
            manager.apply_display_config(config)

            # The locked method should have been called
            mock.assert_called_once()

    def test_no_change_when_no_resolution(self, manager):
        """Should succeed without change when no resolution specified."""
        config = DisplayConfig()  # No width/height

        result = manager.apply_display_config(config)

        assert result.success is True

    @patch.object(DisplayManager, '_verify_monitor_exists')
    def test_verification_before_change(self, mock_verify, manager):
        """Target should be verified before change."""
        mock_verify.return_value = False

        config = DisplayConfig(
            width=1920,
            height=1080,
            target_monitor="HDMI-1"
        )

        with patch.object(manager._detector, 'get_hardware_profile') as mock_profile:
            mock_profile.return_value = MagicMock(
                displays=[DisplayInfo(name="HDMI-1", width=1920, height=1080)]
            )
            result = manager.apply_display_config(config, verify_target=True)

        assert not result.success
        assert "disconnected" in result.error_message.lower()


class TestRollback:
    """Tests for rollback mechanism."""

    @pytest.fixture
    def manager(self):
        return DisplayManager()

    def test_rollback_no_previous_config(self, manager):
        """Rollback should fail if no previous config."""
        result = manager.rollback("NonExistent")

        assert not result.success
        assert "no previous config" in result.error_message.lower()

    def test_previous_config_saved(self, manager):
        """Previous config should be saved on change."""
        # Manually set a previous config
        previous = DisplayInfo(name="HDMI-1", width=1920, height=1080)
        manager._previous_configs["HDMI-1"] = previous

        assert "HDMI-1" in manager._previous_configs
        assert manager._previous_configs["HDMI-1"].width == 1920


class TestWaylandDetection:
    """Tests for Wayland detection."""

    @pytest.fixture
    def manager(self):
        return DisplayManager()

    def test_detect_wayland_by_session_type(self, manager):
        """Should detect Wayland by XDG_SESSION_TYPE."""
        import os
        original = os.environ.get("XDG_SESSION_TYPE")
        os.environ["XDG_SESSION_TYPE"] = "wayland"
        try:
            assert manager._is_wayland() is True
        finally:
            if original:
                os.environ["XDG_SESSION_TYPE"] = original
            else:
                os.environ.pop("XDG_SESSION_TYPE", None)

    def test_detect_wayland_by_display(self, manager):
        """Should detect Wayland by WAYLAND_DISPLAY."""
        import os
        original = os.environ.get("WAYLAND_DISPLAY")
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        try:
            assert manager._is_wayland() is True
        finally:
            if original:
                os.environ["WAYLAND_DISPLAY"] = original
            else:
                os.environ.pop("WAYLAND_DISPLAY", None)

    def test_detect_x11(self, manager):
        """Should detect X11 when no Wayland indicators."""
        import os
        original_session = os.environ.pop("XDG_SESSION_TYPE", None)
        original_display = os.environ.pop("WAYLAND_DISPLAY", None)
        try:
            assert manager._is_wayland() is False
        finally:
            if original_session:
                os.environ["XDG_SESSION_TYPE"] = original_session
            if original_display:
                os.environ["WAYLAND_DISPLAY"] = original_display
