"""Manual achievement entry – for platforms without API support."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from playnite.achievements.platforms.base import (
    PlatformAdapter,
    RawAchievement,
    RawGame,
)
from playnite.database.models import Achievement, Game, UserAchievement

if TYPE_CHECKING:
    from playnite.database.connection import DatabaseManager

log = logging.getLogger(__name__)


class ManualAdapter(PlatformAdapter):
    """Allows users to manually record achievements for any platform."""

    platform_name = "manual"

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def is_configured(self) -> bool:
        return True

    def get_games_with_achievements(self) -> list[RawGame]:
        """Return all manually-entered games and achievements."""
        with self._db.get_session() as session:
            games = session.query(Game).filter(Game.platform == "manual").all()
            results: list[RawGame] = []
            for game in games:
                raw_achievements: list[RawAchievement] = []
                for ach in game.achievements:
                    user_ach = (
                        session.query(UserAchievement)
                        .filter(
                            UserAchievement.achievement_id == ach.id,
                            UserAchievement.platform_user_id == "manual",
                        )
                        .first()
                    )
                    raw_achievements.append(
                        RawAchievement(
                            achievement_id=ach.achievement_id,
                            name=ach.name,
                            description=ach.description or "",
                            hidden=ach.hidden,
                            icon_url=ach.icon_url or "",
                            global_percentage=ach.global_percentage,
                            is_unlocked=user_ach.is_unlocked if user_ach else False,
                            unlock_date=user_ach.unlock_date if user_ach else None,
                            current_value=ach.current_value,
                            max_value=ach.max_value,
                        ),
                    )
                results.append(
                    RawGame(
                        platform_game_id=str(game.id),
                        name=game.name,
                        icon_url=game.icon_url or "",
                        achievements=raw_achievements,
                        total_achievements=len(raw_achievements),
                    ),
                )
            return results

    # ------------------------------------------------------------------
    # Write helpers called directly by the CLI / tracker
    # ------------------------------------------------------------------

    def add_game(self, name: str) -> int:
        """Create a manual game entry. Returns the new game id."""
        with self._db.get_session() as session:
            game = Game(name=name, platform="manual", platform_game_id=f"manual_{name}")
            session.add(game)
            session.flush()
            game_id = game.id
        log.info("Manual game created: %s (id=%s)", name, game_id)
        return game_id

    def add_achievement(
        self,
        game_id: int,
        achievement_id: str,
        name: str,
        description: str = "",
        is_unlocked: bool = False,
        unlock_date: datetime | None = None,
        max_value: float | None = None,
        current_value: float | None = None,
    ) -> int:
        """Add an achievement to a manual game. Returns achievement id."""
        if unlock_date is None and is_unlocked:
            unlock_date = datetime.now(timezone.utc).replace(tzinfo=None)

        with self._db.get_session() as session:
            ach = Achievement(
                game_id=game_id,
                achievement_id=achievement_id,
                name=name,
                description=description,
                max_value=max_value,
                current_value=current_value if current_value is not None else (max_value if is_unlocked else 0.0),
            )
            session.add(ach)
            session.flush()
            ach_id = ach.id

            ua = UserAchievement(
                achievement_id=ach_id,
                platform_user_id="manual",
                is_unlocked=is_unlocked,
                unlock_date=unlock_date,
            )
            session.add(ua)
        log.info("Manual achievement added: %s -> %s", game_id, name)
        return ach_id

    def mark_unlocked(self, achievement_id: int, unlock_date: datetime | None = None) -> bool:
        """Mark an existing achievement as unlocked."""
        if unlock_date is None:
            unlock_date = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._db.get_session() as session:
            ua = (
                session.query(UserAchievement)
                .filter(
                    UserAchievement.achievement_id == achievement_id,
                    UserAchievement.platform_user_id == "manual",
                )
                .first()
            )
            if ua is None:
                return False
            ua.is_unlocked = True
            ua.unlock_date = unlock_date
        return True

    def update_progress(
        self, achievement_id: int, current_value: float, max_value: float | None = None,
    ) -> bool:
        """Update progress for a multi-stage achievement."""
        with self._db.get_session() as session:
            ach = session.get(Achievement, achievement_id)
            if ach is None:
                return False
            ach.current_value = current_value
            if max_value is not None:
                ach.max_value = max_value
            if max_value and current_value >= max_value:
                self.mark_unlocked(achievement_id)
        return True

    def edit_achievement(
        self,
        achievement_id: int,
        name: str | None = None,
        description: str | None = None,
        current_value: float | None = None,
        max_value: float | None = None,
        unlock_date: datetime | None = None,
    ) -> bool:
        """Edit a manually-entered achievement's metadata. Returns False if not found."""
        with self._db.get_session() as session:
            ach = session.get(Achievement, achievement_id)
            if ach is None:
                return False
            if name is not None:
                ach.name = name
            if description is not None:
                ach.description = description
            if current_value is not None:
                ach.current_value = current_value
            if max_value is not None:
                ach.max_value = max_value
            if unlock_date is not None:
                ua = (
                    session.query(UserAchievement)
                    .filter(
                        UserAchievement.achievement_id == achievement_id,
                        UserAchievement.platform_user_id == "manual",
                    )
                    .first()
                )
                if ua:
                    ua.unlock_date = unlock_date
        log.info("Manual achievement %d updated", achievement_id)
        return True

    def delete_achievement(self, achievement_id: int) -> bool:
        """Delete a manually-entered achievement and its unlock record. Returns False if not found."""
        with self._db.get_session() as session:
            ach = session.get(Achievement, achievement_id)
            if ach is None:
                return False
            session.delete(ach)  # cascades to UserAchievement via "all, delete-orphan"
        log.info("Manual achievement %d deleted", achievement_id)
        return True
