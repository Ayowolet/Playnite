"""Sandboxed script execution with restricted imports, file access, and timeouts."""

from __future__ import annotations

import builtins
import io
import logging
import os
import signal
import sys
import threading
import traceback
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from playnite_py.scripting.config import SandboxLevel, ScriptConfig

logger = logging.getLogger(__name__)

# Module-level tracking of timed-out daemon threads so callers (or monitoring
# code) can inspect the current count.
_timed_out_threads: list[threading.Thread] = []
_timed_out_lock = threading.Lock()

_MAX_TRACKED_THREADS = 50


def get_timed_out_thread_count() -> int:
    """Return number of timed-out daemon threads still alive."""
    with _timed_out_lock:
        _timed_out_threads[:] = [t for t in _timed_out_threads if t.is_alive()]
        return len(_timed_out_threads)


class SandboxViolation(Exception):
    """Raised when a script violates sandbox restrictions."""


class ScriptTimeoutError(Exception):
    """Raised when a script exceeds its execution timeout."""


class RestrictedImporter:
    """Custom import hook that restricts which modules scripts can import."""

    def __init__(self, allowed_modules: list[str]):
        self._allowed = set(allowed_modules)

    def find_module(self, name: str, path: Any = None) -> RestrictedImporter | None:
        """Return self to handle blocked imports, or None to allow them."""
        top_level = name.split(".")[0]
        if top_level not in self._allowed:
            return self  # We'll handle it (by raising)
        return None  # Let the normal import system handle it

    def load_module(self, name: str) -> ModuleType:
        """Raise SandboxViolation for disallowed module imports."""
        top_level = name.split(".")[0]
        raise SandboxViolation(
            f"Import of '{name}' is not allowed. "
            f"Top-level module '{top_level}' is not in the allowed list."
        )


class RestrictedFileAccess:
    """Wraps builtins.open to restrict file system access to allowed paths."""

    def __init__(self, allowed_paths: list[str], script_dir: str):
        self._allowed: list[Path] = [Path(p).resolve() for p in allowed_paths]
        self._allowed.append(Path(script_dir).resolve())
        self._original_open = builtins.open

    def __call__(self, file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        path = Path(str(file)).resolve()
        write_mode = any(c in mode for c in "wxa+")

        if not self._is_path_allowed(path, write_mode):
            raise SandboxViolation(
                f"Access to '{path}' is not allowed. "
                f"Allowed paths: {[str(p) for p in self._allowed]}"
            )
        return self._original_open(file, mode, *args, **kwargs)

    def _is_path_allowed(self, path: Path, write: bool) -> bool:
        for allowed in self._allowed:
            try:
                path.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False


class SandboxedExecutor:
    """Execute Python code in a sandboxed environment."""

    def __init__(self, config: ScriptConfig, script_dir: str, site_packages: str | None = None):
        self._config = config
        self._script_dir = script_dir
        self._timeout = config.timeout
        # Per-script venv site-packages path — added to sys.path only during
        # this script's execution, then removed to prevent cross-script leakage.
        self._site_packages = site_packages

    def execute_code(
        self,
        code: str,
        global_vars: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute Python code string in sandbox. Returns the execution namespace."""
        timeout = timeout or self._timeout
        namespace = dict(global_vars or {})
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        result: dict[str, Any] = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": "",
            "namespace": {},
        }

        def _run() -> None:
            nonlocal result
            try:
                compiled = compile(code, "<script>", "exec")
                exec(compiled, namespace)  # noqa: S102
                result["success"] = True
                result["namespace"] = namespace
            except SandboxViolation as e:
                result["error"] = f"Sandbox violation: {e}"
            except ScriptTimeoutError as e:
                result["error"] = f"Timeout: {e}"
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

        with self._sandbox_context(namespace, stdout_capture, stderr_capture):
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                result["error"] = f"Script exceeded timeout of {timeout} seconds"
                with _timed_out_lock:
                    _timed_out_threads[:] = [t for t in _timed_out_threads if t.is_alive()]
                    if len(_timed_out_threads) < _MAX_TRACKED_THREADS:
                        _timed_out_threads.append(thread)
                    count = len(_timed_out_threads)
                if count > 5:
                    logger.warning(
                        "%d timed-out script threads still alive", count
                    )

        result["stdout"] = stdout_capture.getvalue()
        result["stderr"] = stderr_capture.getvalue()
        stdout_capture.close()
        stderr_capture.close()
        return result

    def execute_file(
        self,
        file_path: str,
        global_vars: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute a Python file in sandbox."""
        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"Script file not found: {file_path}",
                "namespace": {},
            }
        code = path.read_text(encoding="utf-8")
        return self.execute_code(code, global_vars, timeout)

    def call_function(
        self,
        namespace: dict[str, Any],
        func_name: str,
        *args: Any,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call a function that exists in a previously-executed namespace."""
        timeout = timeout or self._timeout
        func = namespace.get(func_name)
        if func is None or not callable(func):
            return {
                "success": False,
                "result": None,
                "error": f"Function '{func_name}' not found or not callable",
                "stdout": "",
                "stderr": "",
            }

        result: dict[str, Any] = {
            "success": False,
            "result": None,
            "error": "",
            "stdout": "",
            "stderr": "",
        }
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        def _run() -> None:
            nonlocal result
            try:
                ret = func(*args, **kwargs)
                result["success"] = True
                result["result"] = ret
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

        with self._sandbox_context(namespace, stdout_capture, stderr_capture):
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                result["error"] = f"Function '{func_name}' exceeded timeout of {timeout}s"
                with _timed_out_lock:
                    _timed_out_threads[:] = [t for t in _timed_out_threads if t.is_alive()]
                    if len(_timed_out_threads) < _MAX_TRACKED_THREADS:
                        _timed_out_threads.append(thread)
                    count = len(_timed_out_threads)
                if count > 5:
                    logger.warning(
                        "%d timed-out script threads still alive", count
                    )

        result["stdout"] = stdout_capture.getvalue()
        result["stderr"] = stderr_capture.getvalue()
        stdout_capture.close()
        stderr_capture.close()
        return result

    @contextmanager
    def _sandbox_context(
        self,
        namespace: dict[str, Any],
        stdout_capture: io.StringIO,
        stderr_capture: io.StringIO,
    ):
        """Context manager that sets up and tears down sandbox restrictions.

        Per-script venv site-packages are added to sys.path only for the
        duration of the execution and removed on exit.  This prevents
        Script A's dependencies from leaking into Script B's import
        resolution.
        """
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_meta_path = list(sys.meta_path)
        old_open = builtins.open
        old_sys_path = list(sys.path)
        old_modules = set(sys.modules.keys())

        try:
            # Temporarily add this script's venv site-packages to sys.path
            if self._site_packages and self._site_packages not in sys.path:
                sys.path.insert(0, self._site_packages)

            # Redirect stdout/stderr
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

            if self._config.sandbox_level == SandboxLevel.NONE:
                namespace["__builtins__"] = builtins.__dict__.copy()
                yield
                return

            # Install restricted importer
            allowed = self._config.get_effective_allowed_imports()
            # Always allow playnite_py SDK
            if "playnite_py" not in allowed:
                allowed.append("playnite_py")
            importer = RestrictedImporter(allowed)
            sys.meta_path.insert(0, importer)

            # Set up restricted builtins
            restricted_builtins = self._make_restricted_builtins()
            namespace["__builtins__"] = restricted_builtins

            # Restrict file access for BASIC level
            if self._config.sandbox_level == SandboxLevel.BASIC:
                restricted_open = RestrictedFileAccess(
                    self._config.allowed_paths, self._script_dir
                )
                builtins.open = restricted_open
                restricted_builtins["open"] = restricted_open

            yield

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.meta_path[:] = old_meta_path
            builtins.open = old_open
            # Restore sys.path to its pre-execution state so this script's
            # venv does not persist and interfere with other scripts.
            sys.path[:] = old_sys_path
            # Remove modules imported during this script's execution to
            # prevent stale references on reload.
            new_modules = set(sys.modules.keys()) - old_modules
            for mod_name in new_modules:
                # Only remove script-specific modules, not stdlib/builtins
                if mod_name.startswith("playnite_py"):
                    continue
                mod = sys.modules.get(mod_name)
                if mod is None:
                    continue
                mod_file = getattr(mod, "__file__", None) or ""
                # Only remove modules loaded from the script's venv
                if self._site_packages and mod_file.startswith(self._site_packages):
                    del sys.modules[mod_name]

    def _make_restricted_builtins(self) -> dict[str, Any]:
        """Create a restricted builtins dict based on sandbox level."""
        safe = dict(builtins.__dict__)

        # Remove dangerous builtins
        dangerous = [
            "exec", "eval", "compile", "__import__",
            "globals", "locals", "vars",
            "breakpoint", "exit", "quit",
        ]

        if self._config.sandbox_level == SandboxLevel.STRICT:
            dangerous.extend(["open", "input", "memoryview"])

        for name in dangerous:
            safe.pop(name, None)

        # Provide a safe __import__ that respects allowed modules
        allowed = self._config.get_effective_allowed_imports()
        if "playnite_py" not in allowed:
            allowed.append("playnite_py")

        def safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
            top_level = name.split(".")[0]
            if top_level not in allowed:
                raise SandboxViolation(f"Import of '{name}' is not allowed")
            return builtins.__import__(name, *args, **kwargs)

        safe["__import__"] = safe_import
        return safe
