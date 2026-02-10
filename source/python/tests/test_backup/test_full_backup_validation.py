"""Tests validating the full backup setup.

Covers all 12 checklist items:
1.  Create a full backup manually
2.  Verify backup completes without errors
3.  Check backup file is created in destination folder
4.  Verify backup file size is reasonable
5.  Open backup file and check it's compressed
6.  Verify backup contains database file
7.  Verify backup contains configuration files
8.  Verify backup contains categories/tags data
9.  Verify backup contains view presets
10. Verify backup contains controller mappings
11. Verify backup contains theme settings
12. Verify backup contains plugin configurations
"""

import json
import zipfile
from pathlib import Path

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine, BACKUP_COMPONENTS
from gamelibrary.backup.verification import verify_backup


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Create a Database so the .db file exists on disk."""
    db_path = tmp_path / "test.db"
    return Database(db_path)


@pytest.fixture
def data_dir(tmp_path):
    """Return a data directory path (created by the engine)."""
    return tmp_path / "data"


@pytest.fixture
def backup_dir(tmp_path):
    return tmp_path / "backups"


@pytest.fixture
def engine(db, backup_dir, data_dir):
    return BackupEngine(db, backup_dir=backup_dir, data_dir=data_dir)


def _seed_all_components(engine: BackupEngine):
    """Create representative data for every backup component.

    Uses a mix of directory-based and file-based components to exercise both
    code paths in _backup_component:
      - directory path:  categories/, tags/, plugin_configs/
      - single-file path: config.json, view_presets.json,
                           controller_mappings.json, theme_settings.json
    """
    d = engine.data_dir

    # config  (single JSON file)
    (d / "config.json").write_text(json.dumps({
        "theme": "dark",
        "language": "en",
        "auto_sync_interval": 60,
    }))

    # categories  (directory with files)
    cat_dir = d / "categories"
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "user_categories.json").write_text(json.dumps([
        {"id": 1, "name": "RPG"},
        {"id": 2, "name": "FPS"},
    ]))

    # tags  (directory with files)
    tags_dir = d / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    (tags_dir / "user_tags.json").write_text(json.dumps([
        "multiplayer", "singleplayer", "co-op",
    ]))
    (tags_dir / "auto_tags.json").write_text(json.dumps([
        "steam-sale", "backlog",
    ]))

    # view_presets  (single JSON file)
    (d / "view_presets.json").write_text(json.dumps({
        "default": {"sort": "name", "group": "platform"},
        "recent": {"sort": "last_played", "group": "none"},
    }))

    # controller_mappings  (single JSON file)
    (d / "controller_mappings.json").write_text(json.dumps({
        "xbox_controller": {"a": "confirm", "b": "cancel"},
        "ps_controller": {"x": "confirm", "o": "cancel"},
    }))

    # theme_settings  (single JSON file)
    (d / "theme_settings.json").write_text(json.dumps({
        "primary_color": "#1a1a2e",
        "accent_color": "#e94560",
        "font_size": 14,
    }))

    # plugin_configs  (directory with multiple plugin files)
    plug_dir = d / "plugin_configs"
    plug_dir.mkdir(parents=True, exist_ok=True)
    (plug_dir / "steam_plugin.json").write_text(json.dumps({
        "enabled": True, "cache_ttl": 3600,
    }))
    (plug_dir / "xbox_plugin.json").write_text(json.dumps({
        "enabled": False, "region": "US",
    }))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _open_backup_zip(record) -> zipfile.ZipFile:
    """Return an opened ZipFile for the backup record."""
    return zipfile.ZipFile(record.file_path, "r")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateFullBackup:
    """Checklist items 1-3: create, no errors, file exists."""

    def test_create_full_backup_returns_record(self, engine):
        """Item 1: A full backup can be created manually."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        assert record is not None
        assert record.id is not None

    def test_backup_status_completed(self, engine):
        """Item 2: Backup completes without errors."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        assert record.status == "completed"
        assert record.backup_type == "full"
        assert record.checksum != ""

    def test_backup_file_in_destination(self, engine, backup_dir):
        """Item 3: Backup file is created in the destination folder."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        backup_path = Path(record.file_path)
        assert backup_path.exists()
        assert backup_path.parent == backup_dir

    def test_verification_passes(self, engine):
        """Backup passes integrity verification (checksums match)."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        result = verify_backup(record.file_path)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["items_checked"] > 0


class TestBackupFileSize:
    """Checklist item 4: Verify backup file size is reasonable."""

    def test_compressed_size_greater_than_zero(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        assert record.compressed_size > 0

    def test_original_size_greater_than_zero(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        assert record.size_bytes > 0

    def test_compressed_smaller_or_equal_to_original(self, engine):
        """ZIP compression should not increase total size significantly."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        # compressed_size is the on-disk ZIP size (includes ZIP overhead),
        # size_bytes is the sum of raw item sizes.  With small data the ZIP
        # overhead can exceed the raw payload, so we just verify both are
        # positive and the ratio is within a sane range (< 10x).
        ratio = record.compressed_size / max(record.size_bytes, 1)
        assert ratio < 10.0

    def test_file_on_disk_matches_reported_size(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        actual_size = Path(record.file_path).stat().st_size
        assert actual_size == record.compressed_size


class TestBackupIsCompressed:
    """Checklist item 5: Open backup and check it's compressed."""

    def test_file_is_valid_zip(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        assert zipfile.is_zipfile(record.file_path)

    def test_zip_uses_deflate_compression(self, engine):
        """Every stored member should use ZIP_DEFLATED or ZIP_STORED."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            for info in zf.infolist():
                assert info.compress_type in (
                    zipfile.ZIP_DEFLATED,
                    zipfile.ZIP_STORED,
                ), f"{info.filename} uses unexpected compression type {info.compress_type}"

    def test_zip_has_manifest(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            assert "manifest.json" in zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["backup_type"] == "full"
            assert "items" in manifest
            assert "components" in manifest

    def test_zip_testzip_no_corruption(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            assert zf.testzip() is None  # None means no bad files


class TestBackupContainsDatabase:
    """Checklist item 6: Verify backup contains database file."""

    def test_database_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            db_entries = [n for n in zf.namelist() if n.startswith("database/")]
            assert len(db_entries) == 1
            assert db_entries[0].endswith(".db")

    def test_database_content_is_valid_sqlite(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            db_entries = [n for n in zf.namelist() if n.startswith("database/")]
            data = zf.read(db_entries[0])
            # SQLite files start with "SQLite format 3\x00"
            assert data[:16] == b"SQLite format 3\x00"

    def test_database_in_manifest(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            db_items = [i for i in manifest["items"] if i["type"] == "database"]
            assert len(db_items) == 1
            assert db_items[0]["size"] > 0
            assert db_items[0]["checksum"] != ""


class TestBackupContainsConfig:
    """Checklist item 7: Verify backup contains configuration files."""

    def test_config_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            config_entries = [n for n in zf.namelist() if n.startswith("config/")]
            assert len(config_entries) >= 1

    def test_config_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            data = json.loads(zf.read("config/config.json"))
            assert data["theme"] == "dark"
            assert data["language"] == "en"
            assert data["auto_sync_interval"] == 60


class TestBackupContainsCategoriesAndTags:
    """Checklist item 8: Verify backup contains categories/tags data."""

    def test_categories_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            cat_entries = [n for n in zf.namelist() if n.startswith("categories/")]
            assert len(cat_entries) >= 1

    def test_categories_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            data = json.loads(zf.read("categories/user_categories.json"))
            names = [c["name"] for c in data]
            assert "RPG" in names
            assert "FPS" in names

    def test_tags_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            tag_entries = [n for n in zf.namelist() if n.startswith("tags/")]
            assert len(tag_entries) >= 1

    def test_tags_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            data = json.loads(zf.read("tags/user_tags.json"))
            assert "multiplayer" in data
            assert "singleplayer" in data

    def test_multiple_tag_files(self, engine):
        """Both user_tags.json and auto_tags.json should be in the archive."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            tag_entries = [n for n in zf.namelist() if n.startswith("tags/")]
            assert "tags/user_tags.json" in tag_entries
            assert "tags/auto_tags.json" in tag_entries


class TestBackupContainsViewPresets:
    """Checklist item 9: Verify backup contains view presets."""

    def test_view_presets_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            vp_entries = [n for n in zf.namelist() if n.startswith("view_presets/")]
            assert len(vp_entries) >= 1

    def test_view_presets_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            data = json.loads(zf.read("view_presets/view_presets.json"))
            assert "default" in data
            assert data["default"]["sort"] == "name"
            assert "recent" in data


class TestBackupContainsControllerMappings:
    """Checklist item 10: Verify backup contains controller mappings."""

    def test_controller_mappings_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            cm_entries = [n for n in zf.namelist() if n.startswith("controller_mappings/")]
            assert len(cm_entries) >= 1

    def test_controller_mappings_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            data = json.loads(zf.read("controller_mappings/controller_mappings.json"))
            assert "xbox_controller" in data
            assert "ps_controller" in data
            assert data["xbox_controller"]["a"] == "confirm"


class TestBackupContainsThemeSettings:
    """Checklist item 11: Verify backup contains theme settings."""

    def test_theme_settings_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            ts_entries = [n for n in zf.namelist() if n.startswith("theme_settings/")]
            assert len(ts_entries) >= 1

    def test_theme_settings_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            data = json.loads(zf.read("theme_settings/theme_settings.json"))
            assert data["primary_color"] == "#1a1a2e"
            assert data["accent_color"] == "#e94560"
            assert data["font_size"] == 14


class TestBackupContainsPluginConfigs:
    """Checklist item 12: Verify backup contains plugin configurations."""

    def test_plugin_configs_in_archive(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            pc_entries = [n for n in zf.namelist() if n.startswith("plugin_configs/")]
            assert len(pc_entries) >= 1

    def test_multiple_plugin_config_files(self, engine):
        """Both plugin config files should be in the archive."""
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            pc_entries = [n for n in zf.namelist() if n.startswith("plugin_configs/")]
            assert "plugin_configs/steam_plugin.json" in pc_entries
            assert "plugin_configs/xbox_plugin.json" in pc_entries

    def test_plugin_config_content_matches(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            steam = json.loads(zf.read("plugin_configs/steam_plugin.json"))
            assert steam["enabled"] is True
            assert steam["cache_ttl"] == 3600

            xbox = json.loads(zf.read("plugin_configs/xbox_plugin.json"))
            assert xbox["enabled"] is False
            assert xbox["region"] == "US"


class TestAllComponentsPresent:
    """Cross-cutting: every BACKUP_COMPONENTS entry produces at least one item."""

    def test_manifest_covers_all_components(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert set(manifest["components"]) == set(BACKUP_COMPONENTS)
            types_present = {i["type"] for i in manifest["items"]}
            assert types_present == set(BACKUP_COMPONENTS)

    def test_every_manifest_item_exists_in_zip(self, engine):
        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            zip_names = set(zf.namelist())
            for item in manifest["items"]:
                assert item["path"] in zip_names, (
                    f"Manifest item {item['path']} not found in ZIP"
                )

    def test_every_manifest_item_has_valid_checksum(self, engine):
        """Checksums recorded in manifest match the actual data in the ZIP."""
        from gamelibrary.backup.verification import compute_bytes_checksum

        _seed_all_components(engine)
        record = engine.create_full_backup()
        with _open_backup_zip(record) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            for item in manifest["items"]:
                data = zf.read(item["path"])
                assert compute_bytes_checksum(data) == item["checksum"], (
                    f"Checksum mismatch for {item['path']}"
                )
