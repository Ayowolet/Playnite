"""Tests for backup data integrity — verifying that data survives
the full backup → restore cycle without loss or corruption."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.restore import RestoreEngine
from gamelibrary.backup.verification import compute_bytes_checksum, verify_backup


# ── helpers ──────────────────────────────────────────────────────────

ALL_TABLES = [
    "platforms",
    "games",
    "achievements",
    "achievement_unlocks",
    "sync_history",
    "achievement_milestones",
    "notifications",
    "backups",
    "backup_profiles",
    "backup_items",
    "backup_destinations",
    "restore_history",
]


def _seed_full_db(db: Database) -> dict:
    """Insert data into every user-facing table. Returns a mapping of
    table -> list[dict] so callers can compare after restore."""

    pid = db.execute_insert(
        "INSERT INTO platforms (name, api_type, credentials) VALUES (?, ?, ?)",
        ("Steam", "steam", '{"api_key": "xxx"}'),
    )
    gid = db.execute_insert(
        "INSERT INTO games (platform_id, external_game_id, name, total_achievements) VALUES (?, ?, ?, ?)",
        (pid, "440", "Team Fortress 2", 520),
    )
    aid1 = db.execute_insert(
        "INSERT INTO achievements (game_id, external_achievement_id, name, description, global_completion_pct) VALUES (?, ?, ?, ?, ?)",
        (gid, "ach_1", "Head Shot", "Get 10 headshots", 35.5),
    )
    aid2 = db.execute_insert(
        "INSERT INTO achievements (game_id, external_achievement_id, name, description, global_completion_pct, is_hidden) VALUES (?, ?, ?, ?, ?, ?)",
        (gid, "ach_2", "Secret Move", "Find the secret", 2.1, 1),
    )
    db.execute_insert(
        "INSERT INTO achievement_unlocks (achievement_id, unlocked, unlock_date, source) VALUES (?, ?, ?, ?)",
        (aid1, 1, "2025-06-01T12:00:00", "api"),
    )
    db.execute_insert(
        "INSERT INTO achievement_unlocks (achievement_id, unlocked, unlock_date, source) VALUES (?, ?, ?, ?)",
        (aid2, 0, None, "api"),
    )
    db.execute_insert(
        "INSERT INTO sync_history (platform_id, sync_type, completed_at, achievements_found, new_unlocks, status) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, "full", "2025-06-01T12:05:00", 520, 1, "completed"),
    )
    db.execute_insert(
        "INSERT INTO achievement_milestones (milestone_type, milestone_value, details) VALUES (?, ?, ?)",
        ("total_unlocks", "100", '{"game": "TF2"}'),
    )
    db.execute_insert(
        "INSERT INTO notifications (notification_type, title, message, metadata) VALUES (?, ?, ?, ?)",
        ("unlock", "New unlock!", "You earned Head Shot", '{"ach_id": 1}'),
    )
    db.execute_insert(
        "INSERT INTO backup_profiles (name, description, retention_days, max_backups) VALUES (?, ?, ?, ?)",
        ("daily", "Daily backup", 30, 10),
    )
    db.execute_insert(
        "INSERT INTO backup_destinations (name, dest_type, config) VALUES (?, ?, ?)",
        ("ext_drive", "local", '{"path": "/mnt/ext"}'),
    )

    return _snapshot_db(db)


def _snapshot_db(db: Database) -> dict[str, list[dict]]:
    """Read all rows from every table into plain dicts."""
    snap = {}
    for table in ALL_TABLES:
        rows = db.execute(f"SELECT * FROM {table}")  # noqa: S608
        snap[table] = [dict(r) for r in rows]
    return snap


def _seed_data_files(data_dir: Path) -> dict[str, bytes]:
    """Create representative data files under data_dir and return
    a mapping of relative-path -> bytes for later comparison."""
    files: dict[str, bytes] = {}

    # Directory-based components
    for comp in ("categories", "tags"):
        comp_dir = data_dir / comp
        comp_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            content = json.dumps({comp: f"item_{i}", "index": i}).encode()
            fpath = comp_dir / f"{comp}_{i}.json"
            fpath.write_bytes(content)
            files[f"{comp}/{comp}_{i}.json"] = content

    # Standalone JSON config files
    for comp in ("config", "view_presets", "controller_mappings", "theme_settings", "plugin_configs"):
        content = json.dumps({comp: "value", "nested": {"a": 1}}).encode()
        fpath = data_dir / f"{comp}.json"
        fpath.write_bytes(content)
        files[f"{comp}/{comp}.json"] = content

    return files


def _collect_data_files(data_dir: Path) -> dict[str, bytes]:
    """Walk data_dir and return the same mapping format as _seed_data_files."""
    files: dict[str, bytes] = {}
    if not data_dir.exists():
        return files
    for fpath in sorted(data_dir.rglob("*")):
        if fpath.is_file():
            rel = str(fpath.relative_to(data_dir))
            files[rel] = fpath.read_bytes()
    return files


# ── fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def full_env(tmp_path):
    """Provide a fully seeded environment: db, engine, restore_engine,
    snapshot of original data, and a mapping of original data files."""
    db_path = tmp_path / "source.db"
    db = Database(db_path)
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"

    original_snap = _seed_full_db(db)
    original_files = _seed_data_files(data_dir)

    engine = BackupEngine(db, backup_dir, data_dir)
    return {
        "db": db,
        "engine": engine,
        "backup_dir": backup_dir,
        "data_dir": data_dir,
        "original_snap": original_snap,
        "original_files": original_files,
        "tmp_path": tmp_path,
    }


# ── 1. Restored data exactly matches backed-up data ─────────────────

class TestRestoredDataMatchesOriginal:

    def test_database_content_matches_after_restore(self, full_env):
        """Backed-up DB rows are identical after restore."""
        record = full_env["engine"].create_full_backup()

        # Set up a fresh target
        target_dir = full_env["tmp_path"] / "target"
        target_dir.mkdir()
        target_db_path = target_dir / "restored.db"
        target_data_dir = target_dir / "data"
        target_db = Database(target_db_path)

        restore = RestoreEngine(target_db, target_data_dir)
        restore.restore_full(record.file_path)

        # Re-open the restored DB to read its contents
        restored_db = Database(target_db_path)
        restored_snap = _snapshot_db(restored_db)

        for table in ALL_TABLES:
            original = full_env["original_snap"][table]
            restored = restored_snap[table]
            assert len(restored) == len(original), (
                f"Row count mismatch in {table}: expected {len(original)}, got {len(restored)}"
            )
            for orig_row, rest_row in zip(original, restored):
                assert orig_row == rest_row, f"Row mismatch in {table}"

    def test_data_files_match_after_restore(self, full_env):
        """Non-database data files are byte-identical after restore."""
        record = full_env["engine"].create_full_backup()

        target_dir = full_env["tmp_path"] / "target"
        target_dir.mkdir()
        target_db_path = target_dir / "restored.db"
        target_data_dir = target_dir / "data"
        target_db = Database(target_db_path)

        restore = RestoreEngine(target_db, target_data_dir)
        restore.restore_full(record.file_path)

        restored_files = _collect_data_files(target_data_dir)
        for rel_path, original_bytes in full_env["original_files"].items():
            assert rel_path in restored_files, f"Missing file after restore: {rel_path}"
            assert restored_files[rel_path] == original_bytes, (
                f"Content mismatch for {rel_path}"
            )

    def test_checksums_match_after_restore(self, full_env):
        """SHA-256 checksums of restored files match originals."""
        record = full_env["engine"].create_full_backup()

        target_dir = full_env["tmp_path"] / "target"
        target_dir.mkdir()
        target_db_path = target_dir / "restored.db"
        target_data_dir = target_dir / "data"
        target_db = Database(target_db_path)

        restore = RestoreEngine(target_db, target_data_dir)
        restore.restore_full(record.file_path)

        restored_files = _collect_data_files(target_data_dir)
        for rel_path, original_bytes in full_env["original_files"].items():
            expected = compute_bytes_checksum(original_bytes)
            actual = compute_bytes_checksum(restored_files[rel_path])
            assert actual == expected, f"Checksum mismatch for {rel_path}"

    def test_database_content_preserved_in_zip(self, full_env):
        """The database snapshot inside the ZIP contains all seeded data.

        Note: raw byte comparison is not possible because create_full_backup()
        inserts into backups/backup_items *after* reading the DB bytes.
        """
        record = full_env["engine"].create_full_backup()
        db_name = full_env["db"].get_db_path().name

        with zipfile.ZipFile(record.file_path, "r") as zf:
            db_bytes = zf.read(f"database/{db_name}")

        temp_db = full_env["tmp_path"] / "check_preserved.db"
        temp_db.write_bytes(db_bytes)

        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        # Verify the seeded data is present (seeded before backup)
        platforms = conn.execute("SELECT * FROM platforms").fetchall()
        assert len(platforms) >= 1
        assert dict(platforms[0])["name"] == "Steam"
        games = conn.execute("SELECT * FROM games").fetchall()
        assert len(games) >= 1
        achievements = conn.execute("SELECT * FROM achievements").fetchall()
        assert len(achievements) >= 2
        conn.close()

    def test_manifest_checksums_valid(self, full_env):
        """Every item in manifest has a correct checksum."""
        record = full_env["engine"].create_full_backup()
        result = verify_backup(record.file_path)
        assert result["valid"] is True
        assert result["items_checked"] > 0
        assert result["errors"] == []


# ── 2. Multiple restore operations produce identical results ─────────

class TestMultipleRestoresIdentical:

    def test_two_restores_produce_same_db(self, full_env):
        """Restoring the same backup twice yields identical DB content."""
        record = full_env["engine"].create_full_backup()

        snapshots = []
        for i in range(2):
            tdir = full_env["tmp_path"] / f"restore_{i}"
            tdir.mkdir()
            tdb = Database(tdir / "restored.db")
            restore = RestoreEngine(tdb, tdir / "data")
            restore.restore_full(record.file_path)
            reopened = Database(tdir / "restored.db")
            snapshots.append(_snapshot_db(reopened))

        for table in ALL_TABLES:
            assert snapshots[0][table] == snapshots[1][table], (
                f"Mismatch in {table} across two restores"
            )

    def test_two_restores_produce_same_files(self, full_env):
        """Restoring twice yields byte-identical data files."""
        record = full_env["engine"].create_full_backup()

        file_sets = []
        for i in range(2):
            tdir = full_env["tmp_path"] / f"restore_{i}"
            tdir.mkdir()
            tdb = Database(tdir / "restored.db")
            data_dir = tdir / "data"
            restore = RestoreEngine(tdb, data_dir)
            restore.restore_full(record.file_path)
            file_sets.append(_collect_data_files(data_dir))

        assert file_sets[0].keys() == file_sets[1].keys()
        for key in file_sets[0]:
            assert file_sets[0][key] == file_sets[1][key], (
                f"File {key} differs across two restores"
            )

    def test_restore_is_idempotent(self, full_env):
        """Restoring over an existing restore doesn't corrupt data."""
        record = full_env["engine"].create_full_backup()

        tdir = full_env["tmp_path"] / "idempotent"
        tdir.mkdir()
        tdb = Database(tdir / "restored.db")
        data_dir = tdir / "data"
        restore = RestoreEngine(tdb, data_dir)

        restore.restore_full(record.file_path)
        first_files = _collect_data_files(data_dir)

        # Restore again into same location
        tdb2 = Database(tdir / "restored.db")
        restore2 = RestoreEngine(tdb2, data_dir)
        restore2.restore_full(record.file_path)
        second_files = _collect_data_files(data_dir)

        assert first_files == second_files


# ── 3. Incremental backup chain restores correctly ───────────────────

class TestIncrementalChainRestore:

    def test_incremental_captures_changes(self, full_env):
        """Incremental backup only contains modified data."""
        record_full = full_env["engine"].create_full_backup()

        # Modify a data file
        new_content = json.dumps({"categories": "modified", "index": 99}).encode()
        (full_env["data_dir"] / "categories" / "categories_0.json").write_bytes(new_content)

        record_incr = full_env["engine"].create_incremental_backup(record_full.id)

        with zipfile.ZipFile(record_incr.file_path, "r") as zf:
            names = [n for n in zf.namelist() if n != "manifest.json"]
            # Only changed file should appear (categories_0.json in categories/)
            category_files = [n for n in names if n.startswith("categories/")]
            assert len(category_files) == 1
            assert "categories/categories_0.json" in category_files

    def test_full_plus_incremental_restore_matches_current_state(self, full_env):
        """Restoring full then incremental yields the current data state."""
        record_full = full_env["engine"].create_full_backup()

        # Add a new achievement to the DB
        db = full_env["db"]
        gid = db.execute("SELECT id FROM games LIMIT 1")[0]["id"]
        db.execute_insert(
            "INSERT INTO achievements (game_id, external_achievement_id, name, description, global_completion_pct) VALUES (?, ?, ?, ?, ?)",
            (gid, "ach_new", "New Achievement", "Added after full backup", 50.0),
        )

        # Modify a data file
        new_content = json.dumps({"tags": "updated_tag", "index": 0}).encode()
        (full_env["data_dir"] / "tags" / "tags_0.json").write_bytes(new_content)

        current_snap = _snapshot_db(db)

        record_incr = full_env["engine"].create_incremental_backup(record_full.id)

        # Restore full first, then incremental
        tdir = full_env["tmp_path"] / "chain_restore"
        tdir.mkdir()
        tdb = Database(tdir / "restored.db")
        data_dir = tdir / "data"

        restore = RestoreEngine(tdb, data_dir)
        restore.restore_full(record_full.file_path)
        # Re-open DB after overwrite
        tdb2 = Database(tdir / "restored.db")
        restore2 = RestoreEngine(tdb2, data_dir)
        restore2.restore_full(record_incr.file_path)

        restored_db = Database(tdir / "restored.db")
        restored_snap = _snapshot_db(restored_db)

        # The DB should match the state at incremental time
        # (database component is included in incremental since it changed)
        assert len(restored_snap["achievements"]) == len(current_snap["achievements"])

        # The modified tags file should match
        restored_files = _collect_data_files(data_dir)
        assert restored_files.get("tags/tags_0.json") == new_content

    def test_incremental_unchanged_files_excluded(self, full_env):
        """Non-database files unchanged since full backup are skipped.

        The database component is always included because create_full_backup()
        modifies the DB (inserts into backups/backup_items), so its checksum
        always differs. We verify that *data* files are excluded.
        """
        record_full = full_env["engine"].create_full_backup()

        # Don't change any data files
        record_incr = full_env["engine"].create_incremental_backup(record_full.id)

        with zipfile.ZipFile(record_incr.file_path, "r") as zf:
            names = [n for n in zf.namelist() if n != "manifest.json"]
            non_db = [n for n in names if not n.startswith("database/")]
            # Only the database should appear (it always changes); data files should not
            assert len(non_db) == 0, f"Unexpected unchanged files in incremental: {non_db}"

    def test_incremental_with_new_component_files(self, full_env):
        """New files added to an existing component are captured."""
        record_full = full_env["engine"].create_full_backup()

        # Add a new file to the categories directory
        new_content = json.dumps({"categories": "brand_new", "index": 100}).encode()
        (full_env["data_dir"] / "categories" / "categories_new.json").write_bytes(new_content)

        record_incr = full_env["engine"].create_incremental_backup(record_full.id)

        with zipfile.ZipFile(record_incr.file_path, "r") as zf:
            names = [n for n in zf.namelist() if n != "manifest.json"]
            assert "categories/categories_new.json" in names
            assert zf.read("categories/categories_new.json") == new_content


# ── 4. Encrypted backups decrypt without data loss ───────────────────

class TestEncryptedBackupIntegrity:

    def test_encrypted_backup_restores_same_db(self, full_env):
        """Encrypted backup→decrypt→restore yields original DB data."""
        password = "strong-p@ssw0rd!"
        record = full_env["engine"].create_full_backup(password=password)
        assert record.is_encrypted
        assert record.file_path.endswith(".enc")

        tdir = full_env["tmp_path"] / "enc_restore"
        tdir.mkdir()
        tdb = Database(tdir / "restored.db")
        restore = RestoreEngine(tdb, tdir / "data")
        restore.restore_full(record.file_path, password=password)

        restored_db = Database(tdir / "restored.db")
        restored_snap = _snapshot_db(restored_db)

        for table in ALL_TABLES:
            original = full_env["original_snap"][table]
            restored = restored_snap[table]
            assert len(restored) == len(original), f"Row count mismatch in {table}"
            for orig_row, rest_row in zip(original, restored):
                assert orig_row == rest_row, f"Data loss in {table} after encrypted restore"

    def test_encrypted_backup_restores_same_files(self, full_env):
        """Encrypted backup→decrypt→restore yields original data files."""
        password = "str0ng!"
        record = full_env["engine"].create_full_backup(password=password)

        tdir = full_env["tmp_path"] / "enc_files"
        tdir.mkdir()
        tdb = Database(tdir / "restored.db")
        restore = RestoreEngine(tdb, tdir / "data")
        restore.restore_full(record.file_path, password=password)

        restored_files = _collect_data_files(tdir / "data")
        for rel_path, original_bytes in full_env["original_files"].items():
            assert rel_path in restored_files, f"Missing {rel_path}"
            assert restored_files[rel_path] == original_bytes, (
                f"Content mismatch for {rel_path}"
            )

    def test_encrypted_checksum_differs_from_plaintext(self, full_env):
        """The encrypted file has a different checksum than the plain zip."""
        record_plain = full_env["engine"].create_full_backup()
        record_enc = full_env["engine"].create_full_backup(password="p@ss")

        assert record_plain.checksum != record_enc.checksum
        assert not record_plain.is_encrypted
        assert record_enc.is_encrypted

    def test_encrypted_backup_temp_file_cleaned(self, full_env):
        """Decrypted temp file is removed after restore."""
        password = "cleanup-test"
        record = full_env["engine"].create_full_backup(password=password)

        tdir = full_env["tmp_path"] / "cleanup"
        tdir.mkdir()
        tdb = Database(tdir / "restored.db")
        restore = RestoreEngine(tdb, tdir / "data")
        restore.restore_full(record.file_path, password=password)

        # The backup directory should not contain any stray decrypted files
        backup_dir = full_env["backup_dir"]
        decrypted = list(backup_dir.glob("*_decrypted.zip"))
        assert len(decrypted) == 0, "Temp decrypted file was not cleaned up"


# ── 5. Compressed backups decompress without corruption ──────────────

class TestCompressionIntegrity:

    def test_backup_is_zip_deflated(self, full_env):
        """Backup uses ZIP_DEFLATED compression."""
        record = full_env["engine"].create_full_backup()
        with zipfile.ZipFile(record.file_path, "r") as zf:
            for info in zf.infolist():
                if info.file_size > 0:
                    assert info.compress_type == zipfile.ZIP_DEFLATED, (
                        f"{info.filename} not DEFLATED"
                    )

    def test_compressed_size_smaller_than_original(self, full_env):
        """Compressed backup is smaller than or equal to the sum of uncompressed items."""
        record = full_env["engine"].create_full_backup()
        assert record.compressed_size <= record.size_bytes or record.size_bytes == 0

    def test_decompressed_data_matches_original(self, full_env):
        """Every file in the ZIP decompresses to its original bytes."""
        record = full_env["engine"].create_full_backup()

        with zipfile.ZipFile(record.file_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            for item in manifest["items"]:
                arc_path = item["path"]
                expected_checksum = item["checksum"]
                data = zf.read(arc_path)
                actual_checksum = compute_bytes_checksum(data)
                assert actual_checksum == expected_checksum, (
                    f"Decompression corruption for {arc_path}"
                )

    def test_zip_testzip_reports_no_corruption(self, full_env):
        """zipfile.testzip() confirms no CRC errors."""
        record = full_env["engine"].create_full_backup()
        with zipfile.ZipFile(record.file_path, "r") as zf:
            assert zf.testzip() is None

    def test_verify_backup_passes(self, full_env):
        """The full verification pipeline passes on a fresh backup."""
        record = full_env["engine"].create_full_backup()
        result = verify_backup(record.file_path)
        assert result["valid"] is True
        assert not result["errors"]
        assert result["items_checked"] > 0


# ── 6. Backup includes all database tables ───────────────────────────

class TestBackupIncludesAllTables:

    def test_backed_up_db_has_all_schema_tables(self, full_env):
        """The database file inside the backup contains all expected tables."""
        record = full_env["engine"].create_full_backup()

        db_name = full_env["db"].get_db_path().name
        with zipfile.ZipFile(record.file_path, "r") as zf:
            db_bytes = zf.read(f"database/{db_name}")

        # Write to a temp file and inspect with sqlite3
        temp_db = full_env["tmp_path"] / "inspect.db"
        temp_db.write_bytes(db_bytes)

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables_in_backup = {row[0] for row in cursor.fetchall()}
        conn.close()

        for table in ALL_TABLES:
            assert table in tables_in_backup, (
                f"Table '{table}' missing from backed-up database"
            )

    def test_all_tables_have_data_after_restore(self, full_env):
        """After restore, every seeded table still has its rows."""
        record = full_env["engine"].create_full_backup()

        tdir = full_env["tmp_path"] / "all_tables"
        tdir.mkdir()
        tdb = Database(tdir / "restored.db")
        restore = RestoreEngine(tdb, tdir / "data")
        restore.restore_full(record.file_path)

        restored_db = Database(tdir / "restored.db")
        restored_snap = _snapshot_db(restored_db)

        for table in ALL_TABLES:
            original = full_env["original_snap"][table]
            if original:
                assert len(restored_snap[table]) > 0, (
                    f"Table '{table}' is empty after restore"
                )
                assert len(restored_snap[table]) == len(original), (
                    f"Row count mismatch in '{table}'"
                )

    def test_backed_up_db_preserves_indexes(self, full_env):
        """Indexes from the schema are present in the backed-up database."""
        record = full_env["engine"].create_full_backup()

        db_name = full_env["db"].get_db_path().name
        with zipfile.ZipFile(record.file_path, "r") as zf:
            db_bytes = zf.read(f"database/{db_name}")

        temp_db = full_env["tmp_path"] / "inspect_idx.db"
        temp_db.write_bytes(db_bytes)

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        index_names = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected_indexes = {
            "idx_games_platform",
            "idx_achievements_game",
            "idx_achievement_unlocks_achievement",
            "idx_achievements_global_pct",
            "idx_achievement_unlocks_date",
            "idx_sync_history_platform",
            "idx_backups_profile",
            "idx_backup_items_backup",
        }
        for idx in expected_indexes:
            assert idx in index_names, f"Index '{idx}' missing from backed-up database"

    def test_manifest_lists_database_component(self, full_env):
        """Manifest.json includes 'database' in its components list."""
        record = full_env["engine"].create_full_backup()
        with zipfile.ZipFile(record.file_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert "database" in manifest["components"]
        db_items = [i for i in manifest["items"] if i["type"] == "database"]
        assert len(db_items) >= 1

    def test_backed_up_db_foreign_keys_intact(self, full_env):
        """Foreign key relationships are preserved in the backed-up database."""
        record = full_env["engine"].create_full_backup()

        db_name = full_env["db"].get_db_path().name
        with zipfile.ZipFile(record.file_path, "r") as zf:
            db_bytes = zf.read(f"database/{db_name}")

        temp_db = full_env["tmp_path"] / "inspect_fk.db"
        temp_db.write_bytes(db_bytes)

        conn = sqlite3.connect(str(temp_db))
        conn.execute("PRAGMA foreign_keys=ON")

        # Verify that joining across FKs works correctly
        rows = conn.execute(
            """SELECT g.name, p.name FROM games g
               JOIN platforms p ON g.platform_id = p.id"""
        ).fetchall()
        assert len(rows) > 0
        assert rows[0][1] == "Steam"

        rows = conn.execute(
            """SELECT a.name, g.name FROM achievements a
               JOIN games g ON a.game_id = g.id"""
        ).fetchall()
        assert len(rows) >= 2

        conn.close()
