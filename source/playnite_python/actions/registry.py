"""
ActionRegistry — persistent store for all defined actions, chains, and profiles.

Storage
-------
Actions are persisted to a JSON file (``actions.json``) in the config
directory.  This is intentionally simple — no SQLite overhead for what is
expected to be a small (<1 000 rows) dataset.

Thread safety
-------------
All mutating operations are protected by a :class:`threading.RLock`.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

_log = logging.getLogger(__name__)

from .models import Action, ActionChainDef, ActionProfile, ActionType, TriggerType
from .safe_eval import safe_eval

if TYPE_CHECKING:
    from ..models.game import Game


class ActionRegistry:
    """
    Stores and retrieves :class:`~actions.models.Action` objects.

    Parameters
    ----------
    data_path:
        Directory (or file path) for persistent storage.  If a directory is
        provided, the registry file is created as ``actions.json`` inside it.
    """

    def __init__(self, data_path: str = "config") -> None:
        p = Path(data_path)
        if p.suffix == ".json":
            self._file = p
        else:
            self._file = p / "actions.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)

        self._actions: Dict[str, Action] = {}
        self._chains: Dict[str, ActionChainDef] = {}
        self._profiles: Dict[str, ActionProfile] = {}
        self._lock = threading.RLock()
        self._change_callbacks: List[Callable[[], None]] = []

        if self._file.exists():
            self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning(
                "Failed to load action registry from %s: %s; starting with empty registry",
                self._file, exc,
            )
            return
        for d in data.get("actions", []):
            a = Action.from_dict(d)
            self._actions[a.id] = a
        for d in data.get("chains", []):
            c = ActionChainDef.from_dict(d)
            self._chains[c.id] = c
        for d in data.get("profiles", []):
            p = ActionProfile.from_dict(d)
            self._profiles[p.id] = p

    def save(self) -> None:
        """Flush all actions/chains/profiles to disk."""
        with self._lock:
            data = {
                "actions": [a.to_dict() for a in self._actions.values()],
                "chains": [c.to_dict() for c in self._chains.values()],
                "profiles": [p.to_dict() for p in self._profiles.values()],
            }
        with open(self._file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # ------------------------------------------------------------------
    # Action CRUD
    # ------------------------------------------------------------------

    def add_action(self, action: Action) -> Action:
        with self._lock:
            self._actions[action.id] = action
        self.save()
        self._notify()
        return action

    def update_action(self, action: Action) -> None:
        with self._lock:
            if action.id not in self._actions:
                raise KeyError(f"Action '{action.id}' not found.")
            self._actions[action.id] = action
        self.save()
        self._notify()

    def remove_action(self, action_id: str) -> Optional[Action]:
        """Remove action by ID. Returns the removed :class:`Action`, or *None* if not found."""
        with self._lock:
            action = self._actions.pop(action_id, None)
        self.save()
        self._notify()
        return action

    def get_action(self, action_id: str) -> Optional[Action]:
        with self._lock:
            return self._actions.get(action_id)

    def list_actions(
        self,
        game_id: Optional[str] = None,
        action_type: Optional[ActionType] = None,
        enabled_only: bool = True,
    ) -> List[Action]:
        with self._lock:
            actions = list(self._actions.values())
        if enabled_only:
            actions = [a for a in actions if a.enabled]
        if action_type:
            actions = [a for a in actions if a.type == action_type]
        if game_id is not None:
            # Include actions for this game AND global actions (game_id=None)
            actions = [a for a in actions if a.game_id is None or a.game_id == game_id]
        return sorted(actions, key=lambda a: a.priority)

    def list_global_actions(self, action_type: Optional[ActionType] = None) -> List[Action]:
        return self.list_actions(game_id=None, action_type=action_type)

    def get_actions_for_game(self, game_id: str, trigger: Optional[ActionType] = None) -> List[Action]:
        """
        Return actions applicable to *game_id* (global + game-specific),
        sorted by priority.
        """
        return self.list_actions(game_id=game_id, action_type=trigger)

    # ------------------------------------------------------------------
    # Profile matching
    # ------------------------------------------------------------------

    def get_profile_actions(self, game: "Game") -> List[Action]:
        """
        Return actions from all profiles whose filter expression matches
        *game*.
        """
        matched: List[Action] = []
        with self._lock:
            profiles = [p for p in self._profiles.values() if p.enabled]
        for profile in profiles:
            try:
                ctx = {"game": game}
                if safe_eval(profile.filter_expr, ctx):
                    for action_id in profile.action_ids:
                        action = self.get_action(action_id)
                        if action and action.enabled:
                            matched.append(action)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "Profile %r filter_expr %r raised %s: %s; skipping profile",
                    profile.id, profile.filter_expr, type(exc).__name__, exc,
                )
        return sorted(matched, key=lambda a: a.priority)

    # ------------------------------------------------------------------
    # Chain CRUD
    # ------------------------------------------------------------------

    def add_chain(self, chain: ActionChainDef) -> ActionChainDef:
        with self._lock:
            self._chains[chain.id] = chain
        self.save()
        self._notify()
        return chain

    def update_chain(self, chain: ActionChainDef) -> None:
        with self._lock:
            if chain.id not in self._chains:
                raise KeyError(f"Chain '{chain.id}' not found.")
            self._chains[chain.id] = chain
        self.save()
        self._notify()

    def remove_chain(self, chain_id: str) -> Optional[ActionChainDef]:
        """Remove chain by ID. Returns the removed :class:`ActionChainDef`, or *None* if not found."""
        with self._lock:
            chain = self._chains.pop(chain_id, None)
        self.save()
        self._notify()
        return chain

    def get_chain(self, chain_id: str) -> Optional[ActionChainDef]:
        with self._lock:
            return self._chains.get(chain_id)

    def list_chains(self, game_id: Optional[str] = None) -> List[ActionChainDef]:
        with self._lock:
            chains = list(self._chains.values())
        if game_id is not None:
            chains = [c for c in chains if c.game_id is None or c.game_id == game_id]
        return chains

    def get_chains_for_trigger(
        self, trigger: TriggerType, game_id: Optional[str] = None
    ) -> List[ActionChainDef]:
        return [
            c for c in self.list_chains(game_id)
            if c.trigger == trigger
        ]

    # ------------------------------------------------------------------
    # Profile CRUD
    # ------------------------------------------------------------------

    def add_profile(self, profile: ActionProfile) -> ActionProfile:
        with self._lock:
            self._profiles[profile.id] = profile
        self.save()
        return profile

    def remove_profile(self, profile_id: str) -> Optional[ActionProfile]:
        """Remove profile by ID. Returns the removed :class:`ActionProfile`, or *None* if not found."""
        with self._lock:
            profile = self._profiles.pop(profile_id, None)
        self.save()
        return profile

    def get_profile(self, profile_id: str) -> Optional[ActionProfile]:
        with self._lock:
            return self._profiles.get(profile_id)

    def list_profiles(self) -> List[ActionProfile]:
        with self._lock:
            return list(self._profiles.values())

    # ------------------------------------------------------------------
    # Change notifications
    # ------------------------------------------------------------------

    def on_change(self, callback: Callable[[], None]) -> None:
        self._change_callbacks.append(callback)

    def _notify(self) -> None:
        with self._lock:
            callbacks = list(self._change_callbacks)
        for cb in callbacks:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "total_actions": len(self._actions),
                "enabled_actions": sum(1 for a in self._actions.values() if a.enabled),
                "global_actions": sum(1 for a in self._actions.values() if a.game_id is None),
                "chains": len(self._chains),
                "profiles": len(self._profiles),
            }
