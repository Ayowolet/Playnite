"""Core achievement tracking engine."""

from __future__ import annotations

import logging

from ..database import Database
from ..models import Platform, Game, Achievement
from .platforms.base import PlatformProvider, PlatformGame, PlatformAchievement, AuthenticationError
from .credential_store import encrypt_credentials
from .platforms.steam import SteamProvider
from .platforms.xbox import XboxProvider
from .platforms.psn import PSNProvider
from .platforms.gog import GOGProvider
from .platforms.manual import ManualProvider

logger = logging.getLogger(__name__)

PROVIDER_MAP: dict[str, type[PlatformProvider]] = {
    "steam": SteamProvider,
    "xbox": XboxProvider,
    "psn": PSNProvider,
    "gog": GOGProvider,
    "manual": ManualProvider,
}


def _calculate_difficulty_score(global_pct: float) -> float:
    """Calculate difficulty score (0-100) from global completion percentage.

    Lower global completion = higher difficulty score.
    """
    if global_pct <= 0:
        return 100.0
    if global_pct >= 100:
        return 0.0
    return round(100.0 - global_pct, 2)


class AchievementTracker:
    """Main achievement tracking engine."""

    def __init__(self, db: Database):
        self.db = db

    def register_platform(self, name: str, api_type: str, credentials: dict) -> int:
        """Register a platform with its API credentials."""
        provider = self._get_provider(api_type)
        provider.configure(credentials)

        creds_encrypted = encrypt_credentials(credentials)
        existing = self.db.execute(
            "SELECT id FROM platforms WHERE name = ?", (name,)
        )
        if existing:
            self.db.execute(
                "UPDATE platforms SET api_type = ?, credentials = ?, updated_at = datetime('now') WHERE name = ?",
                (api_type, creds_encrypted, name),
            )
            return existing[0]["id"]

        return self.db.execute_insert(
            "INSERT INTO platforms (name, api_type, credentials) VALUES (?, ?, ?)",
            (name, api_type, creds_encrypted),
        )

    def get_platforms(self) -> list[Platform]:
        rows = self.db.execute("SELECT * FROM platforms WHERE enabled = 1")
        return [Platform.from_row(r) for r in rows]

    def get_platform(self, platform_id: int) -> Platform | None:
        rows = self.db.execute("SELECT * FROM platforms WHERE id = ?", (platform_id,))
        return Platform.from_row(rows[0]) if rows else None

    def import_achievements(self, platform_id: int) -> dict:
        """Import achievements from a platform. Returns sync summary."""
        platform = self.get_platform(platform_id)
        if not platform:
            raise ValueError(f"Platform {platform_id} not found")

        provider = self._get_provider(platform.api_type)
        provider.configure(platform.credentials)

        sync_id = self._start_sync(platform_id)
        total_found = 0
        new_unlocks = 0

        try:
            games = provider.get_games()
            for pg in games:
                game_id = self._upsert_game(platform_id, pg)
                achievements = provider.get_achievements(pg.external_id)
                if not achievements:
                    continue
                self.db.execute(
                    "UPDATE games SET total_achievements = ?, updated_at = datetime('now') WHERE id = ?",
                    (len(achievements), game_id),
                )
                for pa in achievements:
                    total_found += 1
                    was_new = self._upsert_achievement(game_id, pa)
                    if was_new:
                        new_unlocks += 1

            self._persist_credentials(platform_id, provider)
            self._complete_sync(sync_id, total_found, new_unlocks, "completed")
            return {
                "sync_id": sync_id,
                "platform": platform.name,
                "games_processed": len(games),
                "achievements_found": total_found,
                "new_unlocks": new_unlocks,
                "status": "completed",
            }
        except AuthenticationError as e:
            self._persist_credentials(platform_id, provider)
            self._complete_sync(sync_id, total_found, new_unlocks, "auth_failed", str(e))
            raise
        except (ValueError, RuntimeError, OSError, KeyError) as e:
            self._persist_credentials(platform_id, provider)
            self._complete_sync(sync_id, total_found, new_unlocks, "failed", str(e))
            raise

    def import_single_game(self, platform_id: int, game_external_id: str) -> dict:
        """Import achievements for a single game."""
        platform = self.get_platform(platform_id)
        if not platform:
            raise ValueError(f"Platform {platform_id} not found")

        provider = self._get_provider(platform.api_type)
        provider.configure(platform.credentials)

        achievements = provider.get_achievements(game_external_id)
        games = provider.get_games()
        pg = next((g for g in games if g.external_id == game_external_id), None)

        if pg is None:
            pg = PlatformGame(external_id=game_external_id, name=f"Game {game_external_id}")

        game_id = self._upsert_game(platform_id, pg)
        self.db.execute(
            "UPDATE games SET total_achievements = ?, updated_at = datetime('now') WHERE id = ?",
            (len(achievements), game_id),
        )

        new_unlocks = 0
        for pa in achievements:
            was_new = self._upsert_achievement(game_id, pa)
            if was_new:
                new_unlocks += 1

        self._persist_credentials(platform_id, provider)
        return {
            "game_id": game_id,
            "game_name": pg.name,
            "achievements_found": len(achievements),
            "new_unlocks": new_unlocks,
        }

    def add_manual_game(self, platform_name: str, game_name: str, game_id: str | None = None) -> int:
        """Add a game for manual achievement tracking."""
        rows = self.db.execute(
            "SELECT id FROM platforms WHERE api_type = 'manual' AND name = ?", (platform_name,)
        )
        if rows:
            plat_id = rows[0]["id"]
        else:
            plat_id = self.register_platform(platform_name, "manual", {"platform_label": platform_name})

        provider = ManualProvider()
        pg = provider.create_game(game_name, game_id)
        return self._upsert_game(plat_id, pg)

    def add_manual_achievement(
        self,
        game_id: int,
        name: str,
        description: str = "",
        unlocked: bool = False,
        unlock_time: str | None = None,
        global_pct: float = 50.0,
        max_progress: int = 0,
        current_progress: int = 0,
    ) -> int:
        """Add a manual achievement entry."""
        if not (0.0 <= global_pct <= 100.0):
            raise ValueError(f"global_pct must be between 0 and 100, got {global_pct}")
        provider = ManualProvider()
        pa = provider.create_achievement(
            name=name,
            description=description,
            unlocked=unlocked,
            unlock_time=unlock_time,
            global_completion_pct=global_pct,
            max_progress=max_progress,
            current_progress=current_progress,
        )
        ach_id = self._upsert_achievement_def(game_id, pa)
        self._upsert_unlock(ach_id, pa, source="manual")
        # Update total achievements count
        self.db.execute(
            """UPDATE games SET total_achievements = (
                SELECT COUNT(*) FROM achievements WHERE game_id = ?
            ), updated_at = datetime('now') WHERE id = ?""",
            (game_id, game_id),
        )
        return ach_id

    def update_manual_achievement(
        self,
        achievement_id: int,
        unlocked: bool | None = None,
        unlock_time: str | None = None,
        current_progress: int | None = None,
        name: str | None = None,
        description: str | None = None,
        global_pct: float | None = None,
    ):
        """Update a manual achievement's unlock status, progress, or definition fields."""
        # Update definition fields in the achievements table
        def_updates = []
        def_params = []
        if name is not None:
            def_updates.append("name = ?")
            def_params.append(name)
        if description is not None:
            def_updates.append("description = ?")
            def_params.append(description)
        if global_pct is not None:
            def_updates.append("global_completion_pct = ?")
            def_params.append(global_pct)
            def_updates.append("difficulty_score = ?")
            def_params.append(_calculate_difficulty_score(global_pct))
        if def_updates:
            def_updates.append("updated_at = datetime('now')")
            def_params.append(achievement_id)
            self.db.execute(
                f"UPDATE achievements SET {', '.join(def_updates)} WHERE id = ?",
                tuple(def_params),
            )

        # Update unlock fields in the achievement_unlocks table
        unlock_updates = []
        unlock_params = []
        if unlocked is not None:
            unlock_updates.append("unlocked = ?")
            unlock_params.append(int(unlocked))
        if unlock_time is not None:
            unlock_updates.append("unlock_date = ?")
            unlock_params.append(unlock_time)
        if current_progress is not None:
            unlock_updates.append("current_progress = ?")
            unlock_params.append(current_progress)
        if unlock_updates:
            unlock_updates.append("synced_at = datetime('now')")
            unlock_params.append(achievement_id)
            self.db.execute(
                f"UPDATE achievement_unlocks SET {', '.join(unlock_updates)} WHERE achievement_id = ?",
                tuple(unlock_params),
            )

    def delete_achievement(self, achievement_id: int):
        """Delete an achievement and its unlock record (cascades via FK)."""
        rows = self.db.execute(
            "SELECT game_id FROM achievements WHERE id = ?", (achievement_id,)
        )
        self.db.execute(
            "DELETE FROM achievement_unlocks WHERE achievement_id = ?",
            (achievement_id,),
        )
        self.db.execute(
            "DELETE FROM achievements WHERE id = ?",
            (achievement_id,),
        )
        # Update the game's total_achievements count
        if rows:
            game_id = rows[0]["game_id"]
            self.db.execute(
                """UPDATE games SET total_achievements = (
                    SELECT COUNT(*) FROM achievements WHERE game_id = ?
                ), updated_at = datetime('now') WHERE id = ?""",
                (game_id, game_id),
            )

    def get_games(self, platform_id: int | None = None) -> list[Game]:
        if platform_id:
            rows = self.db.execute(
                """SELECT g.*, p.name as platform_name FROM games g
                   JOIN platforms p ON g.platform_id = p.id
                   WHERE g.platform_id = ? ORDER BY g.name""",
                (platform_id,),
            )
        else:
            rows = self.db.execute(
                """SELECT g.*, p.name as platform_name FROM games g
                   JOIN platforms p ON g.platform_id = p.id
                   ORDER BY g.name"""
            )
        return [Game.from_row(r) for r in rows]

    def get_achievements(self, game_id: int, unlocked_only: bool = False) -> list[Achievement]:
        query = """
            SELECT a.*, au.unlocked, au.unlock_date, au.current_progress, au.source
            FROM achievements a
            LEFT JOIN achievement_unlocks au ON a.id = au.achievement_id
            WHERE a.game_id = ?
        """
        if unlocked_only:
            query += " AND au.unlocked = 1"
        query += " ORDER BY a.name"
        rows = self.db.execute(query, (game_id,))
        return [Achievement.from_row(r) for r in rows]

    def get_achievement(self, achievement_id: int) -> Achievement | None:
        rows = self.db.execute(
            """SELECT a.*, au.unlocked, au.unlock_date, au.current_progress, au.source
               FROM achievements a
               LEFT JOIN achievement_unlocks au ON a.id = au.achievement_id
               WHERE a.id = ?""",
            (achievement_id,),
        )
        return Achievement.from_row(rows[0]) if rows else None

    def get_recent_unlocks(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            """SELECT a.name as achievement_name, a.global_completion_pct,
                      g.name as game_name, p.name as platform_name,
                      au.unlock_date, au.source
               FROM achievement_unlocks au
               JOIN achievements a ON au.achievement_id = a.id
               JOIN games g ON a.game_id = g.id
               JOIN platforms p ON g.platform_id = p.id
               WHERE au.unlocked = 1 AND au.unlock_date IS NOT NULL
               ORDER BY au.unlock_date DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    def _persist_credentials(self, platform_id: int, provider: PlatformProvider):
        """Save provider's current credentials back to DB if they changed."""
        updated_creds = provider.get_credentials()
        if not updated_creds:
            return
        encrypted = encrypt_credentials(updated_creds)
        self.db.execute(
            "UPDATE platforms SET credentials = ?, updated_at = datetime('now') WHERE id = ?",
            (encrypted, platform_id),
        )

    def _get_provider(self, api_type: str) -> PlatformProvider:
        cls = PROVIDER_MAP.get(api_type)
        if not cls:
            raise ValueError(f"Unknown platform type: {api_type}")
        return cls()

    def _upsert_game(self, platform_id: int, pg: PlatformGame) -> int:
        existing = self.db.execute(
            "SELECT id FROM games WHERE platform_id = ? AND external_game_id = ?",
            (platform_id, pg.external_id),
        )
        if existing:
            self.db.execute(
                "UPDATE games SET name = ?, icon_url = ?, updated_at = datetime('now') WHERE id = ?",
                (pg.name, pg.icon_url, existing[0]["id"]),
            )
            return existing[0]["id"]
        return self.db.execute_insert(
            "INSERT INTO games (platform_id, external_game_id, name, total_achievements, icon_url) VALUES (?, ?, ?, ?, ?)",
            (platform_id, pg.external_id, pg.name, pg.total_achievements, pg.icon_url),
        )

    def _upsert_achievement(self, game_id: int, pa: PlatformAchievement) -> bool:
        """Upsert achievement definition and unlock status. Returns True if new unlock detected."""
        ach_id = self._upsert_achievement_def(game_id, pa)
        return self._upsert_unlock(ach_id, pa)

    def _upsert_achievement_def(self, game_id: int, pa: PlatformAchievement) -> int:
        difficulty = _calculate_difficulty_score(pa.global_completion_pct)
        existing = self.db.execute(
            "SELECT id FROM achievements WHERE game_id = ? AND external_achievement_id = ?",
            (game_id, pa.external_id),
        )
        if existing:
            self.db.execute(
                """UPDATE achievements SET name = ?, description = ?, icon_url = ?,
                   locked_icon_url = ?, global_completion_pct = ?, difficulty_score = ?,
                   is_hidden = ?, max_progress = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (pa.name, pa.description, pa.icon_url, pa.locked_icon_url,
                 pa.global_completion_pct, difficulty, int(pa.is_hidden),
                 pa.max_progress, existing[0]["id"]),
            )
            return existing[0]["id"]
        return self.db.execute_insert(
            """INSERT INTO achievements (game_id, external_achievement_id, name, description,
               icon_url, locked_icon_url, global_completion_pct, difficulty_score, is_hidden, max_progress)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (game_id, pa.external_id, pa.name, pa.description, pa.icon_url,
             pa.locked_icon_url, pa.global_completion_pct, difficulty,
             int(pa.is_hidden), pa.max_progress),
        )

    def _upsert_unlock(self, ach_id: int, pa: PlatformAchievement, source: str = "api") -> bool:
        existing = self.db.execute(
            "SELECT unlocked FROM achievement_unlocks WHERE achievement_id = ?",
            (ach_id,),
        )
        is_new_unlock = False
        if existing:
            was_unlocked = bool(existing[0]["unlocked"])
            if pa.unlocked and not was_unlocked:
                is_new_unlock = True
            self.db.execute(
                """UPDATE achievement_unlocks SET unlocked = ?, unlock_date = ?,
                   current_progress = ?, source = ?, synced_at = datetime('now')
                   WHERE achievement_id = ?""",
                (int(pa.unlocked), pa.unlock_time, pa.current_progress, source, ach_id),
            )
        else:
            is_new_unlock = pa.unlocked
            self.db.execute_insert(
                """INSERT INTO achievement_unlocks (achievement_id, unlocked, unlock_date, current_progress, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (ach_id, int(pa.unlocked), pa.unlock_time, pa.current_progress, source),
            )
        return is_new_unlock

    def _start_sync(self, platform_id: int) -> int:
        return self.db.execute_insert(
            "INSERT INTO sync_history (platform_id, sync_type) VALUES (?, 'full')",
            (platform_id,),
        )

    def _complete_sync(self, sync_id: int, found: int, new_unlocks: int, status: str, error: str | None = None):
        self.db.execute(
            """UPDATE sync_history SET completed_at = datetime('now'),
               achievements_found = ?, new_unlocks = ?, status = ?, error_message = ?
               WHERE id = ?""",
            (found, new_unlocks, status, error, sync_id),
        )
