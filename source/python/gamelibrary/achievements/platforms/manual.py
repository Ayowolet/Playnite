"""Manual achievement entry for platforms without APIs."""

from __future__ import annotations

from .base import PlatformProvider, PlatformGame, PlatformAchievement


class ManualProvider(PlatformProvider):
    """Manual achievement entry provider - stores data directly in DB."""

    def __init__(self):
        self._platform_label: str = "Manual"

    @property
    def platform_name(self) -> str:
        return self._platform_label

    @property
    def api_type(self) -> str:
        return "manual"

    def configure(self, credentials: dict) -> None:
        self._platform_label = credentials.get("platform_label", "Manual")

    def validate_credentials(self) -> bool:
        return True

    def get_games(self) -> list[PlatformGame]:
        return []

    def get_achievements(self, game_external_id: str) -> list[PlatformAchievement]:
        return []

    @staticmethod
    def create_game(name: str, game_id: str | None = None) -> PlatformGame:
        import uuid
        return PlatformGame(
            external_id=game_id or str(uuid.uuid4()),
            name=name,
        )

    @staticmethod
    def create_achievement(
        name: str,
        description: str = "",
        achievement_id: str | None = None,
        unlocked: bool = False,
        unlock_time: str | None = None,
        global_completion_pct: float = 50.0,
        max_progress: int = 0,
        current_progress: int = 0,
    ) -> PlatformAchievement:
        import uuid
        return PlatformAchievement(
            external_id=achievement_id or str(uuid.uuid4()),
            name=name,
            description=description,
            global_completion_pct=global_completion_pct,
            max_progress=max_progress,
            current_progress=current_progress,
            unlocked=unlocked,
            unlock_time=unlock_time,
        )
