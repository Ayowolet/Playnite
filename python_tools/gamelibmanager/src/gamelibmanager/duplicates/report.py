"""Duplicate detection report generation."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from ..models.game import Game
from .config import DetectionConfig
from .group import DuplicateGroup


@dataclass
class DuplicateReport:
    """Statistics and details for duplicate detection results."""

    total_games_scanned: int = 0
    total_duplicates_found: int = 0
    total_groups: int = 0
    groups: list[DuplicateGroup] = field(default_factory=list)
    scan_duration_seconds: float = 0.0
    config_used: DetectionConfig | None = None

    @property
    def avg_confidence(self) -> float:
        all_scores = []
        for g in self.groups:
            all_scores.extend(g.confidence_scores.values())
        return sum(all_scores) / len(all_scores) if all_scores else 0.0

    @property
    def confidence_distribution(self) -> dict[str, int]:
        buckets = {"90-100%": 0, "80-89%": 0, "70-79%": 0, "60-69%": 0, "<60%": 0}
        for g in self.groups:
            for score in g.confidence_scores.values():
                pct = score * 100
                if pct >= 90:
                    buckets["90-100%"] += 1
                elif pct >= 80:
                    buckets["80-89%"] += 1
                elif pct >= 70:
                    buckets["70-79%"] += 1
                elif pct >= 60:
                    buckets["60-69%"] += 1
                else:
                    buckets["<60%"] += 1
        return buckets

    def to_json(self) -> str:
        return json.dumps({
            "total_games_scanned": self.total_games_scanned,
            "total_duplicates_found": self.total_duplicates_found,
            "total_groups": self.total_groups,
            "scan_duration_seconds": round(self.scan_duration_seconds, 3),
            "avg_confidence": round(self.avg_confidence, 4),
            "confidence_distribution": self.confidence_distribution,
            "groups": [
                {
                    "group_id": g.group_id,
                    "master_game_id": str(g.master_game_id),
                    "members": [
                        {"game_id": str(mid), "confidence": round(g.confidence_scores.get(mid, 0), 4)}
                        for mid in g.member_game_ids
                    ],
                    "size": g.size,
                }
                for g in self.groups
            ],
        }, indent=2)

    def to_text(self) -> str:
        lines = [
            f"Duplicate Detection Report",
            f"=" * 40,
            f"Games scanned: {self.total_games_scanned}",
            f"Duplicates found: {self.total_duplicates_found}",
            f"Groups: {self.total_groups}",
            f"Avg confidence: {self.avg_confidence:.1%}",
            f"Scan duration: {self.scan_duration_seconds:.2f}s",
            "",
        ]
        dist = self.confidence_distribution
        lines.append("Confidence distribution:")
        for bucket, count in dist.items():
            lines.append(f"  {bucket}: {count}")
        lines.append("")

        for g in self.groups:
            lines.append(f"Group #{g.group_id} ({g.size} games):")
            lines.append(f"  Master: {g.master_game_id}")
            for mid in g.member_game_ids:
                conf = g.confidence_scores.get(mid, 0)
                lines.append(f"  - {mid} (confidence: {conf:.1%})")
            lines.append("")

        return "\n".join(lines)

    def to_table(self, db: object) -> str:
        """Format as table showing name, platform, source, install, hidden, confidence."""
        from ..db.database import GameDatabase
        _db: GameDatabase = db  # type: ignore[assignment]

        try:
            from tabulate import tabulate
        except ImportError:
            return self.to_text()

        rows = []
        for g in self.groups:
            for gid in g.all_game_ids:
                game = _db.get_game(gid)
                if not game:
                    continue
                source = _db.get_source(game.source_id)
                platform_names = []
                if game.platform_ids:
                    for pid in game.platform_ids:
                        plat = _db.get_platform(pid)
                        if plat:
                            platform_names.append(plat.name)

                is_master = gid == g.master_game_id
                conf = g.confidence_scores.get(gid, 1.0 if is_master else 0.0)
                rows.append([
                    g.group_id,
                    "*" if is_master else "",
                    game.name,
                    ", ".join(platform_names) if platform_names else "-",
                    source.name if source else "-",
                    "Yes" if game.is_installed else "No",
                    "Yes" if game.hidden else "No",
                    f"{conf:.0%}",
                ])

        headers = ["Group", "Master", "Name", "Platform", "Source", "Installed", "Hidden", "Confidence"]
        return tabulate(rows, headers=headers, tablefmt="simple")
