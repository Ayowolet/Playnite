"""
Plugin manager — loads, registers, and dispatches lifecycle events to plugins.

Usage
-----
::

    from playnite_python.plugins.manager import PluginManager
    from playnite_python.extensions.lifecycle import LifecycleDispatcher

    lifecycle = LifecycleDispatcher()
    plugin_mgr = PluginManager(lifecycle)
    plugin_mgr.register_plugin(MyPlugin(api))

    # Hooks now fire automatically through the lifecycle dispatcher
    lifecycle.on_game_started(game)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from .base import (
    Plugin,
    GetMainMenuItemsArgs,
    GetGameMenuItemsArgs,
    MainMenuItem,
    GameMenuItem,
)

if TYPE_CHECKING:
    from ..extensions.lifecycle import LifecycleDispatcher
    from ..extensions.sdk import PlayniteSDK
    from ..models.game import Game


class PluginManager:
    """
    Manages plugin instances and wires their lifecycle methods into the
    :class:`~extensions.lifecycle.LifecycleDispatcher`.

    Parameters
    ----------
    lifecycle:
        The shared :class:`~extensions.lifecycle.LifecycleDispatcher` that
        drives all lifecycle events.
    """

    def __init__(self, lifecycle: "LifecycleDispatcher") -> None:
        self._lifecycle = lifecycle
        self._plugins: Dict[str, Plugin] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_plugin(self, plugin: Plugin) -> None:
        """
        Register *plugin* and wire all its lifecycle hooks into the dispatcher.

        If a plugin with the same :attr:`~Plugin.plugin_id` is already
        registered, it is replaced.
        """
        self._plugins[plugin.plugin_id] = plugin
        self._wire_plugin_hooks(plugin)

    def unregister_plugin(self, plugin_id: str) -> None:
        """
        Unregister and disconnect a plugin by its ID.

        Raises
        ------
        KeyError
            If no plugin with *plugin_id* is registered.
        """
        if plugin_id not in self._plugins:
            raise KeyError(f"Plugin '{plugin_id}' is not registered.")
        self._lifecycle.unregister_script(f"plugin:{plugin_id}")
        del self._plugins[plugin_id]

    def _wire_plugin_hooks(self, plugin: Plugin) -> None:
        """Register all lifecycle methods of *plugin* with the dispatcher."""
        tag = f"plugin:{plugin.plugin_id}"
        hook_map = {
            "on_application_started": lambda: plugin.on_application_started(),
            "on_application_stopped": lambda: plugin.on_application_stopped(),
            "on_library_updated": lambda: plugin.on_library_updated(),
            "on_game_starting": lambda game: plugin.on_game_starting(game),
            "on_game_started": lambda game: plugin.on_game_started(game),
            "on_game_stopped": lambda game, sec: plugin.on_game_stopped(game, sec),
            "on_game_installed": lambda game: plugin.on_game_installed(game),
            "on_game_uninstalled": lambda game: plugin.on_game_uninstalled(game),
            "on_game_startup_cancelled": lambda game: plugin.on_game_startup_cancelled(game),
            "on_game_installation_cancelled": lambda game: plugin.on_game_installation_cancelled(game),
            "on_game_selected": lambda game: plugin.on_game_selected(game),
            "on_settings_changed": lambda: plugin.on_settings_changed(),
        }
        for hook, cb in hook_map.items():
            try:
                self._lifecycle.register(hook, cb, tag)
            except ValueError:
                pass  # hook not in ALL_HOOKS (forward-compat guard)

    # ------------------------------------------------------------------
    # Dynamic loading from file
    # ------------------------------------------------------------------

    def load_plugin_from_file(self, path: str, api: "PlayniteSDK") -> Plugin:
        """
        Dynamically load the first :class:`Plugin` subclass found in a ``.py``
        file, instantiate it with *api*, and register it.

        Parameters
        ----------
        path:
            Absolute or relative path to a Python source file.
        api:
            The :class:`~extensions.sdk.PlayniteSDK` instance to pass to the
            plugin's constructor.

        Returns
        -------
        Plugin
            The loaded and registered plugin instance.

        Raises
        ------
        ValueError
            If no :class:`Plugin` subclass is found in the module.
        """
        p = Path(path)
        spec = importlib.util.spec_from_file_location(p.stem, str(p))
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load module spec from '{path}'.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
            ):
                instance = obj(api)
                self.register_plugin(instance)
                return instance

        raise ValueError(f"No Plugin subclass found in '{path}'.")

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_plugins(self) -> List[Plugin]:
        """Return all registered plugin instances."""
        return list(self._plugins.values())

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """Return the plugin with *plugin_id*, or *None* if not registered."""
        return self._plugins.get(plugin_id)

    # ------------------------------------------------------------------
    # Aggregated menu items
    # ------------------------------------------------------------------

    def get_all_main_menu_items(self) -> List[MainMenuItem]:
        """Collect main-menu items from every registered plugin."""
        args = GetMainMenuItemsArgs()
        return [
            item
            for plugin in self._plugins.values()
            for item in plugin.get_main_menu_items(args)
        ]

    def get_all_game_menu_items(self, games: List["Game"]) -> List[GameMenuItem]:
        """Collect game context-menu items from every registered plugin."""
        args = GetGameMenuItemsArgs(games=games)
        return [
            item
            for plugin in self._plugins.values()
            for item in plugin.get_game_menu_items(args)
        ]
