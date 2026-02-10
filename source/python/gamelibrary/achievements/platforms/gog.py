"""GOG Galaxy achievement provider."""

from __future__ import annotations

import logging
import requests
from .base import PlatformProvider, PlatformGame, PlatformAchievement, AuthenticationError

logger = logging.getLogger(__name__)

GOG_API_BASE = "https://gameplay.gog.com"
GOG_EMBED_BASE = "https://embed.gog.com"


class GOGProvider(PlatformProvider):
    """GOG Galaxy achievement provider."""

    def __init__(self):
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.user_id: str = ""
        self.client_id: str = ""
        self.client_secret: str = ""

    @property
    def platform_name(self) -> str:
        return "GOG Galaxy"

    @property
    def api_type(self) -> str:
        return "gog"

    def configure(self, credentials: dict) -> None:
        self.access_token = credentials.get("access_token", "")
        self.refresh_token = credentials.get("refresh_token", "")
        self.user_id = credentials.get("user_id", "")
        self.client_id = credentials.get("client_id", "")
        self.client_secret = credentials.get("client_secret", "")

    def get_credentials(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "user_id": self.user_id,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

    def validate_credentials(self) -> bool:
        if not self.access_token:
            if self.refresh_token:
                return self._refresh_access_token()
            return False
        return self._test_token()

    def _refresh_access_token(self) -> bool:
        try:
            resp = requests.get(
                f"{GOG_EMBED_BASE}/token",
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get("access_token", "")
                self.refresh_token = data.get("refresh_token", self.refresh_token)
                self.user_id = str(data.get("user_id", self.user_id))
                return bool(self.access_token)
            return False
        except requests.RequestException:
            return False

    def _test_token(self) -> bool:
        try:
            resp = requests.get(
                f"{GOG_EMBED_BASE}/userData.json",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.user_id = str(data.get("userId", self.user_id))
                return True
            return False
        except requests.RequestException:
            return False

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _authed_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an authenticated request; retry once with token refresh on 401."""
        kwargs.setdefault("timeout", 15)
        kwargs.setdefault("headers", self._headers())
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401 and self.refresh_token:
            logger.info("GOG token expired, attempting refresh")
            if self._refresh_access_token():
                kwargs["headers"] = self._headers()
                resp = requests.request(method, url, **kwargs)
        return resp

    def get_games(self) -> list[PlatformGame]:
        try:
            resp = self._authed_request(
                "GET",
                f"{GOG_EMBED_BASE}/account/getFilteredProducts",
                params={"mediaType": 1, "sortBy": "title"},
                timeout=30,
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("GOG", f"HTTP {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            products = data.get("products", [])

            games = []
            for p in products:
                games.append(PlatformGame(
                    external_id=str(p.get("id", "")),
                    name=p.get("title", ""),
                    icon_url=p.get("image", ""),
                    total_achievements=0,
                ))
            return games
        except AuthenticationError:
            raise
        except requests.RequestException as e:
            logger.error("Failed to fetch GOG games: %s", e)
            return []

    def get_achievements(self, game_external_id: str) -> list[PlatformAchievement]:
        try:
            resp = self._authed_request(
                "GET",
                f"{GOG_API_BASE}/clients/{self.client_id}/users/{self.user_id}/achievements",
                params={"product_id": game_external_id},
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("GOG", f"HTTP {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            results = []
            for item in items:
                date_unlocked = item.get("date_unlocked")
                results.append(PlatformAchievement(
                    external_id=item.get("achievement_id", ""),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    icon_url=item.get("image_url_unlocked", ""),
                    locked_icon_url=item.get("image_url_locked", ""),
                    global_completion_pct=round(item.get("rarity", 50.0), 2),
                    is_hidden=bool(item.get("visible", True) is False),
                    unlocked=date_unlocked is not None,
                    unlock_time=date_unlocked,
                ))
            return results
        except AuthenticationError:
            raise
        except requests.RequestException as e:
            logger.error("Failed to fetch GOG achievements for %s: %s", game_external_id, e)
            return []
