"""CLI commands for achievement tracking.

Usage examples:
  playnite achievements sync
  playnite achievements sync --platform steam
  playnite achievements stats --json
  playnite achievements hunt --max-difficulty 0.5 --max-remaining 10
  playnite achievements export --format json --output ~/achievements.json
  playnite achievements add-manual --game "My Game" --name "First Blood"
  playnite achievements report
  playnite achievements timeline
  playnite achievements challenge
  playnite achievements notifications
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

from playnite.achievements.exporter import AchievementExporter
from playnite.achievements.hunting import AchievementHunter
from playnite.achievements.platforms.gog import GOGAdapter
from playnite.achievements.platforms.manual import ManualAdapter
from playnite.achievements.platforms.psn import PSNAdapter
from playnite.achievements.platforms.steam import SteamAdapter
from playnite.achievements.platforms.xbox import XboxAdapter
from playnite.achievements.stats import AchievementStats
from playnite.achievements.tracker import AchievementTracker

if TYPE_CHECKING:
    from playnite.config import Config
    from playnite.database.connection import DatabaseManager

console = Console()


def _build_tracker(config: Config, db: DatabaseManager) -> AchievementTracker:
    tracker = AchievementTracker(config, db)
    if config.steam.enabled or config.steam.api_key:
        tracker.register_adapter(SteamAdapter(config.steam))
    if config.xbox.enabled or config.xbox.api_key:
        tracker.register_adapter(XboxAdapter(config.xbox))
    if config.psn.enabled or config.psn.npsso_token:
        tracker.register_adapter(PSNAdapter(config.psn))
    if config.gog.enabled or config.gog.client_id:
        tracker.register_adapter(GOGAdapter(config.gog))
    tracker.register_adapter(ManualAdapter(db))
    return tracker


@click.group("achievements")
def achievements_group() -> None:
    """Cross-platform achievement tracking commands."""


# ------------------------------------------------------------------
# sync
# ------------------------------------------------------------------


@achievements_group.command("sync")
@click.option("--platform", "-p", default=None, help="Platform to sync (steam/xbox/psn/gog/all)")
@click.option("--force", is_flag=True, help="Force re-sync even if recently synced")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON")
@click.pass_context
def sync_cmd(ctx, platform, force, output_json) -> None:
    """Sync achievements from configured platforms."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    tracker = _build_tracker(config, db)

    results = tracker.sync(platform=platform, force=force)

    if output_json:
        click.echo(json.dumps([vars(r) for r in results], indent=2, default=str))
        return

    if not results:
        console.print("[yellow]No platforms synced (check configuration)[/yellow]")
        return

    for r in results:
        status = "[green]OK[/green]" if r.success else "[red]FAILED[/red]"
        console.print(
            f"[bold]{r.platform}[/bold] {status} — "
            f"{r.games_synced} games, "
            f"{r.achievements_found} achievements, "
            f"{r.new_unlocks} new unlocks",
        )
        if r.errors:
            for err in r.errors:
                console.print(f"  [red]  Error: {err}[/red]")

    # Show pending notifications
    notifications = tracker.get_pending_notifications()
    if notifications:
        console.print(f"\n[bold yellow]New unlocks ({len(notifications)}):[/bold yellow]")
        for n in notifications:
            console.print(f"  🏆 [green]{n['achievement']}[/green] in {n['game']}")
        tracker.mark_notifications_read()


# ------------------------------------------------------------------
# stats
# ------------------------------------------------------------------


@achievements_group.command("stats")
@click.option("--platform", "-p", default=None, help="Filter to a single platform")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def stats_cmd(ctx, platform, output_json) -> None:
    """Show achievement statistics."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    tracker = _build_tracker(config, db)
    stats = AchievementStats(db)

    global_stats = tracker.get_global_stats()
    velocity = tracker.get_unlock_velocity(days=30)
    milestones = stats.milestone_report()

    if output_json:
        click.echo(
            json.dumps(
                {"global": global_stats, "velocity": velocity, "milestones": milestones},
                indent=2,
                default=str,
            ),
        )
        return

    # Global stats table
    t = Table(title="Achievement Statistics", show_header=True)
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right")
    t.add_row("Total achievements", str(global_stats["total_achievements"]))
    t.add_row("Unlocked", str(global_stats["unlocked"]))
    t.add_row("Locked", str(global_stats["locked"]))
    t.add_row("Completion", f"{global_stats['completion_pct']}%")
    t.add_row("Rare unlocked", str(global_stats["rare_unlocked"]))
    t.add_row("Games tracked", str(global_stats["total_games"]))
    console.print(t)

    # Velocity
    console.print(
        f"\n[bold]Unlock velocity (30d):[/bold] "
        f"{velocity['total']} total, {velocity['avg_per_day']}/day",
    )

    # Next milestone
    nm = milestones.get("next_global_milestone")
    if nm:
        console.print(
            f"[bold]Next milestone:[/bold] {nm} "
            f"({milestones['remaining_for_next']} to go)",
        )


# ------------------------------------------------------------------
# hunt
# ------------------------------------------------------------------


@achievements_group.command("hunt")
@click.option("--max-difficulty", "-d", type=float, default=0.7, show_default=True)
@click.option("--max-remaining", "-r", type=int, default=30, show_default=True)
@click.option("--platform", "-p", default=None)
@click.option("--limit", "-n", type=int, default=10, show_default=True)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def hunt_cmd(ctx, max_difficulty, max_remaining, platform, limit, output_json) -> None:
    """Find achievable games for achievement hunting."""
    db: DatabaseManager = ctx.obj["db"]
    hunter = AchievementHunter(db)
    targets = hunter.find_targets(
        max_difficulty=max_difficulty,
        max_remaining=max_remaining,
        platform=platform,
        limit=limit,
    )

    if output_json:
        click.echo(json.dumps([vars(t) for t in targets], indent=2, default=str))
        return

    if not targets:
        console.print("[yellow]No matching games found. Try relaxing the filters.[/yellow]")
        return

    t = Table(title=f"Achievement Hunting Targets (top {limit})")
    t.add_column("Game", style="bold")
    t.add_column("Platform")
    t.add_column("Done%", justify="right")
    t.add_column("Remaining", justify="right")
    t.add_column("Achievable", justify="right")
    t.add_column("Est. hours", justify="right")
    t.add_column("Score", justify="right")
    for tgt in targets:
        t.add_row(
            tgt.game_name,
            tgt.platform,
            f"{tgt.completion_pct}%",
            str(tgt.remaining),
            str(tgt.achievable_count),
            str(round(tgt.estimated_minutes / 60, 1)),
            str(tgt.achievability_score),
        )
    console.print(t)


# ------------------------------------------------------------------
# challenge
# ------------------------------------------------------------------


@achievements_group.command("challenge")
@click.option("--max-difficulty", "-d", type=float, default=0.5, show_default=True)
@click.option("--max-hours", "-h", type=float, default=10.0, show_default=True)
@click.option("--count", "-n", type=int, default=5, show_default=True)
@click.option("--platform", "-p", default=None)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def challenge_cmd(ctx, max_difficulty, max_hours, count, platform, output_json) -> None:
    """Suggest a set of games as a personal achievement challenge."""
    db: DatabaseManager = ctx.obj["db"]
    hunter = AchievementHunter(db)
    suggestions = hunter.create_challenge(
        max_difficulty=max_difficulty,
        max_hours=max_hours,
        count=count,
        platform=platform,
    )

    if output_json:
        click.echo(json.dumps(suggestions, indent=2))
        return

    if not suggestions:
        console.print("[yellow]No suitable games found for a challenge.[/yellow]")
        return

    total_hrs = sum(s["estimated_hours"] for s in suggestions)
    console.print(
        f"[bold]Challenge mode:[/bold] {len(suggestions)} games, "
        f"~{round(total_hrs, 1)} hours total\n",
    )
    for i, s in enumerate(suggestions, 1):
        console.print(
            f"  {i}. [cyan]{s['game']}[/cyan] ({s['platform']}) — "
            f"{s['achievable_count']} achievements, ~{s['estimated_hours']}h, "
            f"{s['completion_pct']}% done",
        )


# ------------------------------------------------------------------
# export
# ------------------------------------------------------------------


@achievements_group.command("export")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output file path")
@click.option("--unlocked-only", is_flag=True, default=False)
@click.option("--game-id", type=int, multiple=True, help="Limit to specific game IDs")
@click.pass_context
def export_cmd(ctx, fmt, output, unlocked_only, game_id) -> None:
    """Export achievement data to JSON or CSV."""
    db: DatabaseManager = ctx.obj["db"]
    exporter = AchievementExporter(db)
    output_path = Path(output)
    game_ids = list(game_id) if game_id else None

    if fmt == "json":
        count = exporter.export_to_json(output_path, game_ids=game_ids, include_locked=not unlocked_only)
    else:
        count = exporter.export_to_csv(output_path, game_ids=game_ids, include_locked=not unlocked_only)

    console.print(f"[green]Exported {count} achievements to {output_path}[/green]")


# ------------------------------------------------------------------
# add-manual
# ------------------------------------------------------------------


@achievements_group.command("import")
@click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Path to exported JSON file")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def import_cmd(ctx, input_path, output_json) -> None:
    """Import achievements from a previously exported JSON file."""
    from playnite.backup.manager import BackupManager

    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)
    count = mgr.import_library(Path(input_path))

    if output_json:
        click.echo(json.dumps({"imported": count, "source": input_path}))
        return
    console.print(f"[green]Imported {count} achievements from {input_path}[/green]")


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


@achievements_group.command("list")
@click.option("--game", "-g", default=None, help="Filter by game name (partial match)")
@click.option("--game-id", type=int, default=None, help="Filter by game DB id")
@click.option("--platform", "-p", default=None, help="Filter by platform")
@click.option("--unlocked-only", is_flag=True, default=False)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def list_cmd(ctx, game, game_id, platform, unlocked_only, output_json) -> None:
    """List achievements with optional filters."""
    from playnite.database.models import Achievement, Game, UserAchievement

    db: DatabaseManager = ctx.obj["db"]

    with db.get_session() as session:
        q = (
            session.query(Achievement, Game, UserAchievement)
            .join(Game, Achievement.game_id == Game.id)
            .outerjoin(
                UserAchievement,
                UserAchievement.achievement_id == Achievement.id,
            )
        )
        if game:
            q = q.filter(Game.name.ilike(f"%{game}%"))
        if game_id is not None:
            q = q.filter(Game.id == game_id)
        if platform:
            q = q.filter(Game.platform == platform)
        if unlocked_only:
            q = q.filter(UserAchievement.is_unlocked == True)  # noqa: E712

        rows = [
            {
                "achievement_id": a.id,
                "name": a.name,
                "game": g.name,
                "platform": g.platform,
                "global_pct": a.global_percentage,
                "is_unlocked": ua.is_unlocked if ua else False,
                "unlock_date": ua.unlock_date.isoformat() if ua and ua.unlock_date else None,
            }
            for a, g, ua in q.all()
        ]

    if output_json:
        click.echo(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        console.print("[yellow]No achievements found.[/yellow]")
        return

    t = Table(title=f"Achievements ({len(rows)})")
    t.add_column("ID", justify="right")
    t.add_column("Achievement", style="bold")
    t.add_column("Game")
    t.add_column("Platform")
    t.add_column("Global%", justify="right")
    t.add_column("Status")
    t.add_column("Unlock date")
    for row in rows:
        status = "[green]Unlocked[/green]" if row["is_unlocked"] else "[dim]Locked[/dim]"
        t.add_row(
            str(row["achievement_id"]),
            row["name"],
            row["game"],
            row["platform"],
            f"{row['global_pct']:.1f}" if row["global_pct"] is not None else "—",
            status,
            row["unlock_date"] or "—",
        )
    console.print(t)


# ------------------------------------------------------------------
# rare
# ------------------------------------------------------------------


@achievements_group.command("rare")
@click.option("--platform", "-p", default=None, help="Filter by platform")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def rare_cmd(ctx, platform, output_json) -> None:
    """List unlocked rare achievements, sorted by rarity."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    tracker = _build_tracker(config, db)

    achievements = tracker.get_rare_achievements()
    if platform:
        achievements = [a for a in achievements if a["platform"] == platform]

    if output_json:
        click.echo(json.dumps(achievements, indent=2, default=str))
        return

    if not achievements:
        console.print("[yellow]No rare achievements unlocked yet.[/yellow]")
        return

    t = Table(title=f"Rare Achievements ({len(achievements)})")
    t.add_column("Achievement", style="bold")
    t.add_column("Game")
    t.add_column("Platform")
    t.add_column("Global%", justify="right")
    t.add_column("Unlock date")
    for a in achievements:
        t.add_row(
            a["achievement"],
            a["game"],
            a["platform"],
            f"{a['global_pct']:.2f}%" if a["global_pct"] is not None else "—",
            a["unlock_date"].isoformat() if a["unlock_date"] else "—",
        )
    console.print(t)


# ------------------------------------------------------------------
# mark-unlocked
# ------------------------------------------------------------------


@achievements_group.command("mark-unlocked")
@click.option("--achievement-id", "-a", required=True, type=int, help="Achievement DB id")
@click.option("--unlock-date", default=None, help="Override unlock timestamp (ISO, e.g. 2024-06-01)")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def mark_unlocked_cmd(ctx, achievement_id, unlock_date, output_json) -> None:
    """Mark an achievement as unlocked (manual entries only)."""
    from datetime import datetime as _dt

    db: DatabaseManager = ctx.obj["db"]
    manual = ManualAdapter(db)

    date_obj = None
    if unlock_date:
        try:
            date_obj = _dt.fromisoformat(unlock_date)
        except ValueError:
            console.print(f"[red]Invalid date format: {unlock_date}[/red]")
            sys.exit(1)

    ok = manual.mark_unlocked(achievement_id, unlock_date=date_obj)

    if output_json:
        click.echo(json.dumps({"achievement_id": achievement_id, "success": ok}))
        return

    if ok:
        console.print(f"[green]Achievement {achievement_id} marked as unlocked.[/green]")
    else:
        console.print(f"[red]Achievement {achievement_id} not found.[/red]")
        sys.exit(1)


# ------------------------------------------------------------------
# add-manual
# ------------------------------------------------------------------


@achievements_group.command("add-manual")
@click.option("--game", "-g", required=True, help="Game name")
@click.option("--game-id", type=int, default=None, help="Existing game ID (if game already in DB)")
@click.option("--name", "-n", required=True, help="Achievement name")
@click.option("--description", "-d", default="")
@click.option("--unlocked", is_flag=True, default=False)
@click.option("--unlock-date", default=None, help="ISO date string, e.g. 2024-01-15")
@click.option("--max-value", type=float, default=None)
@click.option("--current-value", type=float, default=None)
@click.pass_context
def add_manual_cmd(ctx, game, game_id, name, description, unlocked, unlock_date, max_value, current_value) -> None:
    """Manually add a game achievement (for platforms without API support)."""
    db: DatabaseManager = ctx.obj["db"]
    manual = ManualAdapter(db)

    if game_id is None:
        game_id = manual.add_game(game)
        console.print(f"[green]Created game '{game}' (id={game_id})[/green]")

    from datetime import datetime

    date_obj = None
    if unlock_date:
        try:
            date_obj = datetime.fromisoformat(unlock_date)
        except ValueError:
            console.print(f"[red]Invalid date format: {unlock_date}[/red]")
            sys.exit(1)

    import uuid
    ach_id_str = f"manual_{uuid.uuid4().hex[:8]}"
    ach_id = manual.add_achievement(
        game_id=game_id,
        achievement_id=ach_id_str,
        name=name,
        description=description,
        is_unlocked=unlocked,
        unlock_date=date_obj,
        max_value=max_value,
        current_value=current_value,
    )
    status = "[green]unlocked[/green]" if unlocked else "locked"
    console.print(f"[green]Achievement '{name}' added (id={ach_id}, {status})[/green]")


# ------------------------------------------------------------------
# edit-manual
# ------------------------------------------------------------------


@achievements_group.command("edit-manual")
@click.option("--achievement-id", "-a", required=True, type=int, help="Achievement DB id to edit")
@click.option("--name", "-n", default=None, help="New achievement name")
@click.option("--description", "-d", default=None, help="New description")
@click.option("--current-value", type=float, default=None, help="Updated progress value")
@click.option("--max-value", type=float, default=None, help="Updated maximum progress value")
@click.option("--unlock-date", default=None, help="Override unlock date (ISO, e.g. 2024-06-01)")
@click.pass_context
def edit_manual_cmd(ctx, achievement_id, name, description, current_value, max_value, unlock_date) -> None:
    """Edit a manually-entered achievement."""
    db: DatabaseManager = ctx.obj["db"]
    manual = ManualAdapter(db)

    date_obj = None
    if unlock_date:
        try:
            from datetime import datetime as _dt
            date_obj = _dt.fromisoformat(unlock_date)
        except ValueError:
            console.print(f"[red]Invalid date format: {unlock_date}[/red]")
            sys.exit(1)

    ok = manual.edit_achievement(
        achievement_id=achievement_id,
        name=name,
        description=description,
        current_value=current_value,
        max_value=max_value,
        unlock_date=date_obj,
    )
    if ok:
        console.print(f"[green]Achievement {achievement_id} updated.[/green]")
    else:
        console.print(f"[red]Achievement {achievement_id} not found.[/red]")
        sys.exit(1)


# ------------------------------------------------------------------
# delete-manual
# ------------------------------------------------------------------


@achievements_group.command("delete-manual")
@click.option("--achievement-id", "-a", required=True, type=int, help="Achievement DB id to delete")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_manual_cmd(ctx, achievement_id, yes) -> None:
    """Delete a manually-entered achievement."""
    db: DatabaseManager = ctx.obj["db"]

    if not yes:
        click.confirm(
            f"Delete achievement {achievement_id} and its unlock record?", abort=True,
        )

    manual = ManualAdapter(db)
    ok = manual.delete_achievement(achievement_id)
    if ok:
        console.print(f"[green]Achievement {achievement_id} deleted.[/green]")
    else:
        console.print(f"[red]Achievement {achievement_id} not found.[/red]")
        sys.exit(1)


# ------------------------------------------------------------------
# report
# ------------------------------------------------------------------


@achievements_group.command("report")
@click.option("--output", "-o", default=None, type=click.Path(), help="Save report to JSON file")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def report_cmd(ctx, output, output_json) -> None:
    """Generate a comprehensive achievement report."""
    db: DatabaseManager = ctx.obj["db"]
    exporter = AchievementExporter(db)
    output_path = Path(output) if output else None
    report = exporter.generate_report(output_path=output_path)

    if output_json or output:
        click.echo(json.dumps(report, indent=2, default=str))
        return

    summary = report["summary"]
    console.print("[bold]Achievement Report[/bold]")
    console.print(f"  Games tracked: {summary['total_games']}")
    console.print(f"  Total achievements: {summary['total_achievements']}")
    console.print(f"  Unlocked: {summary['total_unlocked']}")
    console.print(f"  Completion: {summary['completion_pct']}%")
    console.print(f"  Rare unlocked: {summary['rare_unlocked']}")


# ------------------------------------------------------------------
# timeline
# ------------------------------------------------------------------


@achievements_group.command("timeline")
@click.option("--start", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--end", default=None, help="End date (YYYY-MM-DD)")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def timeline_cmd(ctx, start, end, output_json) -> None:
    """Show achievement unlock timeline."""
    from datetime import datetime

    db: DatabaseManager = ctx.obj["db"]
    stats = AchievementStats(db)

    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    timeline = stats.timeline(start_date=start_dt, end_date=end_dt)

    if output_json:
        click.echo(json.dumps(timeline, indent=2))
        return

    if not timeline:
        console.print("[yellow]No unlock history found.[/yellow]")
        return

    max_count = max(m["count"] for m in timeline) if timeline else 1
    console.print("[bold]Achievement Unlock Timeline (monthly)[/bold]\n")
    bar_width = 40
    for entry in timeline:
        bar_len = int((entry["count"] / max_count) * bar_width)
        bar = "█" * bar_len
        console.print(f"  {entry['month']}  {bar:40s}  {entry['count']}")


# ------------------------------------------------------------------
# notifications
# ------------------------------------------------------------------


@achievements_group.command("notifications")
@click.option("--mark-read", is_flag=True, help="Mark all notifications as read")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def notifications_cmd(ctx, mark_read, output_json) -> None:
    """Show pending achievement unlock notifications."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    tracker = _build_tracker(config, db)

    notifications = tracker.get_pending_notifications()

    if output_json:
        click.echo(json.dumps(notifications, indent=2, default=str))
    elif not notifications:
        console.print("[yellow]No pending notifications.[/yellow]")
    else:
        console.print(f"[bold]Pending notifications ({len(notifications)}):[/bold]")
        for n in notifications:
            console.print(f"  [{n['notified_at'][:10]}] {n['achievement']} — {n['game']}")

    if mark_read:
        count = tracker.mark_notifications_read()
        console.print(f"[green]Marked {count} notifications as read.[/green]")
