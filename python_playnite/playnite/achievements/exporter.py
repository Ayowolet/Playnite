"""Export achievement data to JSON or CSV for external analysis."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from playnite.database.models import Achievement, Game, UserAchievement

if TYPE_CHECKING:
    from pathlib import Path

    from playnite.database.connection import DatabaseManager

log = logging.getLogger(__name__)


class AchievementExporter:
    """Exports achievement data to JSON or CSV files."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public export methods
    # ------------------------------------------------------------------

    def export_to_json(
        self,
        output_path: Path,
        game_ids: list[int] | None = None,
        include_locked: bool = True,
    ) -> int:
        """Export achievement data to a JSON file.

        :param output_path: destination file path.
        :param game_ids: if given, only export these games.
        :param include_locked: include locked achievements in output.
        :returns: number of achievements exported.
        """
        rows = self._gather_data(game_ids=game_ids, include_locked=include_locked)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "total": len(rows),
                    "achievements": rows,
                },
                fh,
                indent=2,
                default=str,
            )
        log.info("Exported %d achievements to %s", len(rows), output_path)
        return len(rows)

    def export_to_csv(
        self,
        output_path: Path,
        game_ids: list[int] | None = None,
        include_locked: bool = True,
    ) -> int:
        """Export achievement data to a CSV file."""
        rows = self._gather_data(game_ids=game_ids, include_locked=include_locked)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "game_id",
            "game_name",
            "platform",
            "achievement_id",
            "achievement_name",
            "description",
            "is_unlocked",
            "unlock_date",
            "global_percentage",
            "difficulty_score",
            "is_rare",
            "current_value",
            "max_value",
        ]
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        log.info("Exported %d achievements to %s (CSV)", len(rows), output_path)
        return len(rows)

    def generate_report(self, output_path: Path | None = None) -> dict:
        """Generate an achievement summary report.

        If *output_path* is provided the report is saved to that JSON file.
        Returns the report dict in both cases.
        """
        report: dict = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_games": 0,
                "total_achievements": 0,
                "total_unlocked": 0,
                "total_locked": 0,
                "completion_pct": 0.0,
                "rare_unlocked": 0,
                "platforms": {},
            },
            "games": [],
        }

        with self._db.get_session() as session:
            games = session.query(Game).all()
            for game in games:
                total = len(game.achievements)
                if total == 0:
                    continue
                unlocked = sum(
                    1
                    for ach in game.achievements
                    for ua in ach.user_achievements
                    if ua.is_unlocked
                )
                rare_unlocked = sum(
                    1
                    for ach in game.achievements
                    if ach.is_rare
                    for ua in ach.user_achievements
                    if ua.is_unlocked
                )
                report["games"].append(
                    {
                        "id": game.id,
                        "name": game.name,
                        "platform": game.platform,
                        "total": total,
                        "unlocked": unlocked,
                        "completion_pct": round(unlocked / total * 100, 2),
                    },
                )
                report["summary"]["total_games"] += 1
                report["summary"]["total_achievements"] += total
                report["summary"]["total_unlocked"] += unlocked
                report["summary"]["rare_unlocked"] += rare_unlocked
                platform = game.platform
                p_stats = report["summary"]["platforms"].setdefault(
                    platform, {"games": 0, "total": 0, "unlocked": 0},
                )
                p_stats["games"] += 1
                p_stats["total"] += total
                p_stats["unlocked"] += unlocked

        total_ach = report["summary"]["total_achievements"]
        total_unl = report["summary"]["total_unlocked"]
        report["summary"]["total_locked"] = total_ach - total_unl
        report["summary"]["completion_pct"] = (
            round(total_unl / total_ach * 100, 2) if total_ach else 0.0
        )

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, default=str)
            log.info("Report saved to %s", output_path)

        return report

    # ------------------------------------------------------------------
    # Internal data gathering
    # ------------------------------------------------------------------

    def _gather_data(
        self,
        game_ids: list[int] | None = None,
        include_locked: bool = True,
    ) -> list[dict]:
        with self._db.get_session() as session:
            q = (
                session.query(Achievement, Game, UserAchievement)
                .join(Game, Achievement.game_id == Game.id)
                .outerjoin(
                    UserAchievement,
                    UserAchievement.achievement_id == Achievement.id,
                )
            )
            if game_ids:
                q = q.filter(Game.id.in_(game_ids))
            if not include_locked:
                q = q.filter(UserAchievement.is_unlocked == True)  # noqa: E712
            rows = q.all()

        results: list[dict] = []
        for ach, game, ua in rows:
            results.append(
                {
                    "game_id": game.id,
                    "platform_game_id": game.platform_game_id,
                    "game_name": game.name,
                    "platform": game.platform,
                    "achievement_id": ach.achievement_id,
                    "achievement_name": ach.name,
                    "description": ach.description or "",
                    "is_unlocked": ua.is_unlocked if ua else False,
                    "unlock_date": (
                        ua.unlock_date.isoformat()
                        if ua and ua.unlock_date
                        else None
                    ),
                    "global_percentage": ach.global_percentage,
                    "difficulty_score": ach.difficulty_score,
                    "is_rare": ach.is_rare,
                    "current_value": ach.current_value,
                    "max_value": ach.max_value,
                },
            )
        return results
