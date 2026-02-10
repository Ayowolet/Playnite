"""Core backup engine - creates full and incremental backups."""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..database import Database
from ..models import BackupRecord, BackupReport
from .verification import compute_file_checksum, compute_bytes_checksum
from .encryption import encrypt_file
from .destinations import DestinationManager

logger = logging.getLogger(__name__)

BACKUP_COMPONENTS = [
    "database",
    "config",
    "categories",
    "tags",
    "view_presets",
    "controller_mappings",
    "theme_settings",
    "plugin_configs",
]


class BackupEngine:
    """Creates full and incremental backups."""

    def __init__(self, db: Database, backup_dir: str | Path, data_dir: str | Path | None = None):
        self.db = db
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = Path(data_dir) if data_dir else self.db.get_db_path().parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_full_backup(
        self,
        password: str | None = None,
        profile_id: int | None = None,
        components: list[str] | None = None,
        destination: str = "local",
        destinations: list[str] | None = None,
    ) -> BackupRecord:
        """Create a full backup of all (or selected) components.

        Args:
            destinations: Optional list of registered destination names to
                distribute the backup to after creation.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_full_{timestamp}.zip"
        backup_path = self.backup_dir / backup_filename
        components = components or BACKUP_COMPONENTS
        logger.info("Creating full backup with components: %s", components)

        manifest = {
            "backup_type": "full",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "items": [],
        }

        with zipfile.ZipFile(str(backup_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for component in components:
                items = self._backup_component(zf, component)
                manifest["items"].extend(items)
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        original_size = sum(i.get("size", 0) for i in manifest["items"])
        compressed_size = backup_path.stat().st_size
        checksum = compute_file_checksum(backup_path)

        is_encrypted = False
        if password:
            encrypted_path = backup_path.with_suffix(".zip.enc")
            encrypt_file(backup_path, encrypted_path, password)
            backup_path.unlink()
            backup_path = encrypted_path
            backup_filename = encrypted_path.name
            compressed_size = encrypted_path.stat().st_size
            checksum = compute_file_checksum(encrypted_path)
            is_encrypted = True

        # Distribute to additional destinations
        dist_results = []
        if destinations:
            dest_mgr = DestinationManager(self.db)
            dist_results = dest_mgr.distribute(backup_path, destinations)

        metadata = {"components": components}
        if dist_results:
            metadata["distributions"] = dist_results
            destination = ",".join(
                [destination] + [r["destination"] for r in dist_results if r["status"] == "completed"]
            )

        try:
            record_id = self.db.execute_insert(
                """INSERT INTO backups (profile_id, backup_type, file_path, size_bytes,
                   compressed_size, is_encrypted, destination, checksum, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile_id, "full", str(backup_path), original_size,
                    compressed_size, int(is_encrypted), destination, checksum,
                    json.dumps(metadata),
                ),
            )

            for item in manifest["items"]:
                self.db.execute_insert(
                    """INSERT INTO backup_items (backup_id, item_path, item_type, size_bytes, checksum, modified_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (record_id, item["path"], item["type"], item.get("size", 0),
                     item.get("checksum", ""), item.get("modified_at", "")),
                )
        except Exception:
            # Clean up orphaned backup file if DB insert fails
            if backup_path.exists():
                backup_path.unlink()
                logger.error("Cleaned up orphaned backup file after DB failure: %s", backup_path)
            raise

        return BackupRecord(
            id=record_id,
            profile_id=profile_id,
            backup_type="full",
            file_path=str(backup_path),
            created_at=manifest["created_at"],
            size_bytes=original_size,
            compressed_size=compressed_size,
            is_encrypted=is_encrypted,
            destination=destination,
            checksum=checksum,
            status="completed",
            metadata=metadata,
        )

    def create_incremental_backup(
        self,
        parent_backup_id: int,
        password: str | None = None,
        profile_id: int | None = None,
        components: list[str] | None = None,
        destinations: list[str] | None = None,
    ) -> BackupRecord:
        """Create an incremental backup based on changes since parent backup."""
        logger.info("Creating incremental backup based on parent %d", parent_backup_id)
        parent = self.db.execute("SELECT * FROM backups WHERE id = ?", (parent_backup_id,))
        if not parent:
            raise ValueError(f"Parent backup {parent_backup_id} not found")

        parent_items = self.db.execute(
            "SELECT item_path, checksum, modified_at FROM backup_items WHERE backup_id = ?",
            (parent_backup_id,),
        )
        parent_checksums = {r["item_path"]: r["checksum"] for r in parent_items}

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_incr_{timestamp}.zip"
        backup_path = self.backup_dir / backup_filename
        components = components or BACKUP_COMPONENTS

        manifest = {
            "backup_type": "incremental",
            "parent_backup_id": parent_backup_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "items": [],
        }

        with zipfile.ZipFile(str(backup_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for component in components:
                items = self._backup_component(zf, component, parent_checksums)
                manifest["items"].extend(items)
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        original_size = sum(i.get("size", 0) for i in manifest["items"])
        compressed_size = backup_path.stat().st_size
        checksum = compute_file_checksum(backup_path)

        is_encrypted = False
        if password:
            encrypted_path = backup_path.with_suffix(".zip.enc")
            encrypt_file(backup_path, encrypted_path, password)
            backup_path.unlink()
            backup_path = encrypted_path
            compressed_size = encrypted_path.stat().st_size
            checksum = compute_file_checksum(encrypted_path)
            is_encrypted = True

        # Distribute to additional destinations
        dest_str = "local"
        dist_results = []
        if destinations:
            dest_mgr = DestinationManager(self.db)
            dist_results = dest_mgr.distribute(backup_path, destinations)

        metadata = {"components": components}
        if dist_results:
            metadata["distributions"] = dist_results
            dest_str = ",".join(
                ["local"] + [r["destination"] for r in dist_results if r["status"] == "completed"]
            )

        record_id = self.db.execute_insert(
            """INSERT INTO backups (profile_id, backup_type, file_path, size_bytes,
               compressed_size, is_encrypted, destination, checksum, parent_backup_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id, "incremental", str(backup_path), original_size,
                compressed_size, int(is_encrypted), dest_str, checksum,
                parent_backup_id, json.dumps(metadata),
            ),
        )

        for item in manifest["items"]:
            self.db.execute_insert(
                """INSERT INTO backup_items (backup_id, item_path, item_type, size_bytes, checksum, modified_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (record_id, item["path"], item["type"], item.get("size", 0),
                 item.get("checksum", ""), item.get("modified_at", "")),
            )

        return BackupRecord(
            id=record_id,
            profile_id=profile_id,
            backup_type="incremental",
            file_path=str(backup_path),
            created_at=manifest["created_at"],
            size_bytes=original_size,
            compressed_size=compressed_size,
            is_encrypted=is_encrypted,
            destination=dest_str,
            checksum=checksum,
            parent_backup_id=parent_backup_id,
            status="completed",
            metadata=metadata,
        )

    def get_backup_report(self, backup_id: int) -> BackupReport:
        """Generate a report for a specific backup."""
        rows = self.db.execute("SELECT * FROM backups WHERE id = ?", (backup_id,))
        if not rows:
            raise ValueError(f"Backup {backup_id} not found")
        b = rows[0]

        items = self.db.execute(
            "SELECT item_type, COUNT(*) as count, SUM(size_bytes) as total_size FROM backup_items WHERE backup_id = ? GROUP BY item_type",
            (backup_id,),
        )
        items_by_type = {r["item_type"]: {"count": r["count"], "size": r["total_size"] or 0} for r in items}

        total_items_row = self.db.execute(
            "SELECT COUNT(*) as count FROM backup_items WHERE backup_id = ?",
            (backup_id,),
        )

        orig = b["size_bytes"] or 1
        comp = b["compressed_size"] or 1

        from .verification import verify_backup
        verified = False
        if not b["is_encrypted"]:
            result = verify_backup(b["file_path"])
            verified = result["valid"]

        return BackupReport(
            backup_id=backup_id,
            backup_type=b["backup_type"],
            created_at=b["created_at"],
            file_path=b["file_path"],
            total_items=total_items_row[0]["count"] if total_items_row else 0,
            total_size=b["size_bytes"],
            compressed_size=b["compressed_size"],
            compression_ratio=round(comp / orig, 4) if orig > 0 else 1.0,
            is_encrypted=bool(b["is_encrypted"]),
            items_by_type=items_by_type,
            is_verified=verified,
        )

    def list_backups(self, limit: int = 20) -> list[BackupRecord]:
        rows = self.db.execute(
            "SELECT * FROM backups ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [BackupRecord.from_row(r) for r in rows]

    def delete_backup(self, backup_id: int):
        """Delete a backup record and its file."""
        logger.info("Deleting backup %d", backup_id)
        rows = self.db.execute("SELECT file_path FROM backups WHERE id = ?", (backup_id,))
        if rows:
            path = Path(rows[0]["file_path"])
            if path.exists():
                path.unlink()
            self.db.execute("DELETE FROM backup_items WHERE backup_id = ?", (backup_id,))
            self.db.execute("DELETE FROM backups WHERE id = ?", (backup_id,))

    def cleanup_old_backups(self, max_age_days: int = 30, max_count: int = 10):
        """Remove old backups beyond retention policy."""
        logger.info("Cleaning up backups older than %d days, max count %d", max_age_days, max_count)
        self.db.execute(
            """DELETE FROM backups WHERE id IN (
               SELECT id FROM backups
               WHERE created_at < datetime('now', ?)
               ORDER BY created_at ASC)""",
            (f"-{max_age_days} days",),
        )
        excess = self.db.execute(
            """SELECT id, file_path FROM backups
               ORDER BY created_at DESC
               LIMIT -1 OFFSET ?""",
            (max_count,),
        )
        for r in excess:
            path = Path(r["file_path"])
            if path.exists():
                path.unlink()
            self.db.execute("DELETE FROM backup_items WHERE backup_id = ?", (r["id"],))
            self.db.execute("DELETE FROM backups WHERE id = ?", (r["id"],))

    def _backup_component(
        self,
        zf: zipfile.ZipFile,
        component: str,
        parent_checksums: dict[str, str] | None = None,
    ) -> list[dict]:
        """Back up a single component into the zip file. Returns item manifests."""
        items = []
        if component == "database":
            db_path = self.db.get_db_path()
            if db_path.exists():
                data = db_path.read_bytes()
                checksum = compute_bytes_checksum(data)
                arc_path = f"database/{db_path.name}"
                if parent_checksums and arc_path in parent_checksums:
                    if parent_checksums[arc_path] == checksum:
                        return items
                zf.writestr(arc_path, data)
                items.append({
                    "path": arc_path,
                    "type": "database",
                    "size": len(data),
                    "checksum": checksum,
                    "modified_at": datetime.now(timezone.utc).isoformat(),
                })
        else:
            component_dir = self.data_dir / component
            if component_dir.is_dir():
                for file_path in sorted(component_dir.rglob("*")):
                    if file_path.is_symlink():
                        logger.warning("Skipping symlink: %s", file_path)
                        continue
                    if file_path.is_file():
                        data = file_path.read_bytes()
                        checksum = compute_bytes_checksum(data)
                        arc_path = f"{component}/{file_path.relative_to(component_dir)}"
                        if parent_checksums and arc_path in parent_checksums:
                            if parent_checksums[arc_path] == checksum:
                                continue
                        zf.writestr(arc_path, data)
                        items.append({
                            "path": arc_path,
                            "type": component,
                            "size": len(data),
                            "checksum": checksum,
                            "modified_at": datetime.now(timezone.utc).isoformat(),
                        })
            else:
                config_file = self.data_dir / f"{component}.json"
                if config_file.exists():
                    data = config_file.read_bytes()
                    checksum = compute_bytes_checksum(data)
                    arc_path = f"{component}/{config_file.name}"
                    if parent_checksums and arc_path in parent_checksums:
                        if parent_checksums[arc_path] == checksum:
                            return items
                    zf.writestr(arc_path, data)
                    items.append({
                        "path": arc_path,
                        "type": component,
                        "size": len(data),
                        "checksum": checksum,
                        "modified_at": datetime.now(timezone.utc).isoformat(),
                    })
        return items
