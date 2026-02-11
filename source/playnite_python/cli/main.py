"""
Playnite Python CLI.

All commands support ``--json`` for machine-readable output, enabling
automated testing and scripting.

Entry-point::

    python -m playnite_python.cli.main [command] [args]

Or after ``pip install -e .``::

    playnite [command] [args]

Command groups
--------------
* ``games``      — Query and update the game library.
* ``scripts``    — Manage Python script extensions.
* ``actions``    — Manage and execute game actions.
* ``marketplace`` — Browse and install community scripts.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import click

# Add parent to sys.path so we can import the package when running directly
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from playnite_python.database.game_database import GameDatabase
from playnite_python.models.game import Game, GameAction, GameActionType
from playnite_python.extensions.manager import ScriptManager
from playnite_python.extensions.lifecycle import ALL_HOOKS
from playnite_python.actions.models import (
    Action, ActionType, ActionExecutorType, ActionCondition, ConditionType,
    TriggerType,
)
from playnite_python.actions.registry import ActionRegistry
from playnite_python.actions.chain import ActionChainExecutor
from playnite_python.actions.injector import ActionInjector
from playnite_python.actions.action_logger import ActionExecutionLogger
from playnite_python.actions.scheduler import ActionScheduler
from playnite_python.actions.template import ALL_TEMPLATES
from playnite_python.extensions.marketplace import ScriptMarketplace


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

class AppContext:
    """Holds shared objects across CLI commands."""

    def __init__(self, db_path: str, config_dir: str, extensions_dir: str) -> None:
        self.db_path = db_path
        self.config_dir = config_dir
        self.extensions_dir = extensions_dir
        self._db: Optional[GameDatabase] = None
        self._registry: Optional[ActionRegistry] = None
        self._manager: Optional[ScriptManager] = None
        self._action_logger: Optional[ActionExecutionLogger] = None
        self._injector: Optional[ActionInjector] = None

    @property
    def db(self) -> GameDatabase:
        if self._db is None:
            self._db = GameDatabase(self.db_path)
            self._db.open()
        return self._db

    @property
    def registry(self) -> ActionRegistry:
        if self._registry is None:
            self._registry = ActionRegistry(self.config_dir)
        return self._registry

    @property
    def injector(self) -> ActionInjector:
        if self._injector is None:
            self._injector = ActionInjector(self.registry)
        return self._injector

    @property
    def action_logger(self) -> ActionExecutionLogger:
        if self._action_logger is None:
            self._action_logger = ActionExecutionLogger(
                str(Path(self.config_dir) / "logs" / "actions.jsonl")
            )
        return self._action_logger

    @property
    def script_manager(self) -> ScriptManager:
        if self._manager is None:
            self._manager = ScriptManager(
                extensions_dir=self.extensions_dir,
                db=self.db,
                app_paths={
                    "app": str(Path(self.extensions_dir).parent),
                    "config": self.config_dir,
                    "database": self.db_path,
                    "logs": str(Path(self.config_dir) / "logs" / "scripts"),
                },
            )
        return self._manager

    def close(self) -> None:
        if self._db:
            self._db.close()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _output(data: Any, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for k, v in item.items():
                        click.echo(f"  {k}: {v}")
                    click.echo("")
                else:
                    click.echo(f"  {item}")
        elif isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"{k}: {v}")
        else:
            click.echo(str(data))


def _ok(message: str, as_json: bool, **extra: Any) -> None:
    if as_json:
        click.echo(json.dumps({"ok": True, "message": message, **extra}, indent=2, default=str))
    else:
        click.echo(f"OK: {message}")


def _err(message: str, as_json: bool, **extra: Any) -> None:
    payload = json.dumps({"ok": False, "error": message, **extra}, indent=2, default=str)
    if as_json:
        click.echo(payload, err=True)
    else:
        click.echo(f"ERROR: {message}", err=True)


# ---------------------------------------------------------------------------
# Root command
# ---------------------------------------------------------------------------

DEFAULT_DB = str(Path.home() / ".playnite_python" / "library.db")
DEFAULT_CONFIG = str(Path.home() / ".playnite_python" / "config")
DEFAULT_EXTENSIONS = str(Path.home() / ".playnite_python" / "extensions")


@click.group()
@click.option("--db", default=DEFAULT_DB, envvar="PLAYNITE_DB", help="Path to library database.")
@click.option("--config-dir", default=DEFAULT_CONFIG, envvar="PLAYNITE_CONFIG", help="Config directory.")
@click.option("--extensions-dir", default=DEFAULT_EXTENSIONS, envvar="PLAYNITE_EXTENSIONS", help="Extensions directory.")
@click.pass_context
def cli(ctx: click.Context, db: str, config_dir: str, extensions_dir: str) -> None:
    """Playnite Python — game library manager CLI."""
    ctx.ensure_object(dict)
    ctx.obj = AppContext(db, config_dir, extensions_dir)


# ---------------------------------------------------------------------------
# games
# ---------------------------------------------------------------------------

@cli.group()
def games() -> None:
    """Manage the game library."""


@games.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--installed", is_flag=True, help="Only show installed games.")
@click.option("--search", default="", help="Filter by name/description.")
@click.option("--limit", default=50, help="Maximum results.")
@click.pass_obj
def games_list(
    ctx: AppContext, as_json: bool, installed: bool, search: str, limit: int
) -> None:
    """List games in the library."""
    if search:
        items = ctx.db.games.search(search)[:limit]
    elif installed:
        items = ctx.db.games.get_installed()[:limit]
    else:
        items = ctx.db.games.all()[:limit]
    data = [
        {
            "id": g.id,
            "name": g.name,
            "installed": g.is_installed,
            "play_time_hours": round(g.play_time / 3600, 2),
            "favorite": g.is_favorite,
        }
        for g in items
    ]
    _output(data, as_json)


@games.command("get")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_obj
def games_get(ctx: AppContext, game_id: str, as_json: bool) -> None:
    """Show full details for a game."""
    game = ctx.db.games.get(game_id)
    if game is None:
        _err(f"Game '{game_id}' not found.", as_json)
        sys.exit(1)
    _output(game.to_dict(), as_json)


@games.command("add")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.option("--installed", is_flag=True)
@click.option("--install-dir", default="")
@click.pass_obj
def games_add(
    ctx: AppContext, name: str, as_json: bool, installed: bool, install_dir: str
) -> None:
    """Add a new game to the library."""
    game = Game(name=name, is_installed=installed, install_directory=install_dir)
    ctx.db.games.add(game)
    _ok(f"Added '{name}' with id={game.id}", as_json, id=game.id)


@games.command("update")
@click.argument("game_id")
@click.argument("field")
@click.argument("value")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def games_update(
    ctx: AppContext, game_id: str, field: str, value: str, as_json: bool
) -> None:
    """Update a field on a game (e.g. ``is_favorite true``)."""
    game = ctx.db.games.get(game_id)
    if game is None:
        _err(f"Game '{game_id}' not found.", as_json)
        sys.exit(1)
    # Coerce common types
    coerced: Any = value
    if value.lower() in ("true", "false"):
        coerced = value.lower() == "true"
    elif value.isdigit():
        coerced = int(value)
    try:
        setattr(game, field, coerced)
        ctx.db.games.update(game)
        _ok(f"Updated {field}={coerced!r} on '{game.name}'", as_json)
    except AttributeError:
        _err(f"Unknown field '{field}'", as_json)
        sys.exit(1)


@games.command("remove")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_obj
def games_remove(ctx: AppContext, game_id: str, as_json: bool, confirm: bool) -> None:
    """Remove a game from the library."""
    game = ctx.db.games.get(game_id)
    if game is None:
        _err(f"Game '{game_id}' not found.", as_json)
        sys.exit(1)
    if not confirm and not as_json:
        if not click.confirm(f"Remove '{game.name}'?"):
            return
    ctx.db.games.remove(game_id)
    _ok(f"Removed '{game.name}'", as_json)


@games.command("stats")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def games_stats(ctx: AppContext, as_json: bool) -> None:
    """Show library statistics."""
    _output(ctx.db.get_stats(), as_json)


# ---------------------------------------------------------------------------
# scripts
# ---------------------------------------------------------------------------

@cli.group()
def scripts() -> None:
    """Manage Python script extensions."""


@scripts.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_list(ctx: AppContext, as_json: bool) -> None:
    """List all loaded scripts."""
    mgr = ctx.script_manager
    # Only list, don't load — check extensions dir for .py files
    ext_dir = Path(ctx.extensions_dir)
    found = []
    for py in sorted(ext_dir.glob("*.py")):
        if py.stem.startswith("_"):
            continue
        loaded = mgr.get_script(py.stem)
        found.append(
            {
                "name": py.stem,
                "path": str(py),
                "loaded": loaded is not None,
                "enabled": loaded.config.enabled if loaded else None,
                "hooks": loaded.registered_hooks if loaded else [],
            }
        )
    _output(found, as_json)


@scripts.command("load")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_load(ctx: AppContext, path: str, as_json: bool) -> None:
    """Load a script from PATH."""
    try:
        script = ctx.script_manager.load_script(path)
        _ok(f"Loaded '{script.name}'", as_json, hooks=script.registered_hooks)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@scripts.command("reload")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_reload(ctx: AppContext, name: str, as_json: bool) -> None:
    """Hot-reload a script by name."""
    try:
        script = ctx.script_manager.reload_script(name)
        _ok(f"Reloaded '{name}'", as_json, hooks=script.registered_hooks)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@scripts.command("unload")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_unload(ctx: AppContext, name: str, as_json: bool) -> None:
    """Unload a loaded script."""
    try:
        ctx.script_manager.unload_script(name)
        _ok(f"Unloaded '{name}'", as_json)
    except KeyError as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@scripts.command("enable")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_enable(ctx: AppContext, name: str, as_json: bool) -> None:
    """Enable a loaded script."""
    try:
        ctx.script_manager.enable_script(name)
        _ok(f"Enabled '{name}'", as_json)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@scripts.command("disable")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_disable(ctx: AppContext, name: str, as_json: bool) -> None:
    """Disable a loaded script (hooks unregistered until re-enabled)."""
    try:
        ctx.script_manager.disable_script(name)
        _ok(f"Disabled '{name}'", as_json)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@scripts.command("install-deps")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.option("--force", is_flag=True, help="Reinstall even if already present.")
@click.pass_obj
def scripts_install_deps(ctx: AppContext, name: str, as_json: bool, force: bool) -> None:
    """Install declared dependencies for a script into its isolated venv."""
    mgr = ctx.script_manager
    script = mgr.get_script(name)
    if script is None:
        _err(f"Script '{name}' is not loaded.", as_json)
        sys.exit(1)
    deps = script.config.dependencies
    if not deps:
        _ok(f"No dependencies declared for '{name}'", as_json)
        return
    try:
        installed = mgr._dep_manager.install_dependencies(name, deps, force=force)
        _ok(f"Installed: {installed}", as_json, installed=installed)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@scripts.command("run-hook")
@click.argument("hook_name")
@click.option("--game-id", default=None, help="Game ID to pass to game-level hooks.")
@click.option("--elapsed", default=0.0, type=float, help="Elapsed seconds (for on_game_stopped).")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_run_hook(
    ctx: AppContext, hook_name: str, game_id: Optional[str], elapsed: float, as_json: bool
) -> None:
    """Manually fire a lifecycle hook across all loaded scripts."""
    if hook_name not in ALL_HOOKS:
        _err(f"Unknown hook '{hook_name}'. Valid: {ALL_HOOKS}", as_json)
        sys.exit(1)
    game = ctx.db.games.get(game_id) if game_id else None
    mgr = ctx.script_manager
    if hook_name == "on_game_stopped":
        count = mgr.lifecycle.on_game_stopped(game, elapsed) if game else 0  # type: ignore[arg-type]
    elif hook_name in ("on_game_starting", "on_game_started", "on_game_installed", "on_game_uninstalled"):
        if game is None:
            _err("--game-id is required for game-level hooks.", as_json)
            sys.exit(1)
        count = getattr(mgr.lifecycle, hook_name)(game)
    else:
        count = getattr(mgr.lifecycle, hook_name)()
    _ok(f"Fired '{hook_name}' — {count} handler(s) called", as_json, count=count)


@scripts.command("metrics")
@click.argument("name", required=False)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_metrics(ctx: AppContext, name: Optional[str], as_json: bool) -> None:
    """Show execution metrics for a script (or all scripts)."""
    _output(ctx.script_manager.get_metrics(name), as_json)


@scripts.command("discover")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def scripts_discover(ctx: AppContext, as_json: bool) -> None:
    """Discover and load all scripts in the extensions directory."""
    loaded = ctx.script_manager.discover_and_load()
    _ok(f"Loaded {len(loaded)} script(s)", as_json, scripts=loaded)


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------

@cli.group()
def actions() -> None:
    """Manage and execute game actions."""


@actions.command("list")
@click.option("--game-id", default=None)
@click.option("--type", "action_type", default=None, help="Filter by action type.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_list(
    ctx: AppContext, game_id: Optional[str], action_type: Optional[str], as_json: bool
) -> None:
    """List registered actions."""
    at = ActionType(action_type) if action_type else None
    items = ctx.registry.list_actions(game_id=game_id, action_type=at)
    _output([a.to_dict() for a in items], as_json)


@actions.command("add")
@click.option("--name", default="Custom Action")
@click.option("--type", "action_type", default="pre_launch")
@click.option("--script", "script_code", default="")
@click.option("--executable", default="")
@click.option("--game-id", default=None)
@click.option("--priority", default=100, type=int)
@click.option("--async", "async_", is_flag=True)
@click.option("--timeout", default=60, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_add(
    ctx: AppContext,
    name: str,
    action_type: str,
    script_code: str,
    executable: str,
    game_id: Optional[str],
    priority: int,
    async_: bool,
    timeout: int,
    as_json: bool,
) -> None:
    """Add a new action."""
    exec_type = ActionExecutorType.EXECUTABLE if executable else ActionExecutorType.SCRIPT
    action = Action(
        name=name,
        type=ActionType(action_type),
        executor_type=exec_type,
        script=script_code,
        executable=executable,
        game_id=game_id,
        priority=priority,
        async_=async_,
        timeout=timeout,
    )
    ctx.injector.inject(action, game_id)
    _ok(f"Added action '{name}'", as_json, id=action.id)


@actions.command("remove")
@click.argument("action_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_remove(ctx: AppContext, action_id: str, as_json: bool) -> None:
    """Remove an action by ID."""
    ctx.registry.remove_action(action_id)
    _ok(f"Removed action '{action_id}'", as_json)


@actions.command("run")
@click.argument("action_id")
@click.option("--game-id", default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_run(
    ctx: AppContext, action_id: str, game_id: Optional[str], as_json: bool
) -> None:
    """Execute a single action immediately."""
    action = ctx.registry.get_action(action_id)
    if action is None:
        _err(f"Action '{action_id}' not found.", as_json)
        sys.exit(1)
    game = ctx.db.games.get(game_id) if game_id else None
    executor = ActionChainExecutor()
    logs, success = executor.execute([action], game)
    log = logs[0] if logs else None
    if log:
        ctx.action_logger.record(log)
    if as_json:
        _output([l.to_dict() for l in logs], as_json)
    else:
        for l in logs:
            status = "OK" if l.success else "FAILED"
            click.echo(f"[{status}] {l.action_name} ({l.duration_ms:.0f}ms)")
            if l.error:
                click.echo(f"  Error: {l.error[:200]}", err=True)


@actions.command("inject")
@click.option("--game-id", default=None)
@click.option("--script", "script_code", required=True)
@click.option("--name", default="Injected Action")
@click.option("--type", "action_type", default="pre_launch")
@click.option("--priority", default=100, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_inject(
    ctx: AppContext,
    game_id: Optional[str],
    script_code: str,
    name: str,
    action_type: str,
    priority: int,
    as_json: bool,
) -> None:
    """Inject a script-based action at runtime."""
    action = ctx.injector.inject_pre_launch(
        script=script_code,
        name=name,
        game_id=game_id,
        priority=priority,
    ) if action_type == "pre_launch" else ctx.injector.inject(
        Action(
            name=name,
            type=ActionType(action_type),
            script=script_code,
            game_id=game_id,
            priority=priority,
        )
    )
    _ok(f"Injected action '{name}'", as_json, id=action.id)


@actions.command("chain")
@click.option("--game-id", default=None)
@click.option("--type", "action_type", default="pre_launch", help="Action type to chain.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_chain(
    ctx: AppContext, game_id: Optional[str], action_type: str, as_json: bool
) -> None:
    """Execute the full action chain for a game and action type."""
    at = ActionType(action_type)
    game = ctx.db.games.get(game_id) if game_id else None
    action_list = ctx.registry.get_actions_for_game(game_id, at) if game_id else ctx.registry.list_global_actions(at)
    executor = ActionChainExecutor()
    logs, success = executor.execute(action_list, game)
    ctx.action_logger.record_many(logs)
    if as_json:
        _output(
            {"success": success, "logs": [l.to_dict() for l in logs]},
            as_json,
        )
    else:
        click.echo(f"Chain result: {'OK' if success else 'FAILED'}")
        for l in logs:
            status = "OK" if l.success else ("SKIP" if "Skipped" in l.output else "FAIL")
            click.echo(f"  [{status}] {l.action_name} ({l.duration_ms:.0f}ms)")


@actions.command("log")
@click.option("--limit", default=20, type=int)
@click.option("--game-id", default=None)
@click.option("--action-id", default=None)
@click.option("--failures", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_log(
    ctx: AppContext,
    limit: int,
    game_id: Optional[str],
    action_id: Optional[str],
    failures: bool,
    as_json: bool,
) -> None:
    """View action execution history."""
    alog = ctx.action_logger
    if failures:
        entries = alog.get_failures(limit)
    elif action_id:
        entries = alog.get_for_action(action_id, limit)
    elif game_id:
        entries = alog.get_for_game(game_id, limit)
    else:
        entries = alog.get_recent(limit)
    _output([e.to_dict() for e in entries], as_json)


@actions.command("template-list")
@click.option("--json", "as_json", is_flag=True)
def actions_template_list(as_json: bool) -> None:
    """List available built-in action templates."""
    _output(list(ALL_TEMPLATES.keys()), as_json)


@actions.command("template-apply")
@click.argument("template_name")
@click.option("--game-id", default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_template_apply(
    ctx: AppContext, template_name: str, game_id: Optional[str], as_json: bool
) -> None:
    """Apply a built-in action template (no-arg templates only)."""
    factory = ALL_TEMPLATES.get(template_name)
    if not factory:
        _err(f"Unknown template '{template_name}'. Run 'actions template-list'", as_json)
        sys.exit(1)
    try:
        action = factory()
        action.game_id = game_id
        ctx.injector.inject(action)
        _ok(f"Applied template '{template_name}'", as_json, id=action.id)
    except TypeError as exc:
        _err(f"Template '{template_name}' requires arguments: {exc}", as_json)
        sys.exit(1)


@actions.command("schedule")
@click.argument("action_id")
@click.option("--interval", default=None, type=float, help="Run every N seconds.")
@click.option("--daily-hour", default=None, type=int, help="Run daily at this hour (0-23).")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def actions_schedule(
    ctx: AppContext,
    action_id: str,
    interval: Optional[float],
    daily_hour: Optional[int],
    as_json: bool,
) -> None:
    """Schedule an action to run automatically."""
    action = ctx.registry.get_action(action_id)
    if not action:
        _err(f"Action '{action_id}' not found.", as_json)
        sys.exit(1)

    def _run(aid: str):
        a = ctx.registry.get_action(aid)
        if not a:
            return None
        executor = ActionChainExecutor()
        logs, _ = executor.execute([a])
        return logs[0] if logs else None

    scheduler = ActionScheduler(_run)

    from datetime import timedelta
    if interval:
        job_id = scheduler.schedule_interval(action_id, timedelta(seconds=interval))
        scheduler.start()
        _ok(f"Scheduled '{action.name}' every {interval}s", as_json, job_id=job_id)
    elif daily_hour is not None:
        job_id = scheduler.schedule_daily(action_id, hour=daily_hour)
        scheduler.start()
        _ok(f"Scheduled '{action.name}' daily at {daily_hour:02d}:00", as_json, job_id=job_id)
    else:
        _err("Specify --interval or --daily-hour.", as_json)
        sys.exit(1)


# ---------------------------------------------------------------------------
# marketplace
# ---------------------------------------------------------------------------

@cli.group()
def marketplace() -> None:
    """Browse and install community scripts."""


@marketplace.command("search")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def marketplace_search(ctx: AppContext, query: str, as_json: bool) -> None:
    """Search the community script marketplace."""
    mp = ScriptMarketplace(ctx.extensions_dir)
    try:
        results = mp.search(query)
        _output([e.to_dict() for e in results], as_json)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@marketplace.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.option("--refresh", is_flag=True, help="Force re-download index.")
@click.pass_obj
def marketplace_list(ctx: AppContext, as_json: bool, refresh: bool) -> None:
    """List all scripts in the marketplace."""
    mp = ScriptMarketplace(ctx.extensions_dir)
    try:
        entries = mp.refresh_index(force=refresh)
        _output([e.to_dict() for e in entries], as_json)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@marketplace.command("install")
@click.argument("script_id")
@click.option("--overwrite", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def marketplace_install(ctx: AppContext, script_id: str, overwrite: bool, as_json: bool) -> None:
    """Install a community script by ID."""
    mp = ScriptMarketplace(ctx.extensions_dir)
    try:
        path = mp.install(script_id, overwrite=overwrite)
        _ok(f"Installed '{script_id}'", as_json, path=str(path))
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@marketplace.command("update")
@click.argument("script_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def marketplace_update(ctx: AppContext, script_id: str, as_json: bool) -> None:
    """Update an installed community script."""
    mp = ScriptMarketplace(ctx.extensions_dir)
    try:
        updated = mp.update(script_id)
        if updated:
            _ok(f"Updated '{script_id}'", as_json)
        else:
            _ok(f"'{script_id}' is already up to date", as_json)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


@marketplace.command("check-updates")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def marketplace_check_updates(ctx: AppContext, as_json: bool) -> None:
    """Check all installed scripts for available updates."""
    mp = ScriptMarketplace(ctx.extensions_dir)
    try:
        updates = mp.check_updates()
        _output(updates, as_json)
    except Exception as exc:
        _err(str(exc), as_json)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
