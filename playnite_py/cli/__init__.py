"""CLI entry point for the Playnite Python game library manager.

All core functionality is accessible via CLI commands with optional JSON output.
Command handlers are organized into domain-specific sub-modules.
"""

from __future__ import annotations

import argparse
import json
import sys

from playnite_py.cli._util import _bool_arg, _default_data_dir
from playnite_py.cli.game_commands import (
    cmd_db_stats, cmd_game_add, cmd_game_list, cmd_game_remove,
    cmd_game_show, cmd_game_update,
)
from playnite_py.cli.script_commands import (
    cmd_script_deps, cmd_script_hook, cmd_script_info,
    cmd_script_install_deps, cmd_script_list, cmd_script_load,
    cmd_script_log, cmd_script_metrics, cmd_script_reload,
)
from playnite_py.cli.marketplace_commands import (
    cmd_marketplace_install, cmd_marketplace_search,
)
from playnite_py.cli.action_commands import (
    cmd_action_apply_template, cmd_action_execute, cmd_action_inject,
    cmd_action_list, cmd_action_log, cmd_action_remove, cmd_action_templates,
    cmd_monitor_start, cmd_monitor_status, cmd_profile_create, cmd_profile_list,
)


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="playnite",
        description="Playnite Python - Game library manager CLI",
    )
    parser.add_argument(
        "--data-dir", default=_default_data_dir(),
        help="Data directory (default: ~/.playnite_py)",
    )
    parser.add_argument(
        "--json", action="store_true", default=False,
        help="Output in JSON format",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # -- db --
    p = sub.add_parser("db-stats", help="Show database statistics")
    p.set_defaults(func=cmd_db_stats)

    # -- game --
    p = sub.add_parser("game-list", help="List all games")
    p.set_defaults(func=cmd_game_list)

    p = sub.add_parser("game-add", help="Add a game to the library")
    p.add_argument("name", help="Game name")
    p.add_argument("--source", help="Game source (e.g. Steam, GOG)")
    p.add_argument("--installed", action="store_true", default=False)
    p.set_defaults(func=cmd_game_add)

    p = sub.add_parser("game-show", help="Show game details")
    p.add_argument("id", help="Game ID (or prefix)")
    p.set_defaults(func=cmd_game_show)

    p = sub.add_parser("game-remove", help="Remove a game")
    p.add_argument("id", help="Game ID")
    p.set_defaults(func=cmd_game_remove)

    p = sub.add_parser("game-update", help="Update game fields")
    p.add_argument("id", help="Game ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--set-installed", type=_bool_arg, help="Set installed status")
    p.add_argument("--notes", help="Set notes")
    p.set_defaults(func=cmd_game_update)

    # -- script --
    p = sub.add_parser("script-list", help="List loaded scripts")
    p.set_defaults(func=cmd_script_list)

    p = sub.add_parser("script-load", help="Load all scripts from extensions directory")
    p.set_defaults(func=cmd_script_load)

    p = sub.add_parser("script-reload", help="Reload a specific script")
    p.add_argument("id", help="Script ID")
    p.set_defaults(func=cmd_script_reload)

    p = sub.add_parser("script-info", help="Show script details")
    p.add_argument("id", help="Script ID")
    p.set_defaults(func=cmd_script_info)

    p = sub.add_parser("script-hook", help="Execute a lifecycle hook")
    p.add_argument("hook", help="Hook name (e.g. on_application_started)")
    p.add_argument("--game-id", help="Game ID for game-specific hooks")
    p.set_defaults(func=cmd_script_hook)

    p = sub.add_parser("script-log", help="View script log")
    p.add_argument("id", help="Script ID")
    p.add_argument("--tail", type=int, default=50, help="Lines to show")
    p.set_defaults(func=cmd_script_log)

    p = sub.add_parser("script-metrics", help="View script execution metrics")
    p.add_argument("--id", help="Script ID (omit for all)")
    p.set_defaults(func=cmd_script_metrics)

    p = sub.add_parser("script-deps", help="List installed dependencies for a script")
    p.add_argument("id", help="Script ID")
    p.set_defaults(func=cmd_script_deps)

    p = sub.add_parser("script-install-deps", help="Install script dependencies")
    p.add_argument("id", help="Script ID")
    p.set_defaults(func=cmd_script_install_deps)

    # -- marketplace --
    p = sub.add_parser("marketplace-search", help="Search script marketplace")
    p.add_argument("--query", help="Search query")
    p.add_argument("--refresh", action="store_true", help="Refresh index first")
    p.add_argument("--repo-url", help="Repository URL")
    p.set_defaults(func=cmd_marketplace_search)

    p = sub.add_parser("marketplace-install", help="Install script from marketplace")
    p.add_argument("id", help="Script ID in marketplace")
    p.add_argument("--repo-url", help="Repository URL")
    p.set_defaults(func=cmd_marketplace_install)

    # -- action --
    p = sub.add_parser("action-list", help="List injected actions")
    p.add_argument("--game-id", help="Filter by game ID")
    p.add_argument("--phase", help="Filter by phase")
    p.set_defaults(func=cmd_action_list)

    p = sub.add_parser("action-inject", help="Inject a new action")
    p.add_argument("name", help="Action name")
    p.add_argument("--script", required=True, help="Inline script or file path")
    p.add_argument("--script-path", action="store_true", help="Treat --script as file path")
    p.add_argument("--game-id", help="Target game (omit for global)")
    p.add_argument("--type", default="custom", help="Action type")
    p.add_argument("--phase", default="pre_launch", help="Action phase")
    p.add_argument("--priority", type=int, default=50, help="Priority (0-100)")
    p.add_argument("--async-action", action="store_true", help="Run asynchronously")
    p.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    p.set_defaults(func=cmd_action_inject)

    p = sub.add_parser("action-remove", help="Remove an action")
    p.add_argument("id", help="Action ID")
    p.set_defaults(func=cmd_action_remove)

    p = sub.add_parser("action-execute", help="Execute actions for a game phase")
    p.add_argument("game_id", help="Game ID")
    p.add_argument("phase", help="Phase (pre_launch, launch, post_exit, etc.)")
    p.set_defaults(func=cmd_action_execute)

    p = sub.add_parser("action-log", help="View action execution log")
    p.add_argument("--game-id", help="Filter by game")
    p.add_argument("--limit", type=int, default=50, help="Max entries")
    p.set_defaults(func=cmd_action_log)

    p = sub.add_parser("action-templates", help="List available action templates")
    p.set_defaults(func=cmd_action_templates)

    p = sub.add_parser("action-apply-template", help="Apply an action template to a game")
    p.add_argument("template", help="Template name")
    p.add_argument("game_id", help="Target game ID")
    p.set_defaults(func=cmd_action_apply_template)

    # -- profile --
    p = sub.add_parser("profile-list", help="List action profiles")
    p.set_defaults(func=cmd_profile_list)

    p = sub.add_parser("profile-create", help="Create an action profile")
    p.add_argument("name", help="Profile name")
    p.add_argument("--criteria", required=True, help="JSON criteria")
    p.add_argument("--actions", required=True, help="JSON action templates")
    p.add_argument("--description", help="Profile description")
    p.set_defaults(func=cmd_profile_create)

    # -- monitor --
    p = sub.add_parser("monitor-status", help="Show monitored processes")
    p.set_defaults(func=cmd_monitor_status)

    p = sub.add_parser("monitor-start", help="Start monitoring a game process")
    p.add_argument("game_id", help="Game ID")
    p.add_argument("--process-name", help="Process name to monitor")
    p.add_argument("--pid", type=int, help="Process ID")
    p.set_defaults(func=cmd_monitor_start)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command handler."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        args.func(args)
        return 0
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
