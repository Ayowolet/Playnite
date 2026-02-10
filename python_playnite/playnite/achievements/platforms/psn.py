"""PlayStation Network (PSN) trophy adapter.

Uses the unofficial PSN API endpoints. Requires an NPSSO token which can
be obtained by:
  1. Logging in at https://www.playstation.com
  2. Visiting https://ca.account.sony.com/api/v1/ssocookie
  3. Copying the value of the "npsso" field from the JSON response.

PSN trophy types: bronze, silver, gold, platinum
Difficulty mapping: bronze=0.25, silver=0.50, gold=0.75, platinum=1.0
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
    from playnite.config import PSNConfig

log = logging.getLogger(__name__)

_AUTH_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
_TROPHY_BASE = "https://m.np.playstation.com/api/trophy/v1"
_TROPHY_TYPE_WEIGHT = {"bronze": 0.25, "silver": 0.50, "gold": 0.75, "platinum": 1.0}


class PSNAdapter(PlatformAdapter):
    """Fetch PlayStation trophies via the unofficial PSN API."""

    platform_name = "psn"

    def __init__(self, config: PSNConfig, session: requests.Session | None = None) -> None:
        self._cfg = config
        self._http = session or requests.Session()
        self._access_token: str | None = None

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._cfg.npsso_token)

    def get_games_with_achievements(self) -> list[RawGame]:
        if not self._authenticate():
            log.error("PSN authentication failed; skipping sync")
            return []
        return self._fetch_all_titles()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> bool:
        """Exchange NPSSO token for an OAuth access token."""
        try:
            # Step 1: get auth code
            auth_resp = self._http.get(
                "https://ca.account.sony.com/api/authz/v3/oauth/authorize",
                params={
                    "access_type": "offline",
                    "client_id": "09515159-7237-4370-9b40-3806e67c0891",
                    "redirect_uri": "com.scee.psxandroid.scecompcall://redirect",
                    "response_type": "code",
                    "scope": "psn:mobile.v2.core psn:clientapp",
                },
                headers={"Cookie": f"npsso={self._cfg.npsso_token}"},
                allow_redirects=False,
                timeout=10,
            )
            location = auth_resp.headers.get("Location", "")
            code = ""
            for part in location.split("?", 1)[-1].split("&"):
                if part.startswith("code="):
                    code = part[5:]
                    break
            if not code:
                log.error("PSN: could not extract auth code from redirect")
                return False

            # Step 2: exchange code for access token
            token_resp = self._http.post(
                _AUTH_URL,
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": "com.scee.psxandroid.scecompcall://redirect",
                    "token_format": "jwt",
                },
                auth=("09515159-7237-4370-9b40-3806e67c0891", "ucIZGBFNVOBBGVBaQiDnS"),
                timeout=10,
            )
            token_resp.raise_for_status()
            self._access_token = token_resp.json().get("access_token")
            self._http.headers["Authorization"] = f"Bearer {self._access_token}"
            return bool(self._access_token)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                log.error(
                    "PSN: NPSSO token rejected (HTTP %d) — obtain a fresh npsso token from playstation.com.",
                    exc.response.status_code,
                )
            else:
                log.exception("PSN authentication error: %s", exc)
            return False
        except requests.RequestException as exc:
            log.exception("PSN authentication error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Trophy fetching
    # ------------------------------------------------------------------

    def _fetch_all_titles(self) -> list[RawGame]:
        """Return all trophy titles with earned trophies."""
        titles: list[dict] = []
        url = f"{_TROPHY_BASE}/users/me/trophyTitles"
        while url:
            try:
                resp = self._http.get(url, params={"limit": 200}, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                titles.extend(data.get("trophyTitles", []))
                next_offset = data.get("nextOffset")
                url = (
                    f"{_TROPHY_BASE}/users/me/trophyTitles?offset={next_offset}"
                    if next_offset
                    else ""
                )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in (401, 403):
                    log.error(
                        "PSN: access token rejected (HTTP %d) — re-authenticate.",
                        exc.response.status_code,
                    )
                else:
                    log.exception("PSN trophyTitles error: %s", exc)
                break
            except requests.RequestException as exc:
                log.exception("PSN trophyTitles error: %s", exc)
                break

        results: list[RawGame] = []
        for title in titles:
            comm_id = title.get("npCommunicationId", "")
            name = title.get("trophyTitleName", f"Game {comm_id}")
            icon_url = title.get("trophyTitleIconUrl", "")
            achievements = self._get_trophies_for_title(comm_id)
            if achievements:
                results.append(
                    RawGame(
                        platform_game_id=comm_id,
                        name=name,
                        icon_url=icon_url,
                        achievements=achievements,
                        total_achievements=len(achievements),
                    ),
                )
        return results

    def _get_trophies_for_title(self, np_comm_id: str) -> list[RawAchievement]:
        """Fetch individual trophies plus earned status."""
        trophy_url = (
            f"{_TROPHY_BASE}/npCommunicationIds/{np_comm_id}/trophyGroups/all/trophies"
        )
        earned_url = (
            f"{_TROPHY_BASE}/users/me/npCommunicationIds/{np_comm_id}"
            f"/trophyGroups/all/trophies"
        )
        try:
            t_resp = self._http.get(trophy_url, params={"npServiceName": "trophy2"}, timeout=15)
            e_resp = self._http.get(earned_url, params={"npServiceName": "trophy2"}, timeout=15)
            t_resp.raise_for_status()
            e_resp.raise_for_status()
            trophy_defs = {
                t["trophyId"]: t for t in t_resp.json().get("trophies", [])
            }
            earned_map = {
                t["trophyId"]: t for t in e_resp.json().get("trophies", [])
            }
        except requests.RequestException as exc:
            log.debug("PSN trophies for %s failed: %s", np_comm_id, exc)
            return []

        results: list[RawAchievement] = []
        for tid, defn in trophy_defs.items():
            earned = earned_map.get(tid, {})
            is_unlocked = earned.get("earned", False)
            unlock_date: datetime | None = None
            ts_str = earned.get("earnedDateTime", "")
            if ts_str:
                with contextlib.suppress(ValueError):
                    unlock_date = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00"),
                    ).astimezone(timezone.utc).replace(tzinfo=None)

            trophy_type = defn.get("trophyType", "bronze")
            # Map earned rate to global_percentage (platform provides it per-trophy)
            rate_str = earned.get("trophyEarnedRate", defn.get("trophyEarnedRate", ""))
            global_pct: float | None = None
            with contextlib.suppress(ValueError):
                global_pct = float(rate_str) if rate_str else None

            weight = _TROPHY_TYPE_WEIGHT.get(trophy_type, 0.25)
            results.append(
                RawAchievement(
                    achievement_id=str(tid),
                    name=defn.get("trophyName", f"Trophy {tid}"),
                    description=defn.get("trophyDetail", ""),
                    hidden=defn.get("trophyHidden", False),
                    icon_url=defn.get("trophyIconUrl", ""),
                    global_percentage=global_pct,
                    is_unlocked=is_unlocked,
                    unlock_date=unlock_date,
                    # Use trophy weight as a numeric progress analog
                    current_value=weight if is_unlocked else 0.0,
                    max_value=weight,
                ),
            )
        return results
