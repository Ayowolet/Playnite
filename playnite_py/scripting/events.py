"""Typed event argument classes for script lifecycle hooks.

Mirrors Playnite's OnGameStartingEventArgs, OnGameStartedEventArgs, etc.
providing structured data instead of flat **kwargs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventArgs:
    """Base class for all event arguments."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class GameEventArgs(EventArgs):
    """Base for events that involve a game."""
    game_id: str = ""
    game: dict[str, Any] = field(default_factory=dict)


@dataclass
class OnGameStartingEventArgs(GameEventArgs):
    """Fired before a game launches. Supports cancellation.

    Set ``cancel_startup = True`` in the handler to abort the launch.
    ``source_action`` contains the action dict that will be executed.
    """
    source_action: dict[str, Any] = field(default_factory=dict)
    cancel_startup: bool = False


@dataclass
class OnGameStartedEventArgs(GameEventArgs):
    """Fired after the game process has started."""
    source_action: dict[str, Any] = field(default_factory=dict)
    process_id: int | None = None


@dataclass
class OnGameStoppedEventArgs(GameEventArgs):
    """Fired when a game process exits."""
    session_length: int = 0  # seconds
    exit_code: int | None = None


@dataclass
class OnGameInstalledEventArgs(GameEventArgs):
    """Fired when a game is installed."""


@dataclass
class OnGameUninstalledEventArgs(GameEventArgs):
    """Fired when a game is uninstalled."""


@dataclass
class OnGameSelectedEventArgs(GameEventArgs):
    """Fired when a game is selected in the UI."""
    old_game_id: str = ""


@dataclass
class OnGameStartupCancelledEventArgs(GameEventArgs):
    """Fired when a game startup is cancelled (via ``cancel_startup``)."""
    cancelled_by: str = ""  # script_id that cancelled


@dataclass
class OnGameInstallationCancelledEventArgs(GameEventArgs):
    """Fired when a game installation is cancelled."""


@dataclass
class OnLibraryUpdatedEventArgs(EventArgs):
    """Fired when the game library is updated."""
    added_game_ids: list[str] = field(default_factory=list)
    removed_game_ids: list[str] = field(default_factory=list)
    updated_game_ids: list[str] = field(default_factory=list)


@dataclass
class OnApplicationStartedEventArgs(EventArgs):
    """Fired when the application starts."""
    app_version: str = ""


@dataclass
class OnApplicationStoppedEventArgs(EventArgs):
    """Fired when the application is shutting down."""


# All supported lifecycle hook names
LIFECYCLE_HOOKS = [
    "on_loaded",
    "on_application_started",
    "on_application_stopped",
    "on_library_updated",
    "on_game_starting",             # cancellable pre-launch
    "on_game_started",
    "on_game_stopped",
    "on_game_installed",
    "on_game_uninstalled",
    "on_game_selected",
    "on_game_startup_cancelled",
    "on_game_installation_cancelled",
]


# Map hook names to their event args classes for easy construction
HOOK_EVENT_ARGS_MAP: dict[str, type[EventArgs]] = {
    "on_game_starting": OnGameStartingEventArgs,
    "on_game_started": OnGameStartedEventArgs,
    "on_game_stopped": OnGameStoppedEventArgs,
    "on_game_installed": OnGameInstalledEventArgs,
    "on_game_uninstalled": OnGameUninstalledEventArgs,
    "on_game_selected": OnGameSelectedEventArgs,
    "on_game_startup_cancelled": OnGameStartupCancelledEventArgs,
    "on_game_installation_cancelled": OnGameInstallationCancelledEventArgs,
    "on_library_updated": OnLibraryUpdatedEventArgs,
    "on_application_started": OnApplicationStartedEventArgs,
    "on_application_stopped": OnApplicationStoppedEventArgs,
}
