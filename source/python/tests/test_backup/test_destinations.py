"""Tests validating multiple backup destinations.

Covers all 12 checklist items:
1.  Configure local folder destination
2.  Create backup to local folder
3.  Verify backup appears in local folder
4.  Configure external drive destination
5.  Create backup to external drive
6.  Configure network share destination
7.  Create backup to network share
8.  Configure cloud storage destination (Google Drive/Dropbox/OneDrive)
9.  Create backup to cloud storage
10. Verify upload completes successfully
11. Test with multiple destinations enabled
12. Verify backup goes to all configured destinations
"""

import json
import zipfile
from pathlib import Path

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.destinations import (
    DestinationManager,
    SimulatedCloudProvider,
    get_cloud_provider,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "dest_test.db")


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def backup_dir(tmp_path):
    return tmp_path / "backups"


@pytest.fixture
def engine(db, backup_dir, data_dir):
    return BackupEngine(db, backup_dir=backup_dir, data_dir=data_dir)


@pytest.fixture
def dest_mgr(db):
    return DestinationManager(db)


@pytest.fixture
def local_dest(tmp_path):
    """A local folder path to use as a destination."""
    p = tmp_path / "local_dest"
    p.mkdir()
    return p


@pytest.fixture
def ext_drive(tmp_path):
    """Simulate an external drive as a temp directory."""
    p = tmp_path / "ext_drive" / "GameBackups"
    return p  # not created yet — DestinationManager should create it


@pytest.fixture
def network_share(tmp_path):
    """Simulate a network share as a temp directory."""
    p = tmp_path / "network_share" / "nas_backups"
    return p


@pytest.fixture
def cloud_sim_dir(tmp_path):
    """Directory where the simulated cloud provider stores files."""
    p = tmp_path / "cloud_sim"
    p.mkdir()
    return p


def _seed_data(engine):
    """Put minimal data so backups have content."""
    (engine.data_dir / "config.json").write_text(
        json.dumps({"theme": "dark"})
    )


# ---------------------------------------------------------------------------
# 1-3: Local folder destination
# ---------------------------------------------------------------------------

class TestLocalFolderDestination:
    """Checklist items 1-3: Configure, create, verify local folder."""

    def test_configure_local_destination(self, dest_mgr, local_dest):
        """Item 1: Configure a local folder destination."""
        dest_id = dest_mgr.register_destination(
            "my-local", "local", {"path": str(local_dest)}
        )
        assert dest_id > 0

        dest = dest_mgr.get_destination("my-local")
        assert dest is not None
        assert dest["dest_type"] == "local"
        assert dest["config"]["path"] == str(local_dest)

    def test_create_backup_to_local_folder(self, engine, dest_mgr, local_dest):
        """Item 2: Create a backup distributed to a local folder."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "my-local", "local", {"path": str(local_dest)}
        )

        record = engine.create_full_backup(destinations=["my-local"])
        assert record.status == "completed"

    def test_backup_appears_in_local_folder(self, engine, dest_mgr, local_dest):
        """Item 3: Verify the backup file exists in the destination folder."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "my-local", "local", {"path": str(local_dest)}
        )

        record = engine.create_full_backup(destinations=["my-local"])

        # Check: file in the local destination folder
        files = list(local_dest.iterdir())
        assert len(files) == 1
        assert files[0].name == Path(record.file_path).name
        assert files[0].stat().st_size > 0

    def test_local_copy_is_valid_zip(self, engine, dest_mgr, local_dest):
        """The copy in the destination is a valid, openable ZIP."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "my-local", "local", {"path": str(local_dest)}
        )
        engine.create_full_backup(destinations=["my-local"])

        copied = list(local_dest.iterdir())[0]
        assert zipfile.is_zipfile(str(copied))
        with zipfile.ZipFile(str(copied)) as zf:
            assert "manifest.json" in zf.namelist()


# ---------------------------------------------------------------------------
# 4-5: External drive destination
# ---------------------------------------------------------------------------

class TestExternalDriveDestination:
    """Checklist items 4-5: Configure and create backup to external drive.

    An external drive is just a filesystem path (e.g., /Volumes/MyDrive).
    We simulate it with a temp directory.
    """

    def test_configure_external_drive(self, dest_mgr, ext_drive):
        """Item 4: Configure an external drive destination."""
        dest_id = dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )
        assert dest_id > 0

        # The directory should be created by register_destination
        assert ext_drive.is_dir()

        dest = dest_mgr.get_destination("ext-drive")
        assert dest["dest_type"] == "local"
        assert dest["config"]["path"] == str(ext_drive)

    def test_create_backup_to_external_drive(self, engine, dest_mgr, ext_drive):
        """Item 5: Create a backup to the external drive."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )

        record = engine.create_full_backup(destinations=["ext-drive"])
        assert record.status == "completed"

        files = list(ext_drive.iterdir())
        assert len(files) == 1
        assert files[0].stat().st_size > 0


# ---------------------------------------------------------------------------
# 6-7: Network share destination
# ---------------------------------------------------------------------------

class TestNetworkShareDestination:
    """Checklist items 6-7: Configure and create backup to network share.

    A network share is a mounted filesystem path (e.g., /mnt/nas/backups).
    We simulate it with a temp directory.
    """

    def test_configure_network_share(self, dest_mgr, network_share):
        """Item 6: Configure a network share destination."""
        dest_id = dest_mgr.register_destination(
            "nas-backup", "local", {"path": str(network_share)}
        )
        assert dest_id > 0
        assert network_share.is_dir()

    def test_create_backup_to_network_share(self, engine, dest_mgr, network_share):
        """Item 7: Create a backup to the network share."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "nas-backup", "local", {"path": str(network_share)}
        )

        record = engine.create_full_backup(destinations=["nas-backup"])
        assert record.status == "completed"

        files = list(network_share.iterdir())
        assert len(files) == 1
        assert files[0].name == Path(record.file_path).name


# ---------------------------------------------------------------------------
# 8-10: Cloud storage destination
# ---------------------------------------------------------------------------

class TestCloudStorageDestination:
    """Checklist items 8-10: Configure, create, verify cloud storage.

    Uses SimulatedCloudProvider which copies files to a local directory
    to simulate cloud uploads without requiring real cloud credentials.
    """

    def test_configure_cloud_destination(self, dest_mgr, cloud_sim_dir):
        """Item 8: Configure a cloud storage destination."""
        dest_id = dest_mgr.register_destination(
            "my-gdrive", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )
        assert dest_id > 0

        dest = dest_mgr.get_destination("my-gdrive")
        assert dest["dest_type"] == "cloud"
        assert dest["config"]["provider"] == "simulated"

    def test_create_backup_to_cloud(self, engine, dest_mgr, cloud_sim_dir):
        """Item 9: Create a backup to cloud storage."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "my-gdrive", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )

        record = engine.create_full_backup(destinations=["my-gdrive"])
        assert record.status == "completed"

    def test_upload_completes_successfully(self, engine, dest_mgr, cloud_sim_dir):
        """Item 10: Verify the upload completed successfully."""
        _seed_data(engine)
        dest_mgr.register_destination(
            "my-gdrive", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )

        record = engine.create_full_backup(destinations=["my-gdrive"])

        # Check distribution results in metadata
        assert "distributions" in record.metadata
        dist = record.metadata["distributions"]
        assert len(dist) == 1
        assert dist[0]["status"] == "completed"
        assert dist[0]["destination"] == "my-gdrive"
        assert dist[0]["type"] == "cloud"

        # Check the file actually appeared in the simulated cloud dir
        files = list(cloud_sim_dir.iterdir())
        assert len(files) == 1
        assert files[0].stat().st_size > 0

    def test_cloud_provider_interface(self, cloud_sim_dir, tmp_path):
        """SimulatedCloudProvider implements the CloudProvider interface."""
        provider = SimulatedCloudProvider({
            "provider": "simulated",
            "simulate_dir": str(cloud_sim_dir),
        })
        assert provider.validate_config() is True

        # Create a test file to upload
        test_file = tmp_path / "test_upload.zip"
        test_file.write_text("test content")

        result = provider.upload(test_file, "test_upload.zip")
        assert result["status"] == "completed"
        assert (cloud_sim_dir / "test_upload.zip").exists()

        # Download it back
        download_path = tmp_path / "downloaded.zip"
        result = provider.download("test_upload.zip", download_path)
        assert result["status"] == "completed"
        assert download_path.read_text() == "test content"

    def test_unknown_cloud_provider_raises(self):
        """Requesting an unknown cloud provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown cloud provider"):
            get_cloud_provider({"provider": "nonexistent"})


# ---------------------------------------------------------------------------
# 11-12: Multiple destinations
# ---------------------------------------------------------------------------

class TestMultipleDestinations:
    """Checklist items 11-12: Multiple destinations enabled, backup goes to all."""

    def test_multiple_destinations_configured(
        self, dest_mgr, local_dest, ext_drive, cloud_sim_dir
    ):
        """Item 11: Configure multiple destinations simultaneously."""
        dest_mgr.register_destination(
            "local-folder", "local", {"path": str(local_dest)}
        )
        dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )
        dest_mgr.register_destination(
            "cloud-backup", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )

        dests = dest_mgr.list_destinations()
        assert len(dests) == 3
        names = {d["name"] for d in dests}
        assert names == {"local-folder", "ext-drive", "cloud-backup"}

    def test_backup_goes_to_all_destinations(
        self, engine, dest_mgr, local_dest, ext_drive, cloud_sim_dir
    ):
        """Item 12: A single backup is distributed to all configured destinations."""
        _seed_data(engine)

        dest_mgr.register_destination(
            "local-folder", "local", {"path": str(local_dest)}
        )
        dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )
        dest_mgr.register_destination(
            "cloud-backup", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )

        record = engine.create_full_backup(
            destinations=["local-folder", "ext-drive", "cloud-backup"]
        )

        assert record.status == "completed"

        # Verify: file in local folder
        local_files = list(local_dest.iterdir())
        assert len(local_files) == 1

        # Verify: file on external drive
        ext_files = list(ext_drive.iterdir())
        assert len(ext_files) == 1

        # Verify: file in cloud sim
        cloud_files = list(cloud_sim_dir.iterdir())
        assert len(cloud_files) == 1

        # All copies have the same filename as the original
        original_name = Path(record.file_path).name
        assert local_files[0].name == original_name
        assert ext_files[0].name == original_name
        assert cloud_files[0].name == original_name

    def test_distribution_results_in_metadata(
        self, engine, dest_mgr, local_dest, ext_drive, cloud_sim_dir
    ):
        """Distribution results are recorded in the backup metadata."""
        _seed_data(engine)

        dest_mgr.register_destination(
            "local-folder", "local", {"path": str(local_dest)}
        )
        dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )
        dest_mgr.register_destination(
            "cloud-backup", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )

        record = engine.create_full_backup(
            destinations=["local-folder", "ext-drive", "cloud-backup"]
        )

        assert "distributions" in record.metadata
        dist = record.metadata["distributions"]
        assert len(dist) == 3
        for d in dist:
            assert d["status"] == "completed"

        dest_names = {d["destination"] for d in dist}
        assert dest_names == {"local-folder", "ext-drive", "cloud-backup"}

    def test_destination_field_lists_all(
        self, engine, dest_mgr, local_dest, ext_drive
    ):
        """The record's destination field includes all successful destinations."""
        _seed_data(engine)

        dest_mgr.register_destination(
            "local-folder", "local", {"path": str(local_dest)}
        )
        dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )

        record = engine.create_full_backup(
            destinations=["local-folder", "ext-drive"]
        )

        # destination field is comma-separated: "local,local-folder,ext-drive"
        parts = record.destination.split(",")
        assert "local" in parts
        assert "local-folder" in parts
        assert "ext-drive" in parts

    def test_all_copies_are_identical(
        self, engine, dest_mgr, local_dest, ext_drive, cloud_sim_dir
    ):
        """All destination copies are byte-identical to the original."""
        _seed_data(engine)

        dest_mgr.register_destination(
            "local-folder", "local", {"path": str(local_dest)}
        )
        dest_mgr.register_destination(
            "ext-drive", "local", {"path": str(ext_drive)}
        )
        dest_mgr.register_destination(
            "cloud-backup", "cloud", {
                "provider": "simulated",
                "simulate_dir": str(cloud_sim_dir),
            }
        )

        record = engine.create_full_backup(
            destinations=["local-folder", "ext-drive", "cloud-backup"]
        )

        original_bytes = Path(record.file_path).read_bytes()
        assert list(local_dest.iterdir())[0].read_bytes() == original_bytes
        assert list(ext_drive.iterdir())[0].read_bytes() == original_bytes
        assert list(cloud_sim_dir.iterdir())[0].read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# Edge cases and destination management
# ---------------------------------------------------------------------------

class TestDestinationManagement:
    """CRUD and edge-case tests for DestinationManager."""

    def test_register_and_remove(self, dest_mgr, local_dest):
        dest_mgr.register_destination("temp", "local", {"path": str(local_dest)})
        assert dest_mgr.get_destination("temp") is not None

        dest_mgr.remove_destination("temp")
        assert dest_mgr.get_destination("temp") is None

    def test_update_existing_destination(self, dest_mgr, local_dest, tmp_path):
        dest_mgr.register_destination("reuse", "local", {"path": str(local_dest)})
        new_path = tmp_path / "new_dest"
        new_path.mkdir()
        dest_mgr.register_destination("reuse", "local", {"path": str(new_path)})

        dest = dest_mgr.get_destination("reuse")
        assert dest["config"]["path"] == str(new_path)

    def test_invalid_dest_type_raises(self, dest_mgr):
        with pytest.raises(ValueError, match="Invalid destination type"):
            dest_mgr.register_destination("bad", "ftp", {"path": "/tmp"})

    def test_local_without_path_raises(self, dest_mgr):
        with pytest.raises(ValueError, match="requires 'path'"):
            dest_mgr.register_destination("bad", "local", {})

    def test_cloud_without_provider_raises(self, dest_mgr):
        with pytest.raises(ValueError, match="requires 'provider'"):
            dest_mgr.register_destination("bad", "cloud", {})

    def test_distribute_nonexistent_dest_skipped(self, engine, dest_mgr):
        """Distributing to a non-existent destination name is skipped gracefully."""
        _seed_data(engine)
        record = engine.create_full_backup(destinations=["does-not-exist"])
        # Should still complete — the missing dest is skipped
        assert record.status == "completed"

    def test_no_destinations_means_local_only(self, engine, backup_dir):
        """When no destinations are specified, backup stays in backup_dir only."""
        _seed_data(engine)
        record = engine.create_full_backup()
        assert record.destination == "local"
        assert Path(record.file_path).parent == backup_dir
