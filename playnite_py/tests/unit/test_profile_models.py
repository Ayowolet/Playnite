"""
Unit tests for profile models.

Tests the Profile, ProfileSettings, ProfileSecurity, and related models.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import pytest

from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileStatistics,
    ProfileSecurity,
    ProfileSharing,
    ProfileTemplate,
    DataSharingMode,
)


class TestProfileSettings:
    """Tests for ProfileSettings model."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = ProfileSettings()
        assert settings.theme == "default"
        assert settings.language == "en"
        assert settings.default_view == "grid"
        assert settings.grid_size == 200
        assert settings.show_hidden_games is False
        assert settings.auto_update_library is True

    def test_custom_settings(self):
        """Test custom settings values."""
        settings = ProfileSettings(
            theme="dark",
            language="de",
            default_view="list",
            grid_size=300,
        )
        assert settings.theme == "dark"
        assert settings.language == "de"
        assert settings.default_view == "list"
        assert settings.grid_size == 300

    def test_invalid_view_raises_error(self):
        """Test that invalid view mode raises ValueError."""
        with pytest.raises(ValueError):
            ProfileSettings(default_view="invalid")

    def test_language_validation(self):
        """Test language code validation."""
        # Valid language codes
        ProfileSettings(language="en")
        ProfileSettings(language="de")
        ProfileSettings(language="en-US")

        # Invalid language codes
        with pytest.raises(ValueError):
            ProfileSettings(language="english")


class TestProfileSecurity:
    """Tests for ProfileSecurity model."""

    def test_default_security(self):
        """Test default security values."""
        security = ProfileSecurity()
        assert security.password_protected is False
        assert security.password_hash is None
        assert security.password_salt is None
        assert security.failed_attempts == 0

    def test_set_password(self):
        """Test password setting."""
        security = ProfileSecurity()
        security.set_password("test_password")

        assert security.password_protected is True
        assert security.password_hash is not None
        assert security.password_salt is not None
        assert len(security.password_hash) == 64  # SHA-256 hex length
        assert len(security.password_salt) == 64

    def test_verify_correct_password(self):
        """Test password verification with correct password."""
        security = ProfileSecurity()
        security.set_password("correct_password")

        assert security.verify_password("correct_password") is True
        assert security.failed_attempts == 0

    def test_verify_wrong_password(self):
        """Test password verification with wrong password."""
        security = ProfileSecurity()
        security.set_password("correct_password")

        assert security.verify_password("wrong_password") is False
        assert security.failed_attempts == 1

    def test_clear_password(self):
        """Test password clearing."""
        security = ProfileSecurity()
        security.set_password("password")
        security.clear_password()

        assert security.password_protected is False
        assert security.password_hash is None
        assert security.password_salt is None

    def test_lockout_detection(self):
        """Test lockout status detection."""
        security = ProfileSecurity()
        assert security.is_locked() is False

        # Set lockout
        security.locked_until = datetime.now() + timedelta(minutes=15)
        assert security.is_locked() is True

        # Past lockout
        security.locked_until = datetime.now() - timedelta(minutes=1)
        assert security.is_locked() is False


class TestProfileStatistics:
    """Tests for ProfileStatistics model."""

    def test_default_statistics(self):
        """Test default statistics values."""
        stats = ProfileStatistics()
        assert stats.total_playtime_minutes == 0
        assert stats.game_count == 0
        assert stats.session_count == 0
        assert stats.last_used is None

    def test_record_session(self):
        """Test session recording."""
        stats = ProfileStatistics()
        stats.record_session()

        assert stats.session_count == 1
        assert stats.last_used is not None

    def test_add_playtime(self):
        """Test playtime addition."""
        stats = ProfileStatistics()
        stats.add_playtime(60)
        stats.add_playtime(30)

        assert stats.total_playtime_minutes == 90

    def test_add_negative_playtime_ignored(self):
        """Test that negative playtime is ignored."""
        stats = ProfileStatistics()
        stats.add_playtime(-10)

        assert stats.total_playtime_minutes == 0


class TestProfileSharing:
    """Tests for ProfileSharing model."""

    def test_default_sharing(self):
        """Test default sharing values."""
        sharing = ProfileSharing()
        assert sharing.mode == DataSharingMode.NONE
        assert sharing.share_categories is False
        assert sharing.share_tags is False
        assert sharing.share_metadata_cache is False
        assert sharing.share_media_files is False

    def test_selective_sharing(self):
        """Test selective sharing configuration."""
        sharing = ProfileSharing(
            mode=DataSharingMode.SELECTIVE,
            share_categories=True,
            share_tags=True,
            share_metadata_cache=True,
        )
        assert sharing.mode == DataSharingMode.SELECTIVE
        assert sharing.share_categories is True
        assert sharing.share_tags is True
        assert sharing.share_metadata_cache is True
        assert sharing.share_media_files is False


class TestProfile:
    """Tests for Profile model."""

    def test_profile_creation(self):
        """Test basic profile creation."""
        profile = Profile(name="Test")

        assert profile.name == "Test"
        assert isinstance(profile.id, UUID)
        assert profile.is_active is False
        assert profile.is_default is False

    def test_profile_name_validation(self):
        """Test profile name validation."""
        # Valid names
        Profile(name="Valid Name")
        Profile(name="Profile 123")

        # Invalid names with special characters
        with pytest.raises(ValueError):
            Profile(name="Invalid/Name")
        with pytest.raises(ValueError):
            Profile(name="Invalid:Name")

    def test_profile_to_dict(self):
        """Test profile serialization to dict."""
        profile = Profile(
            name="Test",
            description="Test description",
        )
        data = profile.to_dict()

        assert data["name"] == "Test"
        assert data["description"] == "Test description"
        assert "id" in data
        assert "settings" in data

    def test_profile_from_dict(self):
        """Test profile deserialization from dict."""
        profile = Profile(name="Original")
        data = profile.to_dict()
        restored = Profile.from_dict(data)

        assert restored.name == profile.name
        assert str(restored.id) == str(profile.id)

    def test_profile_from_template(self):
        """Test profile creation from template."""
        template = ProfileTemplate(
            name="Template",
            settings=ProfileSettings(theme="dark"),
        )
        profile = Profile.from_template(template, "New Profile")

        assert profile.name == "New Profile"
        assert profile.settings.theme == "dark"
        assert profile.created_from_template_id == template.id

    def test_effective_settings_no_parent(self):
        """Test effective settings without parent."""
        profile = Profile(name="Test")
        profile.settings.theme = "dark"

        effective = profile.get_effective_settings()
        assert effective.theme == "dark"

    def test_effective_settings_with_parent(self):
        """Test effective settings with inheritance."""
        parent = Profile(name="Parent")
        parent.settings.theme = "dark"
        parent.settings.language = "de"

        child = Profile(name="Child", parent_profile_id=parent.id)
        # Child only overrides language
        child.settings.language = "en"

        effective = child.get_effective_settings(parent)
        assert effective.theme == "dark"  # Inherited
        assert effective.language == "en"  # Overridden


class TestProfileTemplate:
    """Tests for ProfileTemplate model."""

    def test_template_creation(self):
        """Test template creation."""
        template = ProfileTemplate(
            name="My Template",
            description="A custom template",
        )

        assert template.name == "My Template"
        assert template.is_builtin is False
        assert isinstance(template.id, UUID)

    def test_builtin_template(self):
        """Test builtin template flag."""
        template = ProfileTemplate(
            name="Default",
            is_builtin=True,
        )

        assert template.is_builtin is True
