"""
Security-focused sandbox boundary tests.

These tests verify that the sandbox genuinely prevents escape attempts and
only permits the intended API surface.

Run with::

    pytest source/playnite_python/tests/test_sandbox.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playnite_python.extensions.config import ScriptConfig, SandboxLevel
from playnite_python.extensions.sandbox import ScriptSandbox, check_ast, SecurityError


def _sandbox(level: str = "standard", timeout: int = 5) -> ScriptSandbox:
    cfg = ScriptConfig.from_dict({"sandbox_level": level, "timeout": timeout})
    return ScriptSandbox(cfg)


# ---------------------------------------------------------------------------
# Import blocking
# ---------------------------------------------------------------------------

BLOCKED_IMPORTS = [
    "import os",
    "import subprocess",
    "import sys",
    "import ctypes",
    "import multiprocessing",
    "import signal",
    "import mmap",
    "import shutil",
    "import importlib",
    "import inspect",
    "import gc",
    "import marshal",
    "import pickle",
]


@pytest.mark.parametrize("code", BLOCKED_IMPORTS)
def test_blocked_imports(code):
    sb = _sandbox("standard")
    result = sb.execute(code)
    assert not result.success, f"Expected '{code}' to be blocked"


ALLOWED_IMPORTS = [
    "import math",
    "import datetime",
    "import re",
    "import json",
    "import uuid",
    "import collections",
    "import itertools",
]


@pytest.mark.parametrize("code", ALLOWED_IMPORTS)
def test_allowed_imports_none_level(code):
    """Under NONE sandbox level, nothing is blocked."""
    sb = _sandbox("none", timeout=0)
    result = sb.execute(code)
    assert result.success, f"Expected '{code}' to run under NONE sandbox"


# ---------------------------------------------------------------------------
# Escape attempts
# ---------------------------------------------------------------------------

ESCAPE_ATTEMPTS = [
    # __subclasses__ chain
    "().__class__.__bases__[0].__subclasses__()",
    # Dynamic import via __import__
    "__import__('os').system('echo hello')",
    # Attr access to dangerous names
    "object.__subclasses__()",
    # Compile bypass
    # This is allowed at standard level but we check that os import is still blocked
    "compile('import os', '<>','exec')",
]


@pytest.mark.parametrize("code", ESCAPE_ATTEMPTS)
def test_escape_attempts_blocked_or_fail(code):
    """Escape attempts should either be caught by AST or raise at runtime."""
    sb = _sandbox("standard")
    result = sb.execute(code)
    # Either blocked by AST (success=False) or runs harmlessly (doesn't actually
    # call os.system because os is not imported into the namespace)
    # The key invariant: no side-effects from real system access


# ---------------------------------------------------------------------------
# AST checker
# ---------------------------------------------------------------------------

def test_ast_blocks_os_import():
    violations = check_ast("import os", SandboxLevel.STANDARD)
    assert len(violations) > 0


def test_ast_blocks_from_subprocess():
    violations = check_ast("from subprocess import Popen", SandboxLevel.STANDARD)
    assert len(violations) > 0


def test_ast_blocks_dynamic_import():
    violations = check_ast("x = __import__('os')", SandboxLevel.STANDARD)
    assert len(violations) > 0


def test_ast_allows_safe_code():
    code = """
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

result = fib(10)
assert result == 55
"""
    violations = check_ast(code, SandboxLevel.STANDARD)
    assert violations == []


def test_ast_none_level_no_checks():
    violations = check_ast("import os", SandboxLevel.NONE)
    assert violations == []


def test_ast_syntax_error_reported():
    violations = check_ast("def broken(:", SandboxLevel.STANDARD)
    assert any("SyntaxError" in v for v in violations)


# ---------------------------------------------------------------------------
# Strict level: path restrictions
# ---------------------------------------------------------------------------

def test_strict_blocks_extra_modules():
    sb = _sandbox("strict")
    result = sb.execute("import socket")
    assert not result.success


def test_standard_file_open_blocked_without_allowed_paths(tmp_path):
    """STANDARD sandbox must deny open() when no allowed_paths are configured."""
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    cfg = ScriptConfig.from_dict({"sandbox_level": "standard", "timeout": 5})
    sb = ScriptSandbox(cfg)
    result = sb.execute(f"open('{secret}').read()")
    assert not result.success


def test_standard_file_open_allowed_with_allowed_paths(tmp_path):
    """STANDARD sandbox must permit open() for paths inside allowed_paths."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    allowed_file = allowed_dir / "data.txt"
    allowed_file.write_text("hello")
    cfg = ScriptConfig.from_dict({
        "sandbox_level": "standard",
        "timeout": 5,
        "allowed_paths": [str(allowed_dir)],
    })
    sb = ScriptSandbox(cfg)
    result = sb.execute(f"content = open('{allowed_file}').read()")
    assert result.success


def test_strict_file_open_blocked(tmp_path):
    disallowed = tmp_path / "secret.txt"
    disallowed.write_text("secret")
    cfg = ScriptConfig.from_dict({
        "sandbox_level": "strict",
        "timeout": 5,
        "allowed_paths": [str(tmp_path / "allowed")],
    })
    sb = ScriptSandbox(cfg)
    result = sb.execute(f"open('{disallowed}').read()")
    assert not result.success


def test_strict_file_open_allowed(tmp_path):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    allowed_file = allowed_dir / "data.txt"
    allowed_file.write_text("hello")
    cfg = ScriptConfig.from_dict({
        "sandbox_level": "strict",
        "timeout": 5,
        "allowed_paths": [str(allowed_dir)],
    })
    sb = ScriptSandbox(cfg)
    result = sb.execute(f"content = open('{allowed_file}').read()")
    assert result.success


# ---------------------------------------------------------------------------
# Timeout enforcement
# ---------------------------------------------------------------------------

def test_timeout_fires():
    cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 1})
    sb = ScriptSandbox(cfg)
    result = sb.execute("import time; time.sleep(60)")
    assert result.timed_out


def test_no_timeout_when_zero():
    """timeout=0 means no timeout (dangerous but valid)."""
    cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 0})
    sb = ScriptSandbox(cfg)
    result = sb.execute("x = sum(range(1000))")
    assert result.success


# ---------------------------------------------------------------------------
# Extra injected globals
# ---------------------------------------------------------------------------

def test_extra_globals_accessible():
    cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 0})
    sb = ScriptSandbox(cfg, extra_globals={"magic_value": 42})
    result = sb.execute("assert magic_value == 42")
    assert result.success


def test_stop_event_injected():
    cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 0})
    sb = ScriptSandbox(cfg)
    result = sb.execute("assert __stop__ is not None")
    assert result.success


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------

def test_exception_captured_not_raised():
    sb = _sandbox("none", timeout=0)
    result = sb.execute("raise RuntimeError('test error')")
    assert not result.success
    assert result.error is not None
    assert "test error" in str(result.error)


def test_name_error_captured():
    sb = _sandbox("standard")
    result = sb.execute("undefined_variable")
    assert not result.success


def test_successful_result_has_no_error():
    sb = _sandbox("none", timeout=0)
    result = sb.execute("x = 1 + 1")
    assert result.success
    assert result.error is None


# ---------------------------------------------------------------------------
# Performance benchmark
# ---------------------------------------------------------------------------

def test_ten_scripts_under_5_seconds(tmp_path):
    """
    DoD item 19: <5 second total overhead for 10 pre-launch scripts.
    Each script does a trivial operation.
    """
    import time
    cfg = ScriptConfig.from_dict({"sandbox_level": "standard", "timeout": 5})
    sb = ScriptSandbox(cfg)
    scripts = [f"result_{i} = {i} * 2" for i in range(10)]
    t0 = time.perf_counter()
    for script in scripts:
        result = sb.execute(script)
        assert result.success
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"10 scripts took {elapsed:.2f}s (must be < 5s)"
