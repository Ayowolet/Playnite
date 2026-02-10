"""Xbox Live achievement adapter via the OpenXBL API.

API documentation: https://xapi.us/docs
Requires an API key from https://xapi.us (free tier available).
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
    from playnite.config import XboxConfig

log = logging.getLogger(__name__)

_BASE = "https://xapi.us/v2"


class XboxAdapter(PlatformAdapter):
    """Fetch achievements from the OpenXBL API (Xbox Live proxy)."""

    platform_name = "xbox"

    def __init__(self, config: XboxConfig, session: requests.Session | None = None) -> None:
        self._cfg = config
        self._http = session or requests.Session()
        self._http.headers.update(
            {
                "X-Authorization": self._cfg.api_key,
                "Accept": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._cfg.api_key and self._cfg.xuid)

    def get_games_with_achievements(self) -> list[RawGame]:
        """Return all games with achievement data for the configured XUID."""
        titles = self._get_titles()
        results: list[RawGame] = []
        for title in titles:
            title_id = str(title.get("titleId", ""))
            title_name = title.get("name", f"Title {title_id}")
            icon_url = title.get("displayImage", "")
            achievements = self._get_achievements_for_title(title_id)
            if achievements:
                results.append(
                    RawGame(
                        platform_game_id=title_id,
                        name=title_name,
                        icon_url=icon_url,
                        achievements=achievements,
                        total_achievements=len(achievements),
                    ),
                )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_titles(self) -> list[dict]:
        """Retrieve the list of titles that have achievement history."""
        url = f"{_BASE}/{self._cfg.xuid}/achievements"
        try:
            resp = self._http.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # OpenXBL wraps in {"titles": [...]} or returns list directly
            if isinstance(data, list):
                return data
            return data.get("titles", data.get("achievements", []))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                log.error(
                    "Xbox: API key rejected (HTTP %d) — verify your OpenXBL API key.",
                    exc.response.status_code,
                )
            else:
                log.exception("Xbox get_titles failed: %s", exc)
            return []
        except requests.RequestException as exc:
            log.exception("Xbox get_titles failed: %s", exc)
            return []

    def _get_achievements_for_title(self, title_id: str) -> list[RawAchievement]:
        url = f"{_BASE}/{self._cfg.xuid}/achievements/{title_id}"
        try:
            resp = self._http.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            raw_list: list[dict] = data if isinstance(data, list) else data.get("achievements", [])
        except requests.RequestException as exc:
            log.debug("Xbox achievements for title %s failed: %s", title_id, exc)
            return []

        results: list[RawAchievement] = []
        for ach in raw_list:
            is_unlocked = ach.get("progressState", "") == "Achieved"
            unlock_date: datetime | None = None
            progression = ach.get("progression", {})
            ts_str = progression.get("timeUnlocked", "")
            if ts_str and ts_str != "0001-01-01T00:00:00Z":
                with contextlib.suppress(ValueError):
                    unlock_date = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00"),
                    ).astimezone(timezone.utc).replace(tzinfo=None)

            rewards = ach.get("rewards", [{}])
            gamerscore = rewards[0].get("value", 0) if rewards else 0

            results.append(
                RawAchievement(
                    achievement_id=str(ach.get("id", "")),
                    name=ach.get("name", ""),
                    description=ach.get("description", ""),
                    hidden=ach.get("isSecret", False),
                    icon_url=ach.get("mediaAssets", [{}])[0].get("url", "")
                    if ach.get("mediaAssets")
                    else "",
                    global_percentage=None,  # OpenXBL does not expose global %
                    is_unlocked=is_unlocked,
                    unlock_date=unlock_date,
                    # Map gamerscore to a comparable numeric progress field
                    current_value=float(gamerscore) if is_unlocked else 0.0,
                    max_value=float(gamerscore),
                ),
            )
        return results
