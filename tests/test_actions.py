"""Tests for the action injection, chain execution, conditions, and templates."""

import os
import tempfile

import pytest

from playnite_py.models.action import (
    ActionChainResult, ActionCondition, ActionPhase, ActionPriority,
    ActionResult, ActionType, GameAction, GameActionType, TrackingMode,
)
from playnite_py.models.database import GameDatabase
from playnite_py.models.game import Game, Platform
from playnite_py.actions.chain import ActionChainExecutor
from playnite_py.actions.conditions import ConditionEvaluator
from playnite_py.actions.launcher import GameLauncher, LaunchResult
from playnite_py.actions.manager import ActionManager
from playnite_py.actions.monitor import ProcessMonitor, MonitoredProcess
from playnite_py.actions.profiles import ActionProfile, ProfileCriteria, ProfileManager
from playnite_py.actions.rollback import RollbackManager
from playnite_py.actions.scheduler import ActionScheduler
from playnite_py.actions.templates import ActionTemplateRegistry
from playnite_py.actions.triggers import EventTrigger, EventType, TriggerManager
from playnite_py.actions.variables import VariableResolver


# ======================================================================
# Variable Resolution
# ======================================================================

class TestVariableResolver:
    def test_resolve_game_variables(self):
        resolver = VariableResolver()
        game = Game(name="Test Game", source="Steam", playtime=3600)
        ctx = resolver.build_context(game)
        assert ctx["game.name"] == "Test Game"
        assert ctx["game.source"] == "Steam"
        assert ctx["game.playtime"] == "3600"

    def test_resolve_env_variables(self):
        resolver = VariableResolver()
        ctx = resolver.build_context()
        assert "env.os" in ctx
        assert "env.home" in ctx

    def test_resolve_template(self):
        resolver = VariableResolver()
        game = Game(name="My Game")
        ctx = resolver.build_context(game)
        result = resolver.resolve("Playing {game.name} on {env.os}", ctx)
        assert "My Game" in result

    def test_unresolved_variables_preserved(self):
        resolver = VariableResolver()
        ctx = resolver.build_context()
        result = resolver.resolve("{unknown.var}", ctx)
        assert result == "{unknown.var}"

    def test_custom_variables(self):
        resolver = VariableResolver()
        resolver.set_custom_variable("custom", "value")
        ctx = resolver.build_context()
        assert ctx["custom"] == "value"


# ======================================================================
# Condition Evaluation
# ======================================================================

class TestConditionEvaluator:
    def setup_method(self):
        self.evaluator = ConditionEvaluator()

    def test_no_conditions(self):
        action = GameAction(name="test")
        should, reason = self.evaluator.should_execute(action)
        assert should is True

    def test_disabled_action(self):
        action = GameAction(name="test", enabled=False)
        should, reason = self.evaluator.should_execute(action)
        assert should is False

    def test_equals_condition(self):
        action = GameAction(
            conditions=[ActionCondition(field="game.source", operator="equals", value="Steam")]
        )
        game = Game(source="Steam")
        should, _ = self.evaluator.should_execute(action, game)
        assert should is True

        game2 = Game(source="GOG")
        should, _ = self.evaluator.should_execute(action, game2)
        assert should is False

    def test_contains_condition(self):
        action = GameAction(
            conditions=[ActionCondition(field="game.name", operator="contains", value="RPG")]
        )
        game = Game(name="Best RPG Ever")
        should, _ = self.evaluator.should_execute(action, game)
        assert should is True

        game2 = Game(name="Racing Game")
        should, _ = self.evaluator.should_execute(action, game2)
        assert should is False

    def test_gt_condition(self):
        action = GameAction(
            conditions=[ActionCondition(field="game.playtime", operator="gt", value="3600")]
        )
        game = Game(playtime=7200)
        should, _ = self.evaluator.should_execute(action, game)
        assert should is True

        game2 = Game(playtime=1800)
        should, _ = self.evaluator.should_execute(action, game2)
        assert should is False

    def test_is_true_condition(self):
        action = GameAction(
            conditions=[ActionCondition(field="game.is_installed", operator="is_true", value="")]
        )
        game = Game(is_installed=True)
        should, _ = self.evaluator.should_execute(action, game)
        assert should is True

    def test_multiple_conditions_all_must_pass(self):
        action = GameAction(
            conditions=[
                ActionCondition(field="game.source", operator="equals", value="Steam"),
                ActionCondition(field="game.is_installed", operator="is_true", value=""),
            ]
        )
        game = Game(source="Steam", is_installed=True)
        should, _ = self.evaluator.should_execute(action, game)
        assert should is True

        game2 = Game(source="Steam", is_installed=False)
        should, _ = self.evaluator.should_execute(action, game2)
        assert should is False


# ======================================================================
# Action Chain Execution
# ======================================================================

class TestActionChainExecutor:
    def setup_method(self):
        self.db = GameDatabase()
        self.game = Game(name="Test Game", is_installed=True)
        self.db.add_game(self.game)
        self.executor = ActionChainExecutor(self.db)

    def test_empty_chain(self):
        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert result.all_succeeded is True
        assert len(result.results) == 0

    def test_single_action(self):
        action = GameAction(
            name="Print Test",
            script="print('hello from action')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
        )
        self.db.add_action(action)

        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert len(result.results) == 1
        assert result.results[0].success is True
        assert "hello from action" in result.results[0].output

    def test_priority_ordering(self):
        self.db.add_action(GameAction(
            name="Low Priority",
            script="print('low')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=10,
        ))
        self.db.add_action(GameAction(
            name="High Priority",
            script="print('high')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
            priority=90,
        ))

        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert len(result.results) == 2
        # High priority should execute first
        assert result.results[0].action_name == "High Priority"
        assert result.results[1].action_name == "Low Priority"

    def test_action_failure_captured(self):
        self.db.add_action(GameAction(
            name="Failing Action",
            script="raise RuntimeError('intentional failure')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
        ))

        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert result.all_succeeded is False
        assert "intentional failure" in result.results[0].error

    def test_conditional_action_skip(self):
        self.db.add_action(GameAction(
            name="Conditional",
            script="print('should not run')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
            conditions=[ActionCondition(field="game.source", operator="equals", value="Steam")],
        ))
        # Game has empty source, so condition should fail
        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert len(result.results) == 1
        assert "Skipped" in result.results[0].output

    def test_global_actions_included(self):
        self.db.add_action(GameAction(
            name="Global Action",
            script="print('global')",
            game_id=None,  # Global
            phase=ActionPhase.PRE_LAUNCH,
        ))

        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert len(result.results) == 1
        assert result.results[0].success is True

    def test_action_with_variables(self):
        self.db.add_action(GameAction(
            name="Variable Action",
            script="print('Game: {game.name}')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
        ))

        result = self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        assert result.results[0].success is True
        assert "Test Game" in result.results[0].output

    def test_action_log(self):
        self.db.add_action(GameAction(
            name="Logged",
            script="print('logged')",
            game_id=self.game.id,
            phase=ActionPhase.PRE_LAUNCH,
        ))
        self.executor.execute_phase(self.game.id, ActionPhase.PRE_LAUNCH)
        log = self.executor.get_action_log()
        assert len(log) == 1


# ======================================================================
# Templates
# ======================================================================

class TestTemplates:
    def test_builtin_templates_exist(self):
        registry = ActionTemplateRegistry()
        templates = registry.get_all()
        assert len(templates) > 0
        names = [t.name for t in templates]
        assert "Close Background Apps" in names
        assert "Discord Rich Presence" in names
        assert "Backup Save Files" in names

    def test_instantiate_template(self):
        registry = ActionTemplateRegistry()
        template = registry.get_template("Discord Rich Presence")
        assert template is not None
        action = template.instantiate("game-123")
        assert action.game_id == "game-123"
        assert action.name == "Discord Rich Presence"
        assert action.is_async is True

    def test_search_templates(self):
        registry = ActionTemplateRegistry()
        results = registry.search(category="Performance")
        assert len(results) >= 1
        results = registry.search(tags=["network"])
        assert any("VPN" in t.name for t in results)


# ======================================================================
# Profiles
# ======================================================================

class TestProfiles:
    def test_criteria_matching(self):
        criteria = ProfileCriteria(sources=["Steam"], is_installed=True)
        game1 = Game(source="Steam", is_installed=True)
        game2 = Game(source="GOG", is_installed=True)
        game3 = Game(source="Steam", is_installed=False)
        assert criteria.matches(game1) is True
        assert criteria.matches(game2) is False
        assert criteria.matches(game3) is False

    def test_profile_manager(self):
        db = GameDatabase()
        db.add_game(Game(name="Steam Game", source="Steam", is_installed=True))
        db.add_game(Game(name="GOG Game", source="GOG", is_installed=True))

        mgr = ProfileManager(db)
        profile = mgr.create_profile(
            name="Steam Pre-launch",
            criteria={"sources": ["Steam"]},
            action_templates=[{
                "name": "Steam Action",
                "script": "print('steam')",
                "phase": "pre_launch",
            }],
        )

        matching = mgr.get_matching_games(profile.id)
        assert len(matching) == 1
        assert matching[0]["name"] == "Steam Game"


# ======================================================================
# Triggers
# ======================================================================

class TestTriggers:
    def test_fire_event(self):
        fired_actions = []
        mgr = TriggerManager(
            action_callback=lambda aid, gid, data: fired_actions.append(aid)
        )
        trigger = EventTrigger(
            name="Test Trigger",
            event_type=EventType.GAME_STARTED,
            action_id="action-123",
        )
        mgr.add_trigger(trigger)

        result = mgr.fire_event(EventType.GAME_STARTED, "game-1")
        assert len(result) == 1
        assert len(fired_actions) == 1
        assert fired_actions[0] == "action-123"

    def test_trigger_with_game_filter(self):
        fired = []
        mgr = TriggerManager(
            action_callback=lambda aid, gid, data: fired.append(gid)
        )
        trigger = EventTrigger(
            event_type=EventType.GAME_STARTED,
            action_id="a1",
            game_id="game-specific",
        )
        mgr.add_trigger(trigger)

        mgr.fire_event(EventType.GAME_STARTED, "other-game")
        assert len(fired) == 0

        mgr.fire_event(EventType.GAME_STARTED, "game-specific")
        assert len(fired) == 1


# ======================================================================
# Rollback
# ======================================================================

class TestRollback:
    def test_rollback_action(self):
        db = GameDatabase()
        action = GameAction(
            name="Rollback Test",
            script="print('action')",
            rollback_script="print('rolled back')",
        )
        db.add_action(action)

        mgr = RollbackManager(db)
        record = mgr.rollback_action(action.id)
        assert record.success is True
        assert "rolled back" in record.output

    def test_rollback_no_script(self):
        db = GameDatabase()
        action = GameAction(name="No Rollback")
        db.add_action(action)

        mgr = RollbackManager(db)
        record = mgr.rollback_action(action.id)
        assert record.success is False
        assert "No rollback script" in record.error

    def test_rollback_missing_action(self):
        db = GameDatabase()
        mgr = RollbackManager(db)
        record = mgr.rollback_action("nonexistent")
        assert record.success is False


# ======================================================================
# Action Manager (facade)
# ======================================================================

class TestActionManager:
    def test_inject_and_execute(self):
        db = GameDatabase()
        game = Game(name="Manager Test")
        db.add_game(game)

        mgr = ActionManager(db)
        action = GameAction(
            name="Injected",
            script="print('injected action')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
        )
        mgr.inject_action(action)

        result = mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
        assert result.all_succeeded is True
        assert len(result.results) == 1

    def test_template_apply(self):
        db = GameDatabase()
        game = Game(name="Template Test")
        db.add_game(game)

        mgr = ActionManager(db)
        action = mgr.apply_template("Discord Rich Presence", game.id)
        assert action is not None
        assert action.game_id == game.id

    def test_action_log(self):
        db = GameDatabase()
        game = Game(name="Log Test")
        db.add_game(game)

        mgr = ActionManager(db)
        mgr.inject_action(GameAction(
            name="Logged",
            script="print('ok')",
            game_id=game.id,
            phase=ActionPhase.PRE_LAUNCH,
        ))
        mgr.execute_phase(game.id, ActionPhase.PRE_LAUNCH)
        log = mgr.get_action_log()
        assert len(log) >= 1


# ======================================================================
# Process Monitor
# ======================================================================

class TestProcessMonitor:
    def test_start_monitoring_returns_process(self):
        monitor = ProcessMonitor(poll_interval=0.1)
        proc = monitor.start_monitoring(game_id="game-1", process_name="fake.exe", pid=99999)
        assert proc.game_id == "game-1"
        assert proc.process_name == "fake.exe"
        assert proc.pid == 99999
        assert proc.crashed is False
        assert proc.restart_count == 0

    def test_stop_monitoring(self):
        monitor = ProcessMonitor(poll_interval=0.1)
        monitor.start_monitoring(game_id="game-1", pid=99999)
        assert monitor.stop_monitoring("game-1") is True
        assert monitor.stop_monitoring("game-1") is False  # Already removed

    def test_get_status(self):
        monitor = ProcessMonitor(poll_interval=0.1)
        monitor.start_monitoring(game_id="game-1", process_name="test.exe", pid=12345)
        status = monitor.get_status("game-1")
        assert status is not None
        assert status["game_id"] == "game-1"
        assert status["process_name"] == "test.exe"
        assert status["pid"] == 12345

    def test_get_status_unknown_game(self):
        monitor = ProcessMonitor(poll_interval=0.1)
        assert monitor.get_status("nonexistent") is None

    def test_get_all_monitored(self):
        monitor = ProcessMonitor(poll_interval=0.1)
        monitor.start_monitoring(game_id="g1", pid=100)
        monitor.start_monitoring(game_id="g2", pid=200)
        all_procs = monitor.get_all_monitored()
        assert len(all_procs) == 2
        game_ids = {p["game_id"] for p in all_procs}
        assert game_ids == {"g1", "g2"}

    def test_on_process_started_callback(self):
        monitor = ProcessMonitor(poll_interval=0.1)
        started = []
        monitor.on_process_started.append(lambda p: started.append(p.game_id))
        monitor.start_monitoring(game_id="game-1", pid=99999)
        assert started == ["game-1"]

    def test_crash_detection_and_callback(self):
        """Test _handle_exit with non-zero exit code triggers crash callback."""
        monitor = ProcessMonitor(poll_interval=0.1)
        crashed = []
        monitor.on_process_crashed.append(lambda p: crashed.append(p.game_id))

        proc = MonitoredProcess(game_id="game-1", pid=99999, max_restarts=0)
        proc.exit_code = 1  # Non-zero = crash
        # Simulate _handle_exit by calling it directly (bypass psutil wait)
        from unittest.mock import patch
        with patch.object(monitor, '_is_pid_alive', return_value=False):
            # Manually set exit code and call the crash path
            proc.ended = None
            # _handle_exit tries psutil.Process.wait, so mock it
            with patch('playnite_py.actions.monitor.HAS_PSUTIL', False):
                monitor._handle_exit(proc)

        # With HAS_PSUTIL=False, exit_code stays None, so no crash detected
        # Instead test the crash path directly
        proc2 = MonitoredProcess(game_id="game-2", pid=88888, max_restarts=0)
        proc2.exit_code = None  # Reset
        proc2.ended = None
        # Directly test the crash logic by setting exit_code before _handle_exit
        # We need to mock psutil to return a non-zero exit code
        import types
        mock_process = types.SimpleNamespace(wait=lambda timeout=0: 1)
        with patch('playnite_py.actions.monitor.HAS_PSUTIL', True), \
             patch('playnite_py.actions.monitor.psutil') as mock_psutil:
            mock_psutil.Process.return_value = mock_process
            monitor._handle_exit(proc2)

        assert proc2.crashed is True
        assert proc2.exit_code == 1
        assert "game-2" in crashed

    def test_auto_restart_on_crash(self):
        """Test auto-restart when crash detected and max_restarts not reached."""
        from unittest.mock import patch
        import types

        monitor = ProcessMonitor(poll_interval=0.1)
        restart_calls = []
        monitor.set_restart_callback(lambda game_id: (restart_calls.append(game_id), 55555)[1])

        restart_triggered = []
        monitor.on_restart_triggered.append(lambda p: restart_triggered.append(p.game_id))

        proc = MonitoredProcess(game_id="game-1", pid=99999, max_restarts=3)

        mock_process = types.SimpleNamespace(wait=lambda timeout=0: 1)
        with patch('playnite_py.actions.monitor.HAS_PSUTIL', True), \
             patch('playnite_py.actions.monitor.psutil') as mock_psutil:
            mock_psutil.Process.return_value = mock_process
            monitor._handle_exit(proc)

        # Should have restarted
        assert restart_calls == ["game-1"]
        assert restart_triggered == ["game-1"]
        assert proc.pid == 55555
        assert proc.restart_count == 1
        assert proc.ended is None  # Reset after restart
        assert proc.crashed is False  # Reset after restart

    def test_no_restart_when_max_reached(self):
        """Test no restart when max_restarts already reached."""
        from unittest.mock import patch
        import types

        monitor = ProcessMonitor(poll_interval=0.1)
        restart_calls = []
        monitor.set_restart_callback(lambda game_id: (restart_calls.append(game_id), 55555)[1])

        proc = MonitoredProcess(game_id="game-1", pid=99999, max_restarts=2, restart_count=2)

        mock_process = types.SimpleNamespace(wait=lambda timeout=0: 1)
        with patch('playnite_py.actions.monitor.HAS_PSUTIL', True), \
             patch('playnite_py.actions.monitor.psutil') as mock_psutil:
            mock_psutil.Process.return_value = mock_process
            monitor._handle_exit(proc)

        # Should NOT have restarted
        assert restart_calls == []
        assert proc.crashed is True
        assert proc.restart_count == 2  # Unchanged

    def test_normal_exit_callback(self):
        """Test on_process_exited fires for exit_code == 0."""
        from unittest.mock import patch
        import types

        monitor = ProcessMonitor(poll_interval=0.1)
        exited = []
        monitor.on_process_exited.append(lambda p: exited.append(p.game_id))

        proc = MonitoredProcess(game_id="game-1", pid=99999)

        mock_process = types.SimpleNamespace(wait=lambda timeout=0: 0)
        with patch('playnite_py.actions.monitor.HAS_PSUTIL', True), \
             patch('playnite_py.actions.monitor.psutil') as mock_psutil:
            mock_psutil.Process.return_value = mock_process
            monitor._handle_exit(proc)

        assert proc.crashed is False
        assert exited == ["game-1"]

    def test_start_stop_monitor_loop(self):
        """Test that the monitoring loop thread can start and stop cleanly."""
        import time
        monitor = ProcessMonitor(poll_interval=0.05)
        monitor.start()
        assert monitor._running is True
        assert monitor._thread is not None
        assert monitor._thread.is_alive()
        time.sleep(0.1)
        monitor.stop()
        assert monitor._running is False

    def test_monitored_process_to_dict(self):
        proc = MonitoredProcess(
            game_id="g1", process_name="test.exe", pid=1234,
            crashed=True, restart_count=2, max_restarts=3,
        )
        d = proc.to_dict()
        assert d["game_id"] == "g1"
        assert d["process_name"] == "test.exe"
        assert d["pid"] == 1234
        assert d["crashed"] is True
        assert d["restart_count"] == 2


# ======================================================================
# Memory Leak Prevention Tests
# ======================================================================

class TestMemoryLeakPrevention:
    """Tests verifying that unbounded collections are capped."""

    def test_action_chain_log_trimmed(self):
        """ActionChainExecutor._action_log is capped via BoundedList."""
        from playnite_py.models.action import ActionResult
        from playnite_py.utils import BoundedList
        db = GameDatabase()
        executor = ActionChainExecutor(db)
        # Replace the log with a small-capacity BoundedList
        executor._action_log = BoundedList(5)

        for i in range(10):
            result = ActionResult(action_id=f"a{i}", action_name=f"Action {i}")
            with executor._log_lock:
                executor._action_log.append(result)

        assert len(executor._action_log) == 5
        # Oldest entries should have been discarded
        assert executor._action_log[0].action_id == "a5"

    def test_trigger_history_trimmed(self):
        """TriggerManager._history is capped at max_history."""
        mgr = TriggerManager(max_history=5)
        trigger = EventTrigger(
            name="test", event_type=EventType.GAME_STARTED, action_id="a1"
        )
        mgr.add_trigger(trigger)

        for _ in range(10):
            mgr.fire_event(EventType.GAME_STARTED)

        assert len(mgr._history) <= 5

    def test_rollback_history_trimmed(self):
        """RollbackManager._history is capped at max_history."""
        db = GameDatabase()
        mgr = RollbackManager(db, max_history=5)

        for i in range(10):
            mgr.rollback_action(f"nonexistent_{i}")

        assert len(mgr._history) <= 5

    def test_monitor_clear_handlers(self):
        """ProcessMonitor.clear_handlers() removes all event callbacks."""
        monitor = ProcessMonitor()
        monitor.on_process_started.append(lambda p: None)
        monitor.on_process_exited.append(lambda p: None)
        monitor.on_process_crashed.append(lambda p: None)
        monitor.on_restart_triggered.append(lambda p: None)

        assert len(monitor.on_process_started) == 1
        assert len(monitor.on_process_exited) == 1

        monitor.clear_handlers()

        assert len(monitor.on_process_started) == 0
        assert len(monitor.on_process_exited) == 0
        assert len(monitor.on_process_crashed) == 0
        assert len(monitor.on_restart_triggered) == 0


# ======================================================================
# Gap Fix Tests — Action System
# ======================================================================


class TestGameActionTypes:
    """GameActionType enum — File, URL, Emulator, Script."""

    def test_all_action_types_exist(self):
        assert GameActionType.FILE.value == "file"
        assert GameActionType.URL.value == "url"
        assert GameActionType.EMULATOR.value == "emulator"
        assert GameActionType.SCRIPT.value == "script"

    def test_action_round_trip(self):
        action = GameAction(
            name="Launch",
            game_action_type=GameActionType.FILE,
            path="/usr/bin/game",
            is_play_action=True,
            emulator_id="emu-1",
            emulator_profile_id="profile-1",
        )
        d = action.to_dict()
        assert d["game_action_type"] == "file"
        assert d["path"] == "/usr/bin/game"
        assert d["is_play_action"] is True
        assert d["emulator_id"] == "emu-1"

        restored = GameAction.from_dict(d)
        assert restored.game_action_type == GameActionType.FILE
        assert restored.path == "/usr/bin/game"
        assert restored.is_play_action is True


class TestTrackingModes:
    """TrackingMode enum and per-action tracking config."""

    def test_all_tracking_modes(self):
        assert TrackingMode.DEFAULT.value == "default"
        assert TrackingMode.PROCESS.value == "process"
        assert TrackingMode.DIRECTORY.value == "directory"
        assert TrackingMode.ORIGINAL_PROCESS.value == "original_process"
        assert TrackingMode.PROCESS_NAME.value == "process_name"

    def test_action_tracking_fields(self):
        action = GameAction(
            name="Track",
            tracking_mode=TrackingMode.DIRECTORY,
            tracking_path="/opt/games",
            tracking_frequency=5000,
            initial_tracking_delay=2000,
        )
        d = action.to_dict()
        assert d["tracking_mode"] == "directory"
        assert d["tracking_path"] == "/opt/games"
        assert d["tracking_frequency"] == 5000
        assert d["initial_tracking_delay"] == 2000

        restored = GameAction.from_dict(d)
        assert restored.tracking_mode == TrackingMode.DIRECTORY
        assert restored.tracking_frequency == 5000

    def test_monitor_tracking_mode_dispatch(self):
        """ProcessMonitor.start_monitoring accepts tracking mode."""
        monitor = ProcessMonitor()
        proc = monitor.start_monitoring(
            game_id="g1",
            pid=99999,
            tracking_mode=TrackingMode.ORIGINAL_PROCESS,
            tracking_frequency=3000,
            initial_tracking_delay=1000,
        )
        assert proc.tracking_mode == TrackingMode.ORIGINAL_PROCESS
        assert proc.tracking_frequency == 3000
        assert proc.initial_tracking_delay == 1000
        monitor.stop_monitoring("g1")


class TestSessionTracking:
    """Session length tracking in MonitoredProcess."""

    def test_session_length_initialized(self):
        proc = MonitoredProcess(game_id="g1")
        assert proc.session_length == 0
        assert proc.session_start_monotonic > 0

    def test_session_length_in_to_dict(self):
        proc = MonitoredProcess(game_id="g1", session_length=120)
        d = proc.to_dict()
        assert d["session_length"] == 120


class TestCancellation:
    """Cancellation mechanism in ProcessMonitor."""

    def test_cancel_sets_event(self):
        monitor = ProcessMonitor()
        proc = monitor.start_monitoring(game_id="g1", pid=99999)
        assert monitor.is_cancelled("g1") is False

        monitor.cancel("g1")
        assert monitor.is_cancelled("g1") is True
        monitor.stop_monitoring("g1")

    def test_stop_monitoring_sets_cancel(self):
        monitor = ProcessMonitor()
        proc = monitor.start_monitoring(game_id="g1", pid=99999)
        monitor.stop_monitoring("g1")
        assert proc._cancel_event.is_set()


class TestVariableExpansionGaps:
    """Missing variables: InstallDirName, ImagePath, PlayniteDir, etc."""

    def test_install_dir_name(self):
        resolver = VariableResolver()
        game = Game(name="MyGame", install_directory="/opt/games/MyGame")
        ctx = resolver.build_context(game)
        assert ctx["InstallDirName"] == "MyGame"
        assert ctx["game.install_dir_name"] == "MyGame"

    def test_playnite_dir(self):
        resolver = VariableResolver()
        resolver.set_playnite_dir("/usr/share/playnite")
        ctx = resolver.build_context()
        assert ctx["PlayniteDir"] == "/usr/share/playnite"
        assert ctx["playnite_dir"] == "/usr/share/playnite"

    def test_database_id(self):
        resolver = VariableResolver()
        game = Game(name="MyGame")
        ctx = resolver.build_context(game)
        assert ctx["DatabaseId"] == game.id

    def test_plugin_id(self):
        resolver = VariableResolver()
        game = Game(name="MyGame", source="steam")
        ctx = resolver.build_context(game)
        assert ctx["PluginId"] == "steam"
        assert ctx["game.plugin_id"] == "steam"

    def test_emulator_dir(self):
        resolver = VariableResolver()
        resolver.set_emulator_dir("/opt/emulators/retroarch")
        ctx = resolver.build_context()
        assert ctx["EmulatorDir"] == "/opt/emulators/retroarch"

    def test_image_path_variables(self):
        resolver = VariableResolver()
        game = Game(name="MyGame")
        ctx = resolver.build_context(game, extra={"ImagePath": "/roms/game.gba"})
        assert ctx["ImagePath"] == "/roms/game.gba"
        assert ctx["ImageName"] == "game.gba"
        assert ctx["ImageNameNoExt"] == "game"

    def test_c_sharp_compatible_aliases(self):
        resolver = VariableResolver()
        game = Game(name="Test Game", version="1.2", install_directory="/games/test")
        ctx = resolver.build_context(game)
        assert ctx["Name"] == "Test Game"
        assert ctx["GameId"] == game.id
        assert ctx["Version"] == "1.2"
        assert ctx["InstallDir"] == "/games/test"


class TestPlatformNameResolution:
    """Platform IDs resolve to names via lookup table."""

    def test_platform_lookup(self):
        resolver = VariableResolver()
        resolver.set_platform_lookup({"plat-1": "PC", "plat-2": "PlayStation"})
        game = Game(name="Test", platform_ids=["plat-1"])
        ctx = resolver.build_context(game)
        assert ctx["Platform"] == "PC"
        assert ctx["game.platform"] == "PC"

    def test_platform_fallback_to_id(self):
        resolver = VariableResolver()
        resolver.set_platform_lookup({})
        game = Game(name="Test", platform_ids=["unknown-id"])
        ctx = resolver.build_context(game)
        assert ctx["Platform"] == "unknown-id"


class TestPathSeparatorNormalization:
    """Path separator normalization."""

    def test_fix_path_separators(self):
        result = VariableResolver.fix_path_separators("/opt/games/test")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fix_empty_path(self):
        assert VariableResolver.fix_path_separators("") == ""

    def test_resolve_and_fix_paths(self):
        resolver = VariableResolver()
        game = Game(name="Test", install_directory="/opt/games/test")
        ctx = resolver.build_context(game)
        result = resolver.resolve_and_fix_paths("{InstallDir}/saves", ctx)
        assert "test" in result


class TestLauncherBasic:
    """GameLauncher basic operations."""

    def test_launch_result_dataclass(self):
        result = LaunchResult(success=True, session_length=300)
        d = result.to_dict()
        assert d["success"] is True
        assert d["session_length"] == 300

    def test_launcher_game_not_found(self):
        db = GameDatabase()
        monitor = ProcessMonitor()
        launcher = GameLauncher(db, monitor)
        action = GameAction(name="test")
        result = launcher.launch("nonexistent", action)
        assert result.success is False
        assert "not found" in result.error

    def test_launcher_cancellation(self):
        db = GameDatabase()
        game = Game(name="Test")
        db.add_game(game)
        monitor = ProcessMonitor()

        cancelled = False

        def mock_hook(hook_name, **kwargs):
            if hook_name == "on_game_starting":
                return {"cancelled": True, "cancelled_by": "test_script"}
            return {}

        launcher = GameLauncher(db, monitor, execute_hook=mock_hook)
        action = GameAction(name="test")
        result = launcher.launch(game.id, action)
        assert result.cancelled is True
        assert result.cancelled_by == "test_script"

    def test_manager_has_launcher(self):
        db = GameDatabase()
        manager = ActionManager(db)
        assert hasattr(manager, "launcher")
        assert isinstance(manager.launcher, GameLauncher)

    def test_manager_configure_platform_lookup(self):
        db = GameDatabase()
        db.add_platform(Platform(id="p1", name="PC"))
        manager = ActionManager(db)
        manager.configure_platform_lookup()
        assert manager.variable_resolver._platform_lookup == {"p1": "PC"}


class TestSleepHibernationDetection:
    """Sleep/hibernation detection in monitoring loop."""

    def test_monitored_process_has_session_start(self):
        """Verify MonitoredProcess tracks session_start_monotonic."""
        import time
        before = time.monotonic()
        proc = MonitoredProcess(game_id="g1")
        after = time.monotonic()
        assert before <= proc.session_start_monotonic <= after
