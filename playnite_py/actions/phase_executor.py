"""Phase execution with automatic rollback on failure."""

from __future__ import annotations

import logging
from typing import Any

from playnite_py.models.action import ActionChainResult, ActionPhase
from playnite_py.models.database import GameDatabase
from playnite_py.actions.chain import ActionChainExecutor
from playnite_py.actions.rollback import RollbackManager

logger = logging.getLogger(__name__)


class ActionPhaseExecutor:
    """Executes action phases and handles rollback on failure."""

    def __init__(
        self,
        database: GameDatabase,
        chain_executor: ActionChainExecutor,
        rollback_manager: RollbackManager,
    ):
        self._db = database
        self._chain_executor = chain_executor
        self._rollback = rollback_manager

    def execute_phase(
        self,
        game_id: str,
        phase: ActionPhase,
        extra_vars: dict[str, Any] | None = None,
    ) -> ActionChainResult:
        """Execute all actions for a game phase. Handles rollback on failure."""
        result = self._chain_executor.execute_phase(game_id, phase, extra_vars)

        # If the chain failed, attempt rollback
        if not result.all_succeeded:
            game = self._db.get_game(game_id)
            game_ctx = game.to_dict() if game else {}
            rollback_records = self._rollback.rollback_chain(
                result.results, game_ctx
            )
            # Mark rolled-back actions
            for rr in rollback_records:
                for ar in result.results:
                    if ar.action_id == rr.action_id and rr.success:
                        ar.rolled_back = True

        return result

    async def execute_phase_async(
        self,
        game_id: str,
        phase: ActionPhase,
        extra_vars: dict[str, Any] | None = None,
    ) -> ActionChainResult:
        """Execute all actions for a game phase asynchronously."""
        return await self._chain_executor.execute_phase_async(
            game_id, phase, extra_vars
        )
