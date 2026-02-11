"""
Backup and rollback support for library merge operations.

A :class:`BackupRecord` captures a complete serialised snapshot of the
master library immediately before a merge is applied.  If the merge is
rolled back, the snapshot is deserialised and replaces the live library
contents.
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class BackupRecord:
    """Metadata plus serialised library snapshot."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    description: str = ""
    # Path where the backup JSON was written (set by BackupManager)
    backup_path: str = ""
    # Lightweight manifest: just game count, not the full data
    game_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "description": self.description,
            "backup_path": self.backup_path,
            "game_count": self.game_count,
        }


class BackupManager:
    """
    Creates, lists, and restores library backups.

    Backups are stored as ``{backup_dir}/{backup_id}.json`` files alongside a
    ``backups.json`` manifest.
    """

    MANIFEST_FILENAME = "backups.json"

    def __init__(self, backup_dir: str | Path) -> None:
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[BackupRecord] = self._load_manifest()

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, library_data: dict[str, Any], description: str = "") -> BackupRecord:
        """
        Serialise *library_data* to a timestamped JSON file and register the
        backup.

        *library_data* must be the dict produced by
        :meth:`~game_library.storage.json_store.JsonStore._save_flat` or an
        equivalent full-library serialisation.
        """
        record = BackupRecord(
            description=description,
            game_count=len(library_data.get("games", [])),
        )
        backup_path = self.backup_dir / f"{record.id}.json"
        backup_path.write_text(json.dumps(library_data, indent=2, ensure_ascii=False), encoding="utf-8")
        record.backup_path = str(backup_path)
        self._records.append(record)
        self._save_manifest()
        return record

    # ── List / get ────────────────────────────────────────────────────────────

    def list_backups(self) -> list[BackupRecord]:
        return list(self._records)

    def get_backup(self, backup_id: str) -> Optional[BackupRecord]:
        for r in self._records:
            if r.id == backup_id:
                return r
        return None

    def latest(self) -> Optional[BackupRecord]:
        return self._records[-1] if self._records else None

    # ── Restore ───────────────────────────────────────────────────────────────

    def restore(self, backup_id: str) -> dict[str, Any]:
        """
        Load and return the raw library dict from a backup.

        The caller is responsible for deserialising it back into a
        :class:`~game_library.models.Library` (typically via
        :class:`~game_library.storage.json_store.JsonStore`).
        """
        record = self.get_backup(backup_id)
        if record is None:
            raise ValueError(f"No backup found with id {backup_id!r}")
        path = Path(record.backup_path)
        if not path.exists():
            raise FileNotFoundError(f"Backup file not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, backup_id: str) -> bool:
        """Delete a backup file and remove it from the manifest."""
        record = self.get_backup(backup_id)
        if record is None:
            return False
        path = Path(record.backup_path)
        if path.exists():
            path.unlink()
        self._records = [r for r in self._records if r.id != backup_id]
        self._save_manifest()
        return True

    # ── Manifest ──────────────────────────────────────────────────────────────

    def _manifest_path(self) -> Path:
        return self.backup_dir / self.MANIFEST_FILENAME

    def _load_manifest(self) -> list[BackupRecord]:
        path = self._manifest_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [
                BackupRecord(
                    id=entry.get("id", str(uuid.uuid4())),
                    created_at=entry.get("created_at", ""),
                    description=entry.get("description", ""),
                    backup_path=entry.get("backup_path", ""),
                    game_count=entry.get("game_count", 0),
                )
                for entry in data
            ]
        except Exception:
            return []

    def _save_manifest(self) -> None:
        self._manifest_path().write_text(
            json.dumps([r.to_dict() for r in self._records], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
