"""Central achievement tracking engine.

Orchestrates platform adapters, persists data to the database, calculates
statistics, and provides all achievement-related queries.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from playnite.database.models import (
    Achievement,
    AchievementNotification,
    Game,
    SyncLog,
    UserAchievement,
)

if TYPE_CHECKING:
    from playnite.achievements.platforms.base import PlatformAdapter, RawGame
    from playnite.config import Config
    from playnite.database.connection import DatabaseManager

log = logging.getLogger(__name__)

RARE_THRESHOLD_DEFAULT = 10.0  # global completion % below which is considered rare


@dataclass
class SyncResult:
    """Summary of a single platform sync run."""

    platform: str
    games_synced: int = 0
    achievements_found: int = 0
    achievements_unlocked: int = 0
    new_unlocks: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    success: bool = True


@dataclass
class GameCompletionInfo:
    game_id: int
    game_name: str
    platform: str
    total: int
    unlocked: int
    completion_pct: float
    remaining: int
    avg_difficulty: float
    last_unlock: datetime | None


class AchievementTracker:
    """High-level achievement tracking interface.

    Usage::

        tracker = AchievementTracker(config, db_manager)
        tracker.register_adapter(SteamAdapter(config.steam))
        result = tracker.sync("steam")
    """

    def __init__(self, config: Config, db: DatabaseManager) -> None:
        self._cfg = config
        self._db = db
        self._adapters: dict[str, PlatformAdapter] = {}
        self._rare_threshold = config.achievements.rare_threshold

    # ------------------------------------------------------------------
    # Adapter registry
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        self._adapters[adapter.platform_name] = adapter

    def get_adapter(self, platform: str) -> PlatformAdapter | None:
        return self._adapters.get(platform)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync(
        self,
        platform: str | None = None,
        force: bool = False,
    ) -> list[SyncResult]:
        """Sync achievements from one or all platforms.

        :param platform: platform name, or None for all registered adapters.
        :param force: if True, re-fetch even if recently synced.
        :returns: list of SyncResult (one per platform).
        """
        platforms = [platform] if platform else list(self._adapters.keys())
        results: list[SyncResult] = []
        for p in platforms:
            adapter = self._adapters.get(p)
            if adapter is None:
                log.warning("No adapter registered for platform '%s'", p)
                continue
            if not adapter.is_configured():
                log.warning("Adapter '%s' is not configured; skipping", p)
                continue
            result = self._sync_platform(adapter)
            results.append(result)
        return results

    def _sync_platform(self, adapter: PlatformAdapter) -> SyncResult:
        start = time.monotonic()
        result = SyncResult(platform=adapter.platform_name)
        log.info("Starting achievement sync for platform: %s", adapter.platform_name)

        try:
            games = adapter.get_games_with_achievements()
        except Exception as exc:
            log.exception("Sync failed for %s", adapter.platform_name)
            result.success = False
            result.errors.append(str(exc))
            self._write_sync_log(result, time.monotonic() - start)
            return result

        for raw_game in games:
            self._upsert_game(raw_game, adapter.platform_name)
            new = self._upsert_achievements(raw_game, adapter.platform_name)
            result.games_synced += 1
            result.achievements_found += len(raw_game.achievements)
            result.achievements_unlocked += sum(
                1 for a in raw_game.achievements if a.is_unlocked
            )
            result.new_unlocks += new

        result.duration_seconds = time.monotonic() - start
        self._write_sync_log(result, result.duration_seconds)
        log.info(
            "Sync complete for %s: %d games, %d achievements, %d new unlocks",
            adapter.platform_name,
            result.games_synced,
            result.achievements_found,
            result.new_unlocks,
        )
        return result

    # ------------------------------------------------------------------
    # Database upsert helpers
    # ------------------------------------------------------------------

    def _upsert_game(self, raw_game: RawGame, platform: str) -> Game:
        with self._db.get_session() as session:
            game = (
                session.query(Game)
                .filter_by(platform=platform, platform_game_id=raw_game.platform_game_id)
                .first()
            )
            if game is None:
                game = Game(
                    name=raw_game.name,
                    platform=platform,
                    platform_game_id=raw_game.platform_game_id,
                    icon_url=raw_game.icon_url,
                )
                session.add(game)
            else:
                game.name = raw_game.name
                game.icon_url = raw_game.icon_url
            game.total_achievements = raw_game.total_achievements
            game.last_synced = datetime.now(timezone.utc).replace(tzinfo=None)
        return game  # type: ignore[return-value]

    def _upsert_achievements(self, raw_game: RawGame, platform: str) -> int:
        """Upsert achievements for a game. Returns number of newly unlocked."""
        new_unlocks = 0
        with self._db.get_session() as session:
            game = (
                session.query(Game)
                .filter_by(platform=platform, platform_game_id=raw_game.platform_game_id)
                .first()
            )
            if game is None:
                return 0

            for raw_ach in raw_game.achievements:
                ach = (
                    session.query(Achievement)
                    .filter_by(game_id=game.id, achievement_id=raw_ach.achievement_id)
                    .first()
                )
                difficulty = self._calc_difficulty(raw_ach.global_percentage)
                is_rare = (
                    raw_ach.global_percentage is not None
                    and raw_ach.global_percentage < self._rare_threshold
                )
                if ach is None:
                    ach = Achievement(
                        game_id=game.id,
                        achievement_id=raw_ach.achievement_id,
                        name=raw_ach.name,
                        description=raw_ach.description,
                        hidden=raw_ach.hidden,
                        icon_url=raw_ach.icon_url,
                        icon_locked_url=raw_ach.icon_locked_url,
                        global_percentage=raw_ach.global_percentage,
                        difficulty_score=difficulty,
                        is_rare=is_rare,
                        current_value=raw_ach.current_value,
                        max_value=raw_ach.max_value,
                    )
                    session.add(ach)
                    session.flush()
                else:
                    ach.name = raw_ach.name
                    ach.description = raw_ach.description
                    ach.global_percentage = raw_ach.global_percentage
                    ach.difficulty_score = difficulty
                    ach.is_rare = is_rare
                    ach.current_value = raw_ach.current_value

                # Upsert UserAchievement
                user_id = self._platform_user_id(platform)
                ua = (
                    session.query(UserAchievement)
                    .filter_by(achievement_id=ach.id, platform_user_id=user_id)
                    .first()
                )
                was_unlocked = ua.is_unlocked if ua else False
                if ua is None:
                    ua = UserAchievement(
                        achievement_id=ach.id,
                        platform_user_id=user_id,
                        is_unlocked=raw_ach.is_unlocked,
                        unlock_date=raw_ach.unlock_date,
                    )
                    session.add(ua)
                else:
                    ua.is_unlocked = raw_ach.is_unlocked
                    if raw_ach.unlock_date:
                        ua.unlock_date = raw_ach.unlock_date

                # Detect new unlock
                if raw_ach.is_unlocked and not was_unlocked:
                    new_unlocks += 1
                    if self._cfg.achievements.notify_on_unlock:
                        session.flush()  # ensure ach.id populated
                        notif = AchievementNotification(
                            achievement_id=ach.id,
                            platform_user_id=user_id,
                            game_name=raw_game.name,
                            achievement_name=raw_ach.name,
                        )
                        session.add(notif)
        return new_unlocks

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_game_completions(self) -> list[GameCompletionInfo]:
        """Return per-game completion statistics across all platforms."""
        results: list[GameCompletionInfo] = []
        with self._db.get_session() as session:
            games = (
                session.query(Game)
                .options(
                    selectinload(Game.achievements).selectinload(Achievement.user_achievements),
                )
                .all()
            )
            for game in games:
                total = len(game.achievements)
                if total == 0:
                    continue
                user_id = self._platform_user_id(game.platform)
                unlocked_achs = [
                    ua
                    for ach in game.achievements
                    for ua in ach.user_achievements
                    if ua.platform_user_id == user_id and ua.is_unlocked
                ]
                unlocked = len(unlocked_achs)
                last_unlock = max(
                    (ua.unlock_date for ua in unlocked_achs if ua.unlock_date),
                    default=None,
                )
                difficulty_scores = [
                    a.difficulty_score
                    for a in game.achievements
                    if a.difficulty_score is not None
                ]
                avg_diff = sum(difficulty_scores) / len(difficulty_scores) if difficulty_scores else 0.0
                results.append(
                    GameCompletionInfo(
                        game_id=game.id,
                        game_name=game.name,
                        platform=game.platform,
                        total=total,
                        unlocked=unlocked,
                        completion_pct=round(unlocked / total * 100, 2),
                        remaining=total - unlocked,
                        avg_difficulty=round(avg_diff, 3),
                        last_unlock=last_unlock,
                    ),
                )
        return results

    def get_rare_achievements(self) -> list[dict]:
        """Return unlocked rare achievements sorted by rarity (ascending %)."""
        with self._db.get_session() as session:
            rows = (
                session.query(Achievement, Game, UserAchievement)
                .join(Game, Achievement.game_id == Game.id)
                .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
                .filter(
                    Achievement.is_rare == True,  # noqa: E712
                    UserAchievement.is_unlocked == True,  # noqa: E712
                )
                .order_by(Achievement.global_percentage.asc())
                .all()
            )
            return [
                {
                    "achievement": a.name,
                    "game": g.name,
                    "platform": g.platform,
                    "global_pct": a.global_percentage,
                    "unlock_date": ua.unlock_date,
                }
                for a, g, ua in rows
            ]

    def get_unlock_velocity(self, days: int = 30) -> dict:
        """Return per-day unlock counts for the last *days* days."""
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        with self._db.get_session() as session:
            rows = (
                session.query(
                    func.date(UserAchievement.unlock_date).label("day"),
                    func.count().label("count"),
                )
                .filter(
                    UserAchievement.is_unlocked == True,  # noqa: E712
                    UserAchievement.unlock_date >= since,
                )
                .group_by("day")
                .order_by("day")
                .all()
            )
        daily: dict[str, int] = {row.day: row.count for row in rows}
        total = sum(daily.values())
        avg = round(total / days, 2) if days else 0
        return {"daily": daily, "total": total, "avg_per_day": avg, "period_days": days}

    def get_achievement_timeline(self) -> list[dict]:
        """Return all unlocks ordered chronologically."""
        with self._db.get_session() as session:
            rows = (
                session.query(UserAchievement, Achievement, Game)
                .join(Achievement, UserAchievement.achievement_id == Achievement.id)
                .join(Game, Achievement.game_id == Game.id)
                .filter(
                    UserAchievement.is_unlocked == True,  # noqa: E712
                    UserAchievement.unlock_date.isnot(None),
                )
                .order_by(UserAchievement.unlock_date.asc())
                .all()
            )
            return [
                {
                    "unlock_date": ua.unlock_date.isoformat() if ua.unlock_date else None,
                    "achievement": a.name,
                    "game": g.name,
                    "platform": g.platform,
                    "global_pct": a.global_percentage,
                }
                for ua, a, g in rows
            ]

    def get_global_stats(self) -> dict:
        """Return aggregate achievement statistics."""
        with self._db.get_session() as session:
            total_ach = session.query(func.count(Achievement.id)).scalar() or 0
            unlocked = (
                session.query(func.count(UserAchievement.id))
                .filter(UserAchievement.is_unlocked == True)  # noqa: E712
                .scalar()
                or 0
            )
            rare_unlocked = (
                session.query(func.count(Achievement.id))
                .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
                .filter(
                    Achievement.is_rare == True,  # noqa: E712
                    UserAchievement.is_unlocked == True,  # noqa: E712
                )
                .scalar()
                or 0
            )
            total_games = session.query(func.count(Game.id)).scalar() or 0
            platform_rows = (
                session.query(Game.platform, func.count(Game.id))
                .group_by(Game.platform)
                .all()
            )
        completion_pct = round(unlocked / total_ach * 100, 2) if total_ach else 0.0
        return {
            "total_achievements": total_ach,
            "unlocked": unlocked,
            "locked": total_ach - unlocked,
            "completion_pct": completion_pct,
            "rare_unlocked": rare_unlocked,
            "total_games": total_games,
            "platforms": dict(platform_rows),
        }

    def get_pending_notifications(self) -> list[dict]:
        """Return unread unlock notifications."""
        with self._db.get_session() as session:
            rows = (
                session.query(AchievementNotification)
                .filter(AchievementNotification.read_at.is_(None))
                .order_by(AchievementNotification.notified_at.desc())
                .all()
            )
            return [
                {
                    "id": n.id,
                    "game": n.game_name,
                    "achievement": n.achievement_name,
                    "notified_at": n.notified_at.isoformat() if n.notified_at else None,
                }
                for n in rows
            ]

    def mark_notifications_read(self) -> int:
        """Mark all pending notifications as read. Returns count."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._db.get_session() as session:
            rows = (
                session.query(AchievementNotification)
                .filter(AchievementNotification.read_at.is_(None))
                .all()
            )
            count = len(rows)
            for n in rows:
                n.read_at = now
        return count

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_difficulty(global_pct: float | None) -> float | None:
        if global_pct is None:
            return None
        return round(1.0 - (global_pct / 100.0), 4)

    def _platform_user_id(self, platform: str) -> str:
        """Return the configured user ID for a platform."""
        mapping = {
            "steam": self._cfg.steam.steam_id,
            "xbox": self._cfg.xbox.xuid,
            "psn": self._cfg.psn.account_id,
            "gog": self._cfg.gog.user_id,
            "manual": "manual",
        }
        return mapping.get(platform, platform) or platform

    def _write_sync_log(self, result: SyncResult, duration: float) -> None:
        with self._db.get_session() as session:
            log_entry = SyncLog(
                platform=result.platform,
                games_synced=result.games_synced,
                achievements_found=result.achievements_found,
                achievements_unlocked=result.achievements_unlocked,
                new_unlocks=result.new_unlocks,
                status="success" if result.success else "error",
                error_message="; ".join(result.errors) if result.errors else None,
                duration_seconds=duration,
            )
            session.add(log_entry)
