"""Unit tests for backup/cloud.py — cloud sync destination helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from playnite.backup.cloud import (
    SUPPORTED_SERVICES,
    CloudDestination,
    default_sync_path,
    make_destination,
)


class TestCloudDestination:
    def test_resolved_path_with_subfolder(self, tmp_path):
        dest = CloudDestination(service="gdrive", sync_path=str(tmp_path), subfolder="backups")
        assert dest.resolved_path() == tmp_path / "backups"

    def test_resolved_path_empty_subfolder(self, tmp_path):
        dest = CloudDestination(service="gdrive", sync_path=str(tmp_path), subfolder="")
        assert dest.resolved_path() == tmp_path

    def test_is_available_existing_dir(self, tmp_path):
        dest = CloudDestination(service="dropbox", sync_path=str(tmp_path))
        assert dest.is_available() is True

    def test_is_available_missing_dir(self, tmp_path):
        dest = CloudDestination(service="dropbox", sync_path=str(tmp_path / "nonexistent"))
        assert dest.is_available() is False

    def test_label_contains_service_and_subfolder(self):
        dest = CloudDestination(service="gdrive", sync_path="/x", subfolder="pn_bk")
        lbl = dest.label()
        assert "gdrive" in lbl
        assert "pn_bk" in lbl

    def test_default_subfolder(self):
        dest = CloudDestination(service="onedrive", sync_path="/x")
        assert dest.subfolder == "playnite_backups"


class TestDefaultSyncPath:
    def test_gdrive_returns_path(self):
        path = default_sync_path("gdrive")
        assert path is not None and isinstance(path, str)

    def test_dropbox_returns_path(self):
        assert default_sync_path("dropbox") is not None

    def test_onedrive_returns_path(self):
        assert default_sync_path("onedrive") is not None

    def test_unknown_service_returns_none(self):
        assert default_sync_path("unknown_service_xyz") is None

    def test_unrecognised_os_falls_back_to_linux(self):
        with patch("playnite.backup.cloud.platform.system", return_value="FreeBSD"):
            path = default_sync_path("gdrive")
        # The linux fallback key should yield a result
        assert path is not None


class TestMakeDestination:
    def test_make_gdrive_explicit_path(self, tmp_path):
        dest = make_destination("gdrive", sync_path=str(tmp_path))
        assert dest.service == "gdrive"
        assert dest.sync_path == str(tmp_path)

    def test_make_dropbox_default_path(self):
        dest = make_destination("dropbox")
        assert dest.service == "dropbox"
        assert dest.sync_path  # non-empty default path

    def test_make_onedrive_custom_subfolder(self, tmp_path):
        dest = make_destination("onedrive", sync_path=str(tmp_path), subfolder="my_pn")
        assert dest.subfolder == "my_pn"

    def test_make_unknown_service_with_explicit_path(self, tmp_path):
        dest = make_destination("custom_cloud", sync_path=str(tmp_path))
        assert dest.service == "custom_cloud"

    def test_make_unknown_service_no_path_raises(self):
        with pytest.raises(ValueError, match="Unknown cloud service"):
            make_destination("totally_unknown_service_no_path")

    def test_supported_services_constant(self):
        assert set(SUPPORTED_SERVICES) == {"gdrive", "dropbox", "onedrive"}
