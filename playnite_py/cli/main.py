"""
Playnite Python — CLI entry point.

Usage
-----
    playnite --help
    playnite library stats
    playnite recommend generate --mood relaxed --n 10
    playnite capture screenshot --game "Hollow Knight"
    playnite capture start-recording
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from ..config import AppConfig
from .recommend_commands import recommend
from .capture_commands import capture, _instances as _capture_state

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _handle_signal(signum: int, frame: object) -> None:
    """Graceful shutdown on SIGINT / SIGTERM."""
    sig_name = signal.Signals(signum).name
    logging.getLogger(__name__).info("Received %s — shutting down", sig_name)
    sys.exit(0)


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"], "max_content_width": 120}


def _get_config(ctx: click.Context) -> AppConfig:
    return ctx.obj.get("config", AppConfig())


def _output(data: object, fmt: str, console: Console = console) -> None:
    """Output data in the requested format."""
    if fmt == "json":
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        rprint(data)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option("1.0.0", "-V", "--version")
@click.option("--data-dir", envvar="PLAYNITE_DATA_DIR", default=None,
              help="Override data directory path.")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "plain"]),
              default="table", show_default=True, help="Output format.")
@click.option("--profile", "profile_id", default=None, help="User profile ID to use.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable verbose output.")
@click.pass_context
def cli(ctx: click.Context, data_dir: Optional[str], output_format: str,
        profile_id: Optional[str], verbose: bool) -> None:
    """
    Playnite Python — game library manager with intelligent recommendations
    and media capture capabilities.
    """
    ctx.ensure_object(dict)
    _setup_logging(verbose)
    cfg = AppConfig.load()
    if data_dir:
        cfg.data_dir = data_dir
    cfg.default_output_format = output_format
    if profile_id:
        cfg.default_profile_id = profile_id
    cfg.ensure_dirs()
    ctx.obj["config"] = cfg
    ctx.obj["verbose"] = verbose
    ctx.obj["output_format"] = output_format


# ================================================================== #
# Library commands                                                     #
# ================================================================== #

@cli.group()
@click.pass_context
def library(ctx: click.Context) -> None:
    """Manage your game library."""


@library.command("stats")
@click.pass_context
def library_stats(ctx: click.Context) -> None:
    """Show library statistics."""
    from ..library.manager import LibraryManager
    cfg = _get_config(ctx)
    mgr = LibraryManager(cfg)
    stats = mgr.get_stats()
    fmt = ctx.obj.get("output_format", "table")

    if fmt == "json":
        click.echo(json.dumps(stats, indent=2, default=str))
        return

    console.print(f"\n[bold cyan]Library Statistics[/bold cyan]")
    console.print(f"  Total games:     {stats['total_games']}")
    console.print(f"  Owned games:     {stats['owned_games']}")
    console.print(f"  Played games:    {stats['played_games']}")
    console.print(f"  Total playtime:  {stats['total_playtime_hours']}h")
    console.print(f"  Wishlist:        {stats['wishlist_count']}")

    if stats.get("top_genres"):
        console.print("\n[bold]Top Genres:[/bold]")
        for genre, count in stats["top_genres"][:5]:
            console.print(f"  {genre}: {count}")

    if stats.get("most_played"):
        console.print("\n[bold]Most Played:[/bold]")
        for g in stats["most_played"]:
            console.print(f"  {g['name']}: {g['playtime_hours']}h")


@library.command("list")
@click.option("--genre", default=None, help="Filter by genre.")
@click.option("--platform", default=None, help="Filter by platform.")
@click.option("--source", default=None, help="Filter by source (Steam, GOG, etc.).")
@click.option("--played/--unplayed", default=None, help="Filter by play status.")
@click.option("--installed", is_flag=True, default=False, help="Only installed games.")
@click.option("--limit", default=50, show_default=True, help="Max number to show.")
@click.pass_context
def library_list(ctx: click.Context, genre: Optional[str], platform: Optional[str],
                 source: Optional[str], played: Optional[bool],
                 installed: bool, limit: int) -> None:
    """List games in the library."""
    from ..library.manager import LibraryManager
    cfg = _get_config(ctx)
    mgr = LibraryManager(cfg)
    fmt = ctx.obj.get("output_format", "table")

    games = mgr.filter_games(
        genre=genre, platform=platform, source=source,
        installed_only=installed,
    )
    if played is True:
        games = [g for g in games if g.is_played]
    elif played is False:
        games = [g for g in games if not g.is_played]

    games = games[:limit]

    if fmt == "json":
        click.echo(json.dumps([g.to_dict() for g in games], indent=2, default=str))
        return

    table = Table(title=f"Games ({len(games)})", show_lines=False)
    table.add_column("Name", style="cyan", max_width=40)
    table.add_column("Genres", style="green", max_width=30)
    table.add_column("Playtime", justify="right")
    table.add_column("Source", style="dim")
    table.add_column("Status")

    for g in games:
        status = "✓ played" if g.is_played else "⬜ unplayed"
        if g.favorite:
            status += " ♥"
        table.add_row(
            g.name,
            ", ".join(g.genres[:2]),
            f"{g.playtime_hours:.1f}h",
            g.source or "",
            status,
        )
    console.print(table)


@library.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--merge/--no-merge", default=True, show_default=True,
              help="Merge with existing games (skip duplicates).")
@click.pass_context
def library_import(ctx: click.Context, file_path: str, merge: bool) -> None:
    """Import games from a JSON file."""
    from ..library.manager import LibraryManager
    cfg = _get_config(ctx)
    mgr = LibraryManager(cfg)
    count = mgr.import_from_json(Path(file_path), merge=merge)
    console.print(f"[green]Imported {count} games.[/green]")


@library.command("export")
@click.argument("output_path", type=click.Path())
@click.pass_context
def library_export(ctx: click.Context, output_path: str) -> None:
    """Export all games to a JSON file."""
    from ..library.manager import LibraryManager
    cfg = _get_config(ctx)
    mgr = LibraryManager(cfg)
    count = mgr.export_to_json(Path(output_path))
    console.print(f"[green]Exported {count} games to {output_path}[/green]")


@library.command("search")
@click.argument("query")
@click.pass_context
def library_search(ctx: click.Context, query: str) -> None:
    """Search the library by game name."""
    from ..library.manager import LibraryManager
    cfg = _get_config(ctx)
    mgr = LibraryManager(cfg)
    games = mgr.search(query)
    fmt = ctx.obj.get("output_format", "table")

    if fmt == "json":
        click.echo(json.dumps([g.to_dict() for g in games], indent=2, default=str))
        return

    if not games:
        console.print(f"[yellow]No games found matching '{query}'[/yellow]")
        return
    for g in games:
        console.print(f"  [cyan]{g.name}[/cyan]  {', '.join(g.genres[:2])}  {g.playtime_hours:.1f}h")


# ================================================================== #
# Status / health check                                                #
# ================================================================== #

@cli.command("status")
@click.pass_context
def playnite_status(ctx: click.Context) -> None:
    """Show system health: DB connectivity, ffmpeg, and optional dependencies."""
    import shutil
    from ..database.db import GameDatabase, SCHEMA_VERSION

    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")
    checks: dict = {}

    # Database
    try:
        db = GameDatabase(cfg.database_path)
        game_count = db.get_game_count()
        schema_ver = db.get_schema_version()
        db.close()
        checks["database"] = {
            "ok": True,
            "path": str(cfg.database_path),
            "game_count": game_count,
            "schema_version": schema_ver,
            "expected_schema_version": SCHEMA_VERSION,
        }
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}

    # ffmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    checks["ffmpeg"] = {"ok": bool(ffmpeg_path), "path": ffmpeg_path}

    # ffprobe
    ffprobe_path = shutil.which("ffprobe")
    checks["ffprobe"] = {"ok": bool(ffprobe_path), "path": ffprobe_path}

    # Optional Python dependencies
    for dep in ("PIL", "numpy", "sklearn", "mss", "pynput"):
        try:
            __import__(dep)
            checks[dep] = {"ok": True}
        except ImportError:
            checks[dep] = {"ok": False, "note": "optional"}

    # Live capture subsystem state
    try:
        rec = _capture_state.recorder
        checks["recorder"] = {
            "ok": True,
            "active": bool(rec and rec.is_recording()),
            "note": "recording" if (rec and rec.is_recording()) else "idle",
        }
    except Exception as exc:
        checks["recorder"] = {"ok": False, "error": str(exc)}

    try:
        buf = _capture_state.buffer
        checks["buffer"] = {
            "ok": True,
            "active": bool(buf and buf.is_buffering()),
            "note": "buffering" if (buf and buf.is_buffering()) else "idle",
        }
    except Exception as exc:
        checks["buffer"] = {"ok": False, "error": str(exc)}

    try:
        hk = _capture_state.hotkeys
        checks["hotkeys"] = {
            "ok": True,
            "active": bool(hk and getattr(hk, "is_running", False)),
            "note": "active" if (hk and getattr(hk, "is_running", False)) else "idle",
        }
    except Exception as exc:
        checks["hotkeys"] = {"ok": False, "error": str(exc)}

    try:
        ov = _capture_state.overlay
        checks["overlay"] = {
            "ok": True,
            "active": bool(ov and ov.status().get("visible", False)),
            "note": "visible" if (ov and ov.status().get("visible", False)) else "hidden",
        }
    except Exception as exc:
        checks["overlay"] = {"ok": False, "error": str(exc)}

    overall_ok = all(v.get("ok") for v in checks.values())
    result = {"status": "ok" if overall_ok else "degraded", "checks": checks}

    if fmt == "json":
        click.echo(json.dumps(result, indent=2, default=str))
        return

    console.print(f"\n[bold]Playnite Status:[/bold] "
                  f"{'[green]ok[/green]' if overall_ok else '[yellow]degraded[/yellow]'}")
    for name, info in checks.items():
        icon = "[green]✓[/green]" if info.get("ok") else "[yellow]![/yellow]"
        extra = ""
        if "path" in info and info["path"]:
            extra = f" ({info['path']})"
        elif "error" in info:
            extra = f" — {info['error']}"
        elif "note" in info:
            extra = f" ({info['note']})"
        console.print(f"  {icon} {name}{extra}")


# Register subcommand groups
cli.add_command(recommend)
cli.add_command(capture)


if __name__ == "__main__":
    cli()
