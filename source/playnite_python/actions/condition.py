"""
Action condition evaluators.

Conditions are evaluated just before an action runs.  If all conditions pass
(considering the ``operator`` field for OR logic), the action executes.

Built-in condition types
------------------------
* ``ALWAYS``          — always passes (default).
* ``NEVER``           — never passes (useful for disabling an action temporarily).
* ``FILE_EXISTS``     — passes if a filesystem path exists.
* ``PROCESS_RUNNING`` — passes if a process with the given name is running.
* ``GAME_HAS_TAG``    — passes if the game has the named tag.
* ``GAME_IS_INSTALLED`` — passes if the game is installed.
* ``PLATFORM_IS``     — passes if the game's platform name matches.
* ``SCRIPT``          — evaluates a Python expression; passes if truthy.
* ``TIME_IS``         — passes if current hour matches ``HH`` (24-hour).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

_log = logging.getLogger(__name__)

from .models import ActionCondition, ConditionType
from .safe_eval import safe_eval

if TYPE_CHECKING:
    from ..models.game import Game


# ---------------------------------------------------------------------------
# Individual evaluators
# ---------------------------------------------------------------------------

def _eval_always(_condition: ActionCondition, _game: Optional["Game"]) -> bool:
    return True


def _eval_never(_condition: ActionCondition, _game: Optional["Game"]) -> bool:
    return False


def _eval_file_exists(condition: ActionCondition, _game: Optional["Game"]) -> bool:
    return Path(condition.value).exists()


def _eval_process_running(condition: ActionCondition, _game: Optional["Game"]) -> bool:
    target = condition.value.lower()
    try:
        import psutil  # type: ignore[import]
        return any(
            p.name().lower() == target
            for p in psutil.process_iter(["name"])
            if p.info.get("name")
        )
    except ImportError:
        pass
    # Fallback: use tasklist on Windows, pgrep on Unix
    import subprocess, sys
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False,
        )
        return target in result.stdout.lower()
    result = subprocess.run(
        ["pgrep", "-l", target], capture_output=True, text=True, check=False,
    )
    # pgrep: 0 = found, 1 = not found, 2+ = invocation error
    if result.returncode > 1:
        _log.warning(
            "PROCESS_RUNNING: psutil unavailable and pgrep failed "
            "(rc=%d); condition returns False", result.returncode,
        )
    return result.returncode == 0


def _eval_game_has_tag(condition: ActionCondition, game: Optional["Game"]) -> bool:
    if game is None:
        return False
    return condition.value in game.tag_ids or any(
        condition.value.lower() == tid.lower() for tid in game.tag_ids
    )


def _eval_game_is_installed(_condition: ActionCondition, game: Optional["Game"]) -> bool:
    if game is None:
        return False
    return game.is_installed


def _eval_platform_is(condition: ActionCondition, game: Optional["Game"]) -> bool:
    if game is None:
        return False
    return any(
        condition.value.lower() in pid.lower() for pid in game.platform_ids
    )


def _eval_script(condition: ActionCondition, game: Optional["Game"]) -> bool:
    ctx: Dict[str, Any] = {"game": game}
    try:
        return bool(safe_eval(condition.value, ctx))
    except Exception as exc:  # noqa: BLE001
        _log.debug(
            "SCRIPT condition %r raised %s: %s; treating as False",
            condition.value, type(exc).__name__, exc,
        )
        return False


def _eval_time_is(condition: ActionCondition, _game: Optional["Game"]) -> bool:
    from datetime import datetime
    try:
        target_hour = int(condition.value)
        return datetime.now().hour == target_hour
    except ValueError:
        return False


_EVALUATORS: Dict[ConditionType, Callable[[ActionCondition, Optional["Game"]], bool]] = {
    ConditionType.ALWAYS: _eval_always,
    ConditionType.NEVER: _eval_never,
    ConditionType.FILE_EXISTS: _eval_file_exists,
    ConditionType.PROCESS_RUNNING: _eval_process_running,
    ConditionType.GAME_HAS_TAG: _eval_game_has_tag,
    ConditionType.GAME_IS_INSTALLED: _eval_game_is_installed,
    ConditionType.PLATFORM_IS: _eval_platform_is,
    ConditionType.SCRIPT: _eval_script,
    ConditionType.TIME_IS: _eval_time_is,
}


# ---------------------------------------------------------------------------
# Compound evaluator
# ---------------------------------------------------------------------------

def evaluate_conditions(
    conditions: List[ActionCondition],
    game: Optional["Game"] = None,
) -> bool:
    """
    Evaluate a list of conditions applying AND/OR logic.

    If *conditions* is empty, returns *True* (no conditions = always run).

    Evaluation rules
    ----------------
    * Conditions with ``operator="and"`` are ANDed with the running result.
    * Conditions with ``operator="or"`` are ORed.
    * Each condition's final result is XORed with its ``negate`` flag.

    Parameters
    ----------
    conditions:
        List of :class:`~actions.models.ActionCondition`.
    game:
        The game being acted on (may be *None* for non-game-specific actions).

    Returns
    -------
    bool
    """
    if not conditions:
        return True

    result = True
    first = True

    for cond in conditions:
        evaluator = _EVALUATORS.get(cond.type, _eval_always)
        raw = evaluator(cond, game)
        # Apply negate
        value = (not raw) if cond.negate else raw

        if first:
            result = value
            first = False
        elif cond.operator.lower() == "or":
            result = result or value
        else:  # "and" (default)
            result = result and value

    return result


def condition_from_simple(type_str: str, value: str = "", negate: bool = False) -> ActionCondition:
    """Convenience factory for creating simple conditions."""
    return ActionCondition(
        type=ConditionType(type_str),
        value=value,
        negate=negate,
    )
