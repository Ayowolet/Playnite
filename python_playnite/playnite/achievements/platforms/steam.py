"""Steam Web API achievement adapter.

API documentation: https://developer.valvesoftware.com/wiki/Steam_Web_API
Requires a free API key from https://steamcommunity.com/dev/apikey
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

from playnite.achievements.platforms.base import (
    PlatformAdapter,
    RawAchievement,
    RawGame,
)

if TYPE_CHECKING:
    from playnite.config import SteamConfig

log = logging.getLogger(__name__)

_BASE = "https://api.steampowered.com"
_RATE_DELAY = 0.5  # seconds between requests to stay within limits
_MAX_RETRIES = 3
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class SteamAdapter(PlatformAdapter):
    """Fetch achievements from the Steam Web API."""

    platform_name = "steam"

    def __init__(self, config: SteamConfig, session: requests.Session | None = None) -> None:
        self._cfg = config
        self._http = session or requests.Session()
        self._http.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._cfg.api_key and self._cfg.steam_id)

    def get_games_with_achievements(self) -> list[RawGame]:
        """Return all owned games that have achievement data."""
        owned = self._get_owned_games()
        results: list[RawGame] = []
        for game in owned:
            app_id = str(game["appid"])
            name = game.get("name", f"App {app_id}")
            icon_hash = game.get("img_icon_url", "")
            icon_url = (
                f"https://media.steampowered.com/steamcommunity/public/images/apps/{app_id}/{icon_hash}.jpg"
                if icon_hash
                else ""
            )
            achievements = self._get_achievements_for_game(app_id, name)
            if achievements is not None:
                raw_game = RawGame(
                    platform_game_id=app_id,
                    name=name,
                    icon_url=icon_url,
                    achievements=achievements,
                    total_achievements=len(achievements),
                )
                results.append(raw_game)
            time.sleep(_RATE_DELAY)
        return results

    # ------------------------------------------------------------------
    # HTTP helper with retry / back-off
    # ------------------------------------------------------------------

    def _http_get_with_retry(
        self, url: str, params: dict, timeout: int = 15,
    ) -> requests.Response:
        """GET *url*, retrying up to _MAX_RETRIES times with exponential back-off.

        Retries on HTTP 429/5xx responses and connection errors.
        """
        delay = 1.0
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.get(url, params=params, timeout=timeout)
                if resp.status_code not in _RETRY_STATUSES or attempt == _MAX_RETRIES:
                    return resp
                log.warning(
                    "Steam API %s -> HTTP %d (attempt %d/%d), retrying in %.1fs",
                    url, resp.status_code, attempt + 1, _MAX_RETRIES + 1, delay,
                )
            except requests.ConnectionError as exc:
                if attempt == _MAX_RETRIES:
                    raise
                log.warning(
                    "Steam API connection error on %s (attempt %d/%d): %s, retrying in %.1fs",
                    url, attempt + 1, _MAX_RETRIES + 1, exc, delay,
                )
            time.sleep(delay)
            delay *= 2
        return self._http.get(url, params=params, timeout=timeout)  # unreachable

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_owned_games(self) -> list[dict]:
        url = f"{_BASE}/IPlayerService/GetOwnedGames/v0001/"
        params = {
            "key": self._cfg.api_key,
            "steamid": self._cfg.steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        }
        try:
            resp = self._http_get_with_retry(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", {}).get("games", [])
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                log.error(
                    "Steam: API key rejected (HTTP %d) — verify your Steam API key.",
                    exc.response.status_code,
                )
            else:
                log.exception("Steam GetOwnedGames failed: %s", exc)
            return []
        except requests.RequestException as exc:
            log.exception("Steam GetOwnedGames failed: %s", exc)
            return []

    def _get_achievements_for_game(
        self, app_id: str, game_name: str,
    ) -> list[RawAchievement] | None:
        """Return normalised achievements for *app_id*, or None if the game has none."""
        schema = self._get_schema(app_id)
        if not schema:
            return None

        player_data = self._get_player_achievements(app_id)
        global_pcts = self._get_global_percentages(app_id)

        # Build lookup maps
        player_map: dict[str, dict] = {}
        for a in player_data:
            player_map[a["apiname"]] = a

        global_map: dict[str, float] = {}
        for item in global_pcts:
            global_map[item["name"]] = item["percent"]

        results: list[RawAchievement] = []
        for ach in schema:
            api_name = ach.get("name", "")
            player_record = player_map.get(api_name, {})
            is_unlocked = bool(player_record.get("achieved", 0))
            unlock_ts = player_record.get("unlocktime", 0)
            unlock_date: datetime | None = None
            if unlock_ts:
                unlock_date = datetime.fromtimestamp(unlock_ts, tz=timezone.utc).replace(tzinfo=None)

            global_pct = global_map.get(api_name)

            results.append(
                RawAchievement(
                    achievement_id=api_name,
                    name=ach.get("displayName", api_name),
                    description=ach.get("description", ""),
                    hidden=bool(ach.get("hidden", 0)),
                    icon_url=ach.get("icon", ""),
                    icon_locked_url=ach.get("icongray", ""),
                    global_percentage=global_pct,
                    is_unlocked=is_unlocked,
                    unlock_date=unlock_date,
                ),
            )
        return results if results else None

    def _get_schema(self, app_id: str) -> list[dict]:
        url = f"{_BASE}/ISteamUserStats/GetSchemaForGame/v0002/"
        params = {"key": self._cfg.api_key, "appid": app_id, "format": "json"}
        try:
            resp = self._http_get_with_retry(url, params=params)
            resp.raise_for_status()
            game_data = resp.json().get("game", {})
            stats = game_data.get("availableGameStats", {})
            return stats.get("achievements", [])
        except requests.RequestException as exc:
            log.debug("Steam GetSchemaForGame %s failed: %s", app_id, exc)
            return []

    def _get_player_achievements(self, app_id: str) -> list[dict]:
        url = f"{_BASE}/ISteamUserStats/GetPlayerAchievements/v0001/"
        params = {
            "key": self._cfg.api_key,
            "steamid": self._cfg.steam_id,
            "appid": app_id,
            "format": "json",
        }
        try:
            resp = self._http_get_with_retry(url, params=params)
            resp.raise_for_status()
            stats = resp.json().get("playerstats", {})
            if not stats.get("success"):
                return []
            return stats.get("achievements", [])
        except requests.RequestException as exc:
            log.debug("Steam GetPlayerAchievements %s failed: %s", app_id, exc)
            return []

    def _get_global_percentages(self, app_id: str) -> list[dict]:
        url = f"{_BASE}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v0002/"
        params = {"gameid": app_id, "format": "json"}
        try:
            resp = self._http_get_with_retry(url, params=params)
            resp.raise_for_status()
            data = resp.json().get("achievementpercentages", {})
            return data.get("achievements", [])
        except requests.RequestException as exc:
            log.debug("Steam GetGlobalAchievementPercentages %s failed: %s", app_id, exc)
            return []

    # ------------------------------------------------------------------
    # Convenience single-game sync (used by tracker for force refresh)
    # ------------------------------------------------------------------

    def get_achievements_for_app(self, app_id: str, game_name: str) -> list[RawAchievement]:
        result = self._get_achievements_for_game(app_id, game_name)
        return result or []
