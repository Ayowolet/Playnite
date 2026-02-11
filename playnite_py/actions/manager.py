"""Central action manager tying together chains, conditions, templates, and rollback."""

from __future__ import annotations

import logging
from typing import Any

from playnite_py.models.action import (
    ActionChainResult, ActionPhase, ActionType, GameAction,
)
from playnite_py.models.database import GameDatabase
from playnite_py.actions.chain import ActionChainExecutor
from playnite_py.actions.conditions import ConditionEvaluator
from playnite_py.actions.launcher import GameLauncher, LaunchResult
from playnite_py.actions.monitor import ProcessMonitor
from playnite_py.actions.phase_executor import ActionPhaseExecutor
from playnite_py.actions.profiles import ProfileManager
from playnite_py.actions.rollback import RollbackManager
from playnite_py.actions.scheduler import ActionScheduler
from playnite_py.actions.templates import ActionTemplateRegistry
from playnite_py.actions.triggers import EventTrigger, TriggerManager
from playnite_py.actions.variables import VariableResolver

logger = logging.getLogger(__name__)


class ActionManager:
    """Unified facade for the action injection system.

    Provides a single entry point for injecting actions, executing phases,
    managing templates, profiles, triggers, scheduling, and rollback.
    """

    def __init__(self, database: GameDatabase):
        self._db = database

        # Sub-components
        self.variable_resolver = VariableResolver()
        self.condition_evaluator = ConditionEvaluator(self.variable_resolver)
        self.chain_executor = ActionChainExecutor(
            database, self.condition_evaluator, self.variable_resolver
        )
        self.templates = ActionTemplateRegistry()
        self.process_monitor = ProcessMonitor()
        self.rollback = RollbackManager(database)
        self.phase_executor = ActionPhaseExecutor(
            database, self.chain_executor, self.rollback
        )
        self.profiles = ProfileManager(database)
        self.scheduler = ActionScheduler(
            execute_callback=self._scheduled_execute
        )
        self.triggers = TriggerManager(
            action_callback=self._trigger_execute
        )
        self.launcher = GameLauncher(
            database=database,
            process_monitor=self.process_monitor,
            execute_phase=self.execute_phase,
        )

    # ------------------------------------------------------------------
    # Action CRUD
    # ------------------------------------------------------------------

    def inject_action(self, action: GameAction) -> GameAction:
        return self._db.add_action(action)

    def remove_action(self, action_id: str) -> bool:
        return self._db.remove_action(action_id)

    def get_actions(
        self,
        game_id: str | None = None,
        phase: str | None = None,
    ) -> list[GameAction]:
        return self._db.get_actions_for_game(game_id, phase)

    def get_all_actions(self) -> list[GameAction]:
        return self._db.get_all_actions()

    # ------------------------------------------------------------------
    # Phase execution
    # ------------------------------------------------------------------

    def execute_phase(
        self,
        game_id: str,
        phase: ActionPhase,
        extra_vars: dict[str, Any] | None = None,
    ) -> ActionChainResult:
        """Execute all actions for a game phase. Handles rollback on failure."""
        return self.phase_executor.execute_phase(game_id, phase, extra_vars)

    async def execute_phase_async(
        self,
        game_id: str,
        phase: ActionPhase,
        extra_vars: dict[str, Any] | None = None,
    ) -> ActionChainResult:
        return await self.phase_executor.execute_phase_async(
            game_id, phase, extra_vars
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def get_templates(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.templates.get_all()]

    def apply_template(
        self,
        template_name: str,
        game_id: str,
        **overrides: Any,
    ) -> GameAction | None:
        template = self.templates.get_template(template_name)
        if not template:
            return None
        action = template.instantiate(game_id, **overrides)
        self._db.add_action(action)
        return action

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------

    def add_trigger(self, trigger: EventTrigger) -> str:
        return self.triggers.add_trigger(trigger)

    def remove_trigger(self, trigger_id: str) -> bool:
        return self.triggers.remove_trigger(trigger_id)

    def fire_event(
        self,
        event_type: str,
        game_id: str | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> list[str]:
        return self.triggers.fire_event(event_type, game_id, event_data)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def get_action_log(
        self, game_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self.chain_executor.get_action_log(game_id, limit)

    def get_rollback_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.rollback.get_history(limit)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def launch_game(
        self,
        game_id: str,
        action: GameAction,
        extra_vars: dict[str, Any] | None = None,
    ) -> LaunchResult:
        """Launch a game through the integrated controller."""
        return self.launcher.launch(game_id, action, extra_vars=extra_vars)

    def cancel_launch(self, game_id: str) -> None:
        """Cancel a running game launch."""
        self.launcher.cancel(game_id)

    def configure_platform_lookup(self) -> None:
        """Populate the variable resolver's platform id -> name mapping."""
        platforms = self._db.get_platforms()
        self.variable_resolver.set_platform_lookup(
            {p.id: p.name for p in platforms}
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start background services (scheduler, process monitor)."""
        self.configure_platform_lookup()
        self.scheduler.start()
        self.process_monitor.start()

    def stop(self) -> None:
        """Stop background services."""
        self.scheduler.stop()
        self.process_monitor.stop()

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    def _scheduled_execute(self, action_id: str, game_id: str | None) -> None:
        """Callback for scheduled actions."""
        action = self._db.get_action(action_id)
        if not action:
            logger.warning("Scheduled action %s not found", action_id)
            return
        game = self._db.get_game(game_id) if game_id else None
        self.chain_executor._execute_single_action(action, game, None)

    def _trigger_execute(
        self, action_id: str, game_id: str | None, event_data: dict[str, Any]
    ) -> None:
        """Callback for triggered actions."""
        action = self._db.get_action(action_id)
        if not action:
            logger.warning("Triggered action %s not found", action_id)
            return
        game = self._db.get_game(game_id) if game_id else None
        self.chain_executor._execute_single_action(action, game, event_data)
