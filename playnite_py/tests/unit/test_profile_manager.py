"""
Unit tests for profile manager.

Tests the ProfileManager class and its operations.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from playnite_py.profiles.manager import ProfileManager
from playnite_py.core.models.profile import Profile, ProfileSettings


class TestProfileManager:
    """Tests for ProfileManager class."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> ProfileManager:
        """Create a ProfileManager with temp directory."""
        manager = ProfileManager(tmp_path)
        yield manager
        manager.close()

    def test_create_profile(self, manager: ProfileManager):
        """Test creating a profile."""
        profile = manager.create_profile("Test Profile")

        assert profile.name == "Test Profile"
        assert profile.data_directory is not None
        assert profile.data_directory.exists()

    def test_create_profile_with_description(self, manager: ProfileManager):
        """Test creating a profile with description."""
        profile = manager.create_profile(
            "Test",
            description="A test profile",
        )

        assert profile.description == "A test profile"

    def test_create_profile_with_template(self, manager: ProfileManager):
        """Test creating a profile from template."""
        profile = manager.create_profile(
            "Kids Profile",
            template="Kids",
        )

        assert profile.name == "Kids Profile"
        # Kids template has show_hidden_games=False
        assert profile.settings.show_hidden_games is False

    def test_create_duplicate_profile_raises_error(self, manager: ProfileManager):
        """Test that creating duplicate profile raises error."""
        manager.create_profile("Test")

        with pytest.raises(ValueError, match="already exists"):
            manager.create_profile("Test")

    def test_get_profile(self, manager: ProfileManager):
        """Test getting a profile by name."""
        manager.create_profile("Test")

        profile = manager.get_profile("Test")
        assert profile is not None
        assert profile.name == "Test"

    def test_get_nonexistent_profile(self, manager: ProfileManager):
        """Test getting a nonexistent profile."""
        profile = manager.get_profile("Does Not Exist")
        assert profile is None

    def test_list_profiles(self, manager: ProfileManager):
        """Test listing profiles."""
        manager.create_profile("Profile 1")
        manager.create_profile("Profile 2")

        profiles = manager.list_profiles()
        names = [p.name for p in profiles]

        assert "Profile 1" in names
        assert "Profile 2" in names

    def test_switch_profile(self, manager: ProfileManager):
        """Test switching profiles."""
        manager.create_profile("Profile 1")
        manager.create_profile("Profile 2")

        manager.switch_profile("Profile 1")
        assert manager.current_profile is not None
        assert manager.current_profile.name == "Profile 1"

        manager.switch_profile("Profile 2")
        assert manager.current_profile.name == "Profile 2"

    def test_switch_to_nonexistent_profile_raises_error(self, manager: ProfileManager):
        """Test switching to nonexistent profile raises error."""
        with pytest.raises(ValueError, match="not found"):
            manager.switch_profile("Does Not Exist")

    def test_delete_profile(self, manager: ProfileManager):
        """Test deleting a profile."""
        manager.create_profile("Test")

        result = manager.delete_profile("Test")
        assert result is True

        profile = manager.get_profile("Test")
        assert profile is None

    def test_delete_active_profile_raises_error(self, manager: ProfileManager):
        """Test that deleting active profile raises error."""
        manager.create_profile("Test")
        manager.switch_profile("Test")

        with pytest.raises(ValueError, match="active profile"):
            manager.delete_profile("Test")

    def test_rename_profile(self, manager: ProfileManager):
        """Test renaming a profile."""
        manager.create_profile("Old Name")

        profile = manager.rename_profile("Old Name", "New Name")
        assert profile.name == "New Name"

        # Old name should not exist
        assert manager.get_profile("Old Name") is None
        # New name should exist
        assert manager.get_profile("New Name") is not None

    def test_duplicate_profile(self, manager: ProfileManager):
        """Test duplicating a profile."""
        original = manager.create_profile("Original")

        copy = manager.duplicate_profile("Original", "Copy")
        assert copy.name == "Copy"
        assert copy.id != original.id

    def test_set_default_profile(self, manager: ProfileManager):
        """Test setting default profile."""
        manager.create_profile("Profile 1")
        manager.create_profile("Profile 2")

        manager.set_default_profile("Profile 2")

        default = manager.get_default_profile()
        assert default is not None
        assert default.name == "Profile 2"

    def test_get_profile_game_count(self, manager: ProfileManager):
        """Test getting game count for a profile."""
        manager.create_profile("Test")

        count = manager.get_profile_game_count("Test")
        assert count == 0

    def test_update_profile_settings(self, manager: ProfileManager):
        """Test updating profile settings."""
        manager.create_profile("Test")

        new_settings = ProfileSettings(
            theme="dark",
            language="de",
        )
        profile = manager.update_profile_settings("Test", new_settings)

        assert profile.settings.theme == "dark"
        assert profile.settings.language == "de"

    def test_add_switch_callback(self, manager: ProfileManager):
        """Test adding profile switch callback."""
        callback_called = []

        def callback(old, new):
            callback_called.append((old, new))

        manager.add_switch_callback(callback)
        manager.create_profile("Test")
        manager.switch_profile("Test")

        assert len(callback_called) == 1
        assert callback_called[0][0] is None  # No old profile
        assert callback_called[0][1].name == "Test"


class TestProfileManagerSecurity:
    """Tests for ProfileManager security features."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> ProfileManager:
        """Create a ProfileManager with temp directory."""
        manager = ProfileManager(tmp_path)
        yield manager
        manager.close()

    def test_set_profile_password(self, manager: ProfileManager):
        """Test setting profile password."""
        manager.create_profile("Test")

        manager.set_profile_password("Test", "secret123")

        profile = manager.get_profile("Test")
        assert profile.security.password_protected is True

    def test_switch_protected_profile_without_password_raises_error(
        self, manager: ProfileManager
    ):
        """Test switching to protected profile without password."""
        manager.create_profile("Test")
        manager.set_profile_password("Test", "secret123")

        with pytest.raises(PermissionError, match="password protected"):
            manager.switch_profile("Test")

    def test_switch_protected_profile_with_wrong_password_raises_error(
        self, manager: ProfileManager
    ):
        """Test switching to protected profile with wrong password."""
        manager.create_profile("Test")
        manager.set_profile_password("Test", "correct")

        with pytest.raises(PermissionError, match="Invalid password"):
            manager.switch_profile("Test", password="wrong")

    def test_switch_protected_profile_with_correct_password(
        self, manager: ProfileManager
    ):
        """Test switching to protected profile with correct password."""
        manager.create_profile("Test")
        manager.set_profile_password("Test", "secret123")

        profile = manager.switch_profile("Test", password="secret123")
        assert profile.name == "Test"

    def test_remove_profile_password(self, manager: ProfileManager):
        """Test removing profile password."""
        manager.create_profile("Test")
        manager.set_profile_password("Test", "secret123")

        manager.remove_profile_password("Test", "secret123")

        profile = manager.get_profile("Test")
        assert profile.security.password_protected is False


class TestProfileManagerExportImport:
    """Tests for ProfileManager export/import features."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> ProfileManager:
        """Create a ProfileManager with temp directory."""
        manager = ProfileManager(tmp_path)
        yield manager
        manager.close()

    def test_export_profile(self, manager: ProfileManager, tmp_path: Path):
        """Test exporting a profile."""
        manager.create_profile("Test")

        export_path = tmp_path / "export" / "test.ppf"
        result = manager.export_profile("Test", export_path)

        assert result.exists()
        assert result.suffix == ".ppf"

    def test_import_profile(self, manager: ProfileManager, tmp_path: Path):
        """Test importing a profile."""
        # Create and export
        manager.create_profile("Original")
        export_path = tmp_path / "export" / "original.ppf"
        manager.export_profile("Original", export_path)

        # Delete original
        manager.delete_profile("Original")

        # Import
        profile = manager.import_profile(export_path, new_name="Imported")

        assert profile.name == "Imported"
        assert manager.get_profile("Imported") is not None
