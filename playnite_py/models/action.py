"""Game action models for the action injection system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class GameActionType(Enum):
    """How the action executes — mirrors C# GameActionType."""
    FILE = "file"           # Launch an executable file
    URL = "url"             # Open a URL
    EMULATOR = "emulator"   # Start via an emulator profile
    SCRIPT = "script"       # Execute a Python script


class ActionType(Enum):
    PLAY = "play"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    CUSTOM = "custom"


class TrackingMode(Enum):
    """How to monitor the running game process — mirrors C# TrackingMode."""
    DEFAULT = "default"               # Automatic best-effort
    PROCESS = "process"               # Origin process + all child processes
    DIRECTORY = "directory"           # Any process launched from a directory
    ORIGINAL_PROCESS = "original_process"  # Only the originally started process
    PROCESS_NAME = "process_name"     # Any process matching a given name


class ActionPhase(Enum):
    PRE_LAUNCH = "pre_launch"
    LAUNCH = "launch"
    POST_EXIT = "post_exit"
    PRE_INSTALL = "pre_install"
    POST_INSTALL = "post_install"
    PRE_UNINSTALL = "pre_uninstall"
    POST_UNINSTALL = "post_uninstall"


class ActionPriority(Enum):
    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100


# ---------------------------------------------------------------------------
# Condition model
# ---------------------------------------------------------------------------

@dataclass
class ActionCondition:
    """Condition that must be met for an action to execute."""
    field: str = ""           # e.g. "game.is_installed", "game.platform_ids", "env.os"
    operator: str = "equals"  # equals, not_equals, contains, not_contains, matches, gt, lt, gte, lte
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {"field": self.field, "operator": self.operator, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionCondition:
        """Deserialize from a dictionary."""
        return cls(
            field=data.get("field", ""),
            operator=data.get("operator", "equals"),
            value=data.get("value", ""),
        )


# ---------------------------------------------------------------------------
# Main GameAction model
# ---------------------------------------------------------------------------

@dataclass
class GameAction:
    """An injectable game action that can be attached to any game or run globally."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    action_type: ActionType = ActionType.CUSTOM
    game_action_type: GameActionType = GameActionType.SCRIPT
    phase: ActionPhase = ActionPhase.PRE_LAUNCH
    priority: int = ActionPriority.NORMAL.value
    # Script content: either inline Python code or a file path
    script: str = ""
    is_script_path: bool = False
    # File/URL/Emulator fields
    path: str = ""              # Executable path (FILE) or URL (URL) or emulator path
    emulator_id: str = ""       # Reference to emulator config (EMULATOR type)
    emulator_profile_id: str = ""
    is_play_action: bool = False  # Whether this is the primary play action
    # Execution settings
    working_directory: str = ""
    arguments: dict[str, str] = field(default_factory=dict)
    is_async: bool = False
    timeout: int = 30
    enabled: bool = True
    # Process tracking
    tracking_mode: TrackingMode = TrackingMode.DEFAULT
    tracking_path: str = ""              # Path or name for directory/process name tracking
    tracking_frequency: int = 2000       # ms between tracking checks
    initial_tracking_delay: int = 0      # ms before tracking starts
    # Conditions gating execution
    conditions: list[ActionCondition] = field(default_factory=list)
    # Targeting
    game_id: str | None = None  # None means global action
    source_script_id: str | None = None  # Which extension script injected this
    # Rollback support
    rollback_script: str = ""
    rollback_is_script_path: bool = False
    # Metadata
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "action_type": self.action_type.value,
            "game_action_type": self.game_action_type.value,
            "phase": self.phase.value,
            "priority": self.priority,
            "script": self.script,
            "is_script_path": self.is_script_path,
            "path": self.path,
            "emulator_id": self.emulator_id,
            "emulator_profile_id": self.emulator_profile_id,
            "is_play_action": self.is_play_action,
            "working_directory": self.working_directory,
            "arguments": dict(self.arguments),
            "is_async": self.is_async,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "tracking_mode": self.tracking_mode.value,
            "tracking_path": self.tracking_path,
            "tracking_frequency": self.tracking_frequency,
            "initial_tracking_delay": self.initial_tracking_delay,
            "conditions": [c.to_dict() for c in self.conditions],
            "game_id": self.game_id,
            "source_script_id": self.source_script_id,
            "rollback_script": self.rollback_script,
            "rollback_is_script_path": self.rollback_is_script_path,
            "created": self.created,
            "description": self.description,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameAction:
        """Deserialize from a dictionary."""
        d = dict(data)
        if "action_type" in d and isinstance(d["action_type"], str):
            d["action_type"] = ActionType(d["action_type"])
        if "game_action_type" in d and isinstance(d["game_action_type"], str):
            try:
                d["game_action_type"] = GameActionType(d["game_action_type"])
            except ValueError:
                d["game_action_type"] = GameActionType.SCRIPT
        if "tracking_mode" in d and isinstance(d["tracking_mode"], str):
            try:
                d["tracking_mode"] = TrackingMode(d["tracking_mode"])
            except ValueError:
                d["tracking_mode"] = TrackingMode.DEFAULT
        if "phase" in d and isinstance(d["phase"], str):
            d["phase"] = ActionPhase(d["phase"])
        d["conditions"] = [
            ActionCondition.from_dict(c) for c in d.get("conditions", [])
        ]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Execution result models
# ---------------------------------------------------------------------------

@dataclass
class ActionResult:
    """Result of executing a single action."""
    action_id: str = ""
    action_name: str = ""
    success: bool = True
    output: str = ""
    error: str = ""
    duration: float = 0.0  # seconds
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    rolled_back: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "action_id": self.action_id,
            "action_name": self.action_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration": self.duration,
            "timestamp": self.timestamp,
            "rolled_back": self.rolled_back,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionResult:
        """Deserialize from a dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ActionChainResult:
    """Result of executing an entire action chain for one phase."""
    game_id: str = ""
    phase: ActionPhase = ActionPhase.PRE_LAUNCH
    results: list[ActionResult] = field(default_factory=list)
    total_duration: float = 0.0

    @property
    def all_succeeded(self) -> bool:
        """Check whether every action in the chain succeeded."""
        return all(r.success for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "game_id": self.game_id,
            "phase": self.phase.value,
            "results": [r.to_dict() for r in self.results],
            "total_duration": self.total_duration,
            "all_succeeded": self.all_succeeded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionChainResult:
        """Deserialize from a dictionary."""
        d = dict(data)
        if "phase" in d and isinstance(d["phase"], str):
            d["phase"] = ActionPhase(d["phase"])
        d["results"] = [ActionResult.from_dict(r) for r in d.get("results", [])]
        d.pop("all_succeeded", None)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
