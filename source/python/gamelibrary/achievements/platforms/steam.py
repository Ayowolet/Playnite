"""Steam achievement provider using Steam Web API."""

from __future__ import annotations

import logging
import requests
from .base import PlatformProvider, PlatformGame, PlatformAchievement, AuthenticationError

logger = logging.getLogger(__name__)

STEAM_API_BASE = "https://api.steampowered.com"


class SteamProvider(PlatformProvider):
    """Steam Web API achievement provider."""

    def __init__(self):
        self.api_key: str = ""
        self.steam_id: str = ""

    @property
    def platform_name(self) -> str:
        return "Steam"

    @property
    def api_type(self) -> str:
        return "steam"

    def configure(self, credentials: dict) -> None:
        self.api_key = credentials.get("api_key", "")
        self.steam_id = credentials.get("steam_id", "")

    def validate_credentials(self) -> bool:
        if not self.api_key or not self.steam_id:
            return False
        try:
            resp = requests.get(
                f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v2/",
                params={"key": self.api_key, "steamids": self.steam_id},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def get_games(self) -> list[PlatformGame]:
        try:
            resp = requests.get(
                f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/",
                params={
                    "key": self.api_key,
                    "steamid": self.steam_id,
                    "include_appinfo": 1,
                    "include_played_free_games": 1,
                    "format": "json",
                },
                timeout=30,
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("Steam", f"HTTP {resp.status_code}: check your API key")
            resp.raise_for_status()
            data = resp.json().get("response", {})
            games = []
            for g in data.get("games", []):
                appid = str(g["appid"])
                games.append(PlatformGame(
                    external_id=appid,
                    name=g.get("name", f"App {appid}"),
                    icon_url=f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{g.get('img_icon_url', '')}.jpg" if g.get("img_icon_url") else "",
                    total_achievements=0,
                ))
            return games
        except AuthenticationError:
            raise
        except requests.RequestException as e:
            logger.error("Failed to fetch Steam games: %s", e)
            return []

    def get_achievements(self, game_external_id: str) -> list[PlatformAchievement]:
        schema = self._get_achievement_schema(game_external_id)
        if not schema:
            return []
        player_achievements = self._get_player_achievements(game_external_id)
        global_stats = self._get_global_achievement_stats(game_external_id)

        unlock_map = {}
        for pa in player_achievements:
            unlock_map[pa["apiname"]] = pa

        global_map = {}
        for gs in global_stats:
            global_map[gs["name"]] = gs.get("percent", 0.0)

        results = []
        for ach in schema:
            api_name = ach["name"]
            player_data = unlock_map.get(api_name, {})
            results.append(PlatformAchievement(
                external_id=api_name,
                name=ach.get("displayName", api_name),
                description=ach.get("description", ""),
                icon_url=ach.get("icon", ""),
                locked_icon_url=ach.get("icongray", ""),
                global_completion_pct=round(global_map.get(api_name, 0.0), 2),
                is_hidden=bool(ach.get("hidden", 0)),
                unlocked=bool(player_data.get("achieved", 0)),
                unlock_time=self._format_timestamp(player_data.get("unlocktime", 0)),
            ))
        return results

    def _get_achievement_schema(self, appid: str) -> list[dict]:
        try:
            resp = requests.get(
                f"{STEAM_API_BASE}/ISteamUserStats/GetSchemaForGame/v2/",
                params={"key": self.api_key, "appid": appid, "format": "json"},
                timeout=15,
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("Steam", f"HTTP {resp.status_code}: check your API key")
            resp.raise_for_status()
            game_data = resp.json().get("game", {})
            stats = game_data.get("availableGameStats", {})
            return stats.get("achievements", [])
        except AuthenticationError:
            raise
        except requests.RequestException:
            return []

    def _get_player_achievements(self, appid: str) -> list[dict]:
        try:
            resp = requests.get(
                f"{STEAM_API_BASE}/ISteamUserStats/GetPlayerAchievements/v1/",
                params={
                    "key": self.api_key,
                    "steamid": self.steam_id,
                    "appid": appid,
                    "format": "json",
                },
                timeout=15,
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("Steam", f"HTTP {resp.status_code}: check your API key")
            resp.raise_for_status()
            stats = resp.json().get("playerstats", {})
            return stats.get("achievements", [])
        except AuthenticationError:
            raise
        except requests.RequestException:
            return []

    def _get_global_achievement_stats(self, appid: str) -> list[dict]:
        try:
            resp = requests.get(
                f"{STEAM_API_BASE}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                params={"gameid": appid, "format": "json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("achievementpercentages", {})
            return data.get("achievements", [])
        except requests.RequestException:
            return []

    @staticmethod
    def _format_timestamp(ts: int) -> str | None:
        if not ts:
            return None
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
