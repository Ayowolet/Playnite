"""
Lifecycle event dispatcher.

The :class:`LifecycleDispatcher` broadcasts application and game lifecycle
events to all registered script handlers.

Lifecycle hooks
---------------
Application level
~~~~~~~~~~~~~~~~~
* ``on_application_started()``
* ``on_application_stopped()``
* ``on_library_updated()``
* ``on_script_loaded(script_name)``
* ``on_script_unloaded(script_name)``

Game level
~~~~~~~~~~
* ``on_game_starting(game)``
* ``on_game_started(game)``
* ``on_game_stopped(game, elapsed_seconds)``
* ``on_game_installed(game)``
* ``on_game_uninstalled(game)``
* ``on_game_startup_cancelled(game)``
* ``on_game_installation_cancelled(game)``
* ``on_game_selected(game)``
* ``on_settings_changed()``

A script opts into a hook simply by defining a function with the matching
name at module level.  Scripts are not required to define all (or any) hooks.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.game import Game
    from .logger import ScriptLogger

# ---------------------------------------------------------------------------
# Hook names — the exact function names scripts must define
# ---------------------------------------------------------------------------

HOOK_APPLICATION_STARTED = "on_application_started"
HOOK_APPLICATION_STOPPED = "on_application_stopped"
HOOK_LIBRARY_UPDATED = "on_library_updated"
HOOK_SCRIPT_LOADED = "on_script_loaded"
HOOK_SCRIPT_UNLOADED = "on_script_unloaded"
HOOK_GAME_STARTING = "on_game_starting"
HOOK_GAME_STARTED = "on_game_started"
HOOK_GAME_STOPPED = "on_game_stopped"
HOOK_GAME_INSTALLED = "on_game_installed"
HOOK_GAME_UNINSTALLED = "on_game_uninstalled"
HOOK_GAME_STARTUP_CANCELLED = "on_game_startup_cancelled"
HOOK_GAME_INSTALLATION_CANCELLED = "on_game_installation_cancelled"
HOOK_GAME_SELECTED = "on_game_selected"
HOOK_SETTINGS_CHANGED = "on_settings_changed"

ALL_HOOKS: List[str] = [
    HOOK_APPLICATION_STARTED,
    HOOK_APPLICATION_STOPPED,
    HOOK_LIBRARY_UPDATED,
    HOOK_SCRIPT_LOADED,
    HOOK_SCRIPT_UNLOADED,
    HOOK_GAME_STARTING,
    HOOK_GAME_STARTED,
    HOOK_GAME_STOPPED,
    HOOK_GAME_INSTALLED,
    HOOK_GAME_UNINSTALLED,
    HOOK_GAME_STARTUP_CANCELLED,
    HOOK_GAME_INSTALLATION_CANCELLED,
    HOOK_GAME_SELECTED,
    HOOK_SETTINGS_CHANGED,
]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class LifecycleDispatcher:
    """
    Collects callables registered by scripts and fires them on demand.

    Thread-safety
    ~~~~~~~~~~~~~
    All handler mutations are protected by a :class:`threading.RLock` so that
    hot-reload (which removes and re-adds handlers) is safe from any thread.
    Dispatch calls grab a snapshot of handlers before iteration, meaning
    additions during dispatch take effect on the *next* event.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Dict[str, Any]]] = {
            hook: [] for hook in ALL_HOOKS
        }
        self._lock = threading.RLock()
        # Optional error logger — set by manager
        self._error_logger: Optional["ScriptLogger"] = None

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def register(self, hook: str, callback: Callable, script_name: str) -> None:
        """
        Register *callback* for *hook*, tagged with *script_name* so it can
        be removed on unload/hot-reload.
        """
        if hook not in self._handlers:
            raise ValueError(f"Unknown lifecycle hook: '{hook}'")
        with self._lock:
            self._handlers[hook].append(
                {"callback": callback, "script": script_name}
            )

    def register_from_namespace(self, namespace: Dict[str, Any], script_name: str) -> List[str]:
        """
        Scan *namespace* (a script's global dict after exec) for hook functions
        and register them automatically.

        Returns the list of hook names that were registered.
        """
        registered: List[str] = []
        for hook in ALL_HOOKS:
            fn = namespace.get(hook)
            if callable(fn):
                self.register(hook, fn, script_name)
                registered.append(hook)
        return registered

    def unregister_script(self, script_name: str) -> None:
        """Remove all handlers registered by *script_name*."""
        with self._lock:
            for hook in ALL_HOOKS:
                self._handlers[hook] = [
                    h for h in self._handlers[hook] if h["script"] != script_name
                ]

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    def _dispatch(self, hook: str, *args: Any) -> int:
        """
        Call all handlers for *hook* with *args*.

        Exceptions from individual handlers are caught and logged (so one
        broken script doesn't prevent others from receiving the event).

        Returns the number of handlers invoked.
        """
        with self._lock:
            handlers = list(self._handlers.get(hook, []))
        count = 0
        for entry in handlers:
            try:
                entry["callback"](*args)
                count += 1
            except Exception:  # noqa: BLE001
                tb = traceback.format_exc()
                script = entry.get("script", "unknown")
                msg = f"[lifecycle] '{script}' raised in '{hook}':\n{tb}"
                if self._error_logger:
                    self._error_logger.Error(msg)
                else:
                    import sys
                    print(msg, file=sys.stderr)
        return count

    # ------------------------------------------------------------------
    # Public event methods
    # ------------------------------------------------------------------

    def on_application_started(self) -> int:
        return self._dispatch(HOOK_APPLICATION_STARTED)

    def on_application_stopped(self) -> int:
        return self._dispatch(HOOK_APPLICATION_STOPPED)

    def on_library_updated(self) -> int:
        return self._dispatch(HOOK_LIBRARY_UPDATED)

    def on_script_loaded(self, script_name: str) -> int:
        return self._dispatch(HOOK_SCRIPT_LOADED, script_name)

    def on_script_unloaded(self, script_name: str) -> int:
        return self._dispatch(HOOK_SCRIPT_UNLOADED, script_name)

    def on_game_starting(self, game: "Game") -> int:
        return self._dispatch(HOOK_GAME_STARTING, game)

    def on_game_started(self, game: "Game") -> int:
        return self._dispatch(HOOK_GAME_STARTED, game)

    def on_game_stopped(self, game: "Game", elapsed_seconds: float) -> int:
        return self._dispatch(HOOK_GAME_STOPPED, game, elapsed_seconds)

    def on_game_installed(self, game: "Game") -> int:
        return self._dispatch(HOOK_GAME_INSTALLED, game)

    def on_game_uninstalled(self, game: "Game") -> int:
        return self._dispatch(HOOK_GAME_UNINSTALLED, game)

    def on_game_startup_cancelled(self, game: "Game") -> int:
        return self._dispatch(HOOK_GAME_STARTUP_CANCELLED, game)

    def on_game_installation_cancelled(self, game: "Game") -> int:
        return self._dispatch(HOOK_GAME_INSTALLATION_CANCELLED, game)

    def on_game_selected(self, game: Optional["Game"]) -> int:
        return self._dispatch(HOOK_GAME_SELECTED, game)

    def on_settings_changed(self) -> int:
        return self._dispatch(HOOK_SETTINGS_CHANGED)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_handlers(self) -> Dict[str, List[str]]:
        """Return ``{hook_name: [script_name, …]}`` for all registered handlers."""
        with self._lock:
            return {
                hook: [h["script"] for h in handlers]
                for hook, handlers in self._handlers.items()
            }

    def handler_count(self, hook: Optional[str] = None) -> int:
        with self._lock:
            if hook:
                return len(self._handlers.get(hook, []))
            return sum(len(v) for v in self._handlers.values())

    def set_error_logger(self, logger: "ScriptLogger") -> None:
        self._error_logger = logger
