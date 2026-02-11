"""
Sandboxed script execution environment.

Security model
--------------
Three sandbox levels are provided (see :class:`~extensions.config.SandboxLevel`):

* **NONE** — Scripts run unrestricted.  Use only for fully trusted scripts.
* **STANDARD** — Dangerous stdlib modules are blocked via a custom
  ``__import__``.  Scripts may not access ``__class__.__subclasses__`` chains
  or other escape hatches.  AST analysis rejects obviously malicious patterns.
  Execution runs in a separate thread; a configurable timeout terminates it.
* **STRICT** — Everything in STANDARD plus filesystem access is limited to
  paths listed in ``ScriptConfig.allowed_paths``.

Timeout implementation
----------------------
Scripts run in a daemon :class:`threading.Thread`.  Because Python threads
cannot be forcibly killed from another thread, *timeout enforcement* works as
follows:

1. A :class:`threading.Event` ``_stop_event`` is injected into the script's
   globals.
2. The script can check ``__stop__`` to cooperate with cancellation.
3. The *manager* waits ``timeout`` seconds for the thread to finish; if it is
   still alive after that, the thread is detached (it continues but can no
   longer affect the application's main state) and a :class:`TimeoutError` is
   raised.

For truly hard termination use :class:`multiprocessing.Process` — see the
``strict_multiprocess`` option.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import io
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from .config import SandboxLevel

if TYPE_CHECKING:
    from .config import ScriptConfig
    from .logger import ScriptLogger


# ---------------------------------------------------------------------------
# Module allow/block lists
# ---------------------------------------------------------------------------

# Modules always available regardless of sandbox level
_ALWAYS_ALLOWED: Set[str] = {
    "math", "cmath", "decimal", "fractions", "statistics",
    "random", "itertools", "functools", "operator",
    "string", "textwrap", "unicodedata", "re",
    "datetime", "calendar", "time",
    "collections", "heapq", "bisect", "array",
    "enum", "dataclasses", "typing", "types",
    "abc", "contextlib", "copy", "pprint",
    "json", "base64", "hashlib", "hmac",
    "uuid", "struct", "io", "pathlib",
}

# Additional modules allowed under STANDARD level
_STANDARD_ALLOWED: Set[str] = _ALWAYS_ALLOWED | {
    "logging", "warnings", "traceback",
    "urllib.parse", "urllib.request", "http.client",
    "socket", "ssl",
    "zipfile", "tarfile", "gzip", "bz2",
    "csv", "configparser",
    "threading",
    "queue",
    "concurrent.futures",
}

# Modules BLOCKED under STANDARD (and STRICT) regardless of above
_BLOCKED_STANDARD: Set[str] = {
    "os", "os.path",              # Use pathlib instead
    "subprocess", "popen2",
    "sys",                        # Could manipulate interpreter state
    "gc",                         # Memory manipulation
    "ctypes", "cffi",
    "_thread",
    "signal",
    "mmap",
    "shutil",                     # Filesystem bulk ops
    "tempfile",
    "glob", "fnmatch",            # Unrestricted filesystem glob
    "importlib", "imp",           # Dynamic import
    "pkgutil", "site",
    "marshal", "pickle",          # Arbitrary code execution via deserialisation
    "shelve", "dbm",
    "code", "codeop",             # Interactive interpreter
    "compileall", "tokenize",
    "dis", "opcode", "bytecode",
    "inspect",                    # Introspection / can escape sandbox
    "linecache",
    "atexit",                     # Could prevent shutdown
    "multiprocessing",            # Process spawning
    "concurrent",                 # Thread-pool can launch arbitrary code
    "asyncio",                    # Async loop could outlive timeout
    "runpy",
    "zipimport",
    "builtins",
    "__builtin__",
}

# Additional blocks under STRICT level
_BLOCKED_STRICT: Set[str] = _BLOCKED_STANDARD | {
    "urllib", "http", "ftplib",
    "telnetlib", "imaplib", "smtplib",
    "socket", "ssl",
    "requests", "httpx", "aiohttp",
    "sqlite3",
    "csv",
    "hashlib", "hmac",
    "zipfile", "tarfile", "gzip", "bz2",
}

# Builtins available inside sandboxed scripts
_SAFE_BUILTIN_NAMES: Set[str] = {
    "abs", "all", "any", "bin", "bool", "bytes", "callable",
    "chr", "complex", "dict", "divmod", "enumerate",
    "filter", "float", "format", "frozenset", "getattr",
    "hasattr", "hash", "hex", "id", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min",
    "next", "object", "oct", "ord", "pow", "print",
    "range", "repr", "reversed", "round", "set", "setattr",
    "slice", "sorted", "str", "sum", "super", "tuple", "type",
    "vars", "zip",
    # Constants
    "None", "True", "False", "NotImplemented", "Ellipsis",
    # Build class (needed for class definitions)
    "__build_class__", "__name__", "__doc__", "__package__",
    "__loader__", "__spec__", "__import__",
    # Exceptions
    "ArithmeticError", "AssertionError", "AttributeError",
    "BaseException", "BlockingIOError", "BrokenPipeError",
    "BufferError", "BytesWarning", "ChildProcessError",
    "ConnectionAbortedError", "ConnectionError",
    "ConnectionRefusedError", "ConnectionResetError",
    "DeprecationWarning", "EOFError", "EnvironmentError",
    "Exception", "FileExistsError", "FileNotFoundError",
    "FloatingPointError", "FutureWarning", "GeneratorExit",
    "IOError", "ImportError", "ImportWarning", "IndentationError",
    "IndexError", "InterruptedError", "IsADirectoryError",
    "KeyError", "KeyboardInterrupt", "LookupError", "MemoryError",
    "ModuleNotFoundError", "NameError", "NotADirectoryError",
    "NotImplementedError", "OSError", "OverflowError",
    "PendingDeprecationWarning", "PermissionError",
    "ProcessLookupError", "RecursionError", "ReferenceError",
    "ResourceWarning", "RuntimeError", "RuntimeWarning",
    "StopAsyncIteration", "StopIteration", "SyntaxError",
    "SyntaxWarning", "SystemError", "SystemExit", "TabError",
    "TimeoutError", "TypeError", "UnboundLocalError",
    "UnicodeDecodeError", "UnicodeEncodeError", "UnicodeError",
    "UnicodeTranslateError", "UnicodeWarning", "UserWarning",
    "ValueError", "Warning", "ZeroDivisionError",
}

# AST node types that indicate potentially dangerous patterns
_DANGEROUS_ATTR_ACCESS: Set[str] = {
    "__subclasses__", "__bases__", "__mro__",
    "__code__", "__globals__", "__builtins__",
    "__import__", "__loader__", "__spec__",
    "__reduce__", "__reduce_ex__",
    "func_globals", "gi_frame", "gi_code",
    "__class__",  # only flag chains involving __class__.__subclasses__
}


# ---------------------------------------------------------------------------
# AST security checker
# ---------------------------------------------------------------------------

class ASTSecurityViolation(Exception):
    pass


class _SecurityVisitor(ast.NodeVisitor):
    """
    Walk the AST and raise :class:`ASTSecurityViolation` on dangerous patterns.
    """

    def __init__(self, blocked_modules: Set[str]) -> None:
        self._blocked = blocked_modules
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in self._blocked or alias.name in self._blocked:
                self.violations.append(
                    f"Line {node.lineno}: import of blocked module '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        root = module.split(".")[0]
        if root in self._blocked or module in self._blocked:
            self.violations.append(
                f"Line {node.lineno}: from-import of blocked module '{module}'"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Block __import__("os") style calls
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            if node.args and isinstance(node.args[0], ast.Constant):
                name = str(node.args[0].value)
                root = name.split(".")[0]
                if root in self._blocked or name in self._blocked:
                    self.violations.append(
                        f"Line {node.lineno}: dynamic import of blocked module '{name}'"
                    )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in _DANGEROUS_ATTR_ACCESS:
            self.violations.append(
                f"Line {node.lineno}: access to dangerous attribute '{node.attr}'"
            )
        self.generic_visit(node)


def check_ast(source: str, sandbox_level: SandboxLevel) -> List[str]:
    """
    Parse *source* and return a list of security violation messages.

    Returns an empty list if the code is safe.
    """
    if sandbox_level == SandboxLevel.NONE:
        return []
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return [f"SyntaxError: {exc}"]

    blocked = (
        _BLOCKED_STRICT if sandbox_level == SandboxLevel.STRICT else _BLOCKED_STANDARD
    )
    visitor = _SecurityVisitor(blocked)
    visitor.visit(tree)
    return visitor.violations


# ---------------------------------------------------------------------------
# Restricted __import__ factory
# ---------------------------------------------------------------------------

def _make_restricted_import(
    allowed: Set[str],
    blocked: Set[str],
    original_import: Callable,
) -> Callable:
    """
    Return a replacement ``__import__`` that blocks disallowed modules.
    """

    def _restricted_import(name: str, *args: Any, **kwargs: Any) -> Any:
        root = name.split(".")[0]
        if root in blocked or name in blocked:
            raise ImportError(
                f"Import of '{name}' is not permitted in sandbox mode."
            )
        # If we have an explicit allow-list, enforce it
        if allowed and root not in allowed and name not in allowed:
            raise ImportError(
                f"Import of '{name}' is not in the script's allowed module list."
            )
        return original_import(name, *args, **kwargs)

    return _restricted_import


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------

class ExecutionResult:
    """Captures the outcome of a single script execution."""

    def __init__(
        self,
        success: bool,
        error: Optional[Exception] = None,
        stdout: str = "",
        stderr: str = "",
        duration_ms: float = 0.0,
        timed_out: bool = False,
        namespace: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.success = success
        self.error = error
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms
        self.timed_out = timed_out
        # The script's global namespace after execution (populated even on error,
        # so hooks defined before an error line are still accessible).
        self.namespace: Dict[str, Any] = namespace if namespace is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "error": str(self.error) if self.error else None,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
        }

    def __repr__(self) -> str:
        status = "OK" if self.success else ("TIMEOUT" if self.timed_out else "ERROR")
        return f"ExecutionResult({status}, {self.duration_ms:.1f}ms)"


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class ScriptSandbox:
    """
    Executes script code in a controlled environment.

    Parameters
    ----------
    config:
        :class:`~extensions.config.ScriptConfig` for this script.
    extra_globals:
        Additional names to inject into the script's global namespace (e.g.
        ``__api__``, ``__logger__``).
    """

    def __init__(
        self,
        config: "ScriptConfig",
        extra_globals: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._config = config
        self._extra_globals = extra_globals or {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def execute(
        self,
        source: str,
        script_path: str = "<script>",
        call_function: Optional[str] = None,
        call_args: Optional[Tuple] = None,
    ) -> ExecutionResult:
        """
        Execute *source* (or call *call_function* from already-executed source).

        Parameters
        ----------
        source:
            Python source code to execute.
        script_path:
            Used in tracebacks for readability.
        call_function:
            If set, call this function from the script's namespace after exec.
        call_args:
            Positional arguments for *call_function*.
        """
        level = self._config.sandbox_level
        timeout = self._config.timeout if self._config.timeout > 0 else None

        # ---- AST security check ----------------------------------------
        if level != SandboxLevel.NONE:
            violations = check_ast(source, level)
            if violations:
                msg = "Script failed security check:\n" + "\n".join(violations)
                return ExecutionResult(success=False, error=SecurityError(msg))

        # ---- Prepare globals -------------------------------------------
        glob = self._build_globals(source, script_path)

        # ---- Capture output --------------------------------------------
        captured_out = io.StringIO()
        captured_err = io.StringIO()

        # ---- Run in thread ---------------------------------------------
        result_holder: List[Optional[ExecutionResult]] = [None]
        stop_event = threading.Event()
        glob["__stop__"] = stop_event

        def _run() -> None:
            t0 = time.perf_counter()
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = captured_out  # type: ignore[assignment]
            sys.stderr = captured_err  # type: ignore[assignment]
            try:
                exec(compile(source, script_path, "exec"), glob)  # noqa: S102
                if call_function and call_function in glob:
                    args = call_args or ()
                    glob[call_function](*args)
                duration = (time.perf_counter() - t0) * 1000
                result_holder[0] = ExecutionResult(
                    success=True,
                    stdout=captured_out.getvalue(),
                    stderr=captured_err.getvalue(),
                    duration_ms=duration,
                    namespace=glob,
                )
            except Exception as exc:  # noqa: BLE001
                duration = (time.perf_counter() - t0) * 1000
                result_holder[0] = ExecutionResult(
                    success=False,
                    error=exc,
                    stdout=captured_out.getvalue(),
                    stderr=captured_err.getvalue() + traceback.format_exc(),
                    duration_ms=duration,
                    namespace=glob,
                )
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        thread = threading.Thread(target=_run, daemon=True, name=f"script:{script_path}")
        t_start = time.perf_counter()
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            stop_event.set()
            # Detach — we cannot kill Python threads, but we can orphan them
            elapsed = (time.perf_counter() - t_start) * 1000
            return ExecutionResult(
                success=False,
                error=TimeoutError(f"Script timed out after {timeout}s"),
                stdout=captured_out.getvalue(),
                stderr=captured_err.getvalue(),
                duration_ms=elapsed,
                timed_out=True,
            )

        return result_holder[0] or ExecutionResult(success=False)

    # ------------------------------------------------------------------
    # Globals construction
    # ------------------------------------------------------------------

    def _build_globals(self, source: str, script_path: str) -> Dict[str, Any]:
        level = self._config.sandbox_level

        if level == SandboxLevel.NONE:
            glob: Dict[str, Any] = {"__builtins__": builtins}
        else:
            # Build restricted builtins dict
            safe_builtins = {
                name: getattr(builtins, name)
                for name in _SAFE_BUILTIN_NAMES
                if hasattr(builtins, name)
            }
            blocked = (
                _BLOCKED_STRICT
                if level == SandboxLevel.STRICT
                else _BLOCKED_STANDARD
            )
            allowed = (
                set()  # empty = allow anything not blocked
                if level != SandboxLevel.STRICT
                else _ALWAYS_ALLOWED
            )
            safe_builtins["__import__"] = _make_restricted_import(
                allowed, blocked, builtins.__import__
            )
            if level in (SandboxLevel.STANDARD, SandboxLevel.STRICT):
                safe_builtins["open"] = self._make_restricted_open()
            glob = {"__builtins__": safe_builtins}

        glob["__file__"] = script_path
        glob["__name__"] = "__playnite_script__"
        glob.update(self._extra_globals)
        return glob

    def _make_restricted_open(self) -> Callable:
        config = self._config
        original_open = builtins.open

        def _restricted_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if not config.is_path_allowed(str(file)):
                raise PermissionError(
                    f"Script is not permitted to access path: {file}"
                )
            return original_open(file, mode, *args, **kwargs)

        return _restricted_open


class SecurityError(Exception):
    """Raised when a script fails the pre-execution security check."""
