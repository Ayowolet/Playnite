"""Tests for backup profile management."""

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.profiles import BackupProfileManager


@pytest.fixture
def manager(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    return BackupProfileManager(db)


class TestCreateProfile:
    def test_create_profile(self, manager):
        profile = manager.create_profile(
            name="daily",
            description="Daily backup profile",
            retention_days=7,
            max_backups=5,
            encrypt=True,
        )
        assert profile.id is not None
        assert profile.name == "daily"
        assert profile.description == "Daily backup profile"
        assert profile.retention_days == 7
        assert profile.max_backups == 5
        assert profile.encrypt is True

    def test_create_duplicate_profile_fails(self, manager):
        manager.create_profile(name="daily")
        with pytest.raises(ValueError, match="already exists"):
            manager.create_profile(name="daily")


class TestGetProfile:
    def test_get_profile(self, manager):
        created = manager.create_profile(name="weekly", description="Weekly")
        fetched = manager.get_profile("weekly")

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "weekly"
        assert fetched.description == "Weekly"

    def test_get_nonexistent_profile(self, manager):
        assert manager.get_profile("nonexistent") is None


class TestListProfiles:
    def test_list_profiles(self, manager):
        manager.create_profile(name="alpha")
        manager.create_profile(name="beta")

        profiles = manager.list_profiles()
        names = [p.name for p in profiles]

        assert len(profiles) == 2
        assert "alpha" in names
        assert "beta" in names


class TestUpdateProfile:
    def test_update_profile(self, manager):
        profile = manager.create_profile(
            name="mutable",
            description="old description",
            retention_days=30,
        )

        manager.update_profile(
            profile.id,
            description="new description",
            retention_days=60,
            encrypt=True,
        )

        updated = manager.get_profile("mutable")
        assert updated.description == "new description"
        assert updated.retention_days == 60
        assert updated.encrypt is True


class TestDeleteProfile:
    def test_delete_profile(self, manager):
        profile = manager.create_profile(name="temp")
        assert manager.get_profile("temp") is not None

        manager.delete_profile(profile.id)
        assert manager.get_profile("temp") is None
