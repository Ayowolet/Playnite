"""Achievement unlock notifications."""

from __future__ import annotations

import json
import logging

from ..database import Database

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages achievement notifications."""

    def __init__(self, db: Database):
        self.db = db

    def notify_new_unlocks(self, platform_name: str, count: int):
        """Record notification for new achievement unlocks detected during sync."""
        self.db.execute_insert(
            """INSERT INTO notifications (notification_type, title, message, metadata)
               VALUES (?, ?, ?, ?)""",
            (
                "new_unlocks",
                f"New Achievements Unlocked ({platform_name})",
                f"{count} new achievement(s) detected on {platform_name}.",
                json.dumps({"platform": platform_name, "count": count}),
            ),
        )
        logger.info("Notification: %d new unlock(s) on %s", count, platform_name)

    def notify_milestone(self, milestone_type: str, value: str):
        self.db.execute_insert(
            """INSERT INTO notifications (notification_type, title, message, metadata)
               VALUES (?, ?, ?, ?)""",
            (
                "milestone",
                f"Milestone Reached: {milestone_type}",
                f"You've reached {value} - congratulations!",
                json.dumps({"type": milestone_type, "value": value}),
            ),
        )

    def notify_rare_unlock(self, achievement_name: str, game_name: str, pct: float):
        self.db.execute_insert(
            """INSERT INTO notifications (notification_type, title, message, metadata)
               VALUES (?, ?, ?, ?)""",
            (
                "rare_unlock",
                "Rare Achievement Unlocked!",
                f"'{achievement_name}' in {game_name} (only {pct}% of players have this).",
                json.dumps({"achievement": achievement_name, "game": game_name, "pct": pct}),
            ),
        )

    def get_unread(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    def get_all(self, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def mark_read(self, notification_id: int):
        self.db.execute(
            "UPDATE notifications SET read = 1 WHERE id = ?",
            (notification_id,),
        )

    def notify_auth_failure(self, platform_name: str):
        """Record notification for authentication failure during sync."""
        self.db.execute_insert(
            """INSERT INTO notifications (notification_type, title, message, metadata)
               VALUES (?, ?, ?, ?)""",
            (
                "auth_failure",
                f"Authentication Failed ({platform_name})",
                f"Unable to sync {platform_name}: credentials may have expired. Please re-authenticate.",
                json.dumps({"platform": platform_name}),
            ),
        )
        logger.warning("Auth failure notification for %s", platform_name)

    def mark_all_read(self):
        self.db.execute("UPDATE notifications SET read = 1 WHERE read = 0")
