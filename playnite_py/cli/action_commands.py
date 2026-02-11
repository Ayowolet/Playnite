"""CLI handlers for action injection and execution."""

from __future__ import annotations

import argparse

from playnite_py.cli._util import _build_app, _output


def cmd_action_list(args: argparse.Namespace) -> None:
    """List injected actions, optionally filtered by game or phase."""
    db, _, action_mgr = _build_app(args.data_dir)
    game_id = getattr(args, "game_id", None)
    phase = getattr(args, "phase", None)
    actions = action_mgr.get_actions(game_id, phase)
    if args.json:
        _output([a.to_dict() for a in actions], True)
    else:
        if not actions:
            print("No actions found.")
            return
        for a in actions:
            target = a.game_id or "global"
            print(f"  [{a.id[:8]}] {a.name} ({a.phase.value}, target={target})")


def cmd_action_inject(args: argparse.Namespace) -> None:
    """Inject a new action into the system."""
    from playnite_py.models.action import GameAction, ActionType, ActionPhase
    db, _, action_mgr = _build_app(args.data_dir)
    action = GameAction(
        name=args.name,
        script=args.script,
        is_script_path=args.script_path,
        game_id=args.game_id,
        action_type=ActionType(args.type),
        phase=ActionPhase(args.phase),
        priority=args.priority,
        is_async=args.async_action,
        timeout=args.timeout,
    )
    action_mgr.inject_action(action)
    db.save()
    _output({"id": action.id, "name": action.name, "message": "Action injected"}, args.json)


def cmd_action_remove(args: argparse.Namespace) -> None:
    """Remove an action by its ID."""
    db, _, action_mgr = _build_app(args.data_dir)
    if action_mgr.remove_action(args.id):
        db.save()
        _output({"message": f"Action '{args.id}' removed"}, args.json)
    else:
        _output({"error": f"Action '{args.id}' not found"}, args.json)


def cmd_action_execute(args: argparse.Namespace) -> None:
    """Execute all actions for a game phase."""
    from playnite_py.models.action import ActionPhase
    db, engine, action_mgr = _build_app(args.data_dir)
    engine.load_all()
    phase = ActionPhase(args.phase)
    result = action_mgr.execute_phase(args.game_id, phase)
    if args.json:
        _output(result.to_dict(), True)
    else:
        print(f"Phase: {result.phase.value}")
        print(f"Duration: {result.total_duration:.3f}s")
        print(f"All succeeded: {result.all_succeeded}")
        for r in result.results:
            status = "OK" if r.success else "FAIL"
            print(f"  [{status}] {r.action_name} ({r.duration:.3f}s)")
            if r.error:
                print(f"         Error: {r.error[:200]}")
            if r.rolled_back:
                print(f"         (rolled back)")


def cmd_action_log(args: argparse.Namespace) -> None:
    """View the action execution log."""
    _, _, action_mgr = _build_app(args.data_dir)
    game_id = getattr(args, "game_id", None)
    log = action_mgr.get_action_log(game_id, limit=args.limit)
    _output(log, args.json)


def cmd_action_templates(args: argparse.Namespace) -> None:
    """List all available action templates."""
    _, _, action_mgr = _build_app(args.data_dir)
    templates = action_mgr.get_templates()
    _output(templates, args.json)


def cmd_action_apply_template(args: argparse.Namespace) -> None:
    """Apply an action template to a game."""
    db, _, action_mgr = _build_app(args.data_dir)
    action = action_mgr.apply_template(args.template, args.game_id)
    if action:
        db.save()
        _output(action.to_dict(), args.json)
    else:
        _output({"error": f"Template '{args.template}' not found"}, args.json)


def cmd_profile_list(args: argparse.Namespace) -> None:
    """List all action profiles."""
    _, _, action_mgr = _build_app(args.data_dir)
    profiles = action_mgr.profiles.get_all_profiles()
    _output(profiles, args.json)


def cmd_profile_create(args: argparse.Namespace) -> None:
    """Create a new action profile from JSON criteria and templates."""
    import json
    _, _, action_mgr = _build_app(args.data_dir)
    criteria = json.loads(args.criteria)
    templates = json.loads(args.actions)
    profile = action_mgr.profiles.create_profile(
        args.name, criteria, templates, description=args.description or ""
    )
    _output(profile.to_dict(), args.json)


def cmd_monitor_status(args: argparse.Namespace) -> None:
    """Show all currently monitored game processes."""
    _, _, action_mgr = _build_app(args.data_dir)
    monitored = action_mgr.process_monitor.get_all_monitored()
    _output(monitored, args.json)


def cmd_monitor_start(args: argparse.Namespace) -> None:
    """Start monitoring a game process by name or PID."""
    _, _, action_mgr = _build_app(args.data_dir)
    proc = action_mgr.process_monitor.start_monitoring(
        game_id=args.game_id,
        process_name=args.process_name or "",
        pid=args.pid,
    )
    _output(proc.to_dict(), args.json)
