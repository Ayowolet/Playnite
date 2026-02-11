"""
Rollback manager for failed action chains.

When an action chain runs as part of a game launch sequence and one or more
actions fail (or the game never starts), the :class:`RollbackManager` can
undo any side-effects from successfully completed actions that have a
``rollback_script`` defined.

Usage
-----
::

    rm = RollbackManager()

    # Before running an action, push its rollback onto the stack
    for action in pre_launch_actions:
        log = executor.execute_one(action, game)
        if log.success and action.rollback_script:
            rm.push(action, game)

    # If the game doesn't start
    if not game_started:
        rm.rollback_all()
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .models import Action, ActionLog
from ..extensions.sandbox import ScriptSandbox
from ..extensions.config import ScriptConfig, SandboxLevel

if TYPE_CHECKING:
    from ..models.game import Game


class RollbackEntry:
    """One entry on the rollback stack."""

    def __init__(self, action: Action, game: Optional["Game"]) -> None:
        self.action = action
        self.game = game
        self.pushed_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action.id,
            "action_name": self.action.name,
            "game_id": self.game.id if self.game else None,
            "pushed_at": self.pushed_at.isoformat(),
        }


class RollbackManager:
    """
    Stack-based rollback manager.

    Entries are added LIFO so that the last completed action is rolled back
    first (undoing in reverse order).

    Each rollback script is executed inside a :class:`~extensions.sandbox.ScriptSandbox`
    at ``STANDARD`` level with a fixed **30-second timeout**.  This is
    intentionally conservative: rollback scripts should be fast cleanup
    operations.  There is currently no per-action override for this timeout;
    if a rollback script needs more time it should delegate the long-running
    work to a background process rather than blocking.
    """

    def __init__(self) -> None:
        self._stack: List[RollbackEntry] = []

    # ------------------------------------------------------------------
    # Stack management
    # ------------------------------------------------------------------

    def push(self, action: Action, game: Optional["Game"] = None) -> None:
        """
        Push *action* onto the rollback stack.

        Only call this after the action has *successfully* completed.
        """
        if action.rollback_script:
            self._stack.append(RollbackEntry(action, game))

    def clear(self) -> None:
        """Discard all rollback entries (e.g. after successful launch)."""
        self._stack.clear()

    def depth(self) -> int:
        return len(self._stack)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def rollback_all(self) -> List[ActionLog]:
        """
        Execute all rollback scripts in reverse order (LIFO).

        Returns a list of :class:`~actions.models.ActionLog` entries, one per
        rolled-back action.  Never raises; errors are captured in logs.
        """
        logs: List[ActionLog] = []
        while self._stack:
            entry = self._stack.pop()
            log = self._execute_rollback(entry)
            logs.append(log)
        return logs

    def rollback_last(self) -> Optional[ActionLog]:
        """Roll back only the last pushed action."""
        if not self._stack:
            return None
        entry = self._stack.pop()
        return self._execute_rollback(entry)

    def _execute_rollback(self, entry: RollbackEntry) -> ActionLog:
        action = entry.action
        game = entry.game
        log = ActionLog(
            action_id=action.id,
            action_name=f"[ROLLBACK] {action.name}",
            game_id=game.id if game else None,
            game_name=game.name if game else "",
            started_at=datetime.now(),
        )
        config = ScriptConfig.from_dict({
            "sandbox_level": SandboxLevel.STANDARD.value,
            "timeout": 30,
        })
        sandbox = ScriptSandbox(config, extra_globals={"game": game})
        result = sandbox.execute(
            action.rollback_script,
            script_path=f"<rollback:{action.name}>",
        )
        if result.success:
            log.success = True
            log.rolled_back = True
        else:
            log.success = False
            log.error = str(result.error)
        log.output = result.stdout
        log.finished_at = datetime.now()
        log.duration_ms = (
            (log.finished_at - log.started_at).total_seconds() * 1000
        )
        return log

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_pending(self) -> List[Dict[str, Any]]:
        """Return the current rollback stack as a list of dicts (top first)."""
        return [e.to_dict() for e in reversed(self._stack)]
