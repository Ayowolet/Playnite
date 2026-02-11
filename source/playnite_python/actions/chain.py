"""
Action chain executor.

Executes an ordered sequence of :class:`~actions.models.Action` objects for a
game event, honoring:

* ``priority`` — lower numbers run first.
* ``async_`` — fire-and-forget vs. blocking.
* ``conditions`` — skip the action if conditions do not pass.
* ``timeout`` — per-action limit.
* ``rollback_script`` — run if the action fails.
* ``stop_on_failure`` (chain-level) — abort remaining actions on error.

Variable substitution
---------------------
Action scripts and arguments may reference game metadata and custom variables
using ``{var_name}`` syntax.  Built-in variables:

* ``{game.name}`` · ``{game.id}`` · ``{game.install_dir}``
* ``{game.platform}`` (first platform ID)
* ``{game.play_time}`` (seconds)
* ``{timestamp}`` · ``{platform}`` (OS)
"""

from __future__ import annotations

import concurrent.futures
import io
import re
import subprocess
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from .condition import evaluate_conditions
from .models import Action, ActionExecutorType, ActionLog, ActionType
from ..extensions.sandbox import ScriptSandbox
from ..extensions.config import ScriptConfig, SandboxLevel

if TYPE_CHECKING:
    from ..models.game import Game


# ---------------------------------------------------------------------------
# Variable substitution
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\{([^}]+)\}")


def _expand_variables(
    template: str,
    game: Optional["Game"],
    extra_vars: Optional[Dict[str, str]] = None,
) -> str:
    """Replace ``{var}`` tokens in *template* with actual values."""
    vars_: Dict[str, str] = {
        "timestamp": datetime.now().isoformat(),
        "platform": sys.platform,
    }
    if game:
        vars_.update(
            {
                "game.name": game.name,
                "game.id": game.id,
                "game.install_dir": game.install_directory or "",
                "game.version": game.version or "",
                "game.platform": game.platform_ids[0] if game.platform_ids else "",
                "game.play_time": str(game.play_time),
                "game.play_count": str(game.play_count),
                "game.is_installed": str(game.is_installed),
            }
        )
    if extra_vars:
        vars_.update(extra_vars)

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        return vars_.get(key, m.group(0))  # keep original if unknown

    return _VAR_RE.sub(_replace, template)


# ---------------------------------------------------------------------------
# Single action execution
# ---------------------------------------------------------------------------

class ActionExecutionError(Exception):
    """Raised when an action fails and stop_on_failure is set."""


def _execute_single(
    action: Action,
    game: Optional["Game"] = None,
    extra_vars: Optional[Dict[str, str]] = None,
) -> ActionLog:
    """
    Execute one action and return an :class:`~actions.models.ActionLog`.

    Never raises — errors are captured in the log entry.
    """
    log = ActionLog(
        action_id=action.id,
        action_name=action.name,
        game_id=game.id if game else None,
        game_name=game.name if game else "",
        started_at=datetime.now(),
        was_async=action.async_,
    )
    t0 = time.perf_counter()

    try:
        # Evaluate conditions
        if not evaluate_conditions(action.conditions, game):
            log.success = True
            log.output = "Skipped (conditions not met)"
            log.finished_at = datetime.now()
            log.duration_ms = (time.perf_counter() - t0) * 1000
            return log

        # Build resolved script/args
        resolved_script = _expand_variables(action.script, game, extra_vars)
        resolved_args = _expand_variables(action.arguments, game, extra_vars)
        resolved_exec = _expand_variables(action.executable, game, extra_vars)

        captured_out = io.StringIO()

        executor_type = action.executor_type

        if executor_type == ActionExecutorType.SCRIPT:
            # Use 60s default when action has no explicit timeout configured
            _run_script(
                resolved_script, game, extra_vars, captured_out,
                timeout=action.timeout or 60,
            )
        elif executor_type == ActionExecutorType.EXECUTABLE:
            _run_executable(resolved_exec, resolved_args, action.working_dir, action.timeout)
        elif executor_type == ActionExecutorType.URL:
            url = resolved_exec or resolved_script
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError(f"URL scheme not permitted: {url!r}")
            webbrowser.open(url)

        log.success = True
        log.output = captured_out.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.success = False
        log.error = str(exc) + "\n" + traceback.format_exc()
        # Attempt rollback — record failure instead of swallowing it silently
        if action.rollback_script:
            rb_out = io.StringIO()
            try:
                rb_script = _expand_variables(action.rollback_script, game, extra_vars)
                _run_script(rb_script, game, extra_vars, rb_out)
                log.rolled_back = True
            except Exception as rb_exc:  # noqa: BLE001
                log.error += f"\n[Rollback failed: {rb_exc}]"
            log.output += rb_out.getvalue()

    log.finished_at = datetime.now()
    log.duration_ms = (time.perf_counter() - t0) * 1000
    return log


def _run_script(
    script: str,
    game: Optional["Game"],
    extra_vars: Optional[Dict[str, str]],
    output: io.StringIO,
    timeout: int = 0,
) -> None:
    if not script.strip():
        return
    config = ScriptConfig.from_dict({
        "sandbox_level": SandboxLevel.STANDARD.value,
        "timeout": timeout,
    })
    sandbox = ScriptSandbox(config, extra_globals={"game": game, "vars": extra_vars or {}})
    result = sandbox.execute(script, script_path="<action_script>")
    output.write(result.stdout)
    if not result.success:
        if result.timed_out:
            raise TimeoutError(f"Action script timed out after {timeout}s")
        raise RuntimeError(str(result.error))


def _run_executable(
    path: str,
    args: str,
    working_dir: str,
    timeout: int,
) -> None:
    if not path.strip():
        return
    cmd = [path] + (args.split() if args.strip() else [])
    result = subprocess.run(
        cmd,
        cwd=working_dir or None,
        timeout=timeout or None,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Executable exited with code {result.returncode}: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Chain executor
# ---------------------------------------------------------------------------

class ActionChainExecutor:
    """
    Executes a list of :class:`~actions.models.Action` objects for a game.

    Parameters
    ----------
    stop_on_failure:
        If *True*, abort the chain when any synchronous action fails.
    on_action_complete:
        Optional callback fired after each action: ``callback(action, log)``.
    max_workers:
        Size of the thread pool used for async (fire-and-forget) actions.
        Default is 4.  Increase this if your library has many games that
        trigger concurrent async actions simultaneously.
    """

    def __init__(
        self,
        stop_on_failure: bool = False,
        on_action_complete: Optional[Callable[[Action, ActionLog], None]] = None,
        max_workers: int = 4,
    ) -> None:
        self._stop_on_failure = stop_on_failure
        self._on_complete = on_action_complete
        self._async_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="action-async"
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        actions: List[Action],
        game: Optional["Game"] = None,
        extra_vars: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[ActionLog], bool]:
        """
        Execute *actions* in priority order.

        Parameters
        ----------
        actions:
            Actions to execute (will be sorted by priority).
        game:
            Game context (may be *None*).
        extra_vars:
            Additional ``{var}`` substitutions.

        Returns
        -------
        (logs, success)
            *logs* — one :class:`~actions.models.ActionLog` per action.
            *success* — *False* if any synchronous action failed.
        """
        sorted_actions = sorted(actions, key=lambda a: a.priority)
        logs: List[ActionLog] = []
        overall_success = True

        for action in sorted_actions:
            if not action.enabled:
                continue

            if action.async_:
                # Fire-and-forget — don't wait
                self._async_executor.submit(
                    self._run_and_notify, action, game, extra_vars
                )
                # Create a placeholder log so the caller knows it was dispatched
                placeholder = ActionLog(
                    action_id=action.id,
                    action_name=action.name,
                    game_id=game.id if game else None,
                    game_name=game.name if game else "",
                    started_at=datetime.now(),
                    was_async=True,
                    success=True,
                    output="Dispatched asynchronously",
                )
                logs.append(placeholder)
            else:
                log = _execute_single(action, game, extra_vars)
                logs.append(log)
                if self._on_complete:
                    try:
                        self._on_complete(action, log)
                    except Exception:  # noqa: BLE001
                        pass
                if not log.success and log.output != "Skipped (conditions not met)":
                    overall_success = False
                    if self._stop_on_failure:
                        break

        return logs, overall_success

    def _run_and_notify(
        self,
        action: Action,
        game: Optional["Game"],
        extra_vars: Optional[Dict[str, str]],
    ) -> None:
        log = _execute_single(action, game, extra_vars)
        if self._on_complete:
            try:
                self._on_complete(action, log)
            except Exception:  # noqa: BLE001
                pass

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        """
        Shut down the internal thread pool.

        Parameters
        ----------
        wait:
            If *True* (default), block until all pending async actions finish.
            Set to *False* only when the caller can tolerate in-flight actions
            being abandoned (e.g. during a forced application exit).
        cancel_futures:
            If *True*, cancel futures that have not yet started (Python 3.9+).
        """
        self._async_executor.shutdown(wait=wait, cancel_futures=cancel_futures)
