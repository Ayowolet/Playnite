"""Headless navigation state machine for UI traversal."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Set

logger = logging.getLogger(__name__)


class UIState(Enum):
    """All possible UI states."""

    MAIN_MENU = "main_menu"
    LIBRARY = "library"
    GAME_DETAIL = "game_detail"
    SEARCH = "search"
    SETTINGS = "settings"
    FULLSCREEN_MENU = "fullscreen_menu"
    GAME_RUNNING = "game_running"
    OVERLAY = "overlay"


# Valid state transitions: {from_state: {action: to_state}}
TRANSITIONS: Dict[UIState, Dict[str, UIState]] = {
    UIState.MAIN_MENU: {
        "select": UIState.LIBRARY,
        "settings": UIState.SETTINGS,
        "fullscreen": UIState.FULLSCREEN_MENU,
    },
    UIState.LIBRARY: {
        "select": UIState.GAME_DETAIL,
        "search": UIState.SEARCH,
        "back": UIState.MAIN_MENU,
        "menu": UIState.FULLSCREEN_MENU,
    },
    UIState.GAME_DETAIL: {
        "back": UIState.LIBRARY,
        "select": UIState.GAME_RUNNING,
        "menu": UIState.OVERLAY,
    },
    UIState.SEARCH: {
        "back": UIState.LIBRARY,
        "select": UIState.GAME_DETAIL,
    },
    UIState.SETTINGS: {
        "back": UIState.MAIN_MENU,
    },
    UIState.FULLSCREEN_MENU: {
        "back": UIState.MAIN_MENU,
        "library": UIState.LIBRARY,
        "settings": UIState.SETTINGS,
    },
    UIState.GAME_RUNNING: {
        "menu": UIState.OVERLAY,
    },
    UIState.OVERLAY: {
        "back": UIState.GAME_DETAIL,
        "quit_game": UIState.LIBRARY,
    },
}

# Cursor-movement actions that do not change state
NAVIGATION_ACTIONS: Set[str] = {"up", "down", "left", "right", "page_up", "page_down"}


@dataclass
class NavigationEvent:
    action: str
    from_state: str
    to_state: str


class NavigationStateMachine:
    """
    Completely headless state machine.  Can be driven by controller input,
    keyboard events, or test code without any display dependency.
    """

    def __init__(self, initial_state: UIState = UIState.MAIN_MENU):
        self._state = initial_state
        self._history: List[NavigationEvent] = []
        self._callbacks: List[Callable[[NavigationEvent], None]] = []
        self._lock = threading.Lock()
        self._cursor = {"row": 0, "col": 0}
        self._view_config: dict = {
            "fullscreen_mode": False,
            "grid_size": "medium",  # small | medium | large
            "layout": "grid",       # grid | list
            "items_per_row": 5,
        }

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> UIState:
        return self._state

    @property
    def state_name(self) -> str:
        return self._state.value

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, action: str) -> bool:
        """
        Process *action*.  Returns True if the state changed.
        """
        with self._lock:
            a = action.lower()

            if a in NAVIGATION_ACTIONS:
                self._move_cursor(a)
                return False

            next_state = TRANSITIONS.get(self._state, {}).get(a)
            if next_state is None:
                return False

            event = NavigationEvent(
                action=a, from_state=self._state.value, to_state=next_state.value
            )
            self._history.append(event)
            self._state = next_state
            self._cursor = {"row": 0, "col": 0}

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning("navigation callback %r raised: %s", cb, e)
        return True

    def _move_cursor(self, direction: str) -> None:
        if direction == "up":
            self._cursor["row"] = max(0, self._cursor["row"] - 1)
        elif direction == "down":
            self._cursor["row"] += 1
        elif direction == "left":
            self._cursor["col"] = max(0, self._cursor["col"] - 1)
        elif direction == "right":
            self._cursor["col"] += 1

    def can_navigate(self, action: str) -> bool:
        a = action.lower()
        return a in NAVIGATION_ACTIONS or a in TRANSITIONS.get(self._state, {})

    # ------------------------------------------------------------------
    # State callbacks
    # ------------------------------------------------------------------

    def on_state_change(self, callback: Callable[[NavigationEvent], None]) -> None:
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Full state snapshot — JSON-serialisable."""
        return {
            "current_state": self._state.value,
            "cursor_position": dict(self._cursor),
            "available_actions": sorted(
                list(TRANSITIONS.get(self._state, {}).keys()) + list(NAVIGATION_ACTIONS)
            ),
            "view_config": dict(self._view_config),
            "history_length": len(self._history),
        }

    def get_history(self) -> List[dict]:
        return [{"action": e.action, "from": e.from_state, "to": e.to_state} for e in self._history]

    # ------------------------------------------------------------------
    # View configuration
    # ------------------------------------------------------------------

    def set_view_config(self, **kwargs) -> None:
        """Update display/layout preferences (fullscreen, grid size, etc.)."""
        self._view_config.update(kwargs)

    def get_view_config(self) -> dict:
        return dict(self._view_config)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._state = UIState.MAIN_MENU
            self._history.clear()
            self._cursor = {"row": 0, "col": 0}
