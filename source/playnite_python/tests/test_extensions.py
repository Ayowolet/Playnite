"""
Unit tests for the Python Script Extension System.

Run with::

    pytest source/playnite_python/tests/test_extensions.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import pytest

# Ensure the package root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playnite_python.database.game_database import GameDatabase
from playnite_python.extensions.config import ScriptConfig, SandboxLevel
from playnite_python.extensions.dependency import DependencyManager
from playnite_python.extensions.lifecycle import LifecycleDispatcher, ALL_HOOKS
from playnite_python.extensions.logger import ScriptLogManager
from playnite_python.extensions.sandbox import ScriptSandbox, check_ast
from playnite_python.extensions.manager import ScriptManager
from playnite_python.extensions.sdk import PlayniteSDK, PathsAPI
from playnite_python.models.game import Game


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def in_memory_db():
    db = GameDatabase(":memory:")
    db.open()
    yield db
    db.close()


@pytest.fixture
def log_manager(tmp_dir):
    return ScriptLogManager(str(tmp_dir / "logs"))


@pytest.fixture
def sdk(in_memory_db, tmp_dir, log_manager):
    logger = log_manager.get_logger("test")
    paths = PathsAPI(
        app_path=str(tmp_dir),
        config_path=str(tmp_dir / "config"),
        database_path=str(tmp_dir / "library.db"),
        extension_path=str(tmp_dir / "extensions"),
        extension_data_path=str(tmp_dir / "extensions" / ".data" / "test"),
        log_path=str(tmp_dir / "logs"),
    )
    return PlayniteSDK(db=in_memory_db, paths=paths, logger=logger, headless=True)


# ---------------------------------------------------------------------------
# ScriptConfig tests
# ---------------------------------------------------------------------------

class TestScriptConfig:
    def test_defaults(self):
        cfg = ScriptConfig()
        assert cfg.enabled is True
        assert cfg.timeout == 30
        assert cfg.sandbox_level == SandboxLevel.STANDARD

    def test_from_dict(self):
        cfg = ScriptConfig.from_dict(
            {"enabled": False, "timeout": 10, "sandbox_level": "strict", "dependencies": ["requests"]}
        )
        assert cfg.enabled is False
        assert cfg.timeout == 10
        assert cfg.sandbox_level == SandboxLevel.STRICT
        assert cfg.dependencies == ["requests"]

    def test_from_file_missing(self, tmp_dir):
        cfg = ScriptConfig.from_file(str(tmp_dir / "nonexistent.yaml"))
        assert cfg.enabled is True  # falls back to defaults

    def test_allowed_paths_strict(self, tmp_dir):
        cfg = ScriptConfig.from_dict({
            "sandbox_level": "strict",
            "allowed_paths": [str(tmp_dir)],
        })
        assert cfg.is_path_allowed(str(tmp_dir / "save.dat")) is True
        assert cfg.is_path_allowed("/etc/passwd") is False

    def test_allowed_paths_standard(self):
        cfg = ScriptConfig.from_dict({"sandbox_level": "standard"})
        # Under standard mode with no allowed_paths, all paths are denied
        assert cfg.is_path_allowed("/etc/passwd") is False

    def test_allowed_paths_standard_with_configured_paths(self, tmp_dir):
        cfg = ScriptConfig.from_dict({
            "sandbox_level": "standard",
            "allowed_paths": [str(tmp_dir)],
        })
        assert cfg.is_path_allowed(str(tmp_dir / "save.dat")) is True
        assert cfg.is_path_allowed("/etc/passwd") is False


# ---------------------------------------------------------------------------
# ScriptLogger tests
# ---------------------------------------------------------------------------

class TestScriptLogger:
    def test_log_methods(self, log_manager):
        logger = log_manager.get_logger("mylogger")
        logger.Info("test info")
        logger.Warning("test warning")
        logger.Error("test error")
        logger.Debug("test debug")
        history = logger.get_history()
        assert len(history) == 4
        assert history[0]["level"] == "INFO"
        assert history[1]["level"] == "WARNING"
        assert history[2]["level"] == "ERROR"
        assert history[3]["level"] == "DEBUG"

    def test_level_filter(self, log_manager):
        logger = log_manager.get_logger("filter_test")
        logger.Info("i")
        logger.Error("e")
        errors = logger.get_history("ERROR")
        assert len(errors) == 1
        assert errors[0]["message"] == "e"

    def test_clear_history(self, log_manager):
        logger = log_manager.get_logger("clear_test")
        logger.Info("x")
        logger.clear_history()
        assert logger.get_history() == []

    def test_log_file_created(self, tmp_dir):
        mgr = ScriptLogManager(str(tmp_dir / "logs"))
        mgr.get_logger("file_test")
        log_path = mgr.get_log_path("file_test")
        # Log file may not exist until first write; ensure no error


# ---------------------------------------------------------------------------
# Sandbox / AST security tests
# ---------------------------------------------------------------------------

class TestSandboxSecurity:
    def _make_sandbox(self, level=SandboxLevel.STANDARD):
        cfg = ScriptConfig.from_dict({"sandbox_level": level.value, "timeout": 5})
        return ScriptSandbox(cfg)

    def test_safe_code_runs(self):
        sb = self._make_sandbox()
        result = sb.execute("x = 1 + 1")
        assert result.success

    def test_os_import_blocked(self):
        sb = self._make_sandbox()
        result = sb.execute("import os")
        assert not result.success

    def test_subprocess_blocked(self):
        sb = self._make_sandbox()
        result = sb.execute("import subprocess")
        assert not result.success

    def test_sys_blocked(self):
        sb = self._make_sandbox()
        result = sb.execute("import sys")
        assert not result.success

    def test_print_works(self):
        sb = self._make_sandbox()
        result = sb.execute("print('hello')")
        assert result.success

    def test_math_import_allowed(self):
        sb = self._make_sandbox(SandboxLevel.NONE)
        result = sb.execute("import math; x = math.pi")
        assert result.success

    def test_timeout_enforced(self):
        cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 1})
        sb = ScriptSandbox(cfg)
        result = sb.execute("import time; time.sleep(10)")
        assert result.timed_out or not result.success

    def test_syntax_error_caught(self):
        sb = self._make_sandbox()
        result = sb.execute("def broken(:  pass")
        assert not result.success

    def test_ast_check_blocked_module(self):
        violations = check_ast("import os", SandboxLevel.STANDARD)
        assert len(violations) > 0

    def test_ast_check_dynamic_import(self):
        violations = check_ast("__import__('os')", SandboxLevel.STANDARD)
        assert len(violations) > 0

    def test_ast_check_safe(self):
        violations = check_ast("x = [i*2 for i in range(10)]", SandboxLevel.STANDARD)
        assert violations == []

    def test_exception_does_not_crash_caller(self):
        sb = self._make_sandbox(SandboxLevel.NONE)
        result = sb.execute("raise ValueError('oops')")
        assert not result.success
        assert result.error is not None

    def test_none_sandbox_no_restrictions(self):
        cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 0})
        sb = ScriptSandbox(cfg)
        result = sb.execute("x = 42")
        assert result.success


# ---------------------------------------------------------------------------
# LifecycleDispatcher tests
# ---------------------------------------------------------------------------

class TestLifecycleDispatcher:
    def test_register_and_dispatch(self):
        dp = LifecycleDispatcher()
        calls = []
        dp.register("on_application_started", lambda: calls.append("started"), "test_script")
        dp.on_application_started()
        assert calls == ["started"]

    def test_register_from_namespace(self):
        dp = LifecycleDispatcher()
        results = []
        namespace = {
            "on_game_starting": lambda game: results.append(game.name),
            "on_game_stopped": lambda game, elapsed: results.append(elapsed),
        }
        registered = dp.register_from_namespace(namespace, "ns_script")
        assert "on_game_starting" in registered
        assert "on_game_stopped" in registered

        game = Game(name="Portal 2")
        dp.on_game_starting(game)
        assert "Portal 2" in results

    def test_unregister_script(self):
        dp = LifecycleDispatcher()
        calls = []
        dp.register("on_application_started", lambda: calls.append("x"), "to_remove")
        dp.unregister_script("to_remove")
        dp.on_application_started()
        assert calls == []

    def test_exception_in_handler_doesnt_propagate(self):
        dp = LifecycleDispatcher()
        dp.register("on_application_started", lambda: 1 / 0, "buggy_script")
        # Should not raise
        count = dp.on_application_started()
        assert count == 0  # handler raised, so 0 successful calls

    def test_multiple_hooks_fire_in_order(self):
        dp = LifecycleDispatcher()
        order = []
        dp.register("on_library_updated", lambda: order.append(1), "s1")
        dp.register("on_library_updated", lambda: order.append(2), "s2")
        dp.register("on_library_updated", lambda: order.append(3), "s3")
        dp.on_library_updated()
        assert order == [1, 2, 3]

    def test_all_hooks_defined(self):
        dp = LifecycleDispatcher()
        for hook in ALL_HOOKS:
            assert hook in dp.list_handlers()

    def test_handler_count(self):
        dp = LifecycleDispatcher()
        dp.register("on_application_started", lambda: None, "s1")
        dp.register("on_application_started", lambda: None, "s2")
        assert dp.handler_count("on_application_started") == 2


# ---------------------------------------------------------------------------
# ScriptManager tests
# ---------------------------------------------------------------------------

class TestScriptManager:
    def test_load_simple_script(self, tmp_dir, in_memory_db):
        # Write a simple script
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        (ext_dir / "hello.py").write_text(
            textwrap.dedent("""
                calls = []
                def on_application_started():
                    calls.append('started')
            """)
        )
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        script = mgr.load_script(str(ext_dir / "hello.py"))
        assert script.name == "hello"
        assert "on_application_started" in script.registered_hooks

    def test_script_disabled_by_config(self, tmp_dir, in_memory_db):
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        (ext_dir / "disabled.py").write_text("x = 1")
        (ext_dir / "disabled.yaml").write_text("enabled: false\n")
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        with pytest.raises(RuntimeError, match="disabled"):
            mgr.load_script(str(ext_dir / "disabled.py"))

    def test_hot_reload(self, tmp_dir, in_memory_db):
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        script_file = ext_dir / "reloadme.py"
        script_file.write_text("VERSION = 1")
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        mgr.load_script(str(script_file))

        # Modify script on disk
        script_file.write_text("VERSION = 2")
        mgr.reload_script("reloadme")
        reloaded = mgr.get_script("reloadme")
        assert reloaded is not None

    def test_unload_removes_hooks(self, tmp_dir, in_memory_db):
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        (ext_dir / "tounload.py").write_text(
            "def on_application_started(): pass"
        )
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        mgr.load_script(str(ext_dir / "tounload.py"))
        mgr.unload_script("tounload")
        assert "tounload" not in [s["name"] for s in mgr.list_scripts()]

    def test_discover_and_load(self, tmp_dir, in_memory_db):
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        (ext_dir / "alpha.py").write_text("X = 1")
        (ext_dir / "beta.py").write_text("Y = 2")
        (ext_dir / "_ignored.py").write_text("# ignored")
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        loaded = mgr.discover_and_load()
        assert "alpha" in loaded
        assert "beta" in loaded
        assert "_ignored" not in loaded

    def test_script_api_accessible(self, tmp_dir, in_memory_db):
        """Script should be able to call api.database methods."""
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        # Add a test game first
        in_memory_db.games.add(Game(name="TestGame"))
        (ext_dir / "apiscript.py").write_text(
            textwrap.dedent("""
                games = api.database.get_games()
                game_count = len(games)
            """)
        )
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        script = mgr.load_script(str(ext_dir / "apiscript.py"))
        # If script ran without error, API was accessible
        assert script.name == "apiscript"

    def test_metrics_tracked(self, tmp_dir, in_memory_db):
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        (ext_dir / "metrics_test.py").write_text("x = 1")
        mgr = ScriptManager(str(ext_dir), in_memory_db)
        mgr.load_script(str(ext_dir / "metrics_test.py"))
        metrics = mgr.get_metrics("metrics_test")
        assert len(metrics) == 1
        assert metrics[0]["calls"] >= 1


# ---------------------------------------------------------------------------
# SDK tests
# ---------------------------------------------------------------------------

class TestPlayniteSDK:
    def test_database_get_games(self, sdk, in_memory_db):
        game = Game(name="Minecraft")
        in_memory_db.games.add(game)
        games = sdk.database.get_games()
        names = [g.name for g in games]
        assert "Minecraft" in names

    def test_database_add_update_remove(self, sdk, in_memory_db):
        game = sdk.database.add_game(Game(name="Added Game"))
        assert sdk.database.get_game(game.id) is not None
        game.name = "Updated Game"
        sdk.database.update_game(game)
        assert sdk.database.get_game(game.id).name == "Updated Game"
        sdk.database.remove_game(game.id)
        assert sdk.database.get_game(game.id) is None

    def test_notifications_fallback(self, sdk, capsys):
        sdk.notifications.show("Hello world", "info")
        captured = capsys.readouterr()
        assert "Hello world" in captured.err

    def test_paths_accessible(self, sdk, tmp_dir):
        assert sdk.paths.extension_path is not None

    def test_addons_menu_items(self, sdk):
        sdk.addons.add_main_menu_item("My Item", lambda: None)
        items = sdk.addons.get_main_menu_items()
        assert any(i["name"] == "My Item" for i in items)


# ---------------------------------------------------------------------------
# Venv conflict regression tests  (bugs identified and fixed)
# ---------------------------------------------------------------------------

class TestVenvConflictFixes:
    """
    Regression tests for the four venv-conflict bugs:

    Bug 1 (Critical)  — _extract_namespace re-executed the script outside the
                        activated() context, so hooks from scripts that import
                        venv-only packages were silently not registered.
    Bug 2 (Significant) — sys.path mutations in activated() were not protected
                          by a lock; concurrent loads could interleave paths.
    Bug 3 (Moderate)  — _extract_namespace contained dead code that caused the
                        script to execute three times instead of once at load.
    Bug 4 (Minor)     — _installed_cache had an unprotected read-modify-write
                        cycle that could corrupt under concurrent access.
    """

    # ------------------------------------------------------------------
    # Bug 1: namespace captured inside activated() context
    # ------------------------------------------------------------------

    def test_hooks_registered_when_script_imports_venv_package(
        self, tmp_dir, in_memory_db
    ):
        """
        A script that imports a package only available via its venv should
        still have its hook functions registered after load.

        Before the fix _extract_namespace re-executed outside activated(),
        the ImportError was swallowed, and no hooks were ever registered.
        """
        # Create a fake "site-packages" directory with a simple module.
        fake_packages = tmp_dir / "fake_packages"
        fake_packages.mkdir()
        (fake_packages / "fake_lib.py").write_text("ANSWER = 42\n")

        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()
        (ext_dir / "venv_script.py").write_text(
            textwrap.dedent("""\
                import fake_lib
                IMPORTED_ANSWER = fake_lib.ANSWER

                def on_application_started():
                    pass

                def on_game_stopped(game, elapsed):
                    pass
            """)
        )

        mgr = ScriptManager(str(ext_dir), in_memory_db)
        # Redirect site_packages_path for our script to the fake directory.
        original_sp = mgr._dep_manager.site_packages_path
        mgr._dep_manager.site_packages_path = (
            lambda name: fake_packages if name == "venv_script" else original_sp(name)
        )

        script = mgr.load_script(str(ext_dir / "venv_script.py"))

        assert "on_application_started" in script.registered_hooks, (
            "Hook missing — namespace was captured outside venv context (Bug 1)"
        )
        assert "on_game_stopped" in script.registered_hooks
        assert script.namespace.get("IMPORTED_ANSWER") == 42, (
            "Variable missing from namespace — import failed outside venv context"
        )

    def test_namespace_available_on_failed_script(self, tmp_dir, in_memory_db):
        """
        Even when a script raises at module level, the namespace captured up
        to the point of the error is returned (partial namespace).
        """
        cfg = ScriptConfig.from_dict({"sandbox_level": "none", "timeout": 5})
        sb = ScriptSandbox(cfg)
        result = sb.execute(
            textwrap.dedent("""\
                X = 10
                Y = 20
                raise RuntimeError("deliberate error")
                Z = 30
            """)
        )
        assert not result.success
        # Namespace should have X and Y captured before the error.
        assert result.namespace.get("X") == 10
        assert result.namespace.get("Y") == 20
        assert "Z" not in result.namespace

    # ------------------------------------------------------------------
    # Bug 2: sys.path thread safety
    # ------------------------------------------------------------------

    def test_activated_adds_and_removes_path(self, tmp_dir):
        """activated() adds the venv to sys.path and removes it on exit."""
        fake_sp = tmp_dir / "site-packages"
        fake_sp.mkdir()

        dm = DependencyManager(str(tmp_dir / "venvs"))
        dm.site_packages_path = lambda name: fake_sp

        sp_str = str(fake_sp)
        assert sp_str not in sys.path

        with dm.activated("script_a"):
            assert sp_str in sys.path

        assert sp_str not in sys.path

    def test_activated_concurrent_no_path_leak(self, tmp_dir):
        """
        Concurrent activated() calls for different scripts must not leak
        each other's paths after their contexts exit (Bug 2 fix).
        """
        import threading

        n = 6
        fake_dirs = [tmp_dir / f"sp_{i}" for i in range(n)]
        for d in fake_dirs:
            d.mkdir()

        dm = DependencyManager(str(tmp_dir / "venvs"))
        dm.site_packages_path = (
            lambda name: fake_dirs[int(name.split("_")[1])]
        )

        path_present_during = []
        path_errors = []

        def worker(i):
            with dm.activated(f"script_{i}"):
                sp = str(fake_dirs[i])
                if sp not in sys.path:
                    path_errors.append(f"script_{i} path missing during activation")
                else:
                    path_present_during.append(i)
                time.sleep(0.02)  # hold context briefly to force overlap

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not path_errors, f"Paths missing during activation: {path_errors}"
        assert len(path_present_during) == n

        # After all contexts exit, none of the fake dirs must remain.
        for d in fake_dirs:
            assert str(d) not in sys.path, (
                f"{d} leaked into sys.path after activated() exited (Bug 2)"
            )

    def test_activated_idempotent_for_same_path(self, tmp_dir):
        """
        If a path is already on sys.path, activated() must not insert a
        duplicate and must not remove it on exit.
        """
        fake_sp = tmp_dir / "already-there"
        fake_sp.mkdir()
        sp_str = str(fake_sp)

        dm = DependencyManager(str(tmp_dir / "venvs"))
        dm.site_packages_path = lambda name: fake_sp

        sys.path.insert(0, sp_str)
        try:
            with dm.activated("script_x"):
                assert sys.path.count(sp_str) == 1  # no duplicate
            # activated() should not have removed the pre-existing entry
            assert sp_str in sys.path
        finally:
            sys.path.remove(sp_str)

    # ------------------------------------------------------------------
    # Bug 3: script executed exactly once at load
    # ------------------------------------------------------------------

    def test_script_executed_exactly_once(self, tmp_dir, in_memory_db):
        """
        Before the fix, _extract_namespace executed the script two extra
        times outside the sandbox (three total). After the fix, load_script
        executes the script exactly once via sandbox.execute().
        """
        ext_dir = tmp_dir / "extensions"
        ext_dir.mkdir()

        counter_file = tmp_dir / "exec_count.txt"
        counter_file.write_text("0")

        # open() requires allowed_paths in STANDARD sandbox.
        # Write a sibling YAML config granting access to tmp_dir.
        (ext_dir / "once_script.yaml").write_text(
            f"sandbox_level: standard\nallowed_paths:\n  - {tmp_dir}\n"
        )
        script_text = textwrap.dedent(f"""\
            _p = r'{counter_file}'
            with open(_p) as _f:
                _n = int(_f.read())
            with open(_p, 'w') as _f:
                _f.write(str(_n + 1))

            def on_application_started():
                pass
        """)
        (ext_dir / "once_script.py").write_text(script_text)

        mgr = ScriptManager(str(ext_dir), in_memory_db)
        mgr.load_script(str(ext_dir / "once_script.py"))

        assert counter_file.read_text() == "1", (
            f"Script executed {counter_file.read_text()} time(s); expected exactly 1 (Bug 3)"
        )

    def test_extract_namespace_method_removed(self):
        """_extract_namespace (dead-code source) must no longer exist on ScriptManager."""
        assert not hasattr(ScriptManager, "_extract_namespace"), (
            "_extract_namespace still exists — dead code not removed (Bug 3)"
        )

    # ------------------------------------------------------------------
    # Bug 4: _installed_cache thread safety
    # ------------------------------------------------------------------

    def test_installed_cache_concurrent_reads_and_invalidations(self, tmp_dir):
        """
        Concurrent reads, writes, and invalidations of _installed_cache
        must not raise or corrupt data (Bug 4 fix).
        """
        import threading

        dm = DependencyManager(str(tmp_dir / "venvs"))
        # Pre-seed the cache.
        with dm._cache_lock:
            dm._installed_cache["alpha"] = ["requests", "click"]

        errors = []

        def reader():
            for _ in range(100):
                try:
                    with dm._cache_lock:
                        _ = dm._installed_cache.get("alpha", [])
                except Exception as exc:
                    errors.append(f"reader: {exc}")

        def invalidator():
            for _ in range(50):
                try:
                    with dm._cache_lock:
                        dm._installed_cache.pop("alpha", None)
                        dm._installed_cache["alpha"] = ["requests"]
                except Exception as exc:
                    errors.append(f"invalidator: {exc}")

        threads = (
            [threading.Thread(target=reader) for _ in range(4)]
            + [threading.Thread(target=invalidator) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Cache concurrency errors: {errors}"

    def test_cache_lock_exists(self, tmp_dir):
        """DependencyManager must expose _cache_lock (Bug 4 fix)."""
        dm = DependencyManager(str(tmp_dir / "venvs"))
        assert hasattr(dm, "_cache_lock")
        import threading
        assert isinstance(dm._cache_lock, type(threading.Lock()))


# ---------------------------------------------------------------------------
# Dependency installation failure fixes
# ---------------------------------------------------------------------------

class TestDependencyInstallationFailures:
    """
    Regression tests for the dependency installation failure fixes:

    * extras in specifiers (requests[security]>=2.28)
    * hyphen/underscore/dot normalisation (my-package == my_package)
    * python_executable raises DependencyError instead of falling back to host
    * ensure_venv wraps venv.create() exceptions in DependencyError
    * ensure_venv recreates corrupt (directory-exists-but-no-python) venvs
    * DependencyManager.__init__ raises DependencyError on mkdir permission error
    * _get_installed returns [] when python_executable raises DependencyError
    """

    # ------------------------------------------------------------------
    # _normalize_name
    # ------------------------------------------------------------------

    def test_normalize_name_hyphens(self):
        from playnite_python.extensions.dependency import _normalize_name
        assert _normalize_name("my-package") == "my-package"
        assert _normalize_name("my_package") == "my-package"
        assert _normalize_name("My.Package") == "my-package"
        assert _normalize_name("MY---PACKAGE") == "my-package"
        assert _normalize_name("a_.b-c") == "a-b-c"

    # ------------------------------------------------------------------
    # _filter_missing: extras syntax
    # ------------------------------------------------------------------

    def test_filter_missing_handles_extras(self, tmp_dir):
        """requests[security]>=2.28 must be recognised as 'requests' (not reinstalled)."""
        dm = DependencyManager(str(tmp_dir / "venvs"))
        # Pre-seed cache with normalised name as _get_installed would produce
        with dm._cache_lock:
            dm._installed_cache["myscript"] = ["requests"]

        result = dm._filter_missing("myscript", ["requests[security]>=2.28"])
        assert result == [], f"Expected no missing packages, got {result}"

    def test_filter_missing_handles_extras_absent(self, tmp_dir):
        """requests[security] is treated as missing when requests is not installed."""
        dm = DependencyManager(str(tmp_dir / "venvs"))
        with dm._cache_lock:
            dm._installed_cache["myscript"] = ["click"]

        result = dm._filter_missing("myscript", ["requests[security]>=2.28"])
        assert result == ["requests[security]>=2.28"]

    # ------------------------------------------------------------------
    # _filter_missing: hyphen/underscore/dot normalisation
    # ------------------------------------------------------------------

    def test_filter_missing_normalizes_hyphen_underscore(self, tmp_dir):
        """my-package in installed list matches my_package spec (and vice-versa)."""
        dm = DependencyManager(str(tmp_dir / "venvs"))
        # pip reports with hyphens; script declares with underscores
        with dm._cache_lock:
            dm._installed_cache["myscript"] = ["my-package"]

        assert dm._filter_missing("myscript", ["my_package>=1.0"]) == []
        assert dm._filter_missing("myscript", ["my_package"]) == []

    def test_filter_missing_normalizes_dots(self, tmp_dir):
        """my.package normalises to my-package (PEP 503)."""
        dm = DependencyManager(str(tmp_dir / "venvs"))
        with dm._cache_lock:
            dm._installed_cache["myscript"] = ["my-package"]

        assert dm._filter_missing("myscript", ["my.package==2.0"]) == []

    # ------------------------------------------------------------------
    # python_executable: raises instead of falling back to host Python
    # ------------------------------------------------------------------

    def test_python_executable_raises_when_no_venv(self, tmp_dir):
        """python_executable must raise DependencyError when venv is absent."""
        from playnite_python.extensions.dependency import DependencyError

        dm = DependencyManager(str(tmp_dir / "venvs"))
        # No venv directory exists at all
        with pytest.raises(DependencyError, match="No Python executable"):
            dm.python_executable("nonexistent_script")

    def test_python_executable_does_not_return_host_python(self, tmp_dir):
        """python_executable must never return sys.executable as a fallback."""
        import sys
        from playnite_python.extensions.dependency import DependencyError

        dm = DependencyManager(str(tmp_dir / "venvs"))
        try:
            result = dm.python_executable("nonexistent")
            # If it did not raise, it must not be the host interpreter
            assert str(result) != sys.executable, (
                "python_executable fell back to host sys.executable"
            )
        except DependencyError:
            pass  # correct behaviour

    # ------------------------------------------------------------------
    # ensure_venv: exception wrapping
    # ------------------------------------------------------------------

    def test_ensure_venv_wraps_create_exception(self, tmp_dir):
        """venv.create() failures must be re-raised as DependencyError."""
        from unittest.mock import patch
        from playnite_python.extensions.dependency import DependencyError

        dm = DependencyManager(str(tmp_dir / "venvs"))
        with patch("venv.create", side_effect=PermissionError("read-only fs")):
            with pytest.raises(DependencyError, match="Failed to create virtual environment"):
                dm.ensure_venv("myscript")

    def test_ensure_venv_recreates_corrupt_venv(self, tmp_dir):
        """ensure_venv must remove and recreate a directory that lacks a Python binary."""
        from unittest.mock import patch

        dm = DependencyManager(str(tmp_dir / "venvs"))
        corrupt_dir = dm.venv_path("myscript")
        corrupt_dir.mkdir(parents=True)
        # No python executable inside — simulates partial/corrupt creation

        created_dirs = []

        def fake_create(path, **__):  # noqa: ANN003
            created_dirs.append(path)
            # Actually create the directory structure so python_executable finds it
            py = Path(path) / "bin" / "python"
            py.parent.mkdir(parents=True, exist_ok=True)
            py.touch()

        with patch("venv.create", side_effect=fake_create):
            result = dm.ensure_venv("myscript")

        assert len(created_dirs) == 1, "venv.create should be called exactly once"
        assert result == corrupt_dir

    def test_ensure_venv_concurrent_corrupt_calls_exactly_one_create(self, tmp_dir):
        """
        Concurrent ensure_venv() calls for the same corrupt venv must not race:
        exactly one thread should call venv.create(); all others must wait and
        then find a functional venv already built.
        """
        import threading
        from unittest.mock import patch

        dm = DependencyManager(str(tmp_dir / "venvs"))
        corrupt_dir = dm.venv_path("shared_script")
        corrupt_dir.mkdir(parents=True)
        # No python binary — simulates a corrupt/partial venv

        create_count = [0]
        errors = []
        barrier = threading.Barrier(6)  # all threads start simultaneously

        def fake_create(path, **__):
            create_count[0] += 1
            # Simulate work, then make a real-looking venv
            py = Path(path) / "bin" / "python"
            py.parent.mkdir(parents=True, exist_ok=True)
            py.touch()

        def worker():
            try:
                barrier.wait()
                dm.ensure_venv("shared_script")
            except Exception as exc:
                errors.append(str(exc))

        with patch("venv.create", side_effect=fake_create):
            threads = [threading.Thread(target=worker) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors, f"Threads raised exceptions: {errors}"
        assert create_count[0] == 1, (
            f"venv.create() called {create_count[0]} times; expected exactly 1"
        )

    # ------------------------------------------------------------------
    # __init__: permission error on mkdir
    # ------------------------------------------------------------------

    def test_init_raises_on_mkdir_permission_error(self, tmp_dir):
        """DependencyManager.__init__ must raise DependencyError if mkdir fails."""
        from unittest.mock import patch
        from playnite_python.extensions.dependency import DependencyError

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
            with pytest.raises(DependencyError, match="Cannot create venv root"):
                DependencyManager(str(tmp_dir / "venvs"))

    # ------------------------------------------------------------------
    # _get_installed: returns [] when python_executable raises
    # ------------------------------------------------------------------

    def test_get_installed_returns_empty_when_no_venv(self, tmp_dir):
        """_get_installed must return [] (not raise) when the venv doesn't exist."""
        dm = DependencyManager(str(tmp_dir / "venvs"))
        result = dm._get_installed("no_such_script")
        assert result == []


# ---------------------------------------------------------------------------
# Memory leak fixes
# ---------------------------------------------------------------------------

class TestMemoryLeakFixes:
    """
    Regression tests for the 12 memory-leak fixes:

    #1  exec_history cleared on unload
    #2  _metrics entry removed on unload
    #3  _venv_locks pruned when venv is deleted
    #5  AddonsAPI.clear() wipes menu lists
    #6  NotificationAPI.clear_callbacks() wipes callback list
    #7  Script namespace cleared on unload (breaks __globals__ cycle)
    #8  GameDatabaseAPI.clear_change_handlers() wipes callback list
    #9  start_file_watcher() is idempotent — only one thread spawned
    #10 Full SDK resource release on unload (no lingering references)
    #11 Logger history cleared on remove_logger
    #12 Logger file handle closed when load fails before registration
    """

    # ------------------------------------------------------------------
    # #5 — AddonsAPI.clear()
    # ------------------------------------------------------------------

    def test_addons_clear_empties_both_lists(self):
        from playnite_python.extensions.sdk import AddonsAPI
        api = AddonsAPI()
        api.add_main_menu_item("item1", lambda: None)
        api.add_game_menu_item("item2", lambda _g: None)
        assert len(api.get_main_menu_items()) == 1
        assert len(api.get_game_menu_items()) == 1
        api.clear()
        assert api.get_main_menu_items() == []
        assert api.get_game_menu_items() == []

    # ------------------------------------------------------------------
    # #6 — NotificationAPI.clear_callbacks()
    # ------------------------------------------------------------------

    def test_notification_clear_callbacks(self):
        from playnite_python.extensions.sdk import NotificationAPI
        api = NotificationAPI()
        api._register_handler(lambda msg, t: None)
        assert len(api._callbacks) == 1
        api.clear_callbacks()
        assert api._callbacks == []

    # ------------------------------------------------------------------
    # #8 — GameDatabaseAPI.clear_change_handlers()
    # ------------------------------------------------------------------

    def test_database_clear_change_handlers(self, in_memory_db):
        from playnite_python.extensions.sdk import GameDatabaseAPI
        api = GameDatabaseAPI(in_memory_db)
        api._register_change_handler(lambda: None)
        assert len(api._change_callbacks) == 1
        api.clear_change_handlers()
        assert api._change_callbacks == []

    # ------------------------------------------------------------------
    # #1, #2, #7, #10 — _unload_internal clears all resources
    # ------------------------------------------------------------------

    def test_unload_clears_namespace_and_exec_history(
        self, tmp_dir, in_memory_db
    ):
        """
        After _unload_internal, the LoadedScript's namespace must be empty
        and exec_history must be cleared (Leaks #1, #7).
        """
        script = tmp_dir / "cleanup_script.py"
        script.write_text("x = 42\n")

        mgr = ScriptManager(str(tmp_dir), in_memory_db)
        mgr.load_script(str(script))

        loaded = mgr.get_script("cleanup_script")
        assert loaded is not None
        # Hold a direct reference so the object isn't deallocated under us
        ns = loaded.namespace
        history = loaded.exec_history

        mgr.unload_script("cleanup_script")

        assert ns == {}, "namespace must be cleared on unload"
        assert history == [], "exec_history must be cleared on unload"

    def test_unload_clears_metrics(self, tmp_dir, in_memory_db):
        """_metrics entry must be removed on unload (Leak #2)."""
        script = tmp_dir / "metrics_script.py"
        script.write_text("pass\n")

        mgr = ScriptManager(str(tmp_dir), in_memory_db)
        mgr.load_script(str(script))
        assert mgr.get_metrics("metrics_script") != []

        mgr.unload_script("metrics_script")
        assert mgr.get_metrics("metrics_script") == []

    def test_unload_clears_sdk_callbacks(self, tmp_dir, in_memory_db):
        """
        On unload, addons/notifications/database callback lists must be
        emptied (Leaks #5, #6, #8, #10).
        """
        script = tmp_dir / "cb_script.py"
        script.write_text(textwrap.dedent("""\
            api.addons.add_main_menu_item("test", lambda: None)
            api.notifications._register_handler(lambda m, t: None)
            api.database._register_change_handler(lambda: None)
        """))

        mgr = ScriptManager(str(tmp_dir), in_memory_db)
        mgr.load_script(str(script))

        loaded = mgr.get_script("cb_script")
        assert loaded is not None
        # Grab references before unload
        addons = loaded.api.addons
        notif = loaded.api.notifications
        db_api = loaded.api.database

        mgr.unload_script("cb_script")

        assert addons.get_main_menu_items() == [], "menu items not cleared on unload"
        assert notif._callbacks == [], "notification callbacks not cleared on unload"
        assert db_api._change_callbacks == [], "db change handlers not cleared on unload"

    # ------------------------------------------------------------------
    # #9 — start_file_watcher idempotent
    # ------------------------------------------------------------------

    def test_start_file_watcher_idempotent(self, tmp_dir, in_memory_db):
        """Calling start_file_watcher() multiple times must not spawn extra threads."""
        import threading
        mgr = ScriptManager(str(tmp_dir), in_memory_db)
        before = threading.active_count()
        mgr.start_file_watcher()
        mgr.start_file_watcher()
        mgr.start_file_watcher()
        after = threading.active_count()
        assert after - before == 1, (
            f"Expected exactly 1 new thread, got {after - before}"
        )

    # ------------------------------------------------------------------
    # #3 — _venv_locks pruned on remove_venv
    # ------------------------------------------------------------------

    def test_venv_lock_pruned_on_remove_venv(self, tmp_dir):
        """remove_venv must pop the script's entry from _venv_locks (Leak #3)."""
        from unittest.mock import patch

        dm = DependencyManager(str(tmp_dir / "venvs"))

        def fake_create(path, **__):
            py = Path(path) / "bin" / "python"
            py.parent.mkdir(parents=True, exist_ok=True)
            py.touch()

        with patch("venv.create", side_effect=fake_create):
            dm.ensure_venv("my_script")

        # Lock should exist after venv creation
        assert "my_script" in dm._venv_locks

        dm.remove_venv("my_script")

        # Lock must be pruned
        assert "my_script" not in dm._venv_locks, (
            "_venv_locks entry not removed by remove_venv"
        )

    # ------------------------------------------------------------------
    # #11 — logger history cleared on remove_logger
    # ------------------------------------------------------------------

    def test_logger_history_cleared_on_remove(self, tmp_dir):
        """remove_logger must clear the in-memory log history (Leak #11)."""
        log_mgr = ScriptLogManager(str(tmp_dir / "logs"))
        logger = log_mgr.get_logger("hist_script")
        logger.Info("entry 1")
        logger.Error("entry 2")
        assert len(logger.get_history()) == 2

        log_mgr.remove_logger("hist_script")

        # History must be empty now
        assert logger.get_history() == [], "log history not cleared on remove_logger"

    # ------------------------------------------------------------------
    # #12 — logger closed when load fails before registration
    # ------------------------------------------------------------------

    def test_logger_closed_on_failed_load(self, tmp_dir, in_memory_db):
        """
        If load_script raises before the script is registered, the logger's
        file handle must be closed (Leak #12).
        """
        import logging

        script = tmp_dir / "bad_script.py"
        script.write_text("raise RuntimeError('intentional failure')\n")

        mgr = ScriptManager(str(tmp_dir), in_memory_db)
        with pytest.raises(RuntimeError):
            mgr.load_script(str(script))

        # The underlying logging.Logger for 'bad_script' must have no handlers
        underlying = logging.getLogger("script.bad_script")
        assert underlying.handlers == [], (
            "File handler not closed after failed load"
        )
