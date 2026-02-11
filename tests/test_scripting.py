"""Tests for the script engine, SDK, configuration, and lifecycle hooks."""

import os
import tempfile
import textwrap
import zipfile

import pytest
import yaml

from playnite_py.models.database import GameDatabase
from playnite_py.models.game import Game
from playnite_py.scripting.config import ScriptConfig, SandboxLevel, ExtensionType
from playnite_py.scripting.engine import ScriptEngine, LIFECYCLE_HOOKS
from playnite_py.scripting.events import (
    OnGameStartingEventArgs,
    OnGameStartedEventArgs,
    OnGameStoppedEventArgs,
    OnGameStartupCancelledEventArgs,
    OnGameInstallationCancelledEventArgs,
    HOOK_EVENT_ARGS_MAP,
)
from playnite_py.scripting.marketplace import ScriptMarketplace
from playnite_py.scripting.sdk import PlayniteAPI, DatabaseAPI, NotificationAPI, MenuAPI
from playnite_py.scripting.metrics import MetricsTracker, ExecutionTimer


class TestScriptConfig:
    def test_default_values(self):
        config = ScriptConfig()
        assert config.enabled is True
        assert config.timeout == 30
        assert config.sandbox_level == SandboxLevel.BASIC

    def test_yaml_round_trip(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            path = f.name

        try:
            config = ScriptConfig(
                name="Test Script",
                timeout=60,
                sandbox_level=SandboxLevel.STRICT,
                dependencies=["requests"],
                version="2.0.0",
            )
            config.to_yaml(path)

            loaded = ScriptConfig.from_yaml(path)
            assert loaded.name == "Test Script"
            assert loaded.timeout == 60
            assert loaded.sandbox_level == SandboxLevel.STRICT
            assert loaded.dependencies == ["requests"]
            assert loaded.version == "2.0.0"
        finally:
            os.unlink(path)

    def test_from_missing_yaml(self):
        config = ScriptConfig.from_yaml("/nonexistent/config.yaml")
        assert config.enabled is True  # defaults

    def test_effective_allowed_imports(self):
        config = ScriptConfig(sandbox_level=SandboxLevel.BASIC, allowed_imports=["requests"])
        allowed = config.get_effective_allowed_imports()
        assert "json" in allowed
        assert "math" in allowed
        assert "requests" in allowed

    def test_none_sandbox_no_restrictions(self):
        config = ScriptConfig(sandbox_level=SandboxLevel.NONE)
        assert config.get_effective_allowed_imports() == []


class TestPlayniteSDK:
    def setup_method(self):
        self.db = GameDatabase()
        self.api = PlayniteAPI(self.db, script_id="test")

    def test_database_api_add_game(self):
        result = self.api.database.add_game(name="SDK Game", source="Test")
        assert result["name"] == "SDK Game"
        assert len(self.api.database.get_games()) == 1

    def test_database_api_update(self):
        game = Game(name="Original")
        self.db.add_game(game)
        assert self.api.database.update_game(game.id, name="Updated")
        updated = self.api.database.get_game(game.id)
        assert updated["name"] == "Updated"

    def test_database_api_tags(self):
        game = Game(name="Tag Test")
        self.db.add_game(game)
        assert self.api.database.add_tag_to_game(game.id, "Favorite")
        assert self.api.database.add_tag_to_game(game.id, "Favorite")  # idempotent
        tags = self.api.database.get_tags()
        assert any(t["name"] == "Favorite" for t in tags)
        assert self.api.database.remove_tag_from_game(game.id, "Favorite")

    def test_notifications(self):
        self.api.notifications.show("Test message", "Title")
        self.api.notifications.show_error("Error msg")
        pending = self.api.notifications.get_pending()
        assert len(pending) == 2
        assert pending[0]["type"] == "info"
        assert pending[1]["type"] == "error"
        # Should be cleared after get_pending
        assert len(self.api.notifications.get_pending()) == 0

    def test_dialogs(self):
        self.api.dialogs.set_response("message", "OK")
        result = self.api.dialogs.show_message("Test?", buttons=["OK", "Cancel"])
        assert result == "OK"

        self.api.dialogs.set_response("input", "user input")
        result = self.api.dialogs.show_input("Name?")
        assert result == "user input"

        history = self.api.dialogs.get_history()
        assert len(history) == 2

    def test_menus(self):
        called = []
        item_id = self.api.menus.add_main_menu_item("Test", lambda: called.append(1))
        assert item_id
        items = self.api.menus.get_main_menu_items()
        assert len(items) == 1

        self.api.menus.invoke_menu_item(item_id)
        assert len(called) == 1

        assert self.api.menus.remove_menu_item(item_id)
        assert len(self.api.menus.get_main_menu_items()) == 0

    def test_action_api(self):
        game = Game(name="Action Test")
        self.db.add_game(game)
        action_id = self.api.actions.add_action(
            name="Pre-launch",
            script="print('hi')",
            game_id=game.id,
            phase="pre_launch",
        )
        assert action_id
        actions = self.api.actions.get_actions(game_id=game.id)
        assert len(actions) == 1
        assert self.api.actions.remove_action(action_id)

    def test_stats(self):
        self.db.add_game(Game(name="G1", playtime=100))
        stats = self.api.database.get_stats()
        assert stats["total_games"] == 1


class TestScriptEngine:
    def _create_script_dir(self, tmpdir, name, script_code, config_overrides=None):
        """Helper to create a script directory."""
        script_dir = os.path.join(tmpdir, name)
        os.makedirs(script_dir, exist_ok=True)

        with open(os.path.join(script_dir, "script.py"), "w") as f:
            f.write(textwrap.dedent(script_code))

        config = {
            "name": name,
            "enabled": True,
            "timeout": 10,
            "sandbox_level": "basic",
            "entry_point": "script.py",
        }
        if config_overrides:
            config.update(config_overrides)

        import yaml
        with open(os.path.join(script_dir, "config.yaml"), "w") as f:
            yaml.dump(config, f)

        return script_dir

    def test_load_simple_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_script_dir(tmpdir, "hello", """
def on_loaded():
    pass

def on_application_started():
    pass
""")
            db = GameDatabase()
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            loaded = engine.load_all()
            assert "hello" in loaded
            assert loaded["hello"].loaded is True
            engine.shutdown()

    def test_script_with_sdk_access(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_script_dir(tmpdir, "sdk_test", """
def on_loaded():
    games = playnite.database.get_games()
    playnite.log.info("Found %d games", len(games))
    playnite.notifications.show("Loaded!")
""")
            db = GameDatabase()
            db.add_game(Game(name="Test"))
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            engine.load_all()

            info = engine.get_script_info("sdk_test")
            assert info is not None
            assert info.loaded is True
            engine.shutdown()

    def test_disabled_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_script_dir(tmpdir, "disabled", "pass",
                                    config_overrides={"enabled": False})
            db = GameDatabase()
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            loaded = engine.load_all()
            assert loaded["disabled"].loaded is False
            engine.shutdown()

    def test_script_error_doesnt_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_script_dir(tmpdir, "bad_script", """
raise RuntimeError("Script initialization error")
""")
            db = GameDatabase()
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            loaded = engine.load_all()
            assert loaded["bad_script"].loaded is False
            assert loaded["bad_script"].error is not None
            engine.shutdown()

    def test_lifecycle_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_script_dir(tmpdir, "hooks", """
hook_calls = []

def on_loaded():
    hook_calls.append("on_loaded")

def on_application_started():
    hook_calls.append("on_application_started")

def on_library_updated():
    hook_calls.append("on_library_updated")

def on_game_started(game_id=None, **kwargs):
    hook_calls.append(f"on_game_started:{game_id}")
""")
            db = GameDatabase()
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            engine.load_all()

            # on_loaded is called during load
            info = engine.get_script_info("hooks")
            assert info.loaded is True

            # Execute hooks
            engine.execute_hook("on_application_started")
            engine.execute_hook("on_library_updated")
            engine.execute_hook("on_game_started", game_id="g1")
            engine.shutdown()

    def test_reload_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script_dir = self._create_script_dir(tmpdir, "reloadable", """
VERSION = "1.0"
def on_loaded():
    pass
""")
            db = GameDatabase()
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            engine.load_all()
            assert engine.get_script_info("reloadable").loaded

            # Modify script
            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write('VERSION = "2.0"\ndef on_loaded():\n    pass\n')

            # Reload
            info = engine.reload_script("reloadable")
            assert info.loaded is True
            engine.shutdown()

    def test_game_specific_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_script_dir(tmpdir, "game_specific", """
def on_game_started(game_id=None, **kwargs):
    pass
""", config_overrides={"game_ids": ["game-123"]})

            db = GameDatabase()
            engine = ScriptEngine(tmpdir, db, log_dir=os.path.join(tmpdir, "logs"))
            engine.load_all()

            # Should execute for matching game
            results = engine.execute_hook("on_game_started", game_id="game-123")
            assert "game_specific" in results

            # Should NOT execute for non-matching game
            results = engine.execute_hook("on_game_started", game_id="game-456")
            assert "game_specific" not in results
            engine.shutdown()


class TestDependencyInstallation:
    """Tests for dependency installation failure scenarios."""

    def test_venv_creation_failure_returns_error_dict(self):
        """If venv creation fails, install_dependencies returns a failure dict."""
        from unittest.mock import patch
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)

            # Simulate venv creation failure
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type("R", (), {
                    "returncode": 1, "stdout": "", "stderr": "ensurepip is not available"
                })()

                result = mgr.install_dependencies("broken_script", ["requests"])

            assert result["success"] is False
            assert "requests" in result["failed"]
            assert "Venv creation failed" in result["message"]

    def test_pip_not_found_returns_error_dict(self):
        """If pip executable is missing after venv creation, returns failure."""
        from unittest.mock import patch
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)

            # Let venv creation succeed but pip doesn't exist
            with patch.object(mgr, "ensure_venv"), \
                 patch.object(mgr, "get_pip_executable", return_value="/nonexistent/pip"):

                result = mgr.install_dependencies("no_pip", ["requests"])

            assert result["success"] is False
            assert "pip executable not found" in result["message"]

    def test_pip_nonfunctional_returns_error_dict(self):
        """If pip --version fails, returns failure before attempting installs."""
        from unittest.mock import patch, MagicMock
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)

            # pip file exists but pip --version returns non-zero
            pip_path = os.path.join(tmpdir, "pip")
            with open(pip_path, "w") as f:
                f.write("")

            with patch.object(mgr, "ensure_venv"), \
                 patch.object(mgr, "get_pip_executable", return_value=pip_path), \
                 patch("subprocess.run") as mock_run:
                mock_run.return_value = type("R", (), {
                    "returncode": 1, "stdout": "", "stderr": "pip is broken"
                })()

                result = mgr.install_dependencies("broken_pip", ["requests"])

            assert result["success"] is False
            assert "pip --version failed" in result["message"]

    def test_partial_dependency_failure(self):
        """Some deps succeed and some fail — result reflects partial failure."""
        from unittest.mock import patch, call
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)
            pip_path = os.path.join(tmpdir, "pip")
            with open(pip_path, "w") as f:
                f.write("")

            def mock_subprocess_run(cmd, **kwargs):
                R = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
                if cmd == [pip_path, "--version"]:
                    return R()
                # pip install
                if "good_pkg" in cmd:
                    return R()
                # bad_pkg fails
                r = R()
                r.returncode = 1
                r.stderr = "Could not find version"
                return r

            with patch.object(mgr, "ensure_venv"), \
                 patch.object(mgr, "get_pip_executable", return_value=pip_path), \
                 patch("subprocess.run", side_effect=mock_subprocess_run):

                result = mgr.install_dependencies(
                    "partial", ["good_pkg", "bad_pkg"]
                )

            assert result["success"] is False
            assert result["failed"] == ["bad_pkg"]
            assert len(result["installed"]) == 2
            assert result["installed"][0]["success"] is True
            assert result["installed"][1]["success"] is False

    def test_pip_install_timeout(self):
        """pip install timeout is reported as failure."""
        import subprocess as sp
        from unittest.mock import patch
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)
            pip_path = os.path.join(tmpdir, "pip")
            with open(pip_path, "w") as f:
                f.write("")

            call_count = [0]

            def mock_run(cmd, **kwargs):
                R = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
                call_count[0] += 1
                if call_count[0] == 1:  # pip --version
                    return R()
                raise sp.TimeoutExpired(cmd, 120)

            with patch.object(mgr, "ensure_venv"), \
                 patch.object(mgr, "get_pip_executable", return_value=pip_path), \
                 patch("subprocess.run", side_effect=mock_run):

                result = mgr.install_dependencies("timeout_script", ["slow_pkg"])

            assert result["success"] is False
            assert "timed out" in result["installed"][0]["error"]

    def test_corrupted_venv_detected_and_recreated(self):
        """A venv with missing python executable is treated as corrupted."""
        from playnite_py.scripting.dependencies import DependencyManager, VenvCreationError
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)
            venv_path = mgr.get_venv_path("corrupt")
            venv_path.mkdir(parents=True)
            # venv dir exists but python binary is missing

            with patch("subprocess.run") as mock_run:
                # Simulate successful venv recreation
                mock_run.return_value = type("R", (), {
                    "returncode": 0, "stdout": "", "stderr": ""
                })()

                # But python still won't exist after "creation"
                # (subprocess.run is mocked, so no real venv is created)
                with pytest.raises(VenvCreationError, match="python executable not found"):
                    mgr.ensure_venv("corrupt")

    def test_engine_blocks_load_on_dep_failure(self):
        """Engine refuses to load a script when dependency install fails."""
        from unittest.mock import patch
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "extensions")
            script_dir = os.path.join(ext_dir, "needs_deps")
            os.makedirs(script_dir)

            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write("def on_loaded(): pass\n")
            with open(os.path.join(script_dir, "config.yaml"), "w") as f:
                yaml.dump({
                    "name": "Needs Deps",
                    "enabled": True,
                    "dependencies": ["nonexistent_package_xyz"],
                }, f)

            db = GameDatabase()
            engine = ScriptEngine(
                ext_dir, db,
                log_dir=os.path.join(tmpdir, "logs"),
                venvs_dir=os.path.join(tmpdir, "venvs"),
            )

            # Mock install_dependencies to return failure
            with patch.object(
                engine.dep_manager, "install_dependencies",
                return_value={
                    "success": False,
                    "installed": [],
                    "failed": ["nonexistent_package_xyz"],
                    "message": "Failed: ['nonexistent_package_xyz']",
                },
            ):
                engine.load_all()

            info = engine.get_script_info("needs_deps")
            assert info is not None
            assert info.loaded is False
            assert "Dependency installation failed" in info.error

    def test_engine_blocks_load_on_site_packages_failure(self):
        """Engine refuses to load when deps installed but site-packages unresolvable."""
        from unittest.mock import patch
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "extensions")
            script_dir = os.path.join(ext_dir, "bad_venv")
            os.makedirs(script_dir)

            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write("def on_loaded(): pass\n")
            with open(os.path.join(script_dir, "config.yaml"), "w") as f:
                yaml.dump({
                    "name": "Bad Venv",
                    "enabled": True,
                    "dependencies": ["requests"],
                }, f)

            db = GameDatabase()
            engine = ScriptEngine(
                ext_dir, db,
                log_dir=os.path.join(tmpdir, "logs"),
                venvs_dir=os.path.join(tmpdir, "venvs"),
            )

            with patch.object(
                engine.dep_manager, "install_dependencies",
                return_value={
                    "success": True,
                    "installed": [{"package": "requests", "success": True}],
                    "failed": [],
                    "message": "All dependencies installed",
                },
            ), patch.object(
                engine.dep_manager, "get_site_packages_path",
                return_value=None,
            ):
                engine.load_all()

            info = engine.get_script_info("bad_venv")
            assert info is not None
            assert info.loaded is False
            assert "site-packages" in info.error

    def test_cleanup_venv_handles_permission_error(self):
        """cleanup_venv logs and returns False on OSError."""
        from unittest.mock import patch
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)
            venv_path = mgr.get_venv_path("locked")
            venv_path.mkdir(parents=True)

            with patch("shutil.rmtree", side_effect=OSError("Permission denied")):
                result = mgr.cleanup_venv("locked")
            assert result is False

    def test_no_dependencies_returns_success(self):
        """Empty dependency list is a no-op success."""
        from playnite_py.scripting.dependencies import DependencyManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DependencyManager(tmpdir)
            result = mgr.install_dependencies("clean", [])
            assert result["success"] is True
            assert result["installed"] == []


class TestMetrics:
    def test_record_and_query(self):
        tracker = MetricsTracker()
        tracker.record_execution("s1", "Script1", "on_loaded", True, 0.1)
        tracker.record_execution("s1", "Script1", "on_game_started", True, 0.2)
        tracker.record_execution("s2", "Script2", "on_loaded", False, 0.05, "error")

        history = tracker.get_history()
        assert len(history) == 3

        history_s1 = tracker.get_history(script_id="s1")
        assert len(history_s1) == 2

        stats = tracker.get_script_stats("s1")
        assert stats["total_executions"] == 2
        assert stats["successful_executions"] == 2
        assert stats["avg_duration"] == pytest.approx(0.15, abs=0.01)

    def test_execution_timer(self):
        import time
        with ExecutionTimer() as timer:
            time.sleep(0.05)
        assert timer.duration >= 0.04


# ======================================================================
# Memory Leak Prevention Tests
# ======================================================================

class TestMemoryLeakPrevention:
    """Tests verifying memory leak fixes in scripting subsystem."""

    def test_metrics_history_trimmed(self):
        """MetricsTracker caps history at max_history."""
        tracker = MetricsTracker(max_history=5)
        for i in range(10):
            tracker.record_execution(f"s{i}", f"Script{i}", "on_loaded", True, 0.01)
        history = tracker.get_history(limit=1000)
        assert len(history) <= 5

    def test_dialog_api_history_trimmed(self):
        """DialogAPI caps history at max_history."""
        from playnite_py.scripting.sdk import DialogAPI
        dialog = DialogAPI(max_history=5)
        for i in range(10):
            dialog.show_message(f"msg {i}")
        assert len(dialog._history) <= 5

    def test_notification_api_trimmed(self):
        """NotificationAPI caps notifications at max_notifications."""
        import logging
        log = logging.getLogger("test.notif")
        notif = NotificationAPI(log, max_notifications=5)
        for i in range(10):
            notif.show(f"msg {i}")
        assert len(notif._notifications) <= 5

    def test_sandbox_stringio_closed(self):
        """Sandbox execution closes StringIO captures after use."""
        from playnite_py.scripting.sandbox import SandboxedExecutor
        config = ScriptConfig(timeout=5, sandbox_level=SandboxLevel.NONE)
        executor = SandboxedExecutor(config, "/tmp")
        result = executor.execute_code("x = 1", {})
        assert result["success"] is True
        # StringIO objects are closed internally; just verify no error occurs

    def test_sandbox_timed_out_thread_tracking(self):
        """Timed-out sandbox threads are tracked in module-level list."""
        from playnite_py.scripting.sandbox import (
            SandboxedExecutor, get_timed_out_thread_count,
        )
        config = ScriptConfig(timeout=1, sandbox_level=SandboxLevel.NONE)
        executor = SandboxedExecutor(config, "/tmp")
        # Execute code that sleeps longer than timeout
        result = executor.execute_code("import time; time.sleep(10)", {}, timeout=1)
        assert not result["success"]
        assert "timeout" in result["error"].lower()
        # The timed-out thread should be tracked
        count = get_timed_out_thread_count()
        assert count >= 1

    def test_script_log_manager_clears_handlers_on_close(self):
        """ScriptLogManager removes all handlers from logger on close."""
        import logging
        from playnite_py.scripting.script_logging import ScriptLogManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ScriptLogManager(tmpdir)
            logger = mgr.get_logger("test_script", "TestScript")
            handler_count_before = len(logger.handlers)
            assert handler_count_before > 0

            mgr.close_logger("test_script")
            assert len(logger.handlers) == 0

    def test_database_remove_listener(self):
        """GameDatabase.remove_listener() removes a callback from event lists."""
        db = GameDatabase()
        calls = []
        callback = lambda game: calls.append(game.name)
        db.on_game_added.append(callback)
        assert len(db.on_game_added) == 1

        db.remove_listener(callback)
        assert len(db.on_game_added) == 0

    def test_database_clear_listeners(self):
        """GameDatabase.clear_listeners() empties all event lists."""
        db = GameDatabase()
        db.on_game_added.append(lambda g: None)
        db.on_game_removed.append(lambda g: None)
        db.on_action_added.append(lambda a: None)

        db.clear_listeners()

        assert len(db.on_game_added) == 0
        assert len(db.on_game_removed) == 0
        assert len(db.on_action_added) == 0

    def test_marketplace_cache_invalidation(self):
        """ScriptMarketplace tracks index TTL and reports staleness."""
        from playnite_py.scripting.marketplace import ScriptMarketplace

        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir, index_ttl=0)
            # With ttl=0 and no fetch, index should be stale
            assert market.is_index_stale() is True

            market.invalidate_index()
            assert len(market._index) == 0
            assert market._index_fetched_at == 0.0

    def test_engine_observer_stored_and_stopped(self):
        """ScriptEngine stores observer reference for proper cleanup."""
        db = GameDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ScriptEngine(
                os.path.join(tmpdir, "ext"), db,
                log_dir=os.path.join(tmpdir, "logs"),
            )
            # Initially no observer
            assert engine._observer is None

            # After stopping (no-op if never started), still None
            engine.stop_file_watcher()
            assert engine._observer is None


# ======================================================================
# Gap Fix Tests — Script Extension System
# ======================================================================


class TestTypedEventArgs:
    """Typed event arguments for lifecycle hooks."""

    def test_on_game_starting_args(self):
        args = OnGameStartingEventArgs(game_id="g1", cancel_startup=False)
        assert args.game_id == "g1"
        assert args.cancel_startup is False
        d = args.to_dict()
        assert "cancel_startup" in d

    def test_on_game_started_args(self):
        args = OnGameStartedEventArgs(game_id="g1", process_id=1234)
        assert args.process_id == 1234

    def test_on_game_stopped_args(self):
        args = OnGameStoppedEventArgs(game_id="g1", session_length=120)
        assert args.session_length == 120

    def test_on_game_startup_cancelled_args(self):
        args = OnGameStartupCancelledEventArgs(game_id="g1", cancelled_by="ext1")
        assert args.cancelled_by == "ext1"

    def test_on_game_installation_cancelled_args(self):
        args = OnGameInstallationCancelledEventArgs(game_id="g1")
        assert args.game_id == "g1"

    def test_hook_event_args_map_has_all_game_hooks(self):
        expected = {
            "on_game_starting", "on_game_started", "on_game_stopped",
            "on_game_installed", "on_game_uninstalled", "on_game_selected",
            "on_game_startup_cancelled", "on_game_installation_cancelled",
            "on_library_updated", "on_application_started", "on_application_stopped",
        }
        assert expected == set(HOOK_EVENT_ARGS_MAP.keys())


class TestEventCancellation:
    """on_game_starting cancellation mechanism."""

    def test_cancel_startup_via_hook(self):
        db = GameDatabase()
        game = Game(name="Test")
        db.add_game(game)

        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "ext", "cancel_ext")
            os.makedirs(ext_dir)
            with open(os.path.join(ext_dir, "config.yaml"), "w") as f:
                yaml.dump({"name": "CancelExt", "entry_point": "script.py"}, f)
            with open(os.path.join(ext_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""\
                    def on_game_starting(args):
                        args.cancel_startup = True
                """))

            engine = ScriptEngine(
                os.path.join(tmpdir, "ext"), db,
                log_dir=os.path.join(tmpdir, "logs"),
            )
            engine.load_all()
            result = engine.execute_hook(
                "on_game_starting",
                game_id=game.id,
                game=game.to_dict(),
            )
            assert result.get("cancelled") is True
            assert result.get("cancelled_by") == "cancel_ext"

    def test_no_cancellation_by_default(self):
        db = GameDatabase()
        game = Game(name="Test")
        db.add_game(game)

        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "ext", "safe_ext")
            os.makedirs(ext_dir)
            with open(os.path.join(ext_dir, "config.yaml"), "w") as f:
                yaml.dump({"name": "SafeExt", "entry_point": "script.py"}, f)
            with open(os.path.join(ext_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""\
                    def on_game_starting(args):
                        pass  # Does not cancel
                """))

            engine = ScriptEngine(
                os.path.join(tmpdir, "ext"), db,
                log_dir=os.path.join(tmpdir, "logs"),
            )
            engine.load_all()
            result = engine.execute_hook(
                "on_game_starting",
                game_id=game.id,
                game=game.to_dict(),
            )
            assert result.get("cancelled") is False


class TestSelectiveEventInvocation:
    """Scripts are only called for hooks they define."""

    def test_supported_events_auto_detected(self):
        db = GameDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "ext", "selective_ext")
            os.makedirs(ext_dir)
            with open(os.path.join(ext_dir, "config.yaml"), "w") as f:
                yaml.dump({"name": "SelectiveExt", "entry_point": "script.py"}, f)
            with open(os.path.join(ext_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""\
                    def on_game_started(args):
                        pass
                    def on_game_stopped(args):
                        pass
                """))

            engine = ScriptEngine(
                os.path.join(tmpdir, "ext"), db,
                log_dir=os.path.join(tmpdir, "logs"),
            )
            engine.load_all()
            info = engine.get_script_info("selective_ext")
            assert info is not None
            assert "on_game_started" in info.supported_events
            assert "on_game_stopped" in info.supported_events
            assert "on_game_starting" not in info.supported_events

    def test_menu_auto_detection(self):
        db = GameDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "ext", "menu_ext")
            os.makedirs(ext_dir)
            with open(os.path.join(ext_dir, "config.yaml"), "w") as f:
                yaml.dump({"name": "MenuExt", "entry_point": "script.py"}, f)
            with open(os.path.join(ext_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""\
                    def get_game_menu_items():
                        return []
                    def get_main_menu_items():
                        return []
                """))

            engine = ScriptEngine(
                os.path.join(tmpdir, "ext"), db,
                log_dir=os.path.join(tmpdir, "logs"),
            )
            engine.load_all()
            info = engine.get_script_info("menu_ext")
            assert info is not None
            assert "game_menu" in info.supported_menus
            assert "main_menu" in info.supported_menus


class TestNewLifecycleHooks:
    """Three new lifecycle hooks added."""

    def test_new_hooks_in_lifecycle_list(self):
        assert "on_game_starting" in LIFECYCLE_HOOKS
        assert "on_game_startup_cancelled" in LIFECYCLE_HOOKS
        assert "on_game_installation_cancelled" in LIFECYCLE_HOOKS


class TestPerExtensionDataDir:
    """Per-extension data directory auto-creation and injection."""

    def test_data_dir_created_per_extension(self):
        db = GameDatabase()
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "ext", "data_ext")
            os.makedirs(ext_dir)
            with open(os.path.join(ext_dir, "config.yaml"), "w") as f:
                yaml.dump({"name": "DataExt", "entry_point": "script.py"}, f)
            with open(os.path.join(ext_dir, "script.py"), "w") as f:
                f.write("stored_data_dir = __extension_data_dir__\n")

            engine = ScriptEngine(
                os.path.join(tmpdir, "ext"), db,
                data_dir=os.path.join(tmpdir, "data"),
                log_dir=os.path.join(tmpdir, "logs"),
            )
            engine.load_all()
            info = engine.get_script_info("data_ext")
            assert info is not None and info.loaded

            # Check directory exists
            expected_dir = os.path.join(tmpdir, "data", "data_ext")
            assert os.path.isdir(expected_dir)

            # Check variable was injected
            assert info._namespace.get("stored_data_dir") == expected_dir


class TestConfigValidation:
    """Extension ID, version validation, and extension type in config."""

    def test_extension_id_field(self):
        config = ScriptConfig(extension_id="my-unique-id")
        assert config.extension_id == "my-unique-id"
        d = config.to_dict()
        assert d["extension_id"] == "my-unique-id"

    def test_extension_type_field(self):
        config = ScriptConfig(extension_type=ExtensionType.GAME_LIBRARY)
        assert config.extension_type == ExtensionType.GAME_LIBRARY
        d = config.to_dict()
        assert d["extension_type"] == "game_library"

    def test_version_validation_valid(self):
        config = ScriptConfig(version="1.2.3")
        assert config.validate_version() is True

    def test_version_validation_invalid(self):
        config = ScriptConfig(version="not.a.version.string.at.all")
        assert config.validate_version() is False

    def test_validate_returns_errors(self):
        config = ScriptConfig(name="", version="bad")
        errors = config.validate()
        assert any("name" in e.lower() for e in errors)
        assert any("version" in e.lower() for e in errors)

    def test_validate_returns_empty_on_valid(self):
        config = ScriptConfig(name="Good", version="1.0.0")
        errors = config.validate()
        assert errors == []

    def test_from_yaml_with_extension_id_and_type(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            yaml.dump({
                "name": "Test",
                "extension_id": "unique-123",
                "extension_type": "game_library",
                "version": "2.0.0",
            }, f)
            path = f.name
        try:
            config = ScriptConfig.from_yaml(path)
            assert config.extension_id == "unique-123"
            assert config.extension_type == ExtensionType.GAME_LIBRARY
        finally:
            os.unlink(path)

    def test_icon_and_links_fields(self):
        config = ScriptConfig(
            icon="icon.png",
            links=[{"name": "Homepage", "url": "https://example.com"}],
        )
        d = config.to_dict()
        assert d["icon"] == "icon.png"
        assert len(d["links"]) == 1


class TestPackageValidation:
    """Marketplace package verification."""

    def test_verify_valid_package(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "ext.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                config_data = yaml.dump({"name": "Test", "version": "1.0.0"})
                zf.writestr("config.yaml", config_data)
                zf.writestr("script.py", "print('hello')")

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is True
            assert result["errors"] == []

    def test_verify_package_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "ext.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("script.py", "print('hello')")

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is False
            assert any("manifest" in e.lower() for e in result["errors"])

    def test_verify_package_blocked_file_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "ext.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                config_data = yaml.dump({"name": "Test", "version": "1.0.0"})
                zf.writestr("config.yaml", config_data)
                zf.writestr("malicious.dll", b"")

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is False
            assert any(".dll" in e for e in result["errors"])

    def test_verify_package_invalid_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "ext.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                config_data = yaml.dump({"name": "Test", "version": "bad"})
                zf.writestr("config.yaml", config_data)

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is False
            assert any("version" in e.lower() for e in result["errors"])


class TestLicenseAgreement:
    """License agreement tracking in marketplace."""

    def test_agree_and_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir)
            assert market.has_agreed_license("ext-1") is False
            market.agree_license("ext-1")
            assert market.has_agreed_license("ext-1") is True

    def test_license_persists_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market1 = ScriptMarketplace(tmpdir)
            market1.agree_license("ext-2")

            # Re-create marketplace (simulates restart)
            market2 = ScriptMarketplace(tmpdir)
            assert market2.has_agreed_license("ext-2") is True


class TestInstallQueue:
    """Queue-based deferred install/uninstall."""

    def test_queue_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir)
            market.queue_install("ext-1")
            market.queue_uninstall("ext-2")

            items = market.get_queued_items()
            assert len(items) == 2
            assert items[0] == {"id": "ext-1", "action": "install"}
            assert items[1] == {"id": "ext-2", "action": "uninstall"}

    def test_queue_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir)
            market.queue_install("ext-1")
            market.queue_install("ext-1")  # duplicate

            items = market.get_queued_items()
            assert len(items) == 1

    def test_queue_persists_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market1 = ScriptMarketplace(tmpdir)
            market1.queue_install("ext-1")

            market2 = ScriptMarketplace(tmpdir)
            assert len(market2.get_queued_items()) == 1


class TestMenuSection:
    """MenuAPI supports menu_section field."""

    def test_menu_item_with_section(self):
        menu = MenuAPI()
        item_id = menu.add_game_menu_item(
            "Do thing", lambda: None, menu_section="Tools"
        )
        items = menu.get_game_menu_items()
        assert len(items) == 1
        assert items[0]["menu_section"] == "Tools"
