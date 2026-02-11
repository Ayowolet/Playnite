"""Hook dispatching: execute lifecycle hooks across loaded scripts."""

from __future__ import annotations

import logging
from typing import Any

from playnite_py.scripting.events import (
    EventArgs,
    HOOK_EVENT_ARGS_MAP,
    LIFECYCLE_HOOKS,
    OnGameStartingEventArgs,
)
from playnite_py.scripting.loader import ScriptInfo, ScriptLoader
from playnite_py.scripting.sandbox import SandboxedExecutor
from playnite_py.scripting.metrics import MetricsTracker, ExecutionTimer

logger = logging.getLogger(__name__)


class HookDispatcher:
    """Executes lifecycle hooks across all loaded scripts."""

    def __init__(self, loader: ScriptLoader, metrics: MetricsTracker):
        self._loader = loader
        self._metrics = metrics

    def execute_hook(self, hook_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a lifecycle hook across all loaded scripts.

        Returns a dict mapping script_id -> hook result.  For the
        ``on_game_starting`` hook the return dict also includes a top-level
        ``"cancelled"`` key (bool) and ``"cancelled_by"`` (script_id or "").
        """
        if hook_name not in LIFECYCLE_HOOKS:
            logger.warning("Unknown hook: %s", hook_name)

        # Build typed event args if a mapping exists
        args_cls = HOOK_EVENT_ARGS_MAP.get(hook_name)
        event_args: EventArgs | None = None
        if args_cls is not None:
            valid_fields = {f for f in args_cls.__dataclass_fields__}
            event_args = args_cls(**{k: v for k, v in kwargs.items() if k in valid_fields})

        results: dict[str, Any] = {}
        cancelled = False
        cancelled_by = ""

        scripts = self._loader.get_loaded_scripts()

        for info in scripts:
            if not info.loaded:
                continue
            # For game-specific scripts, check if the game matches
            if info.config.game_ids and kwargs.get("game_id"):
                if kwargs["game_id"] not in info.config.game_ids:
                    continue
            # Selective invocation: only call if the script supports the hook
            if info.supported_events and hook_name not in info.supported_events:
                continue

            results[info.id] = self._call_hook_on_script(
                info, hook_name, event_args=event_args, **kwargs
            )

            # Check cancellation for on_game_starting
            if (
                hook_name == "on_game_starting"
                and isinstance(event_args, OnGameStartingEventArgs)
                and event_args.cancel_startup
            ):
                cancelled = True
                cancelled_by = info.id
                break

        if hook_name == "on_game_starting":
            results["cancelled"] = cancelled
            results["cancelled_by"] = cancelled_by

        return results

    def _call_hook_on_script(
        self,
        info: ScriptInfo,
        hook_name: str,
        event_args: EventArgs | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call a specific hook function on a single script."""
        func = info._namespace.get(hook_name)
        if func is None or not callable(func):
            return {"skipped": True, "reason": f"No '{hook_name}' function defined"}

        timer = ExecutionTimer()
        site_packages = self._loader._script_sys_paths.get(info.id)
        executor = SandboxedExecutor(info.config, info.path, site_packages=site_packages)

        # If typed event args are available, pass as single positional arg
        call_kwargs: dict[str, Any] = {}
        call_args: tuple[Any, ...] = ()
        if event_args is not None:
            call_args = (event_args,)
        else:
            call_kwargs = kwargs

        with timer:
            result = executor.call_function(
                info._namespace,
                hook_name,
                *call_args,
                timeout=info.config.timeout,
                **call_kwargs,
            )

        info.execution_count += 1
        self._metrics.record_execution(
            script_id=info.id,
            script_name=info.name,
            hook_name=hook_name,
            success=result["success"],
            duration=timer.duration,
            error=result.get("error", ""),
        )

        return {
            "success": result["success"],
            "result": result.get("result"),
            "error": result.get("error", ""),
            "duration": timer.duration,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
        }
