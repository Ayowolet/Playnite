"""
Integration tests: merge operation while the library file is open in another
application (e.g. Playnite).

On Windows, opening a file for writing holds a mandatory lock that causes
PermissionError for any concurrent write.  These tests simulate that scenario
with unittest.mock so they run identically on all platforms.

The tests verify three guarantees:
1. Read-lock  – a clear, actionable error is surfaced (not a raw OS traceback).
2. Write-lock – the same for writes; the original file is never corrupted.
3. Atomic write – a crash or lock failure mid-save leaves the original intact
                  and no stray .tmp file on disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from game_library.merger.merger import LibraryMerger, MergeConfig
from game_library.merger.strategies import MergeStrategy
from game_library.storage.json_store import JsonStore
from tests.conftest import make_game, make_library


# ── shared helpers ────────────────────────────────────────────────────────────

def _save(path: Path, *game_names: str) -> None:
    games = [make_game(n, year=2020, platforms=["PC"], source="Steam") for n in game_names]
    JsonStore(path).save(make_library("test", games))


def _game_names(path: Path) -> set[str]:
    return {g.Name for g in JsonStore(path).load().all_games()}


# ── read-lock tests ───────────────────────────────────────────────────────────

class TestReadLock:
    def test_load_raises_clear_error(self, tmp_path):
        """PermissionError during read must produce a human-readable message."""
        path = tmp_path / "lib.json"
        _save(path, "Game A")

        with patch.object(Path, "read_text", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError, match="open in another application"):
                JsonStore(path).load()

    def test_load_error_names_the_file(self, tmp_path):
        """The error message must include the filename so the user knows which
        file to close."""
        path = tmp_path / "mylib.json"
        _save(path, "Game A")

        with patch.object(Path, "read_text", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError, match="mylib.json"):
                JsonStore(path).load()

    def test_load_error_suggests_closing_app(self, tmp_path):
        """The error must tell the user to close the other application."""
        path = tmp_path / "lib.json"
        _save(path, "Game A")

        with patch.object(Path, "read_text", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError, match="Close it and retry"):
                JsonStore(path).load()


# ── write-lock tests ──────────────────────────────────────────────────────────

class TestWriteLock:
    def test_save_raises_clear_error_when_tmp_write_locked(self, tmp_path):
        """PermissionError writing the .tmp file must produce a human-readable
        message."""
        path = tmp_path / "lib.json"
        lib = make_library("test", [make_game("Game A")])

        with patch.object(Path, "write_text", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError, match="open in another application"):
                JsonStore(path).save(lib)

    def test_save_raises_clear_error_when_rename_locked(self, tmp_path):
        """PermissionError on the atomic rename must produce a human-readable
        message.  This is the most common failure mode on Windows when Playnite
        holds the file open."""
        path = tmp_path / "lib.json"
        lib = make_library("test", [make_game("Game A")])

        with patch("os.replace", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError, match="open in another application"):
                JsonStore(path).save(lib)

    def test_save_error_names_the_file(self, tmp_path):
        path = tmp_path / "mylib.json"
        lib = make_library("test", [make_game("Game A")])

        with patch("os.replace", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError, match="mylib.json"):
                JsonStore(path).save(lib)


# ── atomic-write guarantees ───────────────────────────────────────────────────

class TestAtomicWrite:
    def test_no_tmp_file_after_successful_save(self, tmp_path):
        """A successful save must not leave a .tmp file on disk."""
        path = tmp_path / "lib.json"
        _save(path, "Game A")

        assert not path.with_suffix(".tmp").exists()
        assert path.exists()

    def test_original_intact_when_rename_locked(self, tmp_path):
        """If the atomic rename fails (file held open), the original library
        file must be unchanged."""
        path = tmp_path / "lib.json"
        _save(path, "Game A")
        original = path.read_text(encoding="utf-8")

        with patch("os.replace", side_effect=PermissionError("locked")):
            with pytest.raises(PermissionError):
                _save(path, "Game B")

        assert path.read_text(encoding="utf-8") == original

    def test_no_tmp_file_after_rename_fails(self, tmp_path):
        """If the atomic rename fails, the .tmp scratch file must be cleaned
        up so no stray files accumulate."""
        path = tmp_path / "lib.json"
        _save(path, "Game A")

        with patch("os.replace", side_effect=PermissionError("locked")):
            with pytest.raises(PermissionError):
                _save(path, "Game B")

        assert not path.with_suffix(".tmp").exists()

    def test_no_tmp_file_after_write_fails(self, tmp_path):
        """If writing the .tmp file itself fails, no .tmp must remain."""
        path = tmp_path / "lib.json"
        lib = make_library("test", [make_game("Game A")])

        with patch.object(Path, "write_text", side_effect=PermissionError("access denied")):
            with pytest.raises(PermissionError):
                JsonStore(path).save(lib)

        assert not path.with_suffix(".tmp").exists()

    def test_roundtrip_after_successful_save(self, tmp_path):
        """Sanity-check: data written atomically must be fully readable back."""
        path = tmp_path / "lib.json"
        _save(path, "Portal 2", "Halo 3")

        assert _game_names(path) == {"Portal 2", "Halo 3"}


# ── full merge pipeline with locked output ────────────────────────────────────

class TestMergePipelineWithLockedFile:
    def test_merge_raises_clear_error_when_output_locked(self, tmp_path):
        """Saving the merged library to a locked file must raise a clear
        PermissionError, not a raw OS exception."""
        out_path = tmp_path / "merged.json"
        lib = make_library("test", [make_game("Game A")])

        with patch("os.replace", side_effect=PermissionError("locked")):
            with pytest.raises(PermissionError, match="open in another application"):
                JsonStore(out_path).save(lib)

    def test_master_intact_when_output_save_fails(self, tmp_path):
        """When the save of the merged result fails (output file locked),
        the original master file must be exactly as it was before the merge
        was attempted."""
        master_path = tmp_path / "master.json"
        source_path = tmp_path / "source.json"

        _save(master_path, "Portal 2")
        _save(source_path, "New Game")
        original_content = master_path.read_text(encoding="utf-8")

        # Reload from disk, run merge in memory
        master = JsonStore(master_path).load()
        source = JsonStore(source_path).load()
        merger = LibraryMerger(
            MergeConfig(strategy=MergeStrategy.MERGE_PREFER_MASTER),
            backup_dir=str(tmp_path / "backups"),
        )
        result = merger.execute(master, source)
        assert result.success is True  # merge itself succeeded

        # Now simulate the master file being locked when we try to save
        with patch("os.replace", side_effect=PermissionError("locked")):
            with pytest.raises(PermissionError):
                JsonStore(master_path).save(master)

        assert master_path.read_text(encoding="utf-8") == original_content

    def test_new_games_not_lost_after_transient_lock(self, tmp_path):
        """If the first save attempt fails but a second attempt succeeds
        (transient lock released), the merged data must be fully persisted."""
        master_path = tmp_path / "master.json"
        source_path = tmp_path / "source.json"

        _save(master_path, "Portal 2")
        _save(source_path, "New Game")

        master = JsonStore(master_path).load()
        source = JsonStore(source_path).load()
        merger = LibraryMerger(
            MergeConfig(strategy=MergeStrategy.MERGE_PREFER_MASTER),
            backup_dir=str(tmp_path / "backups"),
        )
        merger.execute(master, source)

        # First save attempt fails (lock held)
        with patch("os.replace", side_effect=PermissionError("locked")):
            with pytest.raises(PermissionError):
                JsonStore(master_path).save(master)

        # Lock released – second attempt must succeed
        JsonStore(master_path).save(master)

        assert "New Game" in _game_names(master_path)
        assert "Portal 2" in _game_names(master_path)

    def test_backup_still_available_after_save_fails(self, tmp_path):
        """The backup created at the start of execute() must survive even when
        the subsequent save to the master file fails.  The user can then roll
        back safely."""
        master_path = tmp_path / "master.json"
        source_path = tmp_path / "source.json"
        backup_dir = tmp_path / "backups"

        _save(master_path, "Portal 2")
        _save(source_path, "New Game")

        master = JsonStore(master_path).load()
        source = JsonStore(source_path).load()
        merger = LibraryMerger(
            MergeConfig(strategy=MergeStrategy.MERGE_PREFER_MASTER),
            backup_dir=str(backup_dir),
        )
        result = merger.execute(master, source)

        # Verify backup was created
        assert result.backup_record is not None
        backup_path = Path(result.backup_record.backup_path)
        assert backup_path.exists()

        # Simulate locked master file during the save step
        with patch("os.replace", side_effect=PermissionError("locked")):
            with pytest.raises(PermissionError):
                JsonStore(master_path).save(master)

        # Backup must still be readable and contain the original games
        backup_data = json.loads(backup_path.read_text(encoding="utf-8"))
        original_names = {g["Name"] for g in backup_data["games"]}
        assert "Portal 2" in original_names
