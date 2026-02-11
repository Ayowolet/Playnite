"""Pre-built action templates for common game launch patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playnite_py.models.action import (
    ActionCondition, ActionPhase, ActionType, GameAction,
)


@dataclass
class ActionTemplate:
    """A reusable action template that can be instantiated for any game."""
    name: str = ""
    description: str = ""
    category: str = ""
    phase: ActionPhase = ActionPhase.PRE_LAUNCH
    action_type: ActionType = ActionType.CUSTOM
    priority: int = 50
    script: str = ""
    is_async: bool = False
    timeout: int = 30
    conditions: list[ActionCondition] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def instantiate(self, game_id: str, **overrides: Any) -> GameAction:
        """Create a GameAction from this template for a specific game."""
        action = GameAction(
            name=overrides.get("name", self.name),
            action_type=self.action_type,
            phase=overrides.get("phase", self.phase),
            priority=overrides.get("priority", self.priority),
            script=overrides.get("script", self.script),
            is_async=overrides.get("is_async", self.is_async),
            timeout=overrides.get("timeout", self.timeout),
            conditions=list(self.conditions),
            game_id=game_id,
            description=self.description,
            tags=list(self.tags),
        )
        return action

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "phase": self.phase.value,
            "action_type": self.action_type.value,
            "priority": self.priority,
            "script": self.script,
            "is_async": self.is_async,
            "timeout": self.timeout,
            "conditions": [c.to_dict() for c in self.conditions],
            "tags": self.tags,
        }


class ActionTemplateRegistry:
    """Registry of built-in and custom action templates."""

    def __init__(self):
        self._templates: dict[str, ActionTemplate] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in action templates."""
        self.register(ActionTemplate(
            name="Close Background Apps",
            description="Close resource-intensive background applications before launching a game",
            category="Performance",
            phase=ActionPhase.PRE_LAUNCH,
            priority=80,
            is_async=False,
            timeout=15,
            tags=["performance", "cleanup"],
            script="""
import subprocess, sys
apps_to_close = args.get("apps", "").split(",")
closed = []
if sys.platform == "win32":
    for app in apps_to_close:
        app = app.strip()
        if app:
            subprocess.run(["taskkill", "/IM", app, "/F"], capture_output=True)
            closed.append(app)
else:
    for app in apps_to_close:
        app = app.strip()
        if app:
            subprocess.run(["pkill", "-f", app], capture_output=True)
            closed.append(app)
print(f"Closed: {closed}")
""",
        ))

        self.register(ActionTemplate(
            name="Enable VPN",
            description="Connect to VPN before game launch",
            category="Network",
            phase=ActionPhase.PRE_LAUNCH,
            priority=90,
            is_async=True,
            timeout=30,
            tags=["network", "vpn"],
            script="""
import subprocess
vpn_config = args.get("vpn_config", "")
if vpn_config:
    result = subprocess.run(
        ["openvpn", "--config", vpn_config, "--daemon"],
        capture_output=True, text=True, timeout=25
    )
    print(f"VPN started: {result.returncode == 0}")
else:
    print("No VPN config provided")
""",
        ))

        self.register(ActionTemplate(
            name="Discord Rich Presence",
            description="Set Discord Rich Presence to show current game",
            category="Social",
            phase=ActionPhase.PRE_LAUNCH,
            priority=30,
            is_async=True,
            timeout=10,
            tags=["social", "discord"],
            script="""
game_name = game.get("name", "Unknown Game")
print(f"Discord Rich Presence set to: {game_name}")
""",
        ))

        self.register(ActionTemplate(
            name="Backup Save Files",
            description="Back up save files before launching a game",
            category="Data",
            phase=ActionPhase.PRE_LAUNCH,
            priority=70,
            is_async=False,
            timeout=30,
            tags=["backup", "saves"],
            script="""
import shutil, os
from datetime import datetime
save_dir = args.get("save_dir", "")
backup_dir = args.get("backup_dir", "")
if save_dir and backup_dir and os.path.exists(save_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"save_{timestamp}")
    shutil.copytree(save_dir, dest)
    print(f"Backed up to {dest}")
else:
    print("Save directory not found or backup dir not configured")
""",
        ))

        self.register(ActionTemplate(
            name="Log Playtime",
            description="Record game session start/end times",
            category="Tracking",
            phase=ActionPhase.POST_EXIT,
            priority=50,
            is_async=False,
            timeout=5,
            tags=["tracking", "playtime"],
            script="""
import json, os
from datetime import datetime
log_file = args.get("log_file", "playtime_log.json")
entry = {
    "game_id": game.get("id", ""),
    "game_name": game.get("name", ""),
    "timestamp": datetime.now().isoformat(),
    "event": "session_end",
}
existing = []
if os.path.exists(log_file):
    with open(log_file) as f:
        existing = json.load(f)
existing.append(entry)
with open(log_file, "w") as f:
    json.dump(existing, f, indent=2)
print(f"Session logged for {entry['game_name']}")
""",
        ))

        self.register(ActionTemplate(
            name="Set CPU Affinity",
            description="Set CPU affinity for the game process",
            category="Performance",
            phase=ActionPhase.PRE_LAUNCH,
            priority=60,
            is_async=True,
            timeout=10,
            tags=["performance", "cpu"],
            conditions=[
                ActionCondition(field="env.os", operator="not_equals", value="darwin"),
            ],
            script="""
import os
cores = args.get("cores", "")
if cores:
    core_list = [int(c.strip()) for c in cores.split(",")]
    os.sched_setaffinity(0, core_list)
    print(f"CPU affinity set to cores: {core_list}")
""",
        ))

    def register(self, template: ActionTemplate) -> None:
        """Register an action template by name."""
        self._templates[template.name] = template

    def unregister(self, name: str) -> bool:
        """Remove a template by name and return whether it existed."""
        return self._templates.pop(name, None) is not None

    def get_template(self, name: str) -> ActionTemplate | None:
        """Return a template by name, or None if not found."""
        return self._templates.get(name)

    def get_all(self) -> list[ActionTemplate]:
        """Return all registered action templates."""
        return list(self._templates.values())

    def search(
        self,
        query: str = "",
        category: str = "",
        tags: list[str] | None = None,
    ) -> list[ActionTemplate]:
        """Search templates by name, category, or tags."""
        results = list(self._templates.values())
        if query:
            q = query.lower()
            results = [
                t for t in results
                if q in t.name.lower() or q in t.description.lower()
            ]
        if category:
            results = [t for t in results if t.category.lower() == category.lower()]
        if tags:
            tag_set = set(t.lower() for t in tags)
            results = [
                t for t in results
                if tag_set.intersection(tg.lower() for tg in t.tags)
            ]
        return results
