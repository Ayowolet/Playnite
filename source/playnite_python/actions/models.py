"""
Data models for the game action injection system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ActionType(Enum):
    """What the action does."""
    PLAY = "play"               # Replace/override the default play action
    INSTALL = "install"         # Override install
    UNINSTALL = "uninstall"     # Override uninstall
    PRE_LAUNCH = "pre_launch"   # Run before game starts
    POST_EXIT = "post_exit"     # Run after game closes
    CUSTOM = "custom"           # Custom / user-defined


class ActionExecutorType(Enum):
    """How the action is executed."""
    SCRIPT = "script"           # Inline Python script
    EXECUTABLE = "executable"   # Launch an external process
    URL = "url"                 # Open a URL


class ConditionType(Enum):
    FILE_EXISTS = "file_exists"
    PROCESS_RUNNING = "process_running"
    GAME_HAS_TAG = "game_has_tag"
    GAME_IS_INSTALLED = "game_is_installed"
    PLATFORM_IS = "platform_is"
    SCRIPT = "script"
    TIME_IS = "time_is"
    ALWAYS = "always"
    NEVER = "never"


class TriggerType(Enum):
    GAME_STARTING = "game_starting"
    GAME_STARTED = "game_started"
    GAME_STOPPED = "game_stopped"
    GAME_INSTALLED = "game_installed"
    GAME_UNINSTALLED = "game_uninstalled"
    LIBRARY_UPDATED = "library_updated"
    APP_STARTED = "app_started"
    APP_STOPPED = "app_stopped"
    SCHEDULE = "schedule"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Condition model
# ---------------------------------------------------------------------------

@dataclass
class ActionCondition:
    """
    A single condition that determines whether an action should run.

    ``operator`` can be ``"and"`` or ``"or"`` when combining with the
    previous condition in a list.
    """
    type: ConditionType = ConditionType.ALWAYS
    value: str = ""           # Meaning depends on type
    negate: bool = False      # If True, condition passes when check fails
    operator: str = "and"     # "and" | "or" (for multi-condition lists)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "value": self.value,
            "negate": self.negate,
            "operator": self.operator,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionCondition":
        return cls(
            type=ConditionType(d.get("type", "always")),
            value=d.get("value", ""),
            negate=d.get("negate", False),
            operator=d.get("operator", "and"),
        )


# ---------------------------------------------------------------------------
# Action variable
# ---------------------------------------------------------------------------

@dataclass
class ActionVariable:
    """
    A named variable that can be referenced in action scripts/args as
    ``{var_name}``.  Built-in variables (game.name, etc.) are expanded
    automatically by the executor.
    """
    name: str = ""
    value: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "value": self.value, "description": self.description}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionVariable":
        return cls(
            name=d.get("name", ""),
            value=d.get("value", ""),
            description=d.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Main Action model
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """
    An injectable game action.

    Parameters
    ----------
    id:
        Unique identifier (UUID string).
    name:
        Human-readable label.
    type:
        When / how the action participates in game launch.
    executor_type:
        Whether to run a script, an executable, or open a URL.
    script:
        Python source for ``executor_type=SCRIPT``.
    executable:
        Path to executable for ``executor_type=EXECUTABLE``.
    arguments:
        Arguments (may reference ``{var}`` variables).
    working_dir:
        Working directory for executable.
    conditions:
        List of :class:`ActionCondition` that all must pass (logical AND by
        default; individual conditions can use ``operator="or"``).
    priority:
        Lower number = executed first.  Default 100.
    async_:
        If *True*, the action does not block subsequent actions.
    timeout:
        Per-action timeout in seconds (0 = no limit).
    game_id:
        If set, action only applies to this specific game.  ``None`` = global.
    enabled:
        Whether the action is active.
    rollback_script:
        Python source executed if the action fails (best-effort).
    source_script:
        Name of the script/extension that registered this action (if any).
    variables:
        Additional variable definitions.
    triggers:
        Event types that activate this action (used by scheduler/trigger sys).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unnamed Action"
    type: ActionType = ActionType.PRE_LAUNCH
    executor_type: ActionExecutorType = ActionExecutorType.SCRIPT
    script: str = ""
    executable: str = ""
    arguments: str = ""
    working_dir: str = ""
    conditions: List[ActionCondition] = field(default_factory=list)
    priority: int = 100
    async_: bool = False
    timeout: int = 60
    game_id: Optional[str] = None
    enabled: bool = True
    rollback_script: str = ""
    source_script: Optional[str] = None
    variables: List[ActionVariable] = field(default_factory=list)
    triggers: List[TriggerType] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def __repr__(self) -> str:
        return (
            f"Action(id={self.id!r}, name={self.name!r}, "
            f"type={self.type.value!r}, enabled={self.enabled!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "executor_type": self.executor_type.value,
            "script": self.script,
            "executable": self.executable,
            "arguments": self.arguments,
            "working_dir": self.working_dir,
            "conditions": [c.to_dict() for c in self.conditions],
            "priority": self.priority,
            "async_": self.async_,
            "timeout": self.timeout,
            "game_id": self.game_id,
            "enabled": self.enabled,
            "rollback_script": self.rollback_script,
            "source_script": self.source_script,
            "variables": [v.to_dict() for v in self.variables],
            "triggers": [t.value for t in self.triggers],
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Action":
        a = cls()
        a.id = d.get("id", str(uuid.uuid4()))
        a.name = d.get("name", "Unnamed Action")
        a.type = ActionType(d.get("type", "pre_launch"))
        a.executor_type = ActionExecutorType(d.get("executor_type", "script"))
        a.script = d.get("script", "")
        a.executable = d.get("executable", "")
        a.arguments = d.get("arguments", "")
        a.working_dir = d.get("working_dir", "")
        a.conditions = [ActionCondition.from_dict(c) for c in d.get("conditions", [])]
        a.priority = d.get("priority", 100)
        a.async_ = d.get("async_", False)
        a.timeout = d.get("timeout", 60)
        a.game_id = d.get("game_id")
        a.enabled = d.get("enabled", True)
        a.rollback_script = d.get("rollback_script", "")
        a.source_script = d.get("source_script")
        a.variables = [ActionVariable.from_dict(v) for v in d.get("variables", [])]
        a.triggers = [TriggerType(t) for t in d.get("triggers", [])]
        raw_created = d.get("created_at")
        if raw_created:
            a.created_at = datetime.fromisoformat(raw_created)
        return a


# ---------------------------------------------------------------------------
# Action chain definition
# ---------------------------------------------------------------------------

@dataclass
class ActionChainDef:
    """
    An ordered sequence of action IDs to execute for a specific game event.

    The chain executes actions sorted by their ``priority`` field, then by
    their order in this list as a secondary key.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Chain"
    game_id: Optional[str] = None
    action_ids: List[str] = field(default_factory=list)
    trigger: TriggerType = TriggerType.GAME_STARTING
    stop_on_failure: bool = False

    def __repr__(self) -> str:
        return (
            f"ActionChainDef(id={self.id!r}, name={self.name!r}, "
            f"trigger={self.trigger.value!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "game_id": self.game_id,
            "action_ids": self.action_ids,
            "trigger": self.trigger.value,
            "stop_on_failure": self.stop_on_failure,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionChainDef":
        obj = cls()
        obj.id = d.get("id", str(uuid.uuid4()))
        obj.name = d.get("name", "Chain")
        obj.game_id = d.get("game_id")
        obj.action_ids = d.get("action_ids", [])
        obj.trigger = TriggerType(d.get("trigger", "game_starting"))
        obj.stop_on_failure = d.get("stop_on_failure", False)
        return obj


# ---------------------------------------------------------------------------
# Action log entry
# ---------------------------------------------------------------------------

@dataclass
class ActionLog:
    """A single action execution record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str = ""
    action_name: str = ""
    game_id: Optional[str] = None
    game_name: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    success: bool = False
    error: str = ""
    output: str = ""
    duration_ms: float = 0.0
    was_async: bool = False
    rolled_back: bool = False

    def __repr__(self) -> str:
        return (
            f"ActionLog(id={self.id!r}, action_name={self.action_name!r}, "
            f"success={self.success!r})"
        )

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "action_name": self.action_name,
            "game_id": self.game_id,
            "game_name": self.game_name,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "success": self.success,
            "error": self.error,
            "output": self.output,
            "duration_ms": round(self.duration_ms, 2),
            "was_async": self.was_async,
            "rolled_back": self.rolled_back,
        }


# ---------------------------------------------------------------------------
# Action profile (apply same actions to matching games)
# ---------------------------------------------------------------------------

@dataclass
class ActionProfile:
    """
    A set of actions applied to all games matching a filter expression.

    *filter_expr* is a Python expression receiving ``game`` as the variable::

        profile.filter_expr = "game.is_installed and 'RPG' in game.genre_ids"
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Profile"
    filter_expr: str = "True"   # Python expression
    action_ids: List[str] = field(default_factory=list)
    enabled: bool = True

    def __repr__(self) -> str:
        return f"ActionProfile(id={self.id!r}, name={self.name!r}, enabled={self.enabled!r})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "filter_expr": self.filter_expr,
            "action_ids": self.action_ids,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionProfile":
        obj = cls()
        obj.id = d.get("id", str(uuid.uuid4()))
        obj.name = d.get("name", "Profile")
        obj.filter_expr = d.get("filter_expr", "True")
        obj.action_ids = d.get("action_ids", [])
        obj.enabled = d.get("enabled", True)
        return obj
