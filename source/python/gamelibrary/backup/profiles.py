"""Backup profile management."""

from __future__ import annotations

import json

from ..database import Database
from ..models import BackupProfile


class BackupProfileManager:
    """Manages backup profiles for different backup strategies."""

    def __init__(self, db: Database):
        self.db = db

    def create_profile(
        self,
        name: str,
        description: str = "",
        schedule_cron: str | None = None,
        retention_days: int = 30,
        max_backups: int = 10,
        destinations: list[str] | None = None,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        encrypt: bool = False,
    ) -> BackupProfile:
        existing = self.db.execute(
            "SELECT id FROM backup_profiles WHERE name = ?", (name,)
        )
        if existing:
            raise ValueError(f"Profile '{name}' already exists")

        profile_id = self.db.execute_insert(
            """INSERT INTO backup_profiles (name, description, schedule_cron,
               retention_days, max_backups, destinations, include_patterns,
               exclude_patterns, encrypt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, description, schedule_cron, retention_days, max_backups,
                json.dumps(destinations or ["local"]),
                json.dumps(include_patterns or ["*"]),
                json.dumps(exclude_patterns or []),
                int(encrypt),
            ),
        )
        return BackupProfile(
            id=profile_id,
            name=name,
            description=description,
            schedule_cron=schedule_cron,
            retention_days=retention_days,
            max_backups=max_backups,
            destinations=destinations or ["local"],
            include_patterns=include_patterns or ["*"],
            exclude_patterns=exclude_patterns or [],
            encrypt=encrypt,
        )

    def get_profile(self, name: str) -> BackupProfile | None:
        rows = self.db.execute(
            "SELECT * FROM backup_profiles WHERE name = ?", (name,)
        )
        return BackupProfile.from_row(rows[0]) if rows else None

    def get_profile_by_id(self, profile_id: int) -> BackupProfile | None:
        rows = self.db.execute(
            "SELECT * FROM backup_profiles WHERE id = ?", (profile_id,)
        )
        return BackupProfile.from_row(rows[0]) if rows else None

    def list_profiles(self) -> list[BackupProfile]:
        rows = self.db.execute("SELECT * FROM backup_profiles ORDER BY name")
        return [BackupProfile.from_row(r) for r in rows]

    def update_profile(self, profile_id: int, **kwargs):
        allowed = {
            "description", "schedule_cron", "retention_days", "max_backups",
            "destinations", "include_patterns", "exclude_patterns", "encrypt",
        }
        updates = []
        params = []
        for key, val in kwargs.items():
            if key not in allowed:
                continue
            if key in ("destinations", "include_patterns", "exclude_patterns"):
                val = json.dumps(val)
            elif key == "encrypt":
                val = int(val)
            updates.append(f"{key} = ?")
            params.append(val)

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(profile_id)
            self.db.execute(
                f"UPDATE backup_profiles SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )

    def delete_profile(self, profile_id: int):
        self.db.execute("DELETE FROM backup_profiles WHERE id = ?", (profile_id,))
