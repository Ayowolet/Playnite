"""Merge report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from .conflict import ConflictRecord


@dataclass
class MergeReport:
    """Report generated after merge execution."""

    merge_id: int = 0
    timestamp: datetime | None = None
    source_library: str = ""
    target_library: str = ""
    strategy: str = ""
    games_added: int = 0
    games_updated: int = 0
    games_skipped: int = 0
    conflicts_resolved: int = 0
    conflicts_details: list[ConflictRecord] = field(default_factory=list)
    media_files_copied: int = 0
    backup_path: str = ""
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "merge_id": self.merge_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source_library": self.source_library,
            "target_library": self.target_library,
            "strategy": self.strategy,
            "games_added": self.games_added,
            "games_updated": self.games_updated,
            "games_skipped": self.games_skipped,
            "conflicts_resolved": self.conflicts_resolved,
            "media_files_copied": self.media_files_copied,
            "backup_path": self.backup_path,
            "duration_seconds": round(self.duration_seconds, 3),
            "errors": self.errors,
            "warnings": self.warnings,
        }, indent=2)

    def to_text(self) -> str:
        lines = [
            "Merge Report",
            "=" * 40,
            f"Source: {self.source_library}",
            f"Target: {self.target_library}",
            f"Strategy: {self.strategy}",
            f"Timestamp: {self.timestamp.isoformat() if self.timestamp else 'N/A'}",
            f"Duration: {self.duration_seconds:.2f}s",
            "",
            f"Games added:       {self.games_added}",
            f"Games updated:     {self.games_updated}",
            f"Games skipped:     {self.games_skipped}",
            f"Conflicts resolved: {self.conflicts_resolved}",
            f"Media files copied: {self.media_files_copied}",
            f"Backup: {self.backup_path}",
        ]
        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  ! {e}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ? {w}")
        return "\n".join(lines)
