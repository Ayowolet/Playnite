"""Achievement data export to JSON/CSV."""

from __future__ import annotations

import csv
import json
import io
from pathlib import Path

from ..database import Database
from ..models import Achievement


class AchievementExporter:
    """Exports achievement data to JSON and CSV formats."""

    def __init__(self, db: Database):
        self.db = db

    def export_json(self, output_path: str | Path | None = None, game_id: int | None = None) -> str:
        """Export achievements to JSON. Returns JSON string if no path given."""
        data = self._gather_data(game_id)
        json_str = json.dumps(data, indent=2, default=str)
        if output_path:
            Path(output_path).write_text(json_str)
        return json_str

    def export_csv(self, output_path: str | Path | None = None, game_id: int | None = None) -> str:
        """Export achievements to CSV. Returns CSV string if no path given."""
        rows = self._gather_flat_data(game_id)
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        csv_str = output.getvalue()
        if output_path:
            Path(output_path).write_text(csv_str)
        return csv_str

    def _gather_data(self, game_id: int | None = None) -> dict:
        """Gather achievement data as a nested dict."""
        if game_id:
            games = self.db.execute(
                """SELECT g.*, p.name as platform_name FROM games g
                   JOIN platforms p ON g.platform_id = p.id
                   WHERE g.id = ?""",
                (game_id,),
            )
        else:
            games = self.db.execute(
                """SELECT g.*, p.name as platform_name FROM games g
                   JOIN platforms p ON g.platform_id = p.id
                   ORDER BY g.name"""
            )

        result = {"exported_at": self._now(), "games": []}
        for g in games:
            achievements = self.db.execute(
                """SELECT a.*, au.unlocked, au.unlock_date, au.current_progress, au.source
                   FROM achievements a
                   LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
                   WHERE a.game_id = ?
                   ORDER BY a.name""",
                (g["id"],),
            )
            game_data = {
                "id": g["id"],
                "name": g["name"],
                "platform": g["platform_name"],
                "external_id": g["external_game_id"],
                "total_achievements": g["total_achievements"],
                "achievements": [Achievement.from_row(a).to_dict() for a in achievements],
            }
            result["games"].append(game_data)
        return result

    def _gather_flat_data(self, game_id: int | None = None) -> list[dict]:
        """Gather achievement data as flat rows for CSV."""
        query = """
            SELECT g.name as game_name, p.name as platform_name,
                   a.name as achievement_name, a.description,
                   a.global_completion_pct, a.difficulty_score,
                   a.is_hidden, a.max_progress,
                   COALESCE(au.unlocked, 0) as unlocked,
                   au.unlock_date, COALESCE(au.current_progress, 0) as current_progress,
                   COALESCE(au.source, 'api') as source
            FROM achievements a
            LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
            JOIN games g ON a.game_id = g.id
            JOIN platforms p ON g.platform_id = p.id
        """
        params: tuple = ()
        if game_id:
            query += " WHERE a.game_id = ?"
            params = (game_id,)
        query += " ORDER BY g.name, a.name"
        rows = self.db.execute(query, params)
        return [dict(r) for r in rows]

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
