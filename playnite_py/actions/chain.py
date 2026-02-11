"""Action chain execution: run multiple actions in priority order for a game phase."""

from __future__ import annotations

import asyncio
import logging
import time
import threading
import traceback
from pathlib import Path
from typing import Any

from playnite_py.models.action import (
    ActionChainResult, ActionPhase, ActionResult, GameAction,
)
from playnite_py.models.game import Game
from playnite_py.models.database import GameDatabase
from playnite_py.actions.conditions import ConditionEvaluator
from playnite_py.actions.variables import VariableResolver
from playnite_py.scripting.sandbox import SandboxedExecutor
from playnite_py.scripting.config import ScriptConfig, SandboxLevel
from playnite_py.utils import BoundedList

logger = logging.getLogger(__name__)


class ActionChainExecutor:
    """Executes a chain of actions for a given game and phase."""

    def __init__(
        self,
        database: GameDatabase,
        condition_evaluator: ConditionEvaluator | None = None,
        variable_resolver: VariableResolver | None = None,
    ):
        self._db = database
        self._evaluator = condition_evaluator or ConditionEvaluator()
        self._resolver = variable_resolver or VariableResolver()
        self._action_log: BoundedList[ActionResult] = BoundedList(1000)
        self._log_lock = threading.Lock()

    def execute_phase(
        self,
        game_id: str,
        phase: ActionPhase,
        extra_vars: dict[str, Any] | None = None,
    ) -> ActionChainResult:
        """Execute all actions for a game phase synchronously."""
        game = self._db.get_game(game_id)
        # get_actions_for_game already includes global actions (game_id=None)
        all_actions = self._db.get_actions_for_game(game_id, phase.value)

        chain_result = ActionChainResult(game_id=game_id, phase=phase)
        start = time.perf_counter()

        sync_actions = [a for a in all_actions if not a.is_async]
        async_actions = [a for a in all_actions if a.is_async]

        # Start async actions in background threads
        async_threads: list[tuple[threading.Thread, dict]] = []
        for action in async_actions:
            result_holder: dict[str, Any] = {}
            t = threading.Thread(
                target=self._execute_single_action_thread,
                args=(action, game, extra_vars, result_holder),
                daemon=True,
            )
            t.start()
            async_threads.append((t, result_holder))

        # Execute sync actions in order
        for action in sync_actions:
            result = self._execute_single_action(action, game, extra_vars)
            chain_result.results.append(result)
            with self._log_lock:
                self._action_log.append(result)

        # Collect async results (with timeout)
        for t, holder in async_threads:
            t.join(timeout=60)
            if "result" in holder:
                chain_result.results.append(holder["result"])
                with self._log_lock:
                    self._action_log.append(holder["result"])

        chain_result.total_duration = time.perf_counter() - start
        return chain_result

    async def execute_phase_async(
        self,
        game_id: str,
        phase: ActionPhase,
        extra_vars: dict[str, Any] | None = None,
    ) -> ActionChainResult:
        """Async version of execute_phase."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.execute_phase, game_id, phase, extra_vars
        )

    def _execute_single_action(
        self,
        action: GameAction,
        game: Game | None,
        extra_vars: dict[str, Any] | None,
    ) -> ActionResult:
        """Execute a single action and return its result."""
        result = ActionResult(action_id=action.id, action_name=action.name)
        start = time.perf_counter()

        try:
            # Check conditions
            should_run, reason = self._evaluator.should_execute(action, game)
            if not should_run:
                result.success = True
                result.output = f"Skipped: {reason}"
                result.duration = time.perf_counter() - start
                return result

            # Build variable context
            context = self._resolver.build_context(game, extra_vars)

            # Resolve variables in the script
            script = self._resolver.resolve(action.script, context)
            resolved_args = self._resolver.resolve_dict(action.arguments, context)

            # Execute the script
            config = ScriptConfig(
                timeout=action.timeout,
                sandbox_level=SandboxLevel.BASIC,
            )
            executor = SandboxedExecutor(config, action.working_directory or ".")

            global_vars: dict[str, Any] = {
                "game": game.to_dict() if game else {},
                "args": resolved_args,
                "action": action.to_dict(),
            }

            if action.is_script_path:
                exec_result = executor.execute_file(
                    script, global_vars, timeout=action.timeout
                )
            else:
                exec_result = executor.execute_code(
                    script, global_vars, timeout=action.timeout
                )

            result.success = exec_result["success"]
            result.output = exec_result.get("stdout", "")
            result.error = exec_result.get("error", "")

            # Check for modified launch parameters
            ns = exec_result.get("namespace", {})
            if "launch_parameters" in ns:
                result.output += f"\n[launch_parameters: {ns['launch_parameters']}]"

        except Exception as e:
            result.success = False
            result.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

        result.duration = time.perf_counter() - start
        return result

    def _execute_single_action_thread(
        self,
        action: GameAction,
        game: Game | None,
        extra_vars: dict[str, Any] | None,
        holder: dict[str, Any],
    ) -> None:
        holder["result"] = self._execute_single_action(action, game, extra_vars)

    def get_action_log(
        self,
        game_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent action results, optionally filtered by game ID."""
        with self._log_lock:
            log = list(self._action_log)
        if game_id:
            # Filter by looking up action's game_id
            filtered = []
            for entry in log:
                action = self._db.get_action(entry.action_id)
                if action and (action.game_id == game_id or action.game_id is None):
                    filtered.append(entry)
            log = filtered
        return [r.to_dict() for r in log[-limit:]]

    def clear_log(self) -> None:
        """Clear all stored action log entries."""
        with self._log_lock:
            self._action_log.clear()
