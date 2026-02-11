"""Script engine: thin facade coordinating loader, hooks, and file watcher."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playnite_py.models.database import GameDatabase
from playnite_py.scripting.events import LIFECYCLE_HOOKS  # noqa: F401 — re-export
from playnite_py.scripting.loader import ScriptInfo, ScriptLoader  # noqa: F401 — re-export ScriptInfo
from playnite_py.scripting.hooks import HookDispatcher
from playnite_py.scripting.watcher import ScriptFileWatcher
from playnite_py.scripting.script_logging import ScriptLogManager
from playnite_py.scripting.dependencies import DependencyManager
from playnite_py.scripting.metrics import MetricsTracker


class ScriptEngine:
    """Central engine that loads, manages, and executes user extension scripts.

    Delegates to:
    - ``ScriptLoader`` for loading/unloading/reloading scripts
    - ``HookDispatcher`` for executing lifecycle hooks
    - ``ScriptFileWatcher`` for hot-reload on file changes
    """

    def __init__(
        self,
        extensions_dir: str,
        database: GameDatabase,
        data_dir: str = "",
        log_dir: str = "",
        venvs_dir: str = "",
    ):
        _extensions_dir = Path(extensions_dir)
        _log_dir = log_dir or str(_extensions_dir / ".logs")
        _venvs_dir = venvs_dir or str(_extensions_dir / ".venvs")

        # Sub-systems
        self.log_manager = ScriptLogManager(_log_dir)
        self.dep_manager = DependencyManager(_venvs_dir)
        self.metrics = MetricsTracker()

        self.loader = ScriptLoader(
            extensions_dir, database, data_dir, _log_dir, _venvs_dir,
            self.log_manager, self.dep_manager,
        )
        self.hooks = HookDispatcher(self.loader, self.metrics)

        # Wire the on_loaded callback so loading triggers the hook dispatcher
        self.loader.set_on_loaded_callback(
            lambda info: self.hooks._call_hook_on_script(info, "on_loaded")
        )

        self.watcher = ScriptFileWatcher(
            extensions_dir,
            reload_callback=self.loader.reload_script,
            scripts_dict_ref=lambda: self.loader._scripts,
        )

    # ------------------------------------------------------------------
    # Delegated public API
    # ------------------------------------------------------------------

    def load_all(self) -> dict[str, ScriptInfo]:
        """Discover and load all scripts from the extensions directory."""
        return self.loader.load_all()

    def load_script(self, script_dir: str) -> ScriptInfo:
        """Load a single script from the given directory."""
        return self.loader.load_script(script_dir)

    def unload_script(self, script_id: str) -> bool:
        """Unload a script by its ID and clean up its resources."""
        return self.loader.unload_script(script_id)

    def reload_script(self, script_id: str) -> ScriptInfo:
        """Unload and re-load a script by its ID."""
        return self.loader.reload_script(script_id)

    def reload_all(self) -> dict[str, ScriptInfo]:
        """Reload all currently loaded scripts."""
        return self.loader.reload_all()

    def execute_hook(self, hook_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a lifecycle hook across all loaded scripts."""
        return self.hooks.execute_hook(hook_name, **kwargs)

    def get_loaded_scripts(self) -> list[ScriptInfo]:
        """Return a list of all currently loaded script info objects."""
        return self.loader.get_loaded_scripts()

    def get_script_info(self, script_id: str) -> ScriptInfo | None:
        """Return the script info for a given script ID, or None if not found."""
        return self.loader.get_script_info(script_id)

    def start_file_watcher(self) -> None:
        """Start watching the extensions directory for file changes."""
        self.watcher.start()

    def stop_file_watcher(self) -> None:
        """Stop the file system watcher."""
        self.watcher.stop()

    def shutdown(self) -> None:
        """Graceful shutdown: fire on_application_stopped, unload all scripts."""
        self.hooks.execute_hook("on_application_stopped")
        self.watcher.stop()
        self.loader.unload_all()
        self.log_manager.close_all()

    # ------------------------------------------------------------------
    # Backward-compatible properties for test access
    # ------------------------------------------------------------------

    @property
    def _scripts(self) -> dict[str, ScriptInfo]:
        return self.loader._scripts

    @property
    def _script_sys_paths(self) -> dict[str, str]:
        return self.loader._script_sys_paths

    @property
    def _lock(self):
        return self.loader._lock

    @property
    def _extensions_dir(self) -> Path:
        return self.loader._extensions_dir

    @property
    def _observer(self):
        return self.watcher._observer

    @_observer.setter
    def _observer(self, val):
        self.watcher._observer = val

    @property
    def _watcher_running(self) -> bool:
        return self.watcher._watcher_running
