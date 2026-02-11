"""CLI handlers for script extension management."""

from __future__ import annotations

import argparse
import json
import os

from playnite_py.cli._util import _build_app, _output


def cmd_script_list(args: argparse.Namespace) -> None:
    """List all discovered scripts and their load status."""
    _, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    scripts = engine.get_loaded_scripts()
    if args.json:
        _output([s.to_dict() for s in scripts], True)
    else:
        if not scripts:
            print("No scripts found.")
            return
        for s in scripts:
            status = "loaded" if s.loaded else f"error: {s.error}"
            print(f"  [{s.id}] {s.name} - {status}")


def cmd_script_load(args: argparse.Namespace) -> None:
    """Load all scripts from the extensions directory."""
    _, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    results = {}
    for s in engine.get_loaded_scripts():
        results[s.id] = {"loaded": s.loaded, "error": s.error}
    _output(results, args.json)


def cmd_script_reload(args: argparse.Namespace) -> None:
    """Reload a specific script by ID (hot-reload)."""
    _, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    try:
        info = engine.reload_script(args.id)
        _output(info.to_dict(), args.json)
    except KeyError:
        _output({"error": f"Script '{args.id}' not found"}, args.json)


def cmd_script_info(args: argparse.Namespace) -> None:
    """Show detailed information about a loaded script."""
    _, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    info = engine.get_script_info(args.id)
    if info:
        _output(info.to_dict(), args.json)
    else:
        _output({"error": f"Script '{args.id}' not found"}, args.json)


def cmd_script_hook(args: argparse.Namespace) -> None:
    """Execute a lifecycle hook across all loaded scripts."""
    db, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    kwargs = {}
    if args.game_id:
        kwargs["game_id"] = args.game_id
    results = engine.execute_hook(args.hook, **kwargs)
    _output(results, args.json)


def cmd_script_log(args: argparse.Namespace) -> None:
    """View the log output for a specific script."""
    _, engine, _ = _build_app(args.data_dir)
    lines = engine.log_manager.get_log_content(args.id, tail=args.tail)
    if args.json:
        _output(lines, True)
    else:
        for line in lines:
            print(line, end="")


def cmd_script_metrics(args: argparse.Namespace) -> None:
    """View script execution metrics and performance stats."""
    _, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    if args.id:
        stats = engine.metrics.get_script_stats(args.id)
    else:
        stats = engine.metrics.get_script_stats()
    _output(stats, args.json)


def cmd_script_deps(args: argparse.Namespace) -> None:
    """List installed dependencies for a script."""
    _, engine, _ = _build_app(args.data_dir)
    pkgs = engine.dep_manager.get_installed_packages(args.id)
    _output(pkgs, args.json)


def cmd_script_install_deps(args: argparse.Namespace) -> None:
    """Install dependencies declared by a script."""
    _, engine, _ = _build_app(args.data_dir)
    engine.load_all()
    info = engine.get_script_info(args.id)
    if not info:
        _output({"error": f"Script '{args.id}' not found"}, args.json)
        return
    result = engine.dep_manager.install_dependencies(args.id, info.config.dependencies)
    _output(result, args.json)
