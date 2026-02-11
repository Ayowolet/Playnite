"""
Plugin base class.

All Playnite Python plugins inherit from :class:`Plugin`.  The abstract
properties :attr:`plugin_id` and :attr:`name` must be implemented;
everything else has sensible defaults.

Example
-------
::

    class MyPlugin(Plugin):
        @property
        def plugin_id(self) -> str:
            return "com.example.myplugin"

        @property
        def name(self) -> str:
            return "My Plugin"

        def on_game_started(self, game):
            self._api.notifications.show(f"Started: {game.name}")
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.game import Game
    from ..extensions.sdk import PlayniteSDK


# ---------------------------------------------------------------------------
# Data objects for menu registration
# ---------------------------------------------------------------------------

@dataclass
class PluginProperties:
    """Capabilities and metadata for a plugin."""
    has_settings: bool = False


@dataclass
class MainMenuItem:
    """A custom item in the application's main menu bar."""
    description: str
    action: Callable[[], None]
    menu_section: str = ""
    icon_resource_path: str = ""


@dataclass
class GetMainMenuItemsArgs:
    """Arguments passed to :meth:`Plugin.get_main_menu_items`."""
    # Reserved for future use (e.g. current selection context)


@dataclass
class GameMenuItem:
    """A custom item in the game context menu."""
    description: str
    action: Callable[[List["Game"]], None]
    menu_section: str = ""
    icon_resource_path: str = ""


@dataclass
class GetGameMenuItemsArgs:
    """Arguments passed to :meth:`Plugin.get_game_menu_items`."""
    games: List["Game"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract Plugin base
# ---------------------------------------------------------------------------

class Plugin(ABC):
    """
    Abstract base class for all Playnite Python plugins.

    Subclass this and implement at minimum :attr:`plugin_id` and :attr:`name`.
    Override lifecycle hooks and menu-item methods as needed.

    Parameters
    ----------
    api:
        The :class:`~extensions.sdk.PlayniteSDK` instance for this plugin.
    """

    def __init__(self, api: "PlayniteSDK") -> None:
        self._api = api

    # ------------------------------------------------------------------
    # Abstract identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Globally unique identifier for this plugin (e.g. ``"com.example.plugin"``)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name shown in the plugins list."""
        ...

    @property
    def properties(self) -> PluginProperties:
        """Optional capability flags for this plugin."""
        return PluginProperties()

    # ------------------------------------------------------------------
    # Lifecycle hooks — all default to no-op
    # ------------------------------------------------------------------

    def on_application_started(self) -> None:
        """Called when the application has fully started."""

    def on_application_stopped(self) -> None:
        """Called when the application is shutting down."""

    def on_library_updated(self) -> None:
        """Called after the game library has been refreshed."""

    def on_game_starting(self, game: "Game") -> None:
        """Called just before a game process is launched."""

    def on_game_started(self, game: "Game") -> None:
        """Called once a game process is confirmed running."""

    def on_game_stopped(self, game: "Game", elapsed_seconds: float) -> None:
        """Called when a game process exits."""

    def on_game_installed(self, game: "Game") -> None:
        """Called after a game has been installed."""

    def on_game_uninstalled(self, game: "Game") -> None:
        """Called after a game has been uninstalled."""

    def on_game_startup_cancelled(self, game: "Game") -> None:
        """Called when a game startup was cancelled before the process launched."""

    def on_game_installation_cancelled(self, game: "Game") -> None:
        """Called when a game installation was cancelled."""

    def on_game_selected(self, game: Optional["Game"]) -> None:
        """Called when the selected game in the UI changes (*None* = deselected)."""

    def on_settings_changed(self) -> None:
        """Called when application settings have been modified."""

    # ------------------------------------------------------------------
    # Menu items — return empty lists by default
    # ------------------------------------------------------------------

    def get_game_menu_items(self, args: GetGameMenuItemsArgs) -> List[GameMenuItem]:
        """Return custom items for the game context menu."""
        return []

    def get_main_menu_items(self, args: GetMainMenuItemsArgs) -> List[MainMenuItem]:
        """Return custom items for the application main menu."""
        return []

    # ------------------------------------------------------------------
    # Action providers — empty by default
    # ------------------------------------------------------------------

    def get_play_actions(self, game: "Game") -> List[Dict[str, Any]]:
        """Return custom play actions for *game* (overrides library defaults)."""
        return []

    def get_install_actions(self, game: "Game") -> List[Dict[str, Any]]:
        """Return custom install actions for *game*."""
        return []

    def get_uninstall_actions(self, game: "Game") -> List[Dict[str, Any]]:
        """Return custom uninstall actions for *game*."""
        return []

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> Optional[Dict[str, Any]]:
        """Return the current settings dict, or *None* if not implemented."""
        return None

    def load_plugin_settings(self) -> Optional[Dict[str, Any]]:
        """
        Load settings from the plugin's data directory.

        Returns *None* if no settings file exists yet.
        """
        path = Path(self.get_plugin_user_data_path()) / "settings.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def save_plugin_settings(self, settings: Dict[str, Any]) -> None:
        """Persist *settings* to the plugin's data directory."""
        path = Path(self.get_plugin_user_data_path()) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def get_plugin_user_data_path(self) -> str:
        """Return the writable data directory for this plugin."""
        return str(Path(self._api.paths.extension_data_path) / self.plugin_id)
