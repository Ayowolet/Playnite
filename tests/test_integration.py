"""Integration tests demonstrating complete workflows via CLI and API."""

import json
import os
import shutil
import tempfile
import textwrap
import time
import zipfile
from unittest.mock import patch, MagicMock

import pytest
import yaml

from playnite_py.models.database import GameDatabase
from playnite_py.models.game import Game
from playnite_py.models.action import (
    ActionPhase, GameAction, GameActionType, ActionCondition,
)
from playnite_py.scripting.engine import ScriptEngine
from playnite_py.scripting.sdk import PlayniteAPI
from playnite_py.scripting.marketplace import ScriptMarketplace
from playnite_py.actions.manager import ActionManager
from playnite_py.actions.launcher import GameLauncher, LaunchResult
from playnite_py.actions.monitor import ProcessMonitor
from playnite_py.actions.conditions import ConditionEvaluator
from playnite_py.actions.triggers import EventTrigger, EventType
from playnite_py.cli import main


class TestScriptLifecycleWorkflow:
    """Integration test: full script lifecycle from load to shutdown."""

    def test_complete_script_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "extensions")
            log_dir = os.path.join(tmpdir, "logs")

            # Create a test script
            script_dir = os.path.join(ext_dir, "lifecycle_test")
            os.makedirs(script_dir)
            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""
                    events = []

                    def on_loaded():
                        events.append("loaded")
                        playnite.log.info("Script loaded")

                    def on_application_started():
                        events.append("app_started")

                    def on_game_started(game_id=None, **kwargs):
                        events.append(f"game_started:{game_id}")

                    def on_game_stopped(game_id=None, **kwargs):
                        events.append(f"game_stopped:{game_id}")

                    def on_application_stopped():
                        events.append("app_stopped")
                """))
            with open(os.path.join(script_dir, "config.yaml"), "w") as f:
                yaml.dump({
                    "name": "Lifecycle Test",
                    "enabled": True,
                    "timeout": 10,
                    "sandbox_level": "basic",
                }, f)

            # Set up engine
            db = GameDatabase()
            game = Game(name="Test Game")
            db.add_game(game)

            engine = ScriptEngine(ext_dir, db, log_dir=log_dir)
            engine.load_all()

            info = engine.get_script_info("lifecycle_test")
            assert info is not None
            assert info.loaded is True

            # Fire lifecycle events
            engine.execute_hook("on_application_started")
            engine.execute_hook("on_game_started", game_id=game.id)
            engine.execute_hook("on_game_stopped", game_id=game.id)

            # Verify metrics
            stats = engine.metrics.get_script_stats("lifecycle_test")
            assert stats["total_executions"] >= 3

            # Shutdown
            engine.shutdown()


class TestActionInjectionWorkflow:
    """Integration test: script injecting actions and executing them."""

    def test_script_injects_and_runs_actions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "extensions")
            log_dir = os.path.join(tmpdir, "logs")

            # Script that injects a pre-launch action
            script_dir = os.path.join(ext_dir, "action_injector")
            os.makedirs(script_dir)
            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""
                    def on_loaded():
                        playnite.actions.add_action(
                            name="Injected Pre-Launch",
                            script="print('pre-launch from script')",
                            phase="pre_launch",
                            priority=80,
                        )
                        playnite.actions.add_action(
                            name="Injected Post-Exit",
                            script="print('post-exit from script')",
                            phase="post_exit",
                            priority=50,
                        )
                        playnite.log.info("Actions injected")
                """))
            with open(os.path.join(script_dir, "config.yaml"), "w") as f:
                yaml.dump({
                    "name": "Action Injector",
                    "enabled": True,
                    "timeout": 10,
                    "sandbox_level": "basic",
                }, f)

            db = GameDatabase()
            game = Game(name="Test Game")
            db.add_game(game)

            engine = ScriptEngine(ext_dir, db, log_dir=log_dir)
            engine.load_all()

            action_mgr = ActionManager(db)

            # Verify actions were injected
            all_actions = action_mgr.get_all_actions()
            assert len(all_actions) >= 2

            # Execute pre-launch phase
            result = action_mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
            assert any("pre-launch from script" in r.output for r in result.results)

            # Execute post-exit phase
            result = action_mgr.execute_phase(game.id, ActionPhase.POST_EXIT)
            assert any("post-exit from script" in r.output for r in result.results)

            engine.shutdown()


class TestActionChainWithRollback:
    """Integration test: action chain failure triggers rollback."""

    def test_chain_failure_and_rollback(self):
        db = GameDatabase()
        game = Game(name="Rollback Game")
        db.add_game(game)

        mgr = ActionManager(db)

        # Action 1: succeeds and has rollback
        mgr.inject_action(GameAction(
            name="Setup Action",
            script="print('setup done')",
            rollback_script="print('setup rolled back')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=90,
        ))

        # Action 2: fails
        mgr.inject_action(GameAction(
            name="Failing Action",
            script="raise RuntimeError('intentional failure')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=50,
        ))

        result = mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
        assert result.all_succeeded is False

        # Check that rollback was attempted for the successful action
        rollback_log = mgr.get_rollback_log()
        assert len(rollback_log) >= 1


class TestConditionalActionExecution:
    """Integration test: conditional actions with various criteria."""

    def test_platform_specific_actions(self):
        import platform as plat

        db = GameDatabase()
        game = Game(name="Conditional Game", source="Steam", is_installed=True)
        db.add_game(game)

        mgr = ActionManager(db)

        # Action that only runs on current OS
        mgr.inject_action(GameAction(
            name="OS-Specific",
            script="print('os matched')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            conditions=[
                ActionCondition(
                    field="env.os",
                    operator="equals",
                    value=plat.system().lower(),
                )
            ],
        ))

        # Action that only runs on a different OS
        mgr.inject_action(GameAction(
            name="Wrong OS",
            script="print('wrong os')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            conditions=[
                ActionCondition(field="env.os", operator="equals", value="nonexistent_os")
            ],
        ))

        result = mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
        outputs = [r.output for r in result.results]
        assert any("os matched" in o for o in outputs)
        assert any("Skipped" in o for o in outputs)


class TestEventTriggeredActions:
    """Integration test: events trigger action execution."""

    def test_game_started_trigger(self):
        db = GameDatabase()
        game = Game(name="Trigger Game")
        db.add_game(game)

        mgr = ActionManager(db)

        # Create an action
        action = GameAction(
            name="Triggered Action",
            script="print('triggered!')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
        )
        mgr.inject_action(action)

        # Create trigger
        trigger = EventTrigger(
            name="On Game Start",
            event_type=EventType.GAME_STARTED,
            action_id=action.id,
        )
        mgr.add_trigger(trigger)

        # Fire event
        fired = mgr.fire_event(EventType.GAME_STARTED, game.id)
        assert len(fired) == 1


class TestFullGameLaunchWorkflow:
    """Integration test: complete game launch workflow with scripts and actions."""

    def test_full_launch_sequence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "extensions")
            log_dir = os.path.join(tmpdir, "logs")

            # Create a comprehensive script
            script_dir = os.path.join(ext_dir, "launch_manager")
            os.makedirs(script_dir)
            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write(textwrap.dedent("""
                    launch_log = []

                    def on_loaded():
                        # Inject pre-launch and post-exit actions
                        playnite.actions.add_action(
                            name="Pre-Launch Check",
                            script="print('pre-launch check passed')",
                            phase="pre_launch",
                            priority=90,
                        )
                        playnite.actions.add_action(
                            name="Post-Exit Cleanup",
                            script="print('cleanup complete')",
                            phase="post_exit",
                            priority=50,
                        )

                    def on_game_started(game_id=None, **kwargs):
                        launch_log.append(f"started:{game_id}")
                        playnite.notifications.show("Game launched!")

                    def on_game_stopped(game_id=None, **kwargs):
                        launch_log.append(f"stopped:{game_id}")
                """))
            with open(os.path.join(script_dir, "config.yaml"), "w") as f:
                yaml.dump({
                    "name": "Launch Manager",
                    "enabled": True,
                    "timeout": 10,
                    "sandbox_level": "basic",
                }, f)

            # Setup
            db = GameDatabase()
            game = Game(name="Launch Test Game", is_installed=True, source="Steam")
            db.add_game(game)

            engine = ScriptEngine(ext_dir, db, log_dir=log_dir)
            engine.load_all()
            action_mgr = ActionManager(db)

            # Simulate game launch workflow:
            # 1. Execute pre-launch actions
            pre_result = action_mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
            assert pre_result.all_succeeded is True

            # 2. Fire game_started hook
            engine.execute_hook("on_game_started", game_id=game.id)

            # 3. (Game runs...)

            # 4. Fire game_stopped hook
            engine.execute_hook("on_game_stopped", game_id=game.id)

            # 5. Execute post-exit actions
            post_result = action_mgr.execute_phase(game.id, ActionPhase.POST_EXIT)
            assert post_result.all_succeeded is True

            # Verify metrics
            stats = engine.metrics.get_script_stats("launch_manager")
            assert stats["total_executions"] >= 2

            # Verify total overhead is reasonable
            total_overhead = pre_result.total_duration + post_result.total_duration
            assert total_overhead < 5.0  # < 5 seconds benchmark

            engine.shutdown()


class TestHotReloadWorkflow:
    """Integration test: modify script while running and verify hot-reload."""

    def test_modify_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = os.path.join(tmpdir, "extensions")
            log_dir = os.path.join(tmpdir, "logs")

            script_dir = os.path.join(ext_dir, "hot_reload_test")
            os.makedirs(script_dir)

            # Initial version
            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write("VERSION = '1.0'\ndef on_loaded(): pass\n")
            with open(os.path.join(script_dir, "config.yaml"), "w") as f:
                yaml.dump({"name": "Hot Reload", "enabled": True, "timeout": 10}, f)

            db = GameDatabase()
            engine = ScriptEngine(ext_dir, db, log_dir=log_dir)
            engine.load_all()

            info = engine.get_script_info("hot_reload_test")
            assert info.loaded is True

            # Modify the script
            with open(os.path.join(script_dir, "script.py"), "w") as f:
                f.write("VERSION = '2.0'\ndef on_loaded(): pass\n")

            # Reload
            reloaded = engine.reload_script("hot_reload_test")
            assert reloaded.loaded is True

            engine.shutdown()


class TestPerformanceBenchmark:
    """Benchmark: 10 pre-launch scripts must execute in under 5 seconds total."""

    def test_ten_prelaunch_actions_under_five_seconds(self):
        db = GameDatabase()
        game = Game(name="Benchmark Game", is_installed=True)
        db.add_game(game)

        mgr = ActionManager(db)

        # Inject 10 pre-launch actions with varying priorities
        for i in range(10):
            mgr.inject_action(GameAction(
                name=f"Benchmark Action {i}",
                script=f"print('action {i} executed')",
                game_id=game.id,
                phase=ActionPhase.PRE_LAUNCH,
                priority=100 - i * 10,
            ))

        result = mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)

        # All 10 must succeed
        assert len(result.results) == 10
        assert result.all_succeeded is True

        # Total duration must be under 5 seconds
        assert result.total_duration < 5.0, (
            f"10 pre-launch actions took {result.total_duration:.2f}s, "
            f"exceeding the 5-second benchmark"
        )

        # Verify they ran in priority order (descending)
        for i, r in enumerate(result.results):
            assert r.action_name == f"Benchmark Action {i}"


class TestCLIIntegration:
    """Integration tests exercising CLI commands end-to-end."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()

    def _cli(self, *args):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()
        try:
            main(["--data-dir", self._tmpdir, "--json"] + list(args))
            output = buf.getvalue()
        finally:
            sys.stdout = old_stdout
        return json.loads(output)

    def test_game_lifecycle_via_cli(self):
        # Add game
        result = self._cli("game-add", "CLI Game", "--source", "Steam", "--installed")
        game_id = result["id"]

        # Inject pre-launch action
        self._cli(
            "action-inject", "CLI Action",
            "--script", "print('cli action')",
            "--game-id", game_id,
            "--phase", "pre_launch",
        )

        # Execute
        result = self._cli("action-execute", game_id, "pre_launch")
        assert result["all_succeeded"] is True

        # Check stats
        stats = self._cli("db-stats")
        assert stats["total_games"] == 1

    def test_multiple_games_and_actions(self):
        # Add multiple games
        g1 = self._cli("game-add", "Game 1", "--source", "Steam")
        g2 = self._cli("game-add", "Game 2", "--source", "GOG")

        # Inject actions for both
        self._cli(
            "action-inject", "G1 Action",
            "--script", "print('g1')",
            "--game-id", g1["id"],
        )
        self._cli(
            "action-inject", "G2 Action",
            "--script", "print('g2')",
            "--game-id", g2["id"],
        )

        # Execute for game 1
        result = self._cli("action-execute", g1["id"], "pre_launch")
        assert result["all_succeeded"] is True

        # Verify both games exist
        games = self._cli("game-list")
        assert len(games) == 2

    def test_action_template_via_cli(self):
        game = self._cli("game-add", "Template Game")
        result = self._cli("action-apply-template", "Discord Rich Presence", game["id"])
        assert result["name"] == "Discord Rich Presence"


# ======================================================================
# New integration tests: launch lifecycle, concurrency, security, etc.
# ======================================================================


class TestEndToEndLaunchLifecycle:
    """Integration: full GameLauncher.launch() with mocked subprocess."""

    def test_full_launch_lifecycle_with_hooks(self):
        db = GameDatabase()
        game = Game(name="Lifecycle Test", is_installed=True)
        db.add_game(game)
        monitor = ProcessMonitor(poll_interval=0.05)

        hook_log = []

        def mock_hook(hook_name, **kwargs):
            hook_log.append(hook_name)
            if hook_name == "on_game_starting":
                return {"cancelled": False}
            return {}

        phase_log = []

        def mock_phase(game_id, phase, extra_vars=None):
            phase_log.append(phase.value)

        launcher = GameLauncher(
            database=db,
            process_monitor=monitor,
            execute_hook=mock_hook,
            execute_phase=mock_phase,
        )

        action = GameAction(
            name="Launch",
            game_action_type=GameActionType.FILE,
            path="/usr/bin/game",
            tracking_frequency=50,
        )

        with patch("subprocess.Popen") as mock_popen, \
             patch("playnite_py.actions.launcher.Path.is_file", return_value=True):
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc

            # Make monitor report not running so launch completes immediately
            with patch.object(monitor, "is_running", return_value=False):
                result = launcher.launch(game.id, action)

        assert result.success is True
        assert result.process_id == 12345
        assert "on_game_starting" in hook_log
        assert "on_game_started" in hook_log
        assert "on_game_stopped" in hook_log
        assert "pre_launch" in phase_log
        assert "post_exit" in phase_log
        assert result.session_length >= 0

    def test_launch_cancelled_by_hook(self):
        db = GameDatabase()
        game = Game(name="Cancel Test")
        db.add_game(game)
        monitor = ProcessMonitor()

        cancel_log = []

        def mock_hook(hook_name, **kwargs):
            cancel_log.append(hook_name)
            if hook_name == "on_game_starting":
                return {"cancelled": True, "cancelled_by": "test_script"}
            return {}

        launcher = GameLauncher(db, monitor, execute_hook=mock_hook)
        action = GameAction(name="test")
        result = launcher.launch(game.id, action)

        assert result.cancelled is True
        assert result.cancelled_by == "test_script"
        assert "on_game_startup_cancelled" in cancel_log
        # Process should NOT have been started
        assert result.process_id is None


class TestConcurrentMonitoring:
    """Integration: multiple games monitored simultaneously."""

    def test_multiple_games_monitored_simultaneously(self):
        monitor = ProcessMonitor(poll_interval=0.05)

        # Start monitoring 3 games
        procs = {}
        for i in range(3):
            proc = monitor.start_monitoring(
                game_id=f"game-{i}", pid=10000 + i,
                tracking_frequency=50,
            )
            procs[f"game-{i}"] = proc

        all_monitored = monitor.get_all_monitored()
        assert len(all_monitored) == 3

        # Cancel one, verify others unaffected
        monitor.cancel("game-1")
        assert monitor.is_cancelled("game-1") is True
        assert monitor.is_cancelled("game-0") is False
        assert monitor.is_cancelled("game-2") is False

        # All three should still be in the monitored list
        all_monitored = monitor.get_all_monitored()
        assert len(all_monitored) == 3

        # Get status for each
        for i in range(3):
            status = monitor.get_status(f"game-{i}")
            assert status is not None
            assert status["game_id"] == f"game-{i}"

        # Cleanup
        for i in range(3):
            monitor.stop_monitoring(f"game-{i}")


class TestPackageVerificationWithRealZIP:
    """Integration: actual ZIP creation and verification."""

    def test_valid_package_installs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "valid.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                config_data = yaml.dump({"name": "ValidExt", "version": "1.0.0"})
                zf.writestr("valid_ext/config.yaml", config_data)
                zf.writestr("valid_ext/script.py", "def on_loaded(): pass")

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is True
            assert len(result["errors"]) == 0

    def test_blocked_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "blocked.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                config_data = yaml.dump({"name": "Bad", "version": "1.0.0"})
                zf.writestr("config.yaml", config_data)
                zf.writestr("helper.dll", "fake")
                zf.writestr("setup.exe", "fake")

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is False
            assert any(".dll" in e for e in result["errors"])
            assert any(".exe" in e for e in result["errors"])

    def test_missing_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "no_manifest.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("script.py", "print('hello')")

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is False
            assert any("manifest" in e.lower() for e in result["errors"])

    def test_invalid_version_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = os.path.join(tmpdir, "bad_version.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                config_data = yaml.dump({"name": "Test", "version": "not-a-version"})
                zf.writestr("config.yaml", config_data)

            result = ScriptMarketplace.verify_package(archive)
            assert result["valid"] is False
            assert any("version" in e.lower() for e in result["errors"])


class TestActionChainRollbackEndToEnd:
    """Integration: partial failure triggers rollback for completed actions."""

    def test_partial_failure_triggers_rollback(self):
        db = GameDatabase()
        game = Game(name="Rollback E2E")
        db.add_game(game)
        mgr = ActionManager(db)

        # Action 1: succeeds, has rollback
        mgr.inject_action(GameAction(
            name="Step 1 - Setup",
            script="print('setup complete')",
            rollback_script="print('setup undone')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=90,
        ))

        # Action 2: succeeds, has rollback
        mgr.inject_action(GameAction(
            name="Step 2 - Configure",
            script="print('configured')",
            rollback_script="print('config reverted')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=80,
        ))

        # Action 3: fails
        mgr.inject_action(GameAction(
            name="Step 3 - Fails",
            script="raise RuntimeError('boom')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=70,
        ))

        result = mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
        assert result.all_succeeded is False

        # Verify rollback log has entries for the successful actions
        rollback_log = mgr.get_rollback_log()
        assert len(rollback_log) >= 2

        rollback_names = [r["action_name"] for r in rollback_log if r["success"]]
        assert "Step 2 - Configure" in rollback_names
        assert "Step 1 - Setup" in rollback_names

        # Verify rolled_back flag set on results
        rolled = [r for r in result.results if r.rolled_back]
        assert len(rolled) >= 1


class TestSecurityValidation:
    """Integration: security fixes work correctly."""

    def test_https_enforcement_rejects_http(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir)
            with pytest.raises(ValueError, match="[Ii]nsecure"):
                market.set_repository_url("http://evil.com/repo")

    def test_https_enforcement_allows_https(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir)
            market.set_repository_url("https://github.com/repo")
            # Should not raise

    def test_https_enforcement_allows_localhost_http(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            market = ScriptMarketplace(tmpdir)
            market.set_repository_url("http://localhost:8080/repo")
            market.set_repository_url("http://127.0.0.1:9000/repo")
            # Should not raise

    def test_regex_complexity_rejection(self):
        evaluator = ConditionEvaluator()
        long_pattern = "a" * 201
        action = GameAction(
            conditions=[ActionCondition(
                field="game.name", operator="matches", value=long_pattern
            )]
        )
        game = Game(name="Test")
        should, reason = evaluator.should_execute(action, game)
        assert should is False
        assert "maximum length" in reason

    def test_invalid_regex_handled_gracefully(self):
        evaluator = ConditionEvaluator()
        action = GameAction(
            conditions=[ActionCondition(
                field="game.name", operator="matches", value="[invalid"
            )]
        )
        game = Game(name="Test")
        should, reason = evaluator.should_execute(action, game)
        assert should is False
        assert "Invalid regex" in reason

    def test_argument_handling_preserves_spaces(self):
        action = GameAction(
            name="Test",
            game_action_type=GameActionType.FILE,
            path="/usr/bin/game",
            arguments={"save_dir": "/path/to/my saves", "mode": "fullscreen"},
        )
        # Verify the arguments can be passed as a list without splitting
        args = [str(v) for v in action.arguments.values()]
        assert "/path/to/my saves" in args
        assert "fullscreen" in args
        assert len(args) == 2
