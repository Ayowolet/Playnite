"""
ActionInjector — lets scripts inject custom play/install/pre-launch/etc. actions
at runtime without restarting the application.

Injection modes
---------------
* **override** — Replace the game's existing action of the same type entirely.
* **prepend** — Execute before existing actions.
* **append** — Execute after existing actions.

Scripts call the injector through the SDK::

    # Inside a script
    from playnite_python.actions.models import Action, ActionType

    def on_application_started():
        action = Action(
            name="Start Discord",
            type=ActionType.PRE_LAUNCH,
            script="import subprocess; subprocess.Popen(['Discord'])",
        )
        # api.addons doesn't own injector, so pass it in during setup
        __injector__.inject(action, game_id=None)   # global

Or via the CLI::

    playnite actions inject --game-id <uuid> --script "print('hello')" --type pre_launch
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .models import Action, ActionType
from .registry import ActionRegistry

if TYPE_CHECKING:
    from ..models.game import Game


class ActionInjector:
    """
    High-level interface for dynamically injecting actions.

    Parameters
    ----------
    registry:
        :class:`~actions.registry.ActionRegistry` to write into.
    """

    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry
        self._lock = threading.Lock()
        self._inject_hooks: List[Callable[[Action], None]] = []

    @property
    def registry(self) -> ActionRegistry:
        return self._registry

    # ------------------------------------------------------------------
    # Injection
    # ------------------------------------------------------------------

    def inject(self, action: Action, game_id: Optional[str] = None) -> Action:
        """
        Inject *action* into the registry.

        Parameters
        ----------
        action:
            The :class:`~actions.models.Action` to add.  Its ``game_id``
            field will be overridden by the *game_id* parameter if provided.
        game_id:
            Target game ID.  *None* = global (applies to all games).

        Returns
        -------
        Action
            The registered action (with its ``id`` assigned).
        """
        if game_id is not None:
            action.game_id = game_id
        result = self._registry.add_action(action)
        for cb in self._inject_hooks:
            self._safe_call(cb, result)
        return result

    def inject_play(
        self,
        game_id: str,
        script: str,
        name: str = "Custom Play",
        **kwargs: Any,
    ) -> Action:
        """Inject a custom play action for *game_id*."""
        action = Action(
            name=name,
            type=ActionType.PLAY,
            script=script,
            game_id=game_id,
            **kwargs,
        )
        return self.inject(action, game_id)

    def inject_pre_launch(
        self,
        script: str,
        name: str = "Pre-Launch Action",
        game_id: Optional[str] = None,
        priority: int = 100,
        **kwargs: Any,
    ) -> Action:
        """Inject a pre-launch action (global or game-specific)."""
        action = Action(
            name=name,
            type=ActionType.PRE_LAUNCH,
            script=script,
            priority=priority,
            game_id=game_id,
            **kwargs,
        )
        return self.inject(action, game_id)

    def inject_post_exit(
        self,
        script: str,
        name: str = "Post-Exit Action",
        game_id: Optional[str] = None,
        priority: int = 100,
        **kwargs: Any,
    ) -> Action:
        """Inject a post-exit action."""
        action = Action(
            name=name,
            type=ActionType.POST_EXIT,
            script=script,
            priority=priority,
            game_id=game_id,
            **kwargs,
        )
        return self.inject(action, game_id)

    def revoke(self, action_id: str) -> None:
        """Remove a previously injected action."""
        self._registry.remove_action(action_id)

    def revoke_by_source(self, source_script: str) -> int:
        """
        Remove all actions injected by *source_script*.

        Returns the number of actions removed.
        """
        to_remove = [
            a.id
            for a in self._registry.list_actions(enabled_only=False)
            if a.source_script == source_script
        ]
        for action_id in to_remove:
            self._registry.remove_action(action_id)
        return len(to_remove)

    def get_injected_actions(
        self,
        game_id: Optional[str] = None,
        action_type: Optional[ActionType] = None,
    ) -> List[Action]:
        """Return currently injected (registered) actions."""
        return self._registry.list_actions(game_id=game_id, action_type=action_type)

    # ------------------------------------------------------------------
    # Dynamic launcher override
    # ------------------------------------------------------------------

    def override_launcher(
        self,
        game_id: str,
        script: str,
        name: str = "Custom Launcher",
    ) -> Action:
        """
        Replace the default play action with a custom script launcher.

        Removes any existing PLAY-type actions for *game_id* first.
        """
        # Remove existing play overrides for this game
        existing = self._registry.list_actions(game_id=game_id, action_type=ActionType.PLAY)
        for a in existing:
            self._registry.remove_action(a.id)
        return self.inject_play(game_id, script, name=name, priority=0)

    # ------------------------------------------------------------------
    # Launch parameter modification
    # ------------------------------------------------------------------

    def modify_launch_params(
        self,
        game: "Game",
        arguments_append: str = "",
        env_vars: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Inject a pre-launch action that modifies game launch parameters.

        This is a convenience wrapper that injects a small script which
        mutates the game object's play action in-place.

        Parameters
        ----------
        game:
            The game whose play action will be modified.
        arguments_append:
            String to append to the play action's arguments.
        env_vars:
            Environment variables to set (injected via a script).
        """
        lines = []
        if arguments_append:
            lines.append(
                f"action = game.get_play_action()\n"
                f"if action:\n"
                f"    action.arguments = (action.arguments or '') + ' {arguments_append}'"
            )
        if env_vars:
            for k, v in env_vars.items():
                lines.append(f"import os; os.environ[{k!r}] = {v!r}")

        if lines:
            self.inject_pre_launch(
                script="\n".join(lines),
                name="Launch Parameter Modifier",
                game_id=game.id,
                priority=0,
            )

    # ------------------------------------------------------------------
    # On-inject callback
    # ------------------------------------------------------------------

    def on_inject(self, callback: Callable[[Action], None]) -> None:
        """Register a callback that fires whenever a new action is injected."""
        self._inject_hooks.append(callback)

    @staticmethod
    def _safe_call(fn: Callable, *args: Any) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001
            pass
