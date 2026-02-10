"""Abstract base class for platform achievement adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class RawAchievement:
    """Normalised achievement data returned by every platform adapter."""

    achievement_id: str
    name: str
    description: str = ""
    hidden: bool = False
    icon_url: str = ""
    icon_locked_url: str = ""
    global_percentage: float | None = None
    is_unlocked: bool = False
    unlock_date: datetime | None = None
    # Optional progress fields for incremental achievements
    current_value: float | None = None
    max_value: float | None = None


@dataclass
class RawGame:
    """Normalised game entry returned by every platform adapter."""

    platform_game_id: str
    name: str
    icon_url: str = ""
    achievements: list[RawAchievement] = field(default_factory=list)
    total_achievements: int = 0


class PlatformAdapter(ABC):
    """Base class all platform adapters must implement."""

    platform_name: str = "unknown"

    @abstractmethod
    def get_games_with_achievements(self) -> list[RawGame]:
        """Fetch all games and their achievements for the authenticated user."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the adapter has the credentials it needs."""
