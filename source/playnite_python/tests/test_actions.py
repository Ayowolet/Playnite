"""
Unit tests for the Game Action Injection System.

Run with::

    pytest source/playnite_python/tests/test_actions.py -v
"""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playnite_python.actions.action_logger import ActionExecutionLogger
from playnite_python.actions.chain import ActionChainExecutor, _expand_variables
from playnite_python.actions.condition import evaluate_conditions, condition_from_simple
from playnite_python.actions.injector import ActionInjector
from playnite_python.actions.models import (
    Action, ActionChainDef, ActionCondition, ActionLog, ActionProfile,
    ActionType, ActionExecutorType, ConditionType, TriggerType,
)
from playnite_python.actions.monitor import ProcessMonitor
from playnite_python.actions.registry import ActionRegistry
from playnite_python.actions.rollback import RollbackManager
from playnite_python.actions.scheduler import ActionScheduler
from playnite_python.actions.template import (
    discord_rich_presence, game_backup, notify_session_start, playtime_log,
)
from playnite_python.models.game import Game


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry(tmp_path):
    return ActionRegistry(str(tmp_path))


@pytest.fixture
def injector(registry):
    return ActionInjector(registry)


@pytest.fixture
def game():
    return Game(
        id="game-001",
        name="Portal 2",
        is_installed=True,
        install_directory="/games/portal2",
        platform_ids=["Windows"],
        tag_ids=["Puzzle", "Co-op"],
    )


@pytest.fixture
def simple_action():
    return Action(
        name="Test Action",
        type=ActionType.PRE_LAUNCH,
        script="result = 42",
    )


# ---------------------------------------------------------------------------
# Model serialisation
# ---------------------------------------------------------------------------

class TestActionModels:
    def test_action_roundtrip(self, simple_action):
        d = simple_action.to_dict()
        restored = Action.from_dict(d)
        assert restored.id == simple_action.id
        assert restored.name == simple_action.name
        assert restored.type == simple_action.type

    def test_action_condition_roundtrip(self):
        cond = ActionCondition(
            type=ConditionType.FILE_EXISTS,
            value="/tmp/foo",
            negate=True,
            operator="or",
        )
        d = cond.to_dict()
        restored = ActionCondition.from_dict(d)
        assert restored.type == ConditionType.FILE_EXISTS
        assert restored.negate is True
        assert restored.operator == "or"

    def test_action_log_to_dict(self):
        log = ActionLog(
            action_id="a1",
            action_name="test",
            success=True,
            duration_ms=42.5,
        )
        d = log.to_dict()
        assert d["success"] is True
        assert d["duration_ms"] == 42.5

    def test_action_profile_roundtrip(self):
        profile = ActionProfile(
            name="All RPGs",
            filter_expr="'RPG' in game.tag_ids",
            action_ids=["a1", "a2"],
        )
        d = profile.to_dict()
        restored = ActionProfile.from_dict(d)
        assert restored.filter_expr == profile.filter_expr
        assert restored.action_ids == ["a1", "a2"]


# ---------------------------------------------------------------------------
# ActionRegistry tests
# ---------------------------------------------------------------------------

class TestActionRegistry:
    def test_add_and_get(self, registry, simple_action):
        registry.add_action(simple_action)
        fetched = registry.get_action(simple_action.id)
        assert fetched is not None
        assert fetched.name == simple_action.name

    def test_update(self, registry, simple_action):
        registry.add_action(simple_action)
        simple_action.name = "Updated"
        registry.update_action(simple_action)
        assert registry.get_action(simple_action.id).name == "Updated"

    def test_remove(self, registry, simple_action):
        registry.add_action(simple_action)
        registry.remove_action(simple_action.id)
        assert registry.get_action(simple_action.id) is None

    def test_list_by_type(self, registry):
        registry.add_action(Action(name="Pre", type=ActionType.PRE_LAUNCH))
        registry.add_action(Action(name="Post", type=ActionType.POST_EXIT))
        pre = registry.list_actions(action_type=ActionType.PRE_LAUNCH)
        assert all(a.type == ActionType.PRE_LAUNCH for a in pre)

    def test_list_by_game_id(self, registry, game):
        global_action = Action(name="Global", game_id=None)
        game_action = Action(name="GameSpecific", game_id=game.id)
        other_action = Action(name="OtherGame", game_id="other-game")
        registry.add_action(global_action)
        registry.add_action(game_action)
        registry.add_action(other_action)
        # For game.id, should get global + game-specific, but not other-game
        results = registry.get_actions_for_game(game.id)
        names = {a.name for a in results}
        assert "Global" in names
        assert "GameSpecific" in names
        assert "OtherGame" not in names

    def test_persistence(self, tmp_path):
        reg1 = ActionRegistry(str(tmp_path))
        action = Action(name="Persisted")
        reg1.add_action(action)
        # Reload from same path
        reg2 = ActionRegistry(str(tmp_path))
        assert reg2.get_action(action.id) is not None

    def test_profile_matching(self, registry, game):
        action = Action(name="RPG Action")
        registry.add_action(action)
        profile = ActionProfile(
            filter_expr="'Puzzle' in game.tag_ids",
            action_ids=[action.id],
        )
        registry.add_profile(profile)
        matched = registry.get_profile_actions(game)
        assert any(a.name == "RPG Action" for a in matched)

    def test_profile_not_matching(self, registry, game):
        action = Action(name="Unmatched")
        registry.add_action(action)
        profile = ActionProfile(
            filter_expr="'FPS' in game.tag_ids",
            action_ids=[action.id],
        )
        registry.add_profile(profile)
        matched = registry.get_profile_actions(game)
        assert not any(a.name == "Unmatched" for a in matched)

    def test_stats(self, registry):
        registry.add_action(Action(name="A1"))
        registry.add_action(Action(name="A2", enabled=False))
        stats = registry.stats()
        assert stats["total_actions"] == 2
        assert stats["enabled_actions"] == 1


# ---------------------------------------------------------------------------
# Condition tests
# ---------------------------------------------------------------------------

class TestConditions:
    def test_always(self, game):
        assert evaluate_conditions([condition_from_simple("always")], game) is True

    def test_never(self, game):
        assert evaluate_conditions([condition_from_simple("never")], game) is False

    def test_empty_conditions(self, game):
        assert evaluate_conditions([], game) is True

    def test_file_exists_true(self, tmp_path, game):
        f = tmp_path / "test.txt"
        f.write_text("x")
        cond = ActionCondition(type=ConditionType.FILE_EXISTS, value=str(f))
        assert evaluate_conditions([cond], game) is True

    def test_file_exists_false(self, game):
        cond = ActionCondition(type=ConditionType.FILE_EXISTS, value="/nonexistent/file.xyz")
        assert evaluate_conditions([cond], game) is False

    def test_game_has_tag_true(self, game):
        cond = ActionCondition(type=ConditionType.GAME_HAS_TAG, value="Puzzle")
        assert evaluate_conditions([cond], game) is True

    def test_game_has_tag_false(self, game):
        cond = ActionCondition(type=ConditionType.GAME_HAS_TAG, value="FPS")
        assert evaluate_conditions([cond], game) is False

    def test_game_is_installed_true(self, game):
        cond = ActionCondition(type=ConditionType.GAME_IS_INSTALLED, value="")
        assert evaluate_conditions([cond], game) is True

    def test_game_is_installed_false(self, game):
        game.is_installed = False
        cond = ActionCondition(type=ConditionType.GAME_IS_INSTALLED, value="")
        assert evaluate_conditions([cond], game) is False

    def test_platform_is(self, game):
        cond = ActionCondition(type=ConditionType.PLATFORM_IS, value="windows")
        assert evaluate_conditions([cond], game) is True

    def test_negate(self, game):
        cond = ActionCondition(type=ConditionType.ALWAYS, negate=True)
        assert evaluate_conditions([cond], game) is False

    def test_or_operator(self, game):
        never = ActionCondition(type=ConditionType.NEVER, operator="and")
        always = ActionCondition(type=ConditionType.ALWAYS, operator="or")
        assert evaluate_conditions([never, always], game) is True

    def test_script_condition(self, game):
        cond = ActionCondition(type=ConditionType.SCRIPT, value="game.play_time > -1")
        assert evaluate_conditions([cond], game) is True

    def test_script_condition_bad_expr(self, game):
        cond = ActionCondition(type=ConditionType.SCRIPT, value="raise ValueError()")
        # Should not raise; returns False
        assert evaluate_conditions([cond], game) is False


# ---------------------------------------------------------------------------
# ActionChainExecutor tests
# ---------------------------------------------------------------------------

class TestActionChainExecutor:
    def test_execute_single_script(self, game):
        action = Action(
            name="Run script",
            script="result = game.name + '_ok'",
        )
        executor = ActionChainExecutor()
        logs, success = executor.execute([action], game)
        assert success
        assert logs[0].success

    def test_execute_by_priority(self, game):
        order = []
        def make_action(name, priority):
            return Action(
                name=name,
                priority=priority,
                script=f"import sys; sys.stdout.write({name!r})",
            )
        actions = [make_action("C", 30), make_action("A", 10), make_action("B", 20)]
        executor = ActionChainExecutor()
        logs, _ = executor.execute(actions, game)
        names = [l.action_name for l in logs]
        assert names == ["A", "B", "C"]

    def test_condition_skips_action(self, game):
        action = Action(
            name="Should skip",
            conditions=[ActionCondition(type=ConditionType.NEVER)],
            script="raise ValueError('should not run')",
        )
        executor = ActionChainExecutor()
        logs, success = executor.execute([action], game)
        assert success  # Skipping is not a failure
        assert "Skipped" in logs[0].output

    def test_stop_on_failure(self, game):
        a1 = Action(name="Fail", script="raise RuntimeError('fail')", priority=10)
        a2 = Action(name="NotRun", script="x=1", priority=20)
        executor = ActionChainExecutor(stop_on_failure=True)
        logs, success = executor.execute([a1, a2], game)
        assert not success
        assert len(logs) == 1  # Second action never ran

    def test_async_action_dispatched(self, game):
        action = Action(
            name="Async action",
            script="import time; time.sleep(0.1)",
            async_=True,
        )
        executor = ActionChainExecutor()
        logs, success = executor.execute([action], game)
        assert success
        assert logs[0].was_async

    def test_variable_expansion(self, game):
        action = Action(
            name="Vars",
            script="assert '{game.name}' != ''",
        )
        expanded = _expand_variables("Game: {game.name}", game)
        assert expanded == "Game: Portal 2"

    def test_variable_expansion_no_game(self):
        """game=None: {game.*} tokens are preserved; built-in vars still expand."""
        result = _expand_variables("{timestamp} {game.name} {unknown}", game=None)
        assert "{timestamp}" not in result   # built-in var always expands
        assert "{game.name}" in result       # unknown without game → preserved
        assert "{unknown}" in result         # unrecognised key → preserved

    def test_rollback_on_failure(self, game):
        action = Action(
            name="Fail with rollback",
            script="raise RuntimeError('oops')",
            rollback_script="rollback_ran = True",
        )
        executor = ActionChainExecutor()
        logs, _ = executor.execute([action], game)
        assert logs[0].success is False
        assert logs[0].rolled_back is True

    def test_on_action_complete_callback(self, game):
        completed = []
        action = Action(name="CB", script="x=1")
        executor = ActionChainExecutor(on_action_complete=lambda a, l: completed.append(a.name))
        executor.execute([action], game)
        assert "CB" in completed


# ---------------------------------------------------------------------------
# ActionInjector tests
# ---------------------------------------------------------------------------

class TestActionInjector:
    def test_inject(self, injector, game):
        action = Action(name="Injected")
        result = injector.inject(action, game.id)
        assert injector.registry.get_action(result.id) is not None

    def test_inject_pre_launch(self, injector):
        action = injector.inject_pre_launch("print('hi')", name="Hello", game_id="g1")
        assert action.type == ActionType.PRE_LAUNCH
        assert action.game_id == "g1"

    def test_inject_post_exit(self, injector):
        action = injector.inject_post_exit("print('bye')", game_id="g1")
        assert action.type == ActionType.POST_EXIT

    def test_revoke(self, injector, game):
        action = injector.inject_pre_launch("x=1", game_id=game.id)
        injector.revoke(action.id)
        assert injector.registry.get_action(action.id) is None

    def test_revoke_by_source(self, injector):
        a1 = injector.inject_pre_launch("x=1", name="S1")
        a1.source_script = "my_script"
        injector.registry.update_action(a1)
        a2 = injector.inject_pre_launch("x=2", name="S2")
        a2.source_script = "my_script"
        injector.registry.update_action(a2)
        count = injector.revoke_by_source("my_script")
        assert count == 2

    def test_override_launcher(self, injector, game):
        # Add an existing play action
        existing = Action(name="Old Launcher", type=ActionType.PLAY, game_id=game.id)
        injector.registry.add_action(existing)
        # Override
        new_action = injector.override_launcher(game.id, "print('new launcher')")
        play_actions = injector.registry.list_actions(game_id=game.id, action_type=ActionType.PLAY)
        assert len(play_actions) == 1
        assert play_actions[0].id == new_action.id

    def test_on_inject_callback(self, injector):
        fired = []
        injector.on_inject(lambda a: fired.append(a.name))
        injector.inject_pre_launch("x=1", name="Watch Me")
        assert "Watch Me" in fired


# ---------------------------------------------------------------------------
# RollbackManager tests
# ---------------------------------------------------------------------------

class TestRollbackManager:
    def test_push_and_rollback(self, game):
        action = Action(
            name="Reversible",
            rollback_script="rolled_back = True",
        )
        rm = RollbackManager()
        rm.push(action, game)
        logs = rm.rollback_all()
        assert len(logs) == 1
        assert logs[0].success is True
        assert logs[0].rolled_back is True

    def test_rollback_order_lifo(self, game):
        order = []
        a1 = Action(name="First", rollback_script="")
        a2 = Action(name="Second", rollback_script="")
        rm = RollbackManager()
        # Manually push entries (skip rollback_script check)
        from playnite_python.actions.rollback import RollbackEntry
        rm._stack.append(RollbackEntry(a1, game))
        rm._stack.append(RollbackEntry(a2, game))
        assert rm._stack[-1].action.name == "Second"
        entry = rm._stack.pop()
        assert entry.action.name == "Second"

    def test_clear(self, game):
        action = Action(name="X", rollback_script="x=1")
        rm = RollbackManager()
        rm.push(action, game)
        rm.clear()
        assert rm.depth() == 0

    def test_no_rollback_if_script_empty(self, game):
        action = Action(name="NoRB", rollback_script="")
        rm = RollbackManager()
        rm.push(action, game)  # Should not push because rollback_script is empty
        assert rm.depth() == 0


# ---------------------------------------------------------------------------
# ActionExecutionLogger tests
# ---------------------------------------------------------------------------

class TestActionExecutionLogger:
    def test_record_and_retrieve(self, tmp_path):
        logger = ActionExecutionLogger(str(tmp_path / "actions.jsonl"))
        log = ActionLog(action_id="a1", action_name="Test", success=True, duration_ms=10.0)
        logger.record(log)
        recent = logger.get_recent(10)
        assert any(e.action_id == "a1" for e in recent)

    def test_filter_by_game(self, tmp_path):
        logger = ActionExecutionLogger(str(tmp_path / "actions.jsonl"))
        log1 = ActionLog(action_id="a1", game_id="g1", success=True)
        log2 = ActionLog(action_id="a2", game_id="g2", success=True)
        logger.record(log1)
        logger.record(log2)
        results = logger.get_for_game("g1")
        assert all(e.game_id == "g1" for e in results)

    def test_stats(self, tmp_path):
        logger = ActionExecutionLogger(str(tmp_path / "actions.jsonl"))
        logger.record(ActionLog(action_id="a1", success=True, duration_ms=10.0))
        logger.record(ActionLog(action_id="a1", success=False, duration_ms=20.0))
        stats = logger.get_stats("a1")
        assert stats["total_executions"] == 2
        assert stats["failure_count"] == 1

    def test_persistence(self, tmp_path):
        log_path = str(tmp_path / "actions.jsonl")
        logger1 = ActionExecutionLogger(log_path)
        logger1.record(ActionLog(action_id="persist", success=True))
        # Re-open
        logger2 = ActionExecutionLogger(log_path)
        entries = logger2.get_recent(100)
        assert any(e.action_id == "persist" for e in entries)


# ---------------------------------------------------------------------------
# ActionScheduler tests
# ---------------------------------------------------------------------------

class TestActionScheduler:
    def test_schedule_and_fire_event(self):
        called = []

        def runner(action_id):
            called.append(action_id)
            return None

        scheduler = ActionScheduler(runner)
        job_id = scheduler.schedule_on_event("action-1", TriggerType.GAME_STARTING)
        count = scheduler.fire_event(TriggerType.GAME_STARTING)
        assert count == 1
        assert "action-1" in called

    def test_cancel_job(self):
        called = []
        scheduler = ActionScheduler(lambda aid: called.append(aid) or None)
        job_id = scheduler.schedule_on_event("action-x", TriggerType.APP_STARTED)
        scheduler.cancel(job_id)
        count = scheduler.fire_event(TriggerType.APP_STARTED)
        assert count == 0

    def test_interval_job_is_due(self):
        from playnite_python.actions.scheduler import ScheduledJob
        job = ScheduledJob(
            action_id="a1",
            schedule_type="interval",
            interval_seconds=1.0,
        )
        # No last_run = always due
        assert job.is_due(datetime.now()) is True
        job.last_run = datetime.now()
        assert job.is_due(datetime.now()) is False

    def test_once_job_is_due(self):
        from playnite_python.actions.scheduler import ScheduledJob
        past = datetime.now() - timedelta(seconds=10)
        job = ScheduledJob(action_id="a1", schedule_type="once", run_at=past)
        assert job.is_due(datetime.now()) is True
        job.run_count = 1  # already ran
        assert job.is_due(datetime.now()) is False

    def test_on_run_callback_receives_job_and_log(self):
        """on_run callbacks are invoked with the job and log after fire_event."""
        fired = []
        scheduler = ActionScheduler(lambda aid: None)
        scheduler.schedule_on_event("act-cb", TriggerType.GAME_STARTING)
        scheduler.on_run(lambda job, log: fired.append(job.action_id))
        scheduler.fire_event(TriggerType.GAME_STARTING)
        assert fired == ["act-cb"]

    def test_on_run_callback_snapshot_safe_during_mutation(self):
        """Registering a new callback during fire_event must not raise."""
        scheduler = ActionScheduler(lambda aid: None)
        scheduler.schedule_on_event("act-snap", TriggerType.GAME_STARTING)

        def mutating_callback(*_):  # noqa: ANN002
            scheduler.on_run(lambda *_: None)  # concurrent registration

        scheduler.on_run(mutating_callback)
        # Must not raise RuntimeError: list changed size during iteration
        scheduler.fire_event(TriggerType.GAME_STARTING)


# ---------------------------------------------------------------------------
# Template smoke tests
# ---------------------------------------------------------------------------

class TestActionTemplates:
    def test_discord_rich_presence_returns_action(self):
        action = discord_rich_presence()
        assert isinstance(action, Action)
        assert action.type == ActionType.PRE_LAUNCH
        assert action.script

    def test_game_backup_returns_action(self):
        action = game_backup()
        assert isinstance(action, Action)
        assert "shutil" in action.script

    def test_notify_session_start(self):
        action = notify_session_start()
        assert action.async_ is True

    def test_playtime_log(self):
        action = playtime_log()
        assert action.type == ActionType.POST_EXIT


# ---------------------------------------------------------------------------
# ProcessMonitor smoke tests (no actual process)
# ---------------------------------------------------------------------------

class TestProcessMonitor:
    def test_is_running_no_pid(self):
        monitor = ProcessMonitor()
        assert monitor.is_running() is False

    def test_get_info_no_pid(self):
        monitor = ProcessMonitor()
        assert monitor.get_info() is None

    def test_stop_monitoring(self):
        monitor = ProcessMonitor()
        monitor.start_monitoring(process_name="totally_nonexistent_xyz")
        time.sleep(0.2)
        monitor.stop_monitoring()
        # Should not raise


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------

class TestSecurity:
    """Verify safe_eval and sandbox hardening."""

    # -- safe_eval: allowed expressions ------------------------------------

    def test_safe_eval_valid_expression(self):
        from playnite_python.actions.safe_eval import safe_eval
        game = Game(name="Portal 2")
        result = safe_eval('game.name == "Portal 2"', {"game": game})
        assert result is True

    def test_safe_eval_in_operator(self):
        from playnite_python.actions.safe_eval import safe_eval
        game = Game(name="Celeste")
        game.tag_ids = ["tag-puzzle", "tag-indie"]
        result = safe_eval('"tag-puzzle" in game.tag_ids', {"game": game})
        assert result is True

    # -- safe_eval: blocked constructs ------------------------------------

    def test_safe_eval_blocks_dunder_name(self):
        from playnite_python.actions.safe_eval import safe_eval, SafeEvalError
        with pytest.raises((SafeEvalError, ValueError)):
            safe_eval("__import__('os')", {})

    def test_safe_eval_blocks_dunder_attribute(self):
        from playnite_python.actions.safe_eval import safe_eval, SafeEvalError
        game = Game(name="x")
        with pytest.raises((SafeEvalError, ValueError)):
            safe_eval("game.__class__", {"game": game})

    def test_safe_eval_blocks_non_whitelisted_call(self):
        from playnite_python.actions.safe_eval import safe_eval, SafeEvalError
        with pytest.raises((SafeEvalError, ValueError)):
            safe_eval("open('/etc/passwd')", {})

    def test_safe_eval_blocks_lambda(self):
        from playnite_python.actions.safe_eval import safe_eval, SafeEvalError
        with pytest.raises((SafeEvalError, ValueError, SyntaxError)):
            safe_eval("lambda: None", {})

    # -- condition script: class-hierarchy bypass is neutralised -----------

    def test_eval_script_class_hierarchy_bypass_returns_false(self):
        """Class-hierarchy escape attempt must not return a class list."""
        from playnite_python.actions.condition import _eval_script
        from playnite_python.actions.models import ActionCondition, ConditionType
        cond = ActionCondition(
            type=ConditionType.SCRIPT,
            value="''.__class__.__mro__[1].__subclasses__()",
        )
        result = _eval_script(cond, None)
        # safe_eval raises SafeEvalError (dunder attr) → _eval_script catches and returns False
        assert result is False

    # -- sandbox: import is blocked in action scripts ---------------------

    def test_run_script_blocks_os_import(self):
        from playnite_python.actions.chain import ActionChainExecutor
        from playnite_python.actions.models import Action, ActionType
        action = Action(name="bad", type=ActionType.PRE_LAUNCH, script="import os; os.getcwd()")
        executor = ActionChainExecutor()
        logs, _ = executor.execute([action], game=None)
        assert len(logs) == 1
        assert logs[0].success is False

    def test_safe_eval_syntax_error_raises_safe_eval_error(self):
        """Syntax errors in safe_eval must raise SafeEvalError, not bare ValueError."""
        from playnite_python.actions.safe_eval import safe_eval, SafeEvalError
        with pytest.raises(SafeEvalError):
            safe_eval("(((", {})

    def test_safe_eval_method_call_on_string_is_permitted(self):
        """Method calls on safe context objects are allowed by design."""
        from playnite_python.actions.safe_eval import safe_eval
        assert safe_eval('"hello".upper()', {}) == "HELLO"


# ---------------------------------------------------------------------------
# Concurrent access tests
# ---------------------------------------------------------------------------

class TestConcurrentAccess:
    """Verify thread-safety of ActionRegistry and ActionScheduler."""

    def test_registry_concurrent_add_does_not_raise(self, tmp_path):
        """Multiple threads adding actions concurrently must not raise or corrupt state."""
        import threading

        registry = ActionRegistry(str(tmp_path))
        errors: list = []

        def add_batch(n: int, prefix: str) -> None:
            try:
                for i in range(n):
                    registry.add_action(Action(name=f"{prefix}-{i}"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=add_batch, args=(10, f"t{i}"))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent add raised: {errors[0]}"
        assert registry.stats()["total_actions"] == 50

    def test_registry_concurrent_read_and_write(self, tmp_path):
        """Reads and writes from different threads must not raise."""
        import threading

        registry = ActionRegistry(str(tmp_path))
        for i in range(20):
            registry.add_action(Action(name=f"base-{i}"))

        errors: list = []

        def reader() -> None:
            try:
                for _ in range(20):
                    registry.list_actions()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def writer() -> None:
            try:
                for i in range(5):
                    registry.add_action(Action(name=f"new-{i}"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = (
            [threading.Thread(target=reader) for _ in range(4)]
            + [threading.Thread(target=writer) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent read/write raised: {errors[0]}"

    def test_scheduler_concurrent_fire_event_does_not_raise(self):
        """Multiple threads firing the same event concurrently must not raise."""
        import threading

        call_count: list = []
        lock = threading.Lock()

        def runner(action_id: str) -> None:
            with lock:
                call_count.append(action_id)
            return None  # type: ignore[return-value]

        scheduler = ActionScheduler(runner)
        for _ in range(3):
            scheduler.schedule_on_event("act", TriggerType.GAME_STARTED)

        errors: list = []

        def fire() -> None:
            try:
                scheduler.fire_event(TriggerType.GAME_STARTED)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=fire) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent fire_event raised: {errors[0]}"
        # 8 threads × 3 jobs = 24 runner calls expected
        assert len(call_count) == 24
