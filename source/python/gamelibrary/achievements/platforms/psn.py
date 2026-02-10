"""PlayStation Network achievement (trophy) provider."""

from __future__ import annotations

import logging
import requests
from .base import PlatformProvider, PlatformGame, PlatformAchievement, AuthenticationError

logger = logging.getLogger(__name__)

PSN_API_BASE = "https://m.np.playstation.com/api/trophy/v1"

TROPHY_GRADE_PCT = {
    "bronze": 30.0,
    "silver": 15.0,
    "gold": 5.0,
    "platinum": 1.0,
}


class PSNProvider(PlatformProvider):
    """PlayStation Network trophy provider."""

    def __init__(self):
        self.npsso: str = ""
        self.access_token: str = ""
        self.account_id: str = "me"

    @property
    def platform_name(self) -> str:
        return "PlayStation Network"

    @property
    def api_type(self) -> str:
        return "psn"

    def configure(self, credentials: dict) -> None:
        self.npsso = credentials.get("npsso", "")
        self.access_token = credentials.get("access_token", "")
        self.account_id = credentials.get("account_id", "me")

    def get_credentials(self) -> dict:
        return {
            "npsso": self.npsso,
            "access_token": self.access_token,
            "account_id": self.account_id,
        }

    def validate_credentials(self) -> bool:
        if not self.access_token and not self.npsso:
            return False
        if not self.access_token and self.npsso:
            return self._authenticate()
        return self._test_token()

    def _authenticate(self) -> bool:
        try:
            resp = requests.post(
                "https://ca.account.sony.com/api/authz/v3/oauth/token",
                data={
                    "token_format": "jwt",
                    "grant_type": "sso_cookie",
                    "scope": "psn:mobile.v2.core psn:clientapp",
                },
                headers={
                    "Cookie": f"npsso={self.npsso}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                self.access_token = resp.json().get("access_token", "")
                return bool(self.access_token)
            return False
        except requests.RequestException:
            return False

    def _test_token(self) -> bool:
        try:
            resp = requests.get(
                f"{PSN_API_BASE}/users/{self.account_id}/trophyTitles",
                headers=self._headers(),
                params={"limit": 1},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def _authed_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an authenticated request; retry once with re-authentication on 401."""
        kwargs.setdefault("timeout", 15)
        kwargs.setdefault("headers", self._headers())
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401 and self.npsso:
            logger.info("PSN token expired, attempting re-authentication")
            if self._authenticate():
                kwargs["headers"] = self._headers()
                resp = requests.request(method, url, **kwargs)
        return resp

    def get_games(self) -> list[PlatformGame]:
        try:
            games = []
            offset = 0
            limit = 100
            while True:
                resp = self._authed_request(
                    "GET",
                    f"{PSN_API_BASE}/users/{self.account_id}/trophyTitles",
                    params={"limit": limit, "offset": offset},
                    timeout=30,
                )
                if resp.status_code in (401, 403):
                    raise AuthenticationError("PlayStation Network", f"HTTP {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                titles = data.get("trophyTitles", [])
                if not titles:
                    break
                for title in titles:
                    counts = title.get("definedTrophies", {})
                    total = sum(counts.get(k, 0) for k in ("bronze", "silver", "gold", "platinum"))
                    games.append(PlatformGame(
                        external_id=title.get("npCommunicationId", ""),
                        name=title.get("trophyTitleName", ""),
                        icon_url=title.get("trophyTitleIconUrl", ""),
                        total_achievements=total,
                    ))
                if len(titles) < limit:
                    break
                offset += limit
            return games
        except AuthenticationError:
            raise
        except requests.RequestException as e:
            logger.error("Failed to fetch PSN games: %s", e)
            return []

    def get_achievements(self, game_external_id: str) -> list[PlatformAchievement]:
        schema = self._get_trophy_schema(game_external_id)
        player_trophies = self._get_player_trophies(game_external_id)

        player_map = {}
        for t in player_trophies:
            player_map[t.get("trophyId")] = t

        results = []
        for trophy in schema:
            trophy_id = trophy.get("trophyId")
            player_data = player_map.get(trophy_id, {})
            grade = trophy.get("trophyType", "bronze").lower()
            est_pct = TROPHY_GRADE_PCT.get(grade, 50.0)
            rarity = player_data.get("trophyRare", 0)
            global_pct = est_pct
            if rarity == 1:
                global_pct = min(est_pct, 5.0)
            elif rarity == 2:
                global_pct = min(est_pct, 15.0)
            elif rarity == 3:
                global_pct = min(est_pct, 50.0)

            earned = player_data.get("earned", False)
            earned_time = player_data.get("earnedDateTime", None)

            results.append(PlatformAchievement(
                external_id=str(trophy_id),
                name=trophy.get("trophyName", ""),
                description=trophy.get("trophyDetail", ""),
                icon_url=trophy.get("trophyIconUrl", ""),
                global_completion_pct=round(global_pct, 2),
                is_hidden=bool(trophy.get("trophyHidden", False)),
                unlocked=bool(earned),
                unlock_time=earned_time,
            ))
        return results

    def _get_trophy_schema(self, comm_id: str) -> list[dict]:
        try:
            resp = self._authed_request(
                "GET",
                f"{PSN_API_BASE}/npCommunicationIds/{comm_id}/trophyGroups/all/trophies",
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("PlayStation Network", f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json().get("trophies", [])
        except AuthenticationError:
            raise
        except requests.RequestException:
            return []

    def _get_player_trophies(self, comm_id: str) -> list[dict]:
        try:
            resp = self._authed_request(
                "GET",
                f"{PSN_API_BASE}/users/{self.account_id}/npCommunicationIds/{comm_id}/trophyGroups/all/trophies",
            )
            if resp.status_code in (401, 403):
                raise AuthenticationError("PlayStation Network", f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json().get("trophies", [])
        except AuthenticationError:
            raise
        except requests.RequestException:
            return []
