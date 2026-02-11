"""Action rollback: undo changes made by failed actions."""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from playnite_py.models.action import ActionResult, GameAction
from playnite_py.models.database import GameDatabase
from playnite_py.scripting.sandbox import SandboxedExecutor
from playnite_py.scripting.config import ScriptConfig, SandboxLevel
from playnite_py.utils import BoundedList

logger = logging.getLogger(__name__)


@dataclass
class RollbackRecord:
    """Record of a rollback attempt."""
    action_id: str = ""
    action_name: str = ""
    success: bool = False
    output: str = ""
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "action_id": self.action_id,
            "action_name": self.action_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class RollbackManager:
    """Manages rollback scripts for actions and executes them on failure."""

    def __init__(self, database: GameDatabase, max_history: int = 1000):
        self._db = database
        self._history: BoundedList[RollbackRecord] = BoundedList(max_history)

    def rollback_action(
        self,
        action_id: str,
        game_context: dict[str, Any] | None = None,
    ) -> RollbackRecord:
        """Execute the rollback script for a specific action."""
        action = self._db.get_action(action_id)
        record = RollbackRecord(action_id=action_id)

        if not action:
            record.error = f"Action '{action_id}' not found"
            self._history.append(record)
            return record

        record.action_name = action.name

        if not action.rollback_script:
            record.error = "No rollback script defined for this action"
            self._history.append(record)
            return record

        try:
            config = ScriptConfig(
                timeout=action.timeout,
                sandbox_level=SandboxLevel.BASIC,
            )
            executor = SandboxedExecutor(config, action.working_directory or ".")
            global_vars: dict[str, Any] = {
                "game": game_context or {},
                "action": action.to_dict(),
            }

            if action.rollback_is_script_path:
                result = executor.execute_file(
                    action.rollback_script, global_vars, timeout=action.timeout
                )
            else:
                result = executor.execute_code(
                    action.rollback_script, global_vars, timeout=action.timeout
                )

            record.success = result["success"]
            record.output = result.get("stdout", "")
            record.error = result.get("error", "")

        except Exception as e:
            record.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

        self._history.append(record)
        return record

    def rollback_chain(
        self,
        action_results: list[ActionResult],
        game_context: dict[str, Any] | None = None,
    ) -> list[RollbackRecord]:
        """Roll back all actions in a chain that completed, in reverse order."""
        records = []
        for result in reversed(action_results):
            if result.success:
                record = self.rollback_action(result.action_id, game_context)
                records.append(record)
        return records

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent rollback records up to the specified limit."""
        return [r.to_dict() for r in self._history[-limit:]]

    def clear_history(self) -> None:
        """Clear all stored rollback history."""
        self._history.clear()
