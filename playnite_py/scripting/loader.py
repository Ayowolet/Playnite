"""Script loading, unloading, and lifecycle management."""

from __future__ import annotations

import logging
import re as _re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from playnite_py.models.database import GameDatabase
from playnite_py.scripting.config import SandboxLevel, ScriptConfig
from playnite_py.scripting.events import LIFECYCLE_HOOKS
from playnite_py.scripting.sandbox import SandboxedExecutor
from playnite_py.scripting.sdk import PlayniteAPI
from playnite_py.scripting.script_logging import ScriptLogManager
from playnite_py.scripting.dependencies import DependencyManager

logger = logging.getLogger(__name__)


@dataclass
class ScriptInfo:
    """Runtime information about a loaded script."""
    id: str = ""
    name: str = ""
    path: str = ""
    config: ScriptConfig = field(default_factory=ScriptConfig)
    loaded: bool = False
    error: str | None = None
    last_loaded: str = ""
    execution_count: int = 0
    # Auto-detected capabilities
    supported_events: list[str] = field(default_factory=list)
    supported_menus: list[str] = field(default_factory=list)  # "main_menu", "game_menu"
    # Internal state
    _namespace: dict[str, Any] = field(default_factory=dict, repr=False)
    _api: PlayniteAPI | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "config": self.config.to_dict(),
            "loaded": self.loaded,
            "error": self.error,
            "last_loaded": self.last_loaded,
            "execution_count": self.execution_count,
            "supported_events": self.supported_events,
            "supported_menus": self.supported_menus,
        }


class ScriptLoader:
    """Handles discovering, loading, unloading, and reloading scripts."""

    def __init__(
        self,
        extensions_dir: str,
        database: GameDatabase,
        data_dir: str,
        log_dir: str,
        venvs_dir: str,
        log_manager: ScriptLogManager,
        dep_manager: DependencyManager,
    ):
        self._extensions_dir = Path(extensions_dir)
        self._extensions_dir.mkdir(parents=True, exist_ok=True)
        self._database = database
        self._data_dir = data_dir or str(self._extensions_dir / ".data")
        self._log_dir = log_dir or str(self._extensions_dir / ".logs")
        self._venvs_dir = venvs_dir or str(self._extensions_dir / ".venvs")

        self._scripts: dict[str, ScriptInfo] = {}
        self._lock = threading.RLock()
        self._script_sys_paths: dict[str, str] = {}

        self.log_manager = log_manager
        self.dep_manager = dep_manager

        # Callback invoked after a script is loaded (for firing on_loaded hook)
        self._on_loaded_callback: Callable[[ScriptInfo], Any] | None = None

    def set_on_loaded_callback(self, callback: Callable[[ScriptInfo], Any]) -> None:
        """Register a callback to invoke after a script is loaded."""
        self._on_loaded_callback = callback

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self) -> dict[str, ScriptInfo]:
        """Discover and load all scripts from the extensions directory."""
        loaded = {}
        if not self._extensions_dir.exists():
            return loaded

        for entry in sorted(self._extensions_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    info = self.load_script(str(entry))
                    loaded[info.id] = info
                except Exception as e:
                    logger.error("Failed to load script from %s: %s", entry, e)
        return loaded

    def load_script(self, script_dir: str) -> ScriptInfo:
        """Load a single script from a directory."""
        script_dir = str(Path(script_dir).resolve())
        dir_name = Path(script_dir).name

        # Load config
        config_path = Path(script_dir) / "config.yaml"
        config = ScriptConfig.from_yaml(str(config_path))
        if not config.name:
            config.name = dir_name

        script_id = dir_name
        entry_point = Path(script_dir) / config.entry_point

        info = ScriptInfo(
            id=script_id,
            name=config.name,
            path=script_dir,
            config=config,
        )

        if not config.enabled:
            info.loaded = False
            info.error = "Script is disabled"
            with self._lock:
                self._scripts[script_id] = info
            return info

        if not entry_point.exists():
            info.error = f"Entry point not found: {config.entry_point}"
            with self._lock:
                self._scripts[script_id] = info
            return info

        # Install dependencies if needed
        if config.dependencies:
            dep_result = self.dep_manager.install_dependencies(script_id, config.dependencies)
            if not dep_result["success"]:
                failed = dep_result.get("failed", [])
                msg = dep_result.get("message", "Unknown error")
                logger.error(
                    "Dependency installation failed for %s: %s (failed: %s)",
                    script_id, msg, failed,
                )
                info.error = f"Dependency installation failed: {msg}"
                with self._lock:
                    self._scripts[script_id] = info
                return info

        # Resolve the script's venv site-packages path (if any).
        site_packages: str | None = None
        if config.dependencies:
            site_packages = self.dep_manager.get_site_packages_path(script_id)
            if site_packages:
                self._script_sys_paths[script_id] = site_packages
            else:
                logger.error(
                    "Could not resolve site-packages for %s after installing "
                    "dependencies; script cannot load",
                    script_id,
                )
                info.error = (
                    "Dependencies were installed but the venv site-packages "
                    "path could not be resolved"
                )
                with self._lock:
                    self._scripts[script_id] = info
                return info

        # Auto-add dependency package names to allowed_imports
        if config.dependencies and config.sandbox_level != SandboxLevel.NONE:
            for dep in config.dependencies:
                pkg = _re.split(r"[><=!;@\[]", dep, maxsplit=1)[0].strip()
                pkg_import = pkg.replace("-", "_")
                if pkg_import and pkg_import not in config.allowed_imports:
                    config.allowed_imports.append(pkg_import)

        # Create per-extension data directory
        ext_data_dir = Path(self._data_dir) / script_id
        ext_data_dir.mkdir(parents=True, exist_ok=True)

        # Set up logger and API
        script_logger = self.log_manager.get_logger(script_id, config.name)
        api = PlayniteAPI(
            database=self._database,
            script_id=script_id,
            logger=script_logger,
            extensions_dir=str(self._extensions_dir),
            data_dir=str(ext_data_dir),
            log_dir=self._log_dir,
        )

        # Execute in sandbox
        executor = SandboxedExecutor(config, script_dir, site_packages=site_packages)
        global_vars: dict[str, Any] = {
            "playnite": api,
            "__script_dir__": script_dir,
            "__extension_data_dir__": str(ext_data_dir),
        }

        code = entry_point.read_text(encoding="utf-8")
        result = executor.execute_code(code, global_vars, timeout=config.timeout)

        if result["success"]:
            info.loaded = True
            info._namespace = result["namespace"]
            info._api = api
            info.last_loaded = datetime.now(timezone.utc).isoformat()
            script_logger.info("Script loaded successfully")

            # Auto-detect supported events
            info.supported_events = self._detect_supported_events(info._namespace)
            info.supported_menus = self._detect_supported_menus(info._namespace)

            # Call on_loaded hook via callback
            if self._on_loaded_callback:
                self._on_loaded_callback(info)
        else:
            info.error = result["error"]
            script_logger.error("Script load failed: %s", result["error"])

        with self._lock:
            self._scripts[script_id] = info
        return info

    def unload_script(self, script_id: str) -> bool:
        """Unload a script by its ID and clean up its resources."""
        with self._lock:
            info = self._scripts.get(script_id)
            if not info:
                return False
            # Remove actions injected by this script
            actions = self._database.get_all_actions()
            for action in actions:
                if action.source_script_id == script_id:
                    self._database.remove_action(action.id)
            # Remove the script's venv site-packages from sys.path
            old_path = self._script_sys_paths.pop(script_id, None)
            if old_path and old_path in sys.path:
                sys.path.remove(old_path)
            # Clean up
            info._namespace.clear()
            info.loaded = False
            self.log_manager.close_logger(script_id)
            return True

    def reload_script(self, script_id: str) -> ScriptInfo:
        """Unload and re-load a script (hot-reload).

        Holds the lock while reading the script path to prevent another thread
        from modifying the script state between the read and the unload/load.
        """
        with self._lock:
            info = self._scripts.get(script_id)
            if not info:
                raise KeyError(f"Script '{script_id}' not found")
            path = info.path
        self.unload_script(script_id)
        return self.load_script(path)

    def reload_all(self) -> dict[str, ScriptInfo]:
        """Reload all loaded scripts."""
        with self._lock:
            script_ids = list(self._scripts.keys())
        results = {}
        for sid in script_ids:
            try:
                results[sid] = self.reload_script(sid)
            except Exception as e:
                logger.error("Failed to reload %s: %s", sid, e)
        return results

    def unload_all(self) -> None:
        """Unload all loaded scripts."""
        with self._lock:
            for sid in list(self._scripts.keys()):
                self.unload_script(sid)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_loaded_scripts(self) -> list[ScriptInfo]:
        """Return a list of all currently loaded script info objects."""
        with self._lock:
            return list(self._scripts.values())

    def get_script_info(self, script_id: str) -> ScriptInfo | None:
        """Return the script info for a given script ID, or None if not found."""
        with self._lock:
            return self._scripts.get(script_id)

    # ------------------------------------------------------------------
    # Auto-detection of supported events and menus
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_supported_events(namespace: dict[str, Any]) -> list[str]:
        """Return the list of lifecycle hooks the script actually defines."""
        supported = []
        for hook_name in LIFECYCLE_HOOKS:
            func = namespace.get(hook_name)
            if func is not None and callable(func):
                supported.append(hook_name)
        return supported

    @staticmethod
    def _detect_supported_menus(namespace: dict[str, Any]) -> list[str]:
        """Return which menu provider functions the script defines."""
        menus = []
        if callable(namespace.get("get_game_menu_items")):
            menus.append("game_menu")
        if callable(namespace.get("get_main_menu_items")):
            menus.append("main_menu")
        return menus
