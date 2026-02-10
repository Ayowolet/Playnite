"""
CLI commands for the screenshot and video capture system.

playnite capture --help
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, fields as _dc_fields
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from ..config import AppConfig
from ..capture.achievement import AchievementDetector
from ..capture.detector import GameDetector
from ..capture.editor import MediaEditor
from ..capture.hotkeys import HotkeyListener
from ..capture.organizer import MediaOrganizer
from ..capture.overlay import CaptureOverlay
from ..capture.screenshot import ScreenshotCapture
from ..capture.uploader import MediaUploader
from ..capture.video import VideoRecorder
from ..capture.buffer import ReplayBuffer

console = Console()


@dataclass
class CaptureState:
    """Typed container for live capture subsystem instances.

    Using a dataclass instead of a plain dict gives static-type
    checking on attribute access and prevents key-typo bugs at
    development time, while the dunder facade keeps all existing
    ``inst["key"]`` call sites working unchanged.
    """

    recorder: Optional[VideoRecorder] = None
    buffer: Optional[ReplayBuffer] = None
    achievement_detector: Optional[AchievementDetector] = None
    overlay: Optional[CaptureOverlay] = None
    hotkeys: Optional[HotkeyListener] = None

    def reset(self) -> None:
        """Set all fields back to None — used by test teardown."""
        for f in _dc_fields(self):
            object.__setattr__(self, f.name, None)

    def __iter__(self):
        """Support ``for k in _instances`` — yields field names."""
        return iter(f.name for f in _dc_fields(self))

    def __setitem__(self, key: str, value: object) -> None:
        """Support ``inst["recorder"] = x`` call sites unchanged."""
        setattr(self, key, value)

    def __getitem__(self, key: str) -> object:
        """Support ``inst["recorder"]`` call sites unchanged."""
        return getattr(self, key)


# Module-level state container — one instance shared across all commands.
_instances = CaptureState()


def _get_config(ctx: click.Context) -> AppConfig:
    return ctx.obj.get("config", AppConfig())


@click.group("capture")
def capture() -> None:
    """Screenshot, video recording, and media management commands."""


# ================================================================== #
# Detect                                                               #
# ================================================================== #

@capture.command("detect")
@click.option("--simulate", default=None, help="Simulate a running game by name.")
@click.pass_context
def cap_detect(ctx: click.Context, simulate: Optional[str]) -> None:
    """Detect currently running games."""
    fmt = ctx.obj.get("output_format", "table")
    detector = GameDetector()

    if simulate:
        game = detector.simulate_game_start(simulate)
        running = [game]
    else:
        running = detector.detect_running_games()

    if fmt == "json":
        click.echo(json.dumps(
            [{"pid": g.process_id, "name": g.game_name, "exe": g.executable}
             for g in running],
            indent=2,
        ))
        return

    if not running:
        console.print("[yellow]No known games detected.[/yellow]")
        return

    table = Table(title="Running Games")
    table.add_column("PID", style="dim")
    table.add_column("Game Name", style="cyan")
    table.add_column("Executable")
    for g in running:
        table.add_row(str(g.process_id), g.game_name or "Unknown", g.executable)
    console.print(table)


# ================================================================== #
# Screenshot                                                           #
# ================================================================== #

@capture.command("screenshot")
@click.option("--game", "game_name", default=None, help="Game name for organisation.")
@click.option("--game-id", default=None, help="Library game ID.")
@click.option("--monitor", default=1, show_default=True, help="Monitor index (1-based).")
@click.option("--format", "fmt", type=click.Choice(["png", "jpeg", "webp"]),
              default="png", show_default=True)
@click.option("--quality", default=95, show_default=True, help="JPEG quality (1-100).")
@click.option("--output", default=None, type=click.Path(), help="Override output path.")
@click.option("--backend", type=click.Choice(["mss", "pil", "mock"]), default=None,
              help="Capture backend (auto-detect if omitted).")
@click.option("--timestamp-overlay", is_flag=True, default=False,
              help="Add timestamp overlay to screenshot.")
@click.option("--auto-organise/--no-auto-organise", default=True,
              help="Move screenshot into game-organised directory.")
@click.pass_context
def cap_screenshot(ctx: click.Context, game_name: Optional[str], game_id: Optional[str],
                   monitor: int, fmt: str, quality: int, output: Optional[str],
                   backend: Optional[str], timestamp_overlay: bool,
                   auto_organise: bool) -> None:
    """Capture a screenshot."""
    cfg = _get_config(ctx)
    output_fmt = ctx.obj.get("output_format", "table")

    cap = ScreenshotCapture(
        output_dir=cfg.captures_dir / "screenshots" if not output else None,
        fmt=fmt,
        quality=quality,
        backend=backend,
    )
    result = cap.capture(
        game_name=game_name,
        game_id=game_id,
        monitor=monitor,
        add_timestamp_overlay=timestamp_overlay,
    )

    if auto_organise and game_name and result.file_path.exists():
        organiser = MediaOrganizer(cfg.captures_dir)
        new_path = organiser.organise_screenshot(
            result.file_path, game_name, game_id=game_id
        )
        result = result.__class__(
            id=result.id, file_path=new_path, sidecar_path=new_path.with_suffix(".json"),
            width=result.width, height=result.height, file_size_bytes=new_path.stat().st_size
            if new_path.exists() else result.file_size_bytes,
            captured_at=result.captured_at, game_name=result.game_name,
            game_id=result.game_id, backend=result.backend,
        )

    if output_fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        return

    console.print(f"[green]Screenshot saved:[/green] {result.file_path}")
    console.print(f"  Size: {result.width}×{result.height}  "
                  f"File: {result.file_size_bytes / 1024:.1f} KB  "
                  f"Backend: {result.backend}")


# ================================================================== #
# Video recording                                                      #
# ================================================================== #

@capture.command("start-recording")
@click.option("--game", "game_name", default=None, help="Game name.")
@click.option("--game-id", default=None)
@click.option("--codec", default="libx264", show_default=True)
@click.option("--crf", default=23, show_default=True, help="Quality (0-51, lower=better).")
@click.option("--fps", default=30, show_default=True)
@click.option("--resolution", default=None, help="e.g. 1920x1080")
@click.option("--duration", default=None, type=int, help="Auto-stop after N seconds.")
@click.option("--simulate", is_flag=True, default=False,
              help="Simulate recording (no ffmpeg required).")
@click.pass_context
def cap_start_recording(ctx: click.Context, game_name: Optional[str], game_id: Optional[str],
                         codec: str, crf: int, fps: int, resolution: Optional[str],
                         duration: Optional[int], simulate: bool) -> None:
    """Start video recording."""
    inst = _instances
    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")

    inst["recorder"] = VideoRecorder(
        output_dir=cfg.captures_dir / "videos",
        codec=codec, crf=crf, fps=fps, resolution=resolution,
    )
    session = inst["recorder"].start_recording(
        game_name=game_name, game_id=game_id,
        duration_limit=duration, simulate=simulate,
    )

    data = {
        "session_id": session.id,
        "output_path": str(session.output_path),
        "started_at": session.started_at.isoformat(),
        "game_name": session.game_name,
        "simulate": simulate,
    }

    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
        return

    console.print(f"[green]Recording started[/green]  session={session.id[:8]}…")
    console.print(f"  Output: {session.output_path}")
    console.print(f"  Settings: {fps}fps  CRF={crf}  codec={codec}")
    if simulate:
        console.print("[yellow]  (simulation mode — no real video captured)[/yellow]")


@capture.command("stop-recording")
@click.pass_context
def cap_stop_recording(ctx: click.Context) -> None:
    """Stop the current video recording."""
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")

    if not inst["recorder"]:
        console.print("[yellow]No active recording found.[/yellow]")
        return

    result = inst["recorder"].stop_recording()
    inst["recorder"] = None

    if result is None:
        console.print("[yellow]Recording was already stopped.[/yellow]")
        return

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        return

    console.print(f"[green]Recording saved:[/green] {result.file_path}")
    console.print(f"  Duration: {result.duration_seconds:.1f}s  "
                  f"Size: {result.file_size_bytes / (1024*1024):.1f} MB")


@capture.command("recording-status")
@click.pass_context
def cap_recording_status(ctx: click.Context) -> None:
    """Check if a recording is in progress."""
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")
    is_rec = bool(inst["recorder"] and inst["recorder"].is_recording())
    data = {
        "recording": is_rec,
        "session": inst["recorder"].get_session().id if is_rec else None,
    }
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        status = "[green]Recording[/green]" if is_rec else "[dim]Idle[/dim]"
        console.print(f"Status: {status}")


# ================================================================== #
# Instant replay buffer                                                #
# ================================================================== #

@capture.command("start-buffer")
@click.option("--duration", default=60, show_default=True,
              help="Buffer duration in seconds.")
@click.option("--simulate", is_flag=True, default=False)
@click.pass_context
def cap_start_buffer(ctx: click.Context, duration: int, simulate: bool) -> None:
    """Start the instant replay buffer."""
    inst = _instances
    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")

    inst["buffer"] = ReplayBuffer(
        buffer_seconds=duration,
        output_dir=cfg.captures_dir / "replays",
        simulate=simulate,
    )
    inst["buffer"].start()
    data = {"buffering": True, "buffer_seconds": duration, "simulate": simulate}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Replay buffer started[/green]  ({duration}s buffer)")
        if simulate:
            console.print("[yellow]  (simulation mode)[/yellow]")


@capture.command("save-replay")
@click.option("--game", "game_name", default=None)
@click.option("--game-id", default=None)
@click.option("--last-seconds", default=None, type=int,
              help="Save last N seconds (default: full buffer).")
@click.option("--output", default=None, type=click.Path())
@click.pass_context
def cap_save_replay(ctx: click.Context, game_name: Optional[str], game_id: Optional[str],
                    last_seconds: Optional[int], output: Optional[str]) -> None:
    """Save the instant replay buffer to a clip."""
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")

    if not inst["buffer"]:
        console.print("[red]Replay buffer is not running. Use 'capture start-buffer' first.[/red]")
        return

    out_path = Path(output) if output else None
    result = inst["buffer"].save_replay(
        game_name=game_name, game_id=game_id,
        output_path=out_path, last_n_seconds=last_seconds,
    )

    if result is None:
        console.print("[yellow]No buffered footage available.[/yellow]")
        return

    data = {"replay_saved": str(result)}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Replay saved:[/green] {result}")


@capture.command("buffer-status")
@click.pass_context
def cap_buffer_status(ctx: click.Context) -> None:
    """Show current replay buffer status."""
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")
    status = inst["buffer"].status() if inst["buffer"] else {"buffering": False}
    if fmt == "json":
        click.echo(json.dumps(status, indent=2))
    else:
        console.print(f"Buffering: {status.get('buffering', False)}")
        console.print(f"Segments:  {status.get('segments_buffered', 0)}")
        console.print(f"Duration:  {status.get('buffer_duration_seconds', 0)}s / "
                      f"{status.get('configured_buffer_seconds', 0)}s")


# ================================================================== #
# List captures                                                        #
# ================================================================== #

@capture.command("list")
@click.option("--game", "game_name", default=None, help="Filter by game name.")
@click.option("--type", "capture_type", type=click.Choice(["screenshot", "video", "replay"]),
              default=None)
@click.option("--tag", default=None, help="Filter by metadata tag.")
@click.option("--since", default=None, help="Only show captures on or after this date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Only show captures on or before this date (YYYY-MM-DD).")
@click.option("--limit", default=30, show_default=True)
@click.pass_context
def cap_list(ctx: click.Context, game_name: Optional[str],
             capture_type: Optional[str], tag: Optional[str],
             since: Optional[str], until: Optional[str], limit: int) -> None:
    """List captured media files."""
    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")
    organiser = MediaOrganizer(cfg.captures_dir)

    since_dt: Optional[datetime] = None
    until_dt: Optional[datetime] = None
    try:
        if since:
            since_dt = datetime.strptime(since, "%Y-%m-%d")
        if until:
            until_dt = datetime.strptime(until, "%Y-%m-%d")
    except ValueError as exc:
        console.print(f"[red]Invalid date format: {exc}. Use YYYY-MM-DD.[/red]")
        return

    captures = organiser.list_captures(
        game_name=game_name,
        capture_type=capture_type,
        tag_filter=tag,
        since=since_dt,
        until=until_dt,
    )[:limit]

    if fmt == "json":
        click.echo(json.dumps(captures, indent=2, default=str))
        return

    table = Table(title=f"Captures ({len(captures)})")
    table.add_column("Game", style="cyan")
    table.add_column("Type")
    table.add_column("File", style="dim", max_width=40)
    table.add_column("Size", justify="right")
    table.add_column("Date")
    table.add_column("Tags", style="dim")

    for cap in captures:
        size_kb = cap["file_size_bytes"] / 1024
        size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        fname = Path(cap["file_path"]).name
        cap_date = (cap.get("captured_at") or cap.get("modified_at") or "")[:10]
        tags_str = ", ".join(cap.get("tags", []))
        table.add_row(
            cap.get("game_name", "?"),
            cap.get("capture_type", "?"),
            fname,
            size_str,
            cap_date,
            tags_str,
        )
    console.print(table)


# ================================================================== #
# View metadata                                                        #
# ================================================================== #

@capture.command("view-metadata")
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def cap_view_metadata(ctx: click.Context, file_path: str) -> None:
    """Display full sidecar metadata for a captured screenshot or video."""
    fmt = ctx.obj.get("output_format", "table")
    fp = Path(file_path)
    sidecar = fp.with_suffix(".json")

    if not sidecar.exists():
        console.print(f"[yellow]No metadata sidecar found for:[/yellow] {fp.name}")
        console.print("[dim]The file may have been captured without sidecar support.[/dim]")
        return

    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]Failed to read sidecar: {exc}[/red]")
        return

    if fmt == "json":
        click.echo(json.dumps(meta, indent=2, default=str))
        return

    table = Table(title=f"Metadata: {fp.name}", show_header=True)
    table.add_column("Field", style="cyan", min_width=20)
    table.add_column("Value", style="white")

    for key, value in meta.items():
        if isinstance(value, list):
            display = ", ".join(str(v) for v in value) if value else "(none)"
        else:
            display = str(value) if value is not None else "(none)"
        table.add_row(key, display)

    console.print(table)


# ================================================================== #
# Tag captures                                                         #
# ================================================================== #

@capture.command("tag")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--add", "add_tags", multiple=True, metavar="TAG",
              help="Tag to add (repeatable: --add boss --add epic).")
@click.option("--remove", "remove_tags", multiple=True, metavar="TAG",
              help="Tag to remove (repeatable).")
@click.pass_context
def cap_tag(ctx: click.Context, file_path: str,
            add_tags: tuple, remove_tags: tuple) -> None:
    """Add or remove metadata tags on a capture file."""
    cfg = _get_config(ctx)
    organiser = MediaOrganizer(cfg.captures_dir)
    fp = Path(file_path)

    if not add_tags and not remove_tags:
        console.print("[yellow]No --add or --remove tags specified.[/yellow]")
        return

    organiser.tag_capture(fp, list(add_tags), remove_tags=list(remove_tags))

    # Read back updated tags to display
    sidecar = fp.with_suffix(".json")
    updated_tags: list = []
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            updated_tags = meta.get("tags", [])
        except Exception:
            pass

    if add_tags:
        console.print(f"[green]Added:[/green] {', '.join(add_tags)}")
    if remove_tags:
        console.print(f"[red]Removed:[/red] {', '.join(remove_tags)}")
    console.print(f"[cyan]Current tags:[/cyan] {', '.join(updated_tags) or '(none)'}")


# ================================================================== #
# Storage management                                                   #
# ================================================================== #

@capture.command("storage")
@click.pass_context
def cap_storage(ctx: click.Context) -> None:
    """Show capture storage usage."""
    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")
    organiser = MediaOrganizer(cfg.captures_dir)
    usage = organiser.get_storage_usage()

    if fmt == "json":
        click.echo(json.dumps(usage, indent=2))
        return

    console.print(f"\n[bold cyan]Capture Storage Usage[/bold cyan]")
    console.print(f"  Total: {usage['total_gb']:.2f} GB ({usage['total_mb']:.0f} MB)")
    if usage.get("by_game_bytes"):
        console.print("\n[bold]By game:[/bold]")
        for game, size in sorted(usage["by_game_bytes"].items(), key=lambda x: x[1], reverse=True)[:10]:
            mb = size / (1024 * 1024)
            console.print(f"  {game}: {mb:.1f} MB")


@capture.command("cleanup")
@click.option("--max-age-days", default=90, show_default=True,
              help="Delete captures older than N days.")
@click.option("--max-gb", default=None, type=float,
              help="Delete oldest until under this GB limit.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview what would be deleted without actually deleting.")
@click.pass_context
def cap_cleanup(ctx: click.Context, max_age_days: int, max_gb: Optional[float],
                dry_run: bool) -> None:
    """Clean up old captures based on age or storage limit."""
    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")
    organiser = MediaOrganizer(cfg.captures_dir)
    result = organiser.cleanup_old_captures(
        max_age_days=max_age_days, max_total_gb=max_gb, dry_run=dry_run
    )

    if fmt == "json":
        click.echo(json.dumps(result, indent=2))
        return

    prefix = "[yellow](DRY RUN)[/yellow] " if dry_run else ""
    console.print(f"{prefix}[green]Cleanup complete[/green]")
    console.print(f"  Deleted: {result['deleted_count']} files  "
                  f"({result['deleted_bytes'] / 1024 / 1024:.1f} MB freed)")


# ================================================================== #
# Editing                                                              #
# ================================================================== #

@capture.command("trim")
@click.argument("source", type=click.Path(exists=True))
@click.argument("dest", type=click.Path())
@click.argument("start", type=float)
@click.argument("end", type=float)
@click.pass_context
def cap_trim(ctx: click.Context, source: str, dest: str, start: float, end: float) -> None:
    """Trim a video clip. SOURCE DEST START END (seconds)."""
    fmt = ctx.obj.get("output_format", "table")
    editor = MediaEditor()
    result = editor.trim_video(Path(source), Path(dest), start, end)
    data = {"output": str(result)}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Trimmed:[/green] {result}")


@capture.command("crop")
@click.argument("source", type=click.Path(exists=True))
@click.argument("dest", type=click.Path())
@click.option("--left", default=0, type=int)
@click.option("--top", default=0, type=int)
@click.option("--right", required=True, type=int)
@click.option("--bottom", required=True, type=int)
@click.pass_context
def cap_crop(ctx: click.Context, source: str, dest: str,
             left: int, top: int, right: int, bottom: int) -> None:
    """Crop a screenshot."""
    fmt = ctx.obj.get("output_format", "table")
    editor = MediaEditor()
    result = editor.crop_screenshot(Path(source), Path(dest), (left, top, right, bottom))
    data = {"output": str(result)}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Cropped:[/green] {result}")


@capture.command("annotate")
@click.argument("source", type=click.Path(exists=True))
@click.argument("dest", type=click.Path())
@click.argument("text")
@click.option("--x", default=10, type=int)
@click.option("--y", default=10, type=int)
@click.pass_context
def cap_annotate(ctx: click.Context, source: str, dest: str,
                 text: str, x: int, y: int) -> None:
    """Add a text annotation to a screenshot."""
    fmt = ctx.obj.get("output_format", "table")
    editor = MediaEditor()
    result = editor.annotate_screenshot(Path(source), Path(dest), text, (x, y))
    data = {"output": str(result)}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Annotated:[/green] {result}")


@capture.command("montage")
@click.argument("clips", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--output", "-o", required=True, type=click.Path())
@click.option("--clip-duration", default=5.0, show_default=True,
              help="Seconds per clip to include.")
@click.pass_context
def cap_montage(ctx: click.Context, clips: tuple, output: str, clip_duration: float) -> None:
    """Create a highlight montage from multiple video clips."""
    fmt = ctx.obj.get("output_format", "table")
    editor = MediaEditor()
    result = editor.create_montage(
        [Path(c) for c in clips], Path(output), clip_duration=clip_duration
    )
    data = {"output": str(result)}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Montage created:[/green] {result}")


# ================================================================== #
# Upload                                                               #
# ================================================================== #

@capture.command("upload")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--game", "game_name", default=None)
@click.option("--dest-dir", default=None, help="Target directory for local_copy upload.")
@click.option("--simulate", is_flag=True, default=False,
              help="Simulate upload (no files copied).")
@click.pass_context
def cap_upload(ctx: click.Context, file_path: str, game_name: Optional[str],
               dest_dir: Optional[str], simulate: bool) -> None:
    """Upload a captured file."""
    fmt = ctx.obj.get("output_format", "table")

    cfg_data: dict = {"type": "simulated"} if simulate else {
        "type": "local_copy",
        "dest_dir": dest_dir or str(Path.home() / "PlayniteUploads"),
    }
    uploader = MediaUploader(cfg_data)
    result = uploader.upload(Path(file_path), game_name=game_name)

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    if result.success:
        console.print(f"[green]Upload succeeded:[/green] {result.destination}")
    else:
        console.print(f"[red]Upload failed:[/red] {result.error_message}")


# ================================================================== #
# Gallery                                                              #
# ================================================================== #

@capture.command("gallery")
@click.argument("game_name")
@click.option("--output", "-o", default=None, type=click.Path())
@click.pass_context
def cap_gallery(ctx: click.Context, game_name: str, output: Optional[str]) -> None:
    """Generate an HTML screenshot gallery for a game."""
    cfg = _get_config(ctx)
    fmt = ctx.obj.get("output_format", "table")
    organiser = MediaOrganizer(cfg.captures_dir)
    out_path = organiser.create_html_gallery(
        game_name, output_path=Path(output) if output else None
    )
    data = {"gallery_path": str(out_path)}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Gallery created:[/green] {out_path}")


# ================================================================== #
# C14 — Video format conversion                                        #
# ================================================================== #

@capture.command("convert")
@click.argument("source", type=click.Path(exists=True))
@click.argument("dest", type=click.Path())
@click.option("--video-codec", default=None,
              help="Override video codec (e.g. libx264, libvpx-vp9, copy).")
@click.option("--audio-codec", default=None,
              help="Override audio codec (e.g. aac, libopus, mp3).")
@click.pass_context
def cap_convert(
    ctx: click.Context, source: str, dest: str,
    video_codec: Optional[str], audio_codec: Optional[str],
) -> None:
    """Transcode a video to a different format/container.

    The target format is inferred from DEST's file extension.
    Supported containers: mp4, mkv, mov, webm, avi.

    Example: playnite capture convert clip.mp4 clip.webm
    """
    fmt = ctx.obj.get("output_format", "table")
    editor = MediaEditor()
    result = editor.convert_video(
        Path(source), Path(dest),
        video_codec=video_codec,
        audio_codec=audio_codec,
    )
    data = {"output": str(result), "format": Path(dest).suffix.lstrip(".")}
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Converted:[/green] {result}")


# ================================================================== #
# C10 — Highlight detection & auto-montage                            #
# ================================================================== #

@capture.command("highlights")
@click.argument("source", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Output montage file (default: <source>_highlights.mp4).")
@click.option("--threshold", default=0.4, show_default=True, type=float,
              help="Scene-change threshold 0.0–1.0 (higher = fewer highlights).")
@click.option("--clip-duration", default=5.0, show_default=True, type=float,
              help="Seconds per highlight clip.")
@click.option("--min-gap", default=3.0, show_default=True, type=float,
              help="Minimum seconds between detected highlights.")
@click.option("--detect-only", is_flag=True, default=False,
              help="Only report timestamps; do not create a montage.")
@click.pass_context
def cap_highlights(
    ctx: click.Context, source: str, output: Optional[str],
    threshold: float, clip_duration: float, min_gap: float,
    detect_only: bool,
) -> None:
    """Detect highlight moments and optionally build an auto-montage.

    Uses ffmpeg's scene-change filter to locate visually significant moments,
    then trims and concatenates them into a single highlight reel.

    Example: playnite capture highlights gameplay.mp4 -o highlights.mp4
    """
    fmt = ctx.obj.get("output_format", "table")
    editor = MediaEditor()
    src = Path(source)

    moments = editor.detect_highlights(src, scene_threshold=threshold, min_gap_seconds=min_gap)

    if detect_only:
        data = {"source": source, "highlights": [m.to_dict() for m in moments]}
        if fmt == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            console.print(f"[cyan]Detected {len(moments)} highlight(s) in {src.name}[/cyan]")
            for m in moments:
                console.print(f"  {m.timestamp_seconds:.1f}s  score={m.scene_score:.3f}")
        return

    dest_path = Path(output) if output else src.with_name(src.stem + "_highlights.mp4")
    result = editor.auto_montage(
        src, dest_path,
        scene_threshold=threshold,
        clip_duration=clip_duration,
        min_gap_seconds=min_gap,
    )
    data = {
        "output": str(result),
        "highlights_detected": len(moments),
        "clip_duration": clip_duration,
    }
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Highlight montage created:[/green] {result}")
        console.print(f"  Detected {len(moments)} scene change(s)  "
                      f"clip_duration={clip_duration}s")


# ================================================================== #
# C5 — Achievement capture                                             #
# ================================================================== #

@capture.command("achievement")
@click.option("--game", "game_name", default=None, help="Game name.")
@click.option("--name", "achievement_name", default=None,
              help="Achievement name or description.")
@click.option("--monitor", is_flag=True, default=False,
              help="Start background template monitoring.")
@click.option("--stop-monitor", is_flag=True, default=False,
              help="Stop background template monitoring.")
@click.option("--status", "show_status", is_flag=True, default=False,
              help="Show achievement detector status.")
@click.option("--register-template", "template_path", default=None, type=click.Path(),
              help="Register a PNG template for auto-detection.")
@click.option("--template-name", default=None,
              help="Name for the registered template.")
@click.option("--interval", default=2.0, show_default=True, type=float,
              help="Screen-check interval in seconds (monitoring mode).")
@click.pass_context
def cap_achievement(
    ctx: click.Context, game_name: Optional[str], achievement_name: Optional[str],
    monitor: bool, stop_monitor: bool, show_status: bool,
    template_path: Optional[str], template_name: Optional[str],
    interval: float,
) -> None:
    """Capture screenshots on achievement events.

    Without flags: manually trigger an achievement screenshot right now.

    Examples:

      # Manual trigger\n
      playnite capture achievement --game "Hollow Knight" --name "True Ending"

      # Register a template and start monitoring\n
      playnite capture achievement --register-template steam_popup.png --template-name steam
      playnite capture achievement --monitor --game "Hollow Knight"
    """
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")
    cfg = _get_config(ctx)

    if inst["achievement_detector"] is None:
        inst["achievement_detector"] = AchievementDetector(
            output_dir=cfg.captures_dir / "achievements"
        )

    det = inst["achievement_detector"]

    if show_status or stop_monitor:
        if stop_monitor and det.is_monitoring:
            det.stop_monitoring()
            console.print("[yellow]Achievement monitoring stopped.[/yellow]")
        st = det.status()
        if fmt == "json":
            click.echo(json.dumps(st, indent=2))
        else:
            console.print(f"Monitoring: {st['monitoring']}")
            console.print(f"Templates:  {', '.join(st['templates_registered']) or 'none'}")
            console.print(f"Captures:   {st['captures_count']}")
        return

    if template_path:
        name = template_name or Path(template_path).stem
        det.register_template(name, Path(template_path))
        console.print(f"[green]Template registered:[/green] {name}")

    if monitor:
        det.start_monitoring(game_name=game_name, interval_seconds=interval)
        data = {"monitoring": True, "game_name": game_name, "interval": interval}
        if fmt == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            console.print(f"[green]Achievement monitoring started[/green]  "
                          f"interval={interval}s  game={game_name or 'any'}")
        return

    # Default: manual trigger
    result = det.trigger_capture(game_name=game_name, achievement_name=achievement_name)
    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        console.print(f"[green]Achievement screenshot saved:[/green] {result.file_path}")
        if achievement_name:
            console.print(f"  Achievement: {achievement_name}")


# ================================================================== #
# C15 — Recording overlay                                              #
# ================================================================== #

@capture.command("overlay")
@click.option("--show", is_flag=True, default=False, help="Show the overlay window.")
@click.option("--hide", is_flag=True, default=False, help="Hide the overlay window.")
@click.option("--status", "show_status", is_flag=True, default=False,
              help="Show overlay status.")
@click.option("--position",
              type=click.Choice(["top-left", "top-right", "bottom-left", "bottom-right"]),
              default="top-right", show_default=True)
@click.option("--opacity", default=0.80, show_default=True, type=float,
              help="Window opacity 0.1–1.0.")
@click.pass_context
def cap_overlay(
    ctx: click.Context, show: bool, hide: bool, show_status: bool,
    position: str, opacity: float,
) -> None:
    """Manage the floating recording-status overlay window.

    The overlay is a small borderless topmost window that shows
    REC / BUF / IDLE state.  Requires a graphical display; silently
    disabled in headless environments.

    Note: full transparent in-game overlay (over fullscreen DirectX/Metal
    contexts) requires platform-native C extensions not available in pure
    Python.  See capture/overlay.py for details.
    """
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")

    if inst["overlay"] is None:
        inst["overlay"] = CaptureOverlay(opacity=opacity, position=position)

    ov = inst["overlay"]

    if show_status:
        st = ov.status()
        if fmt == "json":
            click.echo(json.dumps(st, indent=2))
        else:
            avail = "[green]yes[/green]" if st["available"] else "[red]no (headless)[/red]"
            console.print(f"Available: {avail}")
            console.print(f"Visible:   {st['visible']}")
            console.print(f"Recording: {st['recording']}")
            console.print(f"Buffering: {st['buffering']}")
        return

    if hide:
        ov.hide()
        data = {"visible": False}
        if fmt == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            console.print("[yellow]Overlay hidden.[/yellow]")
        return

    if show or not (show or hide or show_status):
        ov.show()
        # Sync with recorder / buffer state if active
        is_rec = bool(inst["recorder"] and inst["recorder"].is_recording())
        is_buf = bool(inst["buffer"] and inst["buffer"].status().get("buffering", False))
        ov.set_recording(is_rec)
        ov.set_buffering(is_buf)
        data = ov.status()
        if fmt == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            if data["available"]:
                console.print(f"[green]Overlay shown[/green]  position={position}  "
                              f"opacity={opacity}")
            else:
                console.print("[yellow]Overlay not available in this environment "
                              "(no display / tkinter).[/yellow]")


# ================================================================== #
# C2 — Hotkey listener                                                 #
# ================================================================== #

@capture.command("hotkeys")
@click.option("--start", "do_start", is_flag=True, default=False,
              help="Start the global hotkey listener.")
@click.option("--stop", "do_stop", is_flag=True, default=False,
              help="Stop the global hotkey listener.")
@click.option("--status", "show_status", is_flag=True, default=False,
              help="Show listener status and current bindings.")
@click.option("--screenshot-key", default=None,
              help="Key for screenshot (e.g. f12, <ctrl>+f12).")
@click.option("--record-key", default=None,
              help="Key to toggle video recording (e.g. f9).")
@click.option("--replay-key", default=None,
              help="Key to save replay buffer (e.g. f10).")
@click.pass_context
def cap_hotkeys(
    ctx: click.Context, do_start: bool, do_stop: bool, show_status: bool,
    screenshot_key: Optional[str], record_key: Optional[str], replay_key: Optional[str],
) -> None:
    """Manage global hotkeys for capture actions.

    Binds keyboard shortcuts that work system-wide while games are running.
    Requires pynput (already in requirements.txt).

    Default keys (from config):
      F12  — screenshot
      F9   — toggle video recording
      F10  — save replay buffer

    Example:
      playnite capture hotkeys --start
      playnite capture hotkeys --start --screenshot-key "<ctrl>+f12"
      playnite capture hotkeys --status
      playnite capture hotkeys --stop
    """
    inst = _instances
    fmt = ctx.obj.get("output_format", "table")
    cfg = _get_config(ctx)

    # Callbacks close over `inst` so they can access live recorder/buffer state
    # without needing a Click context at invocation time.
    def _do_screenshot() -> None:
        cap = ScreenshotCapture(
            output_dir=cfg.captures_dir / "screenshots", fmt="png"
        )
        cap.capture()

    def _do_record_toggle() -> None:
        if inst["recorder"] and inst["recorder"].is_recording():
            inst["recorder"].stop_recording()
            inst["recorder"] = None
        else:
            inst["recorder"] = VideoRecorder(output_dir=cfg.captures_dir / "videos")
            inst["recorder"].start_recording(simulate=False)

    def _do_save_replay() -> None:
        if inst["buffer"]:
            inst["buffer"].save_replay()

    if inst["hotkeys"] is None:
        inst["hotkeys"] = HotkeyListener(
            on_screenshot=_do_screenshot,
            on_record_toggle=_do_record_toggle,
            on_save_replay=_do_save_replay,
            screenshot_key=screenshot_key or cfg.capture.screenshot_hotkey,
            record_key=record_key or cfg.capture.record_hotkey,
            replay_key=replay_key or cfg.capture.save_replay_hotkey,
        )
    else:
        if screenshot_key or record_key or replay_key:
            inst["hotkeys"].update_keys(
                screenshot_key=screenshot_key,
                record_key=record_key,
                replay_key=replay_key,
            )

    if do_stop:
        inst["hotkeys"].stop()
        data = {"running": False}
        if fmt == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            console.print("[yellow]Hotkey listener stopped.[/yellow]")
        return

    if do_start:
        ok = inst["hotkeys"].start()
        st = inst["hotkeys"].status()
        if fmt == "json":
            click.echo(json.dumps(st, indent=2))
        else:
            if ok:
                console.print("[green]Hotkey listener started[/green]")
                console.print(f"  Screenshot : {st['screenshot_key']}")
                console.print(f"  Record     : {st['record_key']}")
                console.print(f"  Save replay: {st['replay_key']}")
            else:
                console.print(
                    "[yellow]Hotkey listener could not start. "
                    "pynput may be unavailable or no display is reachable.[/yellow]"
                )
        return

    # Default / --status: show current state
    st = inst["hotkeys"].status()
    if fmt == "json":
        click.echo(json.dumps(st, indent=2))
    else:
        running_str = "[green]running[/green]" if st["running"] else "[dim]stopped[/dim]"
        avail_str = "[green]yes[/green]" if st["pynput_available"] else "[red]no[/red]"
        console.print(f"Status:          {running_str}")
        console.print(f"pynput available: {avail_str}")
        console.print(f"Screenshot key:  {st['screenshot_key']}")
        console.print(f"Record key:      {st['record_key']}")
        console.print(f"Replay key:      {st['replay_key']}")
