"""Event-based triggers: execute actions based on system and library events."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from playnite_py.utils import BoundedList

logger = logging.getLogger(__name__)


class EventType:
    """Known event types that can trigger actions."""
    GAME_ADDED = "game_added"
    GAME_REMOVED = "game_removed"
    GAME_UPDATED = "game_updated"
    GAME_STARTED = "game_started"
    GAME_STOPPED = "game_stopped"
    GAME_INSTALLED = "game_installed"
    GAME_UNINSTALLED = "game_uninstalled"
    LIBRARY_UPDATED = "library_updated"
    APP_STARTED = "app_started"
    APP_STOPPED = "app_stopped"
    TIMER = "timer"
    CUSTOM = "custom"


@dataclass
class EventTrigger:
    """A trigger that fires an action when a specific event occurs."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    event_type: str = ""
    action_id: str = ""
    game_id: str | None = None  # None = any game
    enabled: bool = True
    # Optional filter: only trigger if event data matches
    filters: dict[str, str] = field(default_factory=dict)
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "event_type": self.event_type,
            "action_id": self.action_id,
            "game_id": self.game_id,
            "enabled": self.enabled,
            "filters": dict(self.filters),
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventTrigger:
        """Deserialize from a dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TriggerManager:
    """Manages event triggers and dispatches actions when events occur."""

    def __init__(
        self,
        action_callback: Callable[[str, str | None, dict[str, Any]], None] | None = None,
        max_history: int = 1000,
    ):
        """
        Args:
            action_callback: Called with (action_id, game_id, event_data) when trigger fires.
        """
        self._triggers: dict[str, EventTrigger] = {}
        self._lock = threading.Lock()
        self._action_callback = action_callback
        self._history: BoundedList[dict[str, Any]] = BoundedList(max_history)

    def add_trigger(self, trigger: EventTrigger) -> str:
        """Register a new event trigger and return its ID."""
        with self._lock:
            self._triggers[trigger.id] = trigger
        return trigger.id

    def remove_trigger(self, trigger_id: str) -> bool:
        """Remove a trigger by ID and return whether it existed."""
        with self._lock:
            return self._triggers.pop(trigger_id, None) is not None

    def get_triggers(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """Return all triggers, optionally filtered by event type."""
        with self._lock:
            triggers = list(self._triggers.values())
        if event_type:
            triggers = [t for t in triggers if t.event_type == event_type]
        return [t.to_dict() for t in triggers]

    def fire_event(
        self,
        event_type: str,
        game_id: str | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> list[str]:
        """Fire an event and execute any matching triggers.

        Returns list of trigger IDs that fired.
        """
        event_data = event_data or {}
        fired: list[str] = []

        with self._lock:
            triggers = list(self._triggers.values())

        for trigger in triggers:
            if not trigger.enabled:
                continue
            if trigger.event_type != event_type:
                continue
            if trigger.game_id and trigger.game_id != game_id:
                continue
            if not self._check_filters(trigger.filters, event_data):
                continue

            fired.append(trigger.id)
            self._history.append({
                "trigger_id": trigger.id,
                "event_type": event_type,
                "game_id": game_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if self._action_callback:
                try:
                    self._action_callback(trigger.action_id, game_id, event_data)
                except Exception as e:
                    logger.error(
                        "Trigger %s action failed: %s", trigger.id, e
                    )

        return fired

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent trigger fire history up to the specified limit."""
        return self._history[-limit:]

    @staticmethod
    def _check_filters(
        filters: dict[str, str], event_data: dict[str, Any]
    ) -> bool:
        """Check if event data matches all trigger filters."""
        for key, expected in filters.items():
            actual = str(event_data.get(key, ""))
            if actual.lower() != expected.lower():
                return False
        return True
