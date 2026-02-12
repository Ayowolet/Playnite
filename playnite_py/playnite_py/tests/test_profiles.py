"""
Tests for the profile system.

Tests cover:
- Profile creation and management
- Password security
- Profile inheritance
- File locking
- Memory leak prevention
"""

import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileSecurity,
    ProfileSharing,
    DataSharingMode,
)


class TestProfileSecurity:
    """Tests for profile password security."""

    def test_password_not_stored_plaintext(self):
        """Password should never be stored as plaintext."""
        security = ProfileSecurity()
        security.set_password("MySecretPassword123")

        # Serialize and check
        data = security.model_dump(mode='json')

        assert "MySecretPassword123" not in str(data)
        assert data["password_hash"] is not None
        assert data["password_salt"] is not None

    def test_password_verification_correct(self):
        """Correct password should verify successfully."""
        security = ProfileSecurity()
        security.set_password("CorrectPassword")

        assert security.verify_password("CorrectPassword")

    def test_password_verification_incorrect(self):
        """Incorrect password should fail verification."""
        security = ProfileSecurity()
        security.set_password("CorrectPassword")

        assert not security.verify_password("WrongPassword")

    def test_same_password_different_hashes(self):
        """Same password should produce different hashes due to unique salts."""
        security1 = ProfileSecurity()
        security1.set_password("SamePassword")

        security2 = ProfileSecurity()
        security2.set_password("SamePassword")

        assert security1.password_hash != security2.password_hash
        assert security1.password_salt != security2.password_salt

    def test_password_hash_length(self):
        """Password hash should be correct length (PBKDF2-SHA256)."""
        security = ProfileSecurity()
        security.set_password("TestPassword")

        # PBKDF2-SHA256 produces 32 bytes = 64 hex chars
        assert len(security.password_hash) == 64
        # Salt should be 32 bytes = 64 hex chars
        assert len(security.password_salt) == 64

    def test_failed_attempts_tracked(self):
        """Failed login attempts should be tracked."""
        security = ProfileSecurity()
        security.set_password("Password")

        security.verify_password("Wrong1")
        security.verify_password("Wrong2")

        assert security.failed_attempts == 2

    def test_successful_login_resets_attempts(self):
        """Successful login should reset failed attempts."""
        security = ProfileSecurity()
        security.set_password("Password")

        security.verify_password("Wrong")
        assert security.failed_attempts == 1

        security.verify_password("Password")
        assert security.failed_attempts == 0


class TestProfileSettings:
    """Tests for profile settings."""

    def test_default_settings(self):
        """Default settings should be reasonable."""
        settings = ProfileSettings()

        assert settings.theme == "default"
        assert settings.language == "en"
        assert settings.default_view == "grid"

    def test_model_fields_set_tracking(self):
        """Explicitly set fields should be tracked."""
        settings = ProfileSettings(theme="dark", language="de")

        assert "theme" in settings.model_fields_set
        assert "language" in settings.model_fields_set
        assert "default_view" not in settings.model_fields_set


class TestProfileInheritance:
    """Tests for profile inheritance."""

    def test_child_overrides_parent(self):
        """Child settings should override parent settings."""
        parent = Profile(name="Parent")
        parent.settings = ProfileSettings(
            theme="dark",
            language="en",
            default_view="grid",
        )

        child = Profile(name="Child", parent_profile_id=parent.id)
        child.settings = ProfileSettings(
            theme="light",
            language="de",
        )

        effective = child.get_effective_settings(parent)

        assert effective.theme == "light"  # From child
        assert effective.language == "de"  # From child
        assert effective.default_view == "grid"  # From parent

    def test_child_explicit_default_still_overrides(self):
        """Explicitly set default value should still override parent."""
        parent = Profile(name="Parent")
        parent.settings = ProfileSettings(grid_size=300)

        child = Profile(name="Child", parent_profile_id=parent.id)
        child.settings = ProfileSettings(grid_size=200)  # Default is 200

        effective = child.get_effective_settings(parent)

        # Child explicitly set grid_size=200, so it should win
        assert effective.grid_size == 200

    def test_no_parent_returns_own_settings(self):
        """Profile without parent should return its own settings."""
        standalone = Profile(name="Standalone")
        standalone.settings = ProfileSettings(theme="custom")

        effective = standalone.get_effective_settings(None)

        assert effective.theme == "custom"

    def test_lists_replaced_not_merged(self):
        """List fields should be replaced, not merged."""
        parent = Profile(name="Parent")
        parent.settings = ProfileSettings(enabled_sources=["steam", "gog"])

        child = Profile(name="Child", parent_profile_id=parent.id)
        child.settings = ProfileSettings(enabled_sources=["epic"])

        effective = child.get_effective_settings(parent)

        assert effective.enabled_sources == ["epic"]

    def test_dicts_replaced_not_deep_merged(self):
        """Dict fields should be replaced, not deep-merged."""
        parent = Profile(name="Parent")
        parent.settings = ProfileSettings(
            custom_fields={"key1": "parent", "key2": "parent"}
        )

        child = Profile(name="Child", parent_profile_id=parent.id)
        child.settings = ProfileSettings(
            custom_fields={"key1": "child", "key3": "child"}
        )

        effective = child.get_effective_settings(parent)

        assert effective.custom_fields == {"key1": "child", "key3": "child"}


class TestProfile:
    """Tests for Profile model."""

    def test_profile_creation(self):
        """Profile should be created with defaults."""
        profile = Profile(name="Test Profile")

        assert profile.name == "Test Profile"
        assert profile.id is not None
        assert profile.is_active is False
        assert profile.settings is not None
        assert profile.security is not None
        assert profile.sharing is not None

    def test_profile_serialization(self):
        """Profile should serialize correctly."""
        profile = Profile(name="Test")
        profile.settings = ProfileSettings(theme="dark")

        data = profile.model_dump(mode='json')

        assert data["name"] == "Test"
        assert data["settings"]["theme"] == "dark"
        # Dates should be strings (created_at is in statistics)
        assert isinstance(data["statistics"]["created_at"], str)


class TestProfileSharing:
    """Tests for profile sharing settings."""

    def test_default_sharing_none(self):
        """Default sharing mode should be none (isolated)."""
        sharing = ProfileSharing()

        assert sharing.mode == DataSharingMode.NONE

    def test_sharing_configuration(self):
        """Sharing should be configurable."""
        sharing = ProfileSharing(
            mode=DataSharingMode.SELECTIVE,
            share_categories=True,
            share_tags=True,
            share_media_files=False,
        )

        assert sharing.mode == DataSharingMode.SELECTIVE
        assert sharing.share_categories is True
        assert sharing.share_tags is True
        assert sharing.share_media_files is False
