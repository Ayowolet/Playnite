"""Base class for platform achievement providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PlatformAchievement:
    """Raw achievement data from a platform API."""
    external_id: str
    name: str
    description: str = ""
    icon_url: str = ""
    locked_icon_url: str = ""
    global_completion_pct: float = 0.0
    is_hidden: bool = False
    max_progress: int = 0
    unlocked: bool = False
    unlock_time: str | None = None
    current_progress: int = 0


@dataclass
class PlatformGame:
    """Raw game data from a platform API."""
    external_id: str
    name: str
    icon_url: str = ""
    total_achievements: int = 0
    achievements: list[PlatformAchievement] | None = None


class AuthenticationError(Exception):
    """Raised when a platform API returns 401/403 after retry attempts."""

    def __init__(self, platform: str, message: str = ""):
        self.platform = platform
        msg = (
            f"Authentication failed for {platform}: {message}"
            if message
            else f"Authentication failed for {platform}"
        )
        super().__init__(msg)


class PlatformProvider(ABC):
    """Abstract base class for platform achievement providers."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...

    @property
    @abstractmethod
    def api_type(self) -> str:
        ...

    @abstractmethod
    def configure(self, credentials: dict) -> None:
        ...

    @abstractmethod
    def validate_credentials(self) -> bool:
        ...

    @abstractmethod
    def get_games(self) -> list[PlatformGame]:
        ...

    @abstractmethod
    def get_achievements(self, game_external_id: str) -> list[PlatformAchievement]:
        ...

    def get_credentials(self) -> dict:
        """Return current credentials state. Override to include refreshed tokens."""
        return {}

    def get_all_achievements(self) -> dict[str, list[PlatformAchievement]]:
        """Fetch achievements for all games. Returns {game_external_id: [achievements]}."""
        result = {}
        for game in self.get_games():
            achievements = self.get_achievements(game.external_id)
            if achievements:
                result[game.external_id] = achievements
        return result
