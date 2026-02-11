"""
Script manager — loads, unloads, hot-reloads, and dispatches to scripts.

Directory layout
----------------
The extensions directory should look like::

    extensions/
        my_script.py
        my_script.yaml          # optional config
        another_script.py
        another_script.yaml

The manager scans for ``*.py`` files on startup.  Config is loaded from the
sibling ``<name>.yaml`` file (defaults used if absent).

Script namespace
----------------
Every script gets these pre-injected names in its global scope:

``__api__`` / ``api``
    :class:`~extensions.sdk.PlayniteSDK` instance.
``__logger__`` / ``__logger``
    :class:`~extensions.logger.ScriptLogger` for this script.
``__stop__``
    :class:`threading.Event` set when the script should terminate.
``__attributes__``
    Dict parsed from the ``__attributes__`` module-level variable if present.
``__exports__``
    List parsed from the ``__exports__`` module-level variable if present.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .config import ScriptConfig, SandboxLevel
from .dependency import DependencyManager
from .lifecycle import LifecycleDispatcher
from .logger import ScriptLogManager
from .sandbox import ScriptSandbox, ExecutionResult
from .sdk import PathsAPI, PlayniteSDK

if TYPE_CHECKING:
    from ..database.game_database import GameDatabase


# ---------------------------------------------------------------------------
# Loaded script record
# ---------------------------------------------------------------------------

@dataclass
class LoadedScript:
    """Metadata about a script that has been successfully loaded."""
    name: str
    path: str
    config: ScriptConfig
    namespace: Dict[str, Any]
    registered_hooks: List[str]
    api: PlayniteSDK
    loaded_at: float = field(default_factory=time.time)
    # Execution history: list of ExecutionResult
    exec_history: List[ExecutionResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        history = [r.to_dict() for r in self.exec_history[-50:]]
        return {
            "name": self.name,
            "path": self.path,
            "enabled": self.config.enabled,
            "sandbox": self.config.sandbox_level.value,
            "timeout": self.config.timeout,
            "hooks": self.registered_hooks,
            "loaded_at": self.loaded_at,
            "exec_count": len(self.exec_history),
            "last_error": next(
                (r.to_dict() for r in reversed(self.exec_history) if not r.success),
                None,
            ),
            "recent_history": history,
            "metadata": self.config.metadata,
        }


# ---------------------------------------------------------------------------
# Execution metrics
# ---------------------------------------------------------------------------

@dataclass
class ScriptMetrics:
    """Aggregate execution metrics for a single script."""
    name: str
    call_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    total_duration_ms: float = 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.call_count if self.call_count else 0.0

    def record(self, result: ExecutionResult) -> None:
        self.call_count += 1
        self.total_duration_ms += result.duration_ms
        if not result.success:
            self.error_count += 1
        if result.timed_out:
            self.timeout_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "calls": self.call_count,
            "errors": self.error_count,
            "timeouts": self.timeout_count,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class ScriptManager:
    """
    Central controller for the script extension system.

    Parameters
    ----------
    extensions_dir:
        Directory containing ``*.py`` script files.
    db:
        Open :class:`~database.game_database.GameDatabase` instance.
    app_paths:
        Dict with keys ``app``, ``config``, ``database``, ``logs``.
    headless:
        If *True*, all dialogs use stdin/stdout (no GUI widgets).
    """

    def __init__(
        self,
        extensions_dir: str,
        db: "GameDatabase",
        app_paths: Optional[Dict[str, str]] = None,
        headless: bool = True,
    ) -> None:
        self._ext_dir = Path(extensions_dir)
        self._ext_dir.mkdir(parents=True, exist_ok=True)
        self._db = db
        self._headless = headless

        paths = app_paths or {}
        self._app_path = paths.get("app", str(Path.cwd()))
        self._config_path = paths.get("config", str(Path.cwd() / "config"))
        self._db_path = paths.get("database", "library.db")
        self._log_dir = paths.get("logs", "logs/scripts")

        self._log_manager = ScriptLogManager(self._log_dir)
        self._dep_manager = DependencyManager(str(self._ext_dir / ".venvs"))
        self._lifecycle = LifecycleDispatcher()
        self._scripts: Dict[str, LoadedScript] = {}
        self._metrics: Dict[str, ScriptMetrics] = {}
        self._lock = threading.RLock()
        self._watcher_started = False

        # Set up a global error logger for the lifecycle dispatcher
        self._global_logger = self._log_manager.get_logger("_system")
        self._lifecycle.set_error_logger(self._global_logger)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def lifecycle(self) -> LifecycleDispatcher:
        return self._lifecycle

    @property
    def loaded_scripts(self) -> Dict[str, LoadedScript]:
        with self._lock:
            return dict(self._scripts)

    # ------------------------------------------------------------------
    # Discovery & loading
    # ------------------------------------------------------------------

    def discover_and_load(self) -> List[str]:
        """
        Scan ``extensions_dir`` for ``*.py`` files and load each one.

        Returns the names of successfully loaded scripts.
        """
        loaded = []
        for py_file in sorted(self._ext_dir.glob("*.py")):
            if py_file.stem.startswith("_"):
                continue
            try:
                self.load_script(str(py_file))
                loaded.append(py_file.stem)
            except Exception:  # noqa: BLE001
                tb = traceback.format_exc()
                self._global_logger.Error(
                    f"Failed to load '{py_file.stem}':\n{tb}"
                )
        return loaded

    def load_script(self, script_path: str) -> LoadedScript:
        """
        Load a single script from *script_path*.

        1. Reads config from sibling YAML file.
        2. Installs declared dependencies.
        3. Executes the script source inside a :class:`ScriptSandbox`.
        4. Registers lifecycle hooks from the script's namespace.
        5. Fires ``on_script_loaded`` event.

        Parameters
        ----------
        script_path:
            Absolute or relative path to the ``.py`` file.

        Returns
        -------
        LoadedScript

        Raises
        ------
        RuntimeError
            If script execution fails or is insecure.
        """
        p = Path(script_path).resolve()
        name = p.stem

        config_path = p.with_suffix(".yaml")
        config = ScriptConfig.from_file(str(config_path))

        if not config.enabled:
            raise RuntimeError(f"Script '{name}' is disabled in its config.")

        logger = self._log_manager.get_logger(name)
        logger.Info(f"Loading script '{name}' from {p}")

        # Track whether we successfully registered the script so the except
        # handler knows whether to release the logger (if the script was never
        # registered, no other code path will close its file handle).
        _script_registered = False
        try:
            # Install dependencies
            if config.dependencies:
                logger.Info(f"Installing dependencies: {config.dependencies}")
                try:
                    self._dep_manager.install_dependencies(name, config.dependencies)
                except Exception as exc:  # noqa: BLE001
                    logger.Error(f"Dependency install failed: {exc}")
                    raise RuntimeError(f"Cannot load '{name}': dependency install failed") from exc

            # Build SDK for this script
            api = self._build_sdk(name, p, logger)

            # Build globals to inject
            extra_globals: Dict[str, Any] = {
                "__api__": api,
                "api": api,
                "__logger__": logger,
                "__logger": logger,  # Playnite C# style
            }

            # Execute the script
            source = p.read_text(encoding="utf-8")
            sandbox = ScriptSandbox(config, extra_globals)
            with self._dep_manager.activated(name):
                result = sandbox.execute(source, script_path=str(p))

            if not result.success:
                logger.Error(f"Script execution error: {result.error}")
                if not result.timed_out:
                    raise RuntimeError(f"Script '{name}' failed to load: {result.error}")

            # Use the namespace captured during execution (imports resolved inside the
            # activated venv context, so venv-installed packages are present).
            namespace: Dict[str, Any] = result.namespace

            # Register lifecycle hooks
            hooks = self._lifecycle.register_from_namespace(namespace, name)
            logger.Info(f"Registered hooks: {hooks or 'none'}")

            # Create record
            script_record = LoadedScript(
                name=name,
                path=str(p),
                config=config,
                namespace=namespace,
                registered_hooks=hooks,
                api=api,
            )
            script_record.exec_history.append(result)

            with self._lock:
                # Unload existing if re-loading
                if name in self._scripts:
                    self._unload_internal(name)
                self._scripts[name] = script_record
                self._metrics[name] = ScriptMetrics(name=name)
                self._metrics[name].record(result)
                _script_registered = True

        except Exception:
            # If the script was never added to _scripts, release its logger's
            # file handle now — no other code path will close it.
            if not _script_registered:
                self._log_manager.remove_logger(name)
            raise

        self._lifecycle.on_script_loaded(name)
        logger.Info(f"Script '{name}' loaded successfully.")
        return script_record

    def _build_sdk(self, name: str, script_path: Path, logger: Any) -> PlayniteSDK:
        data_dir = self._ext_dir / ".data" / name
        data_dir.mkdir(parents=True, exist_ok=True)
        paths = PathsAPI(
            app_path=self._app_path,
            config_path=self._config_path,
            database_path=self._db_path,
            extension_path=str(self._ext_dir),
            extension_data_path=str(data_dir),
            log_path=self._log_dir,
        )
        return PlayniteSDK(
            db=self._db,
            paths=paths,
            logger=logger,
            headless=self._headless,
            lifecycle=self._lifecycle,
        )

    # ------------------------------------------------------------------
    # Unload / reload
    # ------------------------------------------------------------------

    def unload_script(self, script_name: str) -> None:
        """Unload a script by name, unregistering all its hooks."""
        with self._lock:
            if script_name not in self._scripts:
                raise KeyError(f"Script '{script_name}' is not loaded.")
            self._unload_internal(script_name)
        self._lifecycle.on_script_unloaded(script_name)

    def _unload_internal(self, name: str) -> None:
        script = self._scripts.get(name)
        if script is not None:
            # 1. Release all callback and menu-item references held by the
            #    script's SDK.  Callbacks defined in script code have a
            #    __globals__ pointer back to the script's namespace, so leaving
            #    them in these lists would prevent the namespace—and every
            #    object it holds—from being garbage-collected.
            script.api.addons.clear()
            script.api.notifications.clear_callbacks()
            script.api.database.clear_change_handlers()
            # 2. Explicitly break the namespace → api → ... → namespace cycle
            #    so Python's cyclic garbage collector doesn't need to do extra
            #    work and the memory is freed promptly.
            script.namespace.clear()
            # 3. Drop execution history to release ExecutionResult objects.
            script.exec_history.clear()

        self._lifecycle.unregister_script(name)
        self._scripts.pop(name, None)
        self._metrics.pop(name, None)
        self._log_manager.remove_logger(name)

    def reload_script(self, script_name: str) -> LoadedScript:
        """
        Hot-reload a script without restarting the application.

        The script file is re-read from disk, its old hooks are removed, and
        the new version is loaded.
        """
        with self._lock:
            existing = self._scripts.get(script_name)
        path = existing.path if existing else str(self._ext_dir / f"{script_name}.py")
        return self.load_script(path)

    def reload_all(self) -> List[str]:
        """Reload all currently loaded scripts."""
        names = list(self._scripts.keys())
        reloaded = []
        for name in names:
            try:
                self.reload_script(name)
                reloaded.append(name)
            except Exception:  # noqa: BLE001
                pass
        return reloaded

    # ------------------------------------------------------------------
    # Hook dispatch
    # ------------------------------------------------------------------

    def call_hook(self, hook_name: str, *args: Any) -> int:
        """
        Directly invoke a lifecycle hook by name.

        Returns the number of handlers called.
        """
        method = getattr(self._lifecycle, hook_name, None)
        if not callable(method):
            raise ValueError(f"Unknown lifecycle hook: '{hook_name}'")
        return method(*args)

    # ------------------------------------------------------------------
    # Script function invocation
    # ------------------------------------------------------------------

    def invoke_function(self, script_name: str, function_name: str, *args: Any) -> Any:
        """
        Call a named function in a loaded script's namespace.

        Parameters
        ----------
        script_name:
            Name of the loaded script.
        function_name:
            Name of the callable defined in the script's global namespace.
        *args:
            Positional arguments forwarded to the function.

        Returns
        -------
        Any
            Return value of the called function.

        Raises
        ------
        KeyError
            If *script_name* is not loaded.
        AttributeError
            If *function_name* is not found or not callable in the script.
        """
        with self._lock:
            script = self._scripts.get(script_name)
        if script is None:
            raise KeyError(f"Script '{script_name}' is not loaded.")
        fn = script.namespace.get(function_name)
        if not callable(fn):
            raise AttributeError(
                f"'{function_name}' not found or not callable in '{script_name}'."
            )
        return fn(*args)

    def set_variable(self, script_name: str, name: str, value: Any) -> None:
        """
        Inject a variable into a loaded script's namespace.

        Parameters
        ----------
        script_name:
            Name of the loaded script.
        name:
            Variable name to set in the script's global namespace.
        value:
            Value to assign.

        Raises
        ------
        KeyError
            If *script_name* is not loaded.
        """
        with self._lock:
            script = self._scripts.get(script_name)
        if script is None:
            raise KeyError(f"Script '{script_name}' is not loaded.")
        script.namespace[name] = value

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable_script(self, script_name: str) -> None:
        with self._lock:
            if script_name not in self._scripts:
                raise KeyError(f"Script '{script_name}' is not loaded.")
            self._scripts[script_name].config.enabled = True

    def disable_script(self, script_name: str) -> None:
        with self._lock:
            if script_name not in self._scripts:
                raise KeyError(f"Script '{script_name}' is not loaded.")
            self._scripts[script_name].config.enabled = False
            self._lifecycle.unregister_script(script_name)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_scripts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._scripts.values()]

    def get_script(self, name: str) -> Optional[LoadedScript]:
        with self._lock:
            return self._scripts.get(name)

    def get_metrics(self, script_name: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if script_name:
                m = self._metrics.get(script_name)
                return [m.to_dict()] if m else []
            return [m.to_dict() for m in self._metrics.values()]

    def get_exported_menu_items(self) -> Dict[str, List[Any]]:
        """Return all menu items registered by all scripts."""
        main_items: List[Any] = []
        game_items: List[Any] = []
        with self._lock:
            for script in self._scripts.values():
                main_items.extend(script.api.addons.get_main_menu_items())
                game_items.extend(script.api.addons.get_game_menu_items())
        return {"main_menu": main_items, "game_menu": game_items}

    # ------------------------------------------------------------------
    # File-system watcher (optional hot-reload)
    # ------------------------------------------------------------------

    def start_file_watcher(self) -> None:
        """
        Start a background thread that watches ``extensions_dir`` for changes
        and hot-reloads modified scripts.

        Idempotent: calling this more than once has no effect — only one
        watcher thread is ever started per manager instance.

        Requires no external packages.
        """
        with self._lock:
            if self._watcher_started:
                return
            self._watcher_started = True
        t = threading.Thread(target=self._watch_loop, daemon=True, name="script-watcher")
        t.start()

    def _watch_loop(self) -> None:
        mtimes: Dict[str, float] = {}
        while True:
            time.sleep(2)
            try:
                for py_file in self._ext_dir.glob("*.py"):
                    if py_file.stem.startswith("_"):
                        continue
                    mtime = py_file.stat().st_mtime
                    if py_file.stem in mtimes and mtime != mtimes[py_file.stem]:
                        self._global_logger.Info(f"Detected change in '{py_file.stem}', hot-reloading.")
                        try:
                            self.reload_script(py_file.stem)
                        except Exception:  # noqa: BLE001
                            self._global_logger.Error(traceback.format_exc())
                    mtimes[py_file.stem] = mtime
            except Exception:  # noqa: BLE001
                pass
