"""GOG Galaxy achievement adapter.

Uses the unofficial GOG Galaxy API with OAuth2.
The user must authenticate via browser; see docs/platform_api_setup.md for steps.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

from playnite.achievements.platforms.base import (
    PlatformAdapter,
    RawAchievement,
    RawGame,
)

if TYPE_CHECKING:
    from playnite.config import GOGConfig

log = logging.getLogger(__name__)

_AUTH_BASE = "https://auth.gog.com"
_GALAXY_BASE = "https://gameplay.gog.com"
_EMBED_BASE = "https://embed.gog.com"


class GOGAdapter(PlatformAdapter):
    """Fetch achievements from the GOG Galaxy API."""

    platform_name = "gog"

    def __init__(self, config: GOGConfig, session: requests.Session | None = None) -> None:
        self._cfg = config
        self._http = session or requests.Session()

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._cfg.access_token or self._cfg.client_id)

    def get_games_with_achievements(self) -> list[RawGame]:
        if not self._ensure_token():
            log.error("GOG: no access token available; skipping sync")
            return []
        user_id = self._cfg.user_id or self._get_user_id()
        if not user_id:
            log.error("GOG: could not determine user_id")
            return []
        return self._fetch_games(user_id)

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------

    def _ensure_token(self) -> bool:
        if self._cfg.access_token:
            self._http.headers["Authorization"] = f"Bearer {self._cfg.access_token}"
            return True
        if self._cfg.refresh_token:
            return self._refresh_token()
        return False

    def _refresh_token(self) -> bool:
        try:
            resp = self._http.get(
                f"{_AUTH_BASE}/token",
                params={
                    "client_id": self._cfg.client_id,
                    "client_secret": self._cfg.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self._cfg.refresh_token,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._cfg.access_token = data.get("access_token", "")
            self._cfg.refresh_token = data.get("refresh_token", self._cfg.refresh_token)
            if self._cfg.access_token:
                self._http.headers["Authorization"] = f"Bearer {self._cfg.access_token}"
                return True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                log.error(
                    "GOG: refresh token rejected (HTTP %d) — re-authenticate via browser.",
                    exc.response.status_code,
                )
            else:
                log.exception("GOG token refresh failed: %s", exc)
        except requests.RequestException as exc:
            log.exception("GOG token refresh failed: %s", exc)
        return False

    def _get_user_id(self) -> str:
        try:
            resp = self._http.get(f"{_EMBED_BASE}/userData.json", timeout=10)
            resp.raise_for_status()
            return str(resp.json().get("userId", ""))
        except requests.RequestException as exc:
            log.exception("GOG userData fetch failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Achievement fetching
    # ------------------------------------------------------------------

    def _fetch_games(self, user_id: str) -> list[RawGame]:
        """Fetch all games and their achievements."""
        try:
            resp = self._http.get(
                f"{_EMBED_BASE}/account/getFilteredProducts",
                params={"mediaType": 1, "totalPages": 1},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            games_raw: list[dict] = data.get("products", [])
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                log.error(
                    "GOG: access token rejected (HTTP %d) — re-authenticate via browser.",
                    exc.response.status_code,
                )
            else:
                log.exception("GOG getFilteredProducts failed: %s", exc)
            return []
        except requests.RequestException as exc:
            log.exception("GOG getFilteredProducts failed: %s", exc)
            return []

        results: list[RawGame] = []
        for g in games_raw:
            client_id = str(g.get("id", ""))
            name = g.get("title", f"Game {client_id}")
            icon_url = f"https:{g.get('image', '')}_200.jpg" if g.get("image") else ""
            achievements = self._fetch_achievements(client_id, user_id)
            if achievements:
                results.append(
                    RawGame(
                        platform_game_id=client_id,
                        name=name,
                        icon_url=icon_url,
                        achievements=achievements,
                        total_achievements=len(achievements),
                    ),
                )
        return results

    def _fetch_achievements(self, client_id: str, user_id: str) -> list[RawAchievement]:
        url = f"{_GALAXY_BASE}/clients/{client_id}/users/{user_id}/achievements"
        try:
            resp = self._http.get(url, timeout=15)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            achievements_data: list[dict] = data.get("items", [])
        except requests.RequestException as exc:
            log.debug("GOG achievements for %s failed: %s", client_id, exc)
            return []

        results: list[RawAchievement] = []
        for ach in achievements_data:
            date_str = ach.get("date_unlocked", "") or ""
            unlock_date: datetime | None = None
            is_unlocked = bool(date_str)
            if date_str:
                with contextlib.suppress(ValueError):
                    unlock_date = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00"),
                    ).astimezone(timezone.utc).replace(tzinfo=None)

            results.append(
                RawAchievement(
                    achievement_id=ach.get("achievement_id", ""),
                    name=ach.get("name", ""),
                    description=ach.get("description", ""),
                    hidden=not ach.get("visible", True),
                    icon_url=ach.get("image_url_unlocked", ""),
                    icon_locked_url=ach.get("image_url_locked", ""),
                    global_percentage=None,  # GOG API does not expose global %
                    is_unlocked=is_unlocked,
                    unlock_date=unlock_date,
                ),
            )
        return results
