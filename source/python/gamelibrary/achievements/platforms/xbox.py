"""Xbox Live achievement provider using Xbox API."""

from __future__ import annotations

import logging
import requests
from .base import PlatformProvider, PlatformGame, PlatformAchievement, AuthenticationError

logger = logging.getLogger(__name__)

XBOX_API_BASE = "https://xbl.io/api/v2"


class XboxProvider(PlatformProvider):
    """Xbox Live achievement provider via OpenXBL API."""

    def __init__(self):
        self.api_key: str = ""
        self.xuid: str = ""

    @property
    def platform_name(self) -> str:
        return "Xbox Live"

    @property
    def api_type(self) -> str:
        return "xbox"

    def configure(self, credentials: dict) -> None:
        self.api_key = credentials.get("api_key", "")
        self.xuid = credentials.get("xuid", "")

    def validate_credentials(self) -> bool:
        if not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{XBOX_API_BASE}/account",
                headers={"X-Authorization": self.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not self.xuid and "profileUsers" in data:
                    users = data["profileUsers"]
                    if users:
                        self.xuid = users[0].get("id", "")
                return True
            return False
        except requests.RequestException:
            return False

    def _headers(self) -> dict:
        return {"X-Authorization": self.api_key, "Accept": "application/json"}

    def get_games(self) -> list[PlatformGame]:
        try:
            resp = requests.get(
                f"{XBOX_API_BASE}/achievements",
                headers=self._headers(),
                timeout=30,
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("Xbox Live", f"HTTP {resp.status_code}: check your API key")
            resp.raise_for_status()
            data = resp.json()
            titles = data.get("titles", [])

            games = []
            seen_ids = set()
            for title in titles:
                title_id = str(title.get("titleId", ""))
                if title_id in seen_ids:
                    continue
                seen_ids.add(title_id)
                achievement_summary = title.get("achievement", {})
                games.append(PlatformGame(
                    external_id=title_id,
                    name=title.get("name", ""),
                    icon_url=title.get("displayImage", ""),
                    total_achievements=achievement_summary.get("totalGamerscore", 0),
                ))
            return games
        except AuthenticationError:
            raise
        except requests.RequestException as e:
            logger.error("Failed to fetch Xbox games: %s", e)
            return []

    def get_achievements(self, game_external_id: str) -> list[PlatformAchievement]:
        try:
            resp = requests.get(
                f"{XBOX_API_BASE}/achievements/title/{game_external_id}",
                headers=self._headers(),
                timeout=30,
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("Xbox Live", f"HTTP {resp.status_code}: check your API key")
            resp.raise_for_status()
            data = resp.json()
            achievement_list = data.get("achievements", [])

            results = []
            for ach in achievement_list:
                progression = ach.get("progression", {})
                requirements = progression.get("requirements", [{}])
                current_val = 0
                target_val = 0
                if requirements:
                    req = requirements[0]
                    current_val = int(req.get("current", "0") or "0")
                    target_val = int(req.get("target", "0") or "0")

                rarity = ach.get("rarity", {})
                global_pct = rarity.get("currentPercentage", 0.0)
                time_unlocked = progression.get("timeUnlocked", "")
                is_unlocked = time_unlocked != "" and time_unlocked != "0001-01-01T00:00:00.0000000Z"

                media_assets = ach.get("mediaAssets", [])
                icon = media_assets[0].get("url", "") if media_assets else ""

                results.append(PlatformAchievement(
                    external_id=str(ach.get("id", "")),
                    name=ach.get("name", ""),
                    description=ach.get("description", ""),
                    icon_url=icon,
                    global_completion_pct=round(float(global_pct), 2),
                    is_hidden=ach.get("isSecret", False),
                    max_progress=target_val,
                    current_progress=current_val,
                    unlocked=is_unlocked,
                    unlock_time=time_unlocked if is_unlocked else None,
                ))
            return results
        except AuthenticationError:
            raise
        except requests.RequestException as e:
            logger.error("Failed to fetch Xbox achievements for %s: %s", game_external_id, e)
            return []
