"""Disaster recovery for corrupted database scenarios."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..database import Database, SCHEMA_SQL
from .restore import RestoreEngine

logger = logging.getLogger(__name__)


class DisasterRecovery:
    """Handles database corruption and disaster recovery."""

    def __init__(self, db: Database, backup_dir: str | Path, data_dir: str | Path | None = None):
        self.db = db
        self.backup_dir = Path(backup_dir)
        self.data_dir = Path(data_dir) if data_dir else self.db.get_db_path().parent / "data"

    def check_database_health(self) -> dict:
        """Check if the database is healthy and report any issues."""
        db_path = self.db.get_db_path()
        result = {
            "path": str(db_path),
            "exists": db_path.exists(),
            "healthy": False,
            "size_bytes": 0,
            "issues": [],
        }

        if not db_path.exists():
            result["issues"].append("Database file does not exist")
            return result

        result["size_bytes"] = db_path.stat().st_size

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("PRAGMA integrity_check")
            check = cursor.fetchone()
            if check and check[0] == "ok":
                result["healthy"] = True
            else:
                result["issues"].append(f"Integrity check failed: {check}")

            cursor = conn.execute("PRAGMA quick_check")
            quick = cursor.fetchone()
            if quick and quick[0] != "ok":
                result["issues"].append(f"Quick check failed: {quick}")

            conn.close()
        except sqlite3.Error as e:
            result["issues"].append(f"Database error: {e}")

        return result

    def recover_from_backup(
        self,
        password: str | None = None,
    ) -> dict:
        """Attempt to recover from the most recent valid backup."""
        backups = self._find_valid_backups()
        if not backups:
            raise RuntimeError("No valid backups found for recovery")

        for backup_path in backups:
            try:
                restore = RestoreEngine(self.db, self.data_dir)
                result = restore.restore_full(backup_path, password)
                result["recovered_from"] = str(backup_path)
                return result
            except Exception as e:
                logger.warning("Recovery from %s failed: %s", backup_path, e)
                continue

        raise RuntimeError("All recovery attempts failed")

    def rebuild_database(self) -> dict:
        """Rebuild a fresh database schema (last resort)."""
        db_path = self.db.get_db_path()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        corrupt_backup_path = None

        if db_path.exists():
            corrupt_backup_path = db_path.with_name(f"{db_path.stem}_corrupt_{timestamp}{db_path.suffix}")
            shutil.move(str(db_path), str(corrupt_backup_path))
            logger.info("Moved corrupt database to %s", corrupt_backup_path)

        conn = sqlite3.connect(str(db_path))
        conn.executescript(SCHEMA_SQL)
        conn.close()

        self.db._init_db()

        return {
            "status": "rebuilt",
            "new_database": str(db_path),
            "corrupt_backup": str(corrupt_backup_path) if corrupt_backup_path else None,
            "timestamp": timestamp,
        }

    def export_for_migration(self, output_path: str | Path, password: str | None = None) -> dict:
        """Export all library data for migration to a different system."""
        from .engine import BackupEngine
        engine = BackupEngine(self.db, self.backup_dir, self.data_dir)
        record = engine.create_full_backup(password=password)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        source = Path(record.file_path)
        shutil.copy2(str(source), str(output_path))
        return {
            "exported_to": str(output_path),
            "size_bytes": output_path.stat().st_size,
            "is_encrypted": record.is_encrypted,
            "checksum": record.checksum,
        }

    def import_from_backup(
        self,
        import_path: str | Path,
        password: str | None = None,
    ) -> dict:
        """Import library data from a backup file (migration)."""
        restore = RestoreEngine(self.db, self.data_dir)
        return restore.restore_full(import_path, password)

    def _find_valid_backups(self) -> list[Path]:
        """Find valid backup files ordered by most recent first."""
        backup_files = []
        for ext in ("*.zip", "*.zip.enc"):
            backup_files.extend(self.backup_dir.glob(ext))
        backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return backup_files
