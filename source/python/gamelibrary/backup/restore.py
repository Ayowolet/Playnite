"""Backup restore functionality with selective component restore."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag

from ..database import Database
from .encryption import decrypt_file
from .verification import verify_backup

logger = logging.getLogger(__name__)

MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB decompression limit
MAX_FILE_COUNT = 50_000  # Max files in a single backup archive


class RestoreEngine:
    """Restores data from backup files."""

    def __init__(self, db: Database, data_dir: str | Path | None = None):
        self.db = db
        self.data_dir = Path(data_dir) if data_dir else self.db.get_db_path().parent / "data"

    def restore_full(
        self,
        backup_path: str | Path,
        password: str | None = None,
        components: list[str] | None = None,
    ) -> dict:
        """Restore from a backup file, optionally selecting specific components.

        Returns summary of what was restored.
        """
        backup_path = Path(backup_path)
        logger.info("Starting restore from %s", backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        working_path = backup_path
        temp_decrypted = None

        if backup_path.suffix == ".enc":
            if not password:
                raise ValueError("Backup is encrypted but no password provided")
            temp_decrypted = backup_path.with_suffix("")
            if temp_decrypted.suffix != ".zip":
                temp_decrypted = backup_path.parent / (backup_path.stem.replace(".zip", "") + "_decrypted.zip")
            try:
                decrypt_file(backup_path, temp_decrypted, password)
            except InvalidTag:
                if temp_decrypted.exists():
                    temp_decrypted.unlink()
                raise ValueError(
                    "Incorrect password or corrupted encrypted backup"
                )
            except Exception:
                if temp_decrypted.exists():
                    temp_decrypted.unlink()
                raise
            working_path = temp_decrypted

        try:
            verification = verify_backup(working_path)
            if not verification["valid"]:
                if verification["errors"]:
                    raise ValueError(f"Backup verification failed: {'; '.join(verification['errors'])}")

            return self._do_restore(working_path, components)
        finally:
            if temp_decrypted and temp_decrypted.exists():
                temp_decrypted.unlink()

    def restore_selective(
        self,
        backup_path: str | Path,
        components: list[str],
        password: str | None = None,
    ) -> dict:
        """Restore only specific components from a backup."""
        return self.restore_full(backup_path, password, components)

    def list_backup_contents(self, backup_path: str | Path, password: str | None = None) -> dict:
        """List what's inside a backup without restoring."""
        backup_path = Path(backup_path)
        working_path = backup_path
        temp_decrypted = None

        if backup_path.suffix == ".enc":
            if not password:
                raise ValueError("Backup is encrypted but no password provided")
            temp_decrypted = backup_path.parent / (backup_path.stem.replace(".zip", "") + "_peek.zip")
            try:
                decrypt_file(backup_path, temp_decrypted, password)
            except InvalidTag:
                if temp_decrypted.exists():
                    temp_decrypted.unlink()
                raise ValueError(
                    "Incorrect password or corrupted encrypted backup"
                )
            except Exception:
                if temp_decrypted.exists():
                    temp_decrypted.unlink()
                raise
            working_path = temp_decrypted

        try:
            with zipfile.ZipFile(str(working_path), "r") as zf:
                file_count = len(zf.namelist())
                if file_count > MAX_FILE_COUNT:
                    raise ValueError(
                        f"Archive contains {file_count} files, exceeding limit of {MAX_FILE_COUNT}"
                    )
                if "manifest.json" in zf.namelist():
                    manifest = json.loads(zf.read("manifest.json"))
                    return {
                        "backup_type": manifest.get("backup_type", "unknown"),
                        "created_at": manifest.get("created_at", "unknown"),
                        "components": manifest.get("components", []),
                        "items": manifest.get("items", []),
                        "total_files": len(zf.namelist()) - 1,
                    }
                return {
                    "backup_type": "unknown",
                    "files": zf.namelist(),
                    "total_files": len(zf.namelist()),
                }
        finally:
            if temp_decrypted and temp_decrypted.exists():
                temp_decrypted.unlink()

    def _do_restore(self, zip_path: Path, components: list[str] | None = None) -> dict:
        """Perform the actual restore from a zip file."""
        result = {
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "components_restored": [],
            "items_restored": 0,
            "errors": [],
        }

        with zipfile.ZipFile(str(zip_path), "r") as zf:
            # Decompression bomb protection
            file_count = len(zf.namelist())
            if file_count > MAX_FILE_COUNT:
                raise ValueError(
                    f"Archive contains {file_count} files, exceeding limit of {MAX_FILE_COUNT}"
                )
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            if total_uncompressed > MAX_TOTAL_SIZE:
                raise ValueError(
                    f"Archive uncompressed size ({total_uncompressed} bytes) exceeds "
                    f"limit of {MAX_TOTAL_SIZE} bytes"
                )

            if "manifest.json" in zf.namelist():
                json.loads(zf.read("manifest.json"))  # validate manifest is parseable

            available_components = set()
            for name in zf.namelist():
                if name == "manifest.json":
                    continue
                component = name.split("/")[0]
                available_components.add(component)

            restore_components = components or list(available_components)

            for component in restore_components:
                if component not in available_components:
                    result["errors"].append(f"Component '{component}' not found in backup")
                    continue

                try:
                    count = self._restore_component(zf, component)
                    result["components_restored"].append(component)
                    result["items_restored"] += count
                except Exception as e:
                    result["errors"].append(f"Failed to restore {component}: {e}")

        backup_id = self._find_backup_id(str(zip_path))
        if backup_id:
            self.db.execute_insert(
                """INSERT INTO restore_history (backup_id, items_restored, components, status, error_message)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    backup_id,
                    result["items_restored"],
                    json.dumps(result["components_restored"]),
                    "completed" if not result["errors"] else "partial",
                    "; ".join(result["errors"]) if result["errors"] else None,
                ),
            )

        return result

    def _restore_component(self, zf: zipfile.ZipFile, component: str) -> int:
        """Restore a single component from the zip. Returns count of items restored."""
        logger.info("Restoring component: %s", component)
        count = 0
        prefix = f"{component}/"

        for name in zf.namelist():
            if not name.startswith(prefix):
                continue
            if name == prefix:
                continue

            if component == "database":
                db_data = zf.read(name)
                db_path = self.db.get_db_path()
                backup_current = db_path.with_suffix(".db.pre_restore")
                if db_path.exists():
                    shutil.copy2(str(db_path), str(backup_current))
                db_path.write_bytes(db_data)
                count += 1
            else:
                relative = name[len(prefix):]
                target = self.data_dir / component / relative
                # Zip Slip protection: ensure resolved path is within data_dir
                target_resolved = target.resolve()
                safe_base = (self.data_dir / component).resolve()
                if not str(target_resolved).startswith(str(safe_base) + "/") and target_resolved != safe_base:
                    logger.warning("Skipping path traversal attempt: %s", name)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
                count += 1

        return count

    def _find_backup_id(self, file_path: str) -> int | None:
        rows = self.db.execute(
            "SELECT id FROM backups WHERE file_path LIKE ?",
            (f"%{Path(file_path).name}%",),
        )
        return rows[0]["id"] if rows else None
