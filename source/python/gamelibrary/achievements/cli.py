"""CLI commands for achievement tracking."""

from __future__ import annotations

import json
import click

from ..database import Database
from .tracker import AchievementTracker
from .stats import AchievementStats
from .hunting import AchievementHunter
from .challenge import ChallengeMode
from .sync import SyncScheduler
from .export import AchievementExporter
from .notifications import NotificationManager


def _output(data, as_json: bool):
    """Output data as JSON or formatted text."""
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for k, v in item.items():
                        click.echo(f"  {k}: {v}")
                    click.echo("  ---")
                else:
                    click.echo(f"  {item}")


@click.group("achievements")
@click.option("--db", "db_path", default=None, help="Database path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def achievements_cli(ctx, db_path, as_json):
    """Cross-platform achievement tracking commands."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = Database(db_path) if db_path else Database()
    ctx.obj["json"] = as_json


@achievements_cli.command("register-platform")
@click.argument("name")
@click.argument("api_type", type=click.Choice(["steam", "xbox", "psn", "gog", "manual"]))
@click.option("--api-key", default="", help="API key (omit to be prompted securely)")
@click.option("--user-id", default="", help="User/Steam ID")
@click.option("--extra", default="{}", help="Extra credentials JSON")
@click.pass_context
def register_platform(ctx, name, api_type, api_key, user_id, extra):
    """Register a gaming platform for achievement tracking."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)

    # Prompt securely for API key if needed but not provided
    if not api_key and api_type in ("steam", "xbox"):
        api_key = click.prompt("API key", hide_input=True)

    creds = json.loads(extra)
    if api_key:
        creds["api_key"] = api_key
    if user_id:
        if api_type == "steam":
            creds["steam_id"] = user_id
        elif api_type == "xbox":
            creds["xuid"] = user_id
        elif api_type == "psn":
            creds["account_id"] = user_id
        elif api_type == "gog":
            creds["user_id"] = user_id

    platform_id = tracker.register_platform(name, api_type, creds)
    result = {"platform_id": platform_id, "name": name, "api_type": api_type}
    _output(result, ctx.obj["json"])


@achievements_cli.command("platforms")
@click.pass_context
def list_platforms(ctx):
    """List registered platforms."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    platforms = tracker.get_platforms()
    data = [p.to_dict() for p in platforms]
    _output(data, ctx.obj["json"])


@achievements_cli.command("import")
@click.argument("platform_id", type=int)
@click.option("--game-id", default=None, help="Import single game by external ID")
@click.pass_context
def import_achievements(ctx, platform_id, game_id):
    """Import achievements from a platform."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    if game_id:
        result = tracker.import_single_game(platform_id, game_id)
    else:
        result = tracker.import_achievements(platform_id)
    _output(result, ctx.obj["json"])


@achievements_cli.command("sync")
@click.option("--platform-id", type=int, default=None, help="Sync specific platform")
@click.pass_context
def sync_achievements(ctx, platform_id):
    """Sync achievements from all or specific platform."""
    db = ctx.obj["db"]
    scheduler = SyncScheduler(db)
    if platform_id:
        result = scheduler.sync_platform(platform_id)
        _output(result, ctx.obj["json"])
    else:
        results = scheduler.sync_all()
        _output(results, ctx.obj["json"])


@achievements_cli.command("sync-history")
@click.option("--limit", default=20)
@click.pass_context
def sync_history(ctx, limit):
    """Show sync history."""
    db = ctx.obj["db"]
    scheduler = SyncScheduler(db)
    records = scheduler.get_sync_history(limit)
    _output([r.to_dict() for r in records], ctx.obj["json"])


@achievements_cli.command("games")
@click.option("--platform-id", type=int, default=None)
@click.pass_context
def list_games(ctx, platform_id):
    """List tracked games."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    games = tracker.get_games(platform_id)
    _output([g.to_dict() for g in games], ctx.obj["json"])


@achievements_cli.command("list")
@click.argument("game_id", type=int)
@click.option("--unlocked-only", is_flag=True)
@click.pass_context
def list_achievements(ctx, game_id, unlocked_only):
    """List achievements for a game."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    achievements = tracker.get_achievements(game_id, unlocked_only)
    _output([a.to_dict() for a in achievements], ctx.obj["json"])


@achievements_cli.command("stats")
@click.option("--game-id", type=int, default=None, help="Stats for specific game")
@click.pass_context
def show_stats(ctx, game_id):
    """Show achievement statistics."""
    db = ctx.obj["db"]
    stats = AchievementStats(db)
    if game_id:
        result = stats.get_game_stats(game_id)
    else:
        result = stats.get_overall_stats()
    _output(result.to_dict(), ctx.obj["json"])


@achievements_cli.command("velocity")
@click.pass_context
def show_velocity(ctx):
    """Show achievement unlock velocity."""
    db = ctx.obj["db"]
    stats = AchievementStats(db)
    velocity = stats.get_unlock_velocity(days=365)
    _output(velocity, ctx.obj["json"])


@achievements_cli.command("timeline")
@click.option("--days", default=365, help="Number of days to show")
@click.pass_context
def show_timeline(ctx, days):
    """Show achievement unlock timeline."""
    db = ctx.obj["db"]
    stats = AchievementStats(db)
    timeline = stats.get_unlock_timeline(days)
    _output(timeline, ctx.obj["json"])


@achievements_cli.command("difficulty")
@click.pass_context
def show_difficulty(ctx):
    """Show achievement difficulty distribution."""
    db = ctx.obj["db"]
    stats = AchievementStats(db)
    dist = stats.get_difficulty_distribution()
    _output(dist, ctx.obj["json"])


@achievements_cli.command("platform-stats")
@click.pass_context
def show_platform_stats(ctx):
    """Show statistics by platform."""
    db = ctx.obj["db"]
    stats = AchievementStats(db)
    data = stats.get_platform_stats()
    _output(data, ctx.obj["json"])


@achievements_cli.command("milestones")
@click.pass_context
def show_milestones(ctx):
    """Show achievement milestones."""
    db = ctx.obj["db"]
    stats = AchievementStats(db)
    stats.check_milestones()
    milestones = stats.generate_milestone_report()
    _output([m.to_dict() for m in milestones], ctx.obj["json"])


@achievements_cli.command("hunt-near-complete")
@click.option("--threshold", default=80.0, help="Minimum completion % to show")
@click.pass_context
def hunt_near_complete(ctx, threshold):
    """Find games near 100% completion."""
    db = ctx.obj["db"]
    hunter = AchievementHunter(db)
    results = hunter.get_near_completion_games(threshold)
    _output(results, ctx.obj["json"])


@achievements_cli.command("hunt-easiest")
@click.option("--game-id", type=int, default=None)
@click.option("--limit", default=20)
@click.pass_context
def hunt_easiest(ctx, game_id, limit):
    """Find easiest remaining achievements."""
    db = ctx.obj["db"]
    hunter = AchievementHunter(db)
    results = hunter.get_easiest_remaining(game_id, limit)
    _output(results, ctx.obj["json"])


@achievements_cli.command("hunt-rare")
@click.option("--threshold", default=10.0, help="Max global completion %")
@click.option("--unlocked-only", is_flag=True)
@click.pass_context
def hunt_rare(ctx, threshold, unlocked_only):
    """Find rare achievements."""
    db = ctx.obj["db"]
    hunter = AchievementHunter(db)
    results = hunter.get_rare_achievements(threshold, unlocked_only)
    _output(results, ctx.obj["json"])


@achievements_cli.command("hunt-progress")
@click.pass_context
def hunt_progress(ctx):
    """Show achievements with partial progress."""
    db = ctx.obj["db"]
    hunter = AchievementHunter(db)
    results = hunter.get_in_progress_achievements()
    _output(results, ctx.obj["json"])


@achievements_cli.command("hunt-completable")
@click.option("--max-remaining", default=10, help="Max remaining achievements")
@click.pass_context
def hunt_completable(ctx, max_remaining):
    """Find games with few achievements remaining."""
    db = ctx.obj["db"]
    hunter = AchievementHunter(db)
    results = hunter.get_completable_games(max_remaining)
    _output(results, ctx.obj["json"])


@achievements_cli.command("challenge")
@click.option("--difficulty", type=click.Choice(["easy", "medium", "hard"]), default="medium")
@click.option("--limit", default=5)
@click.pass_context
def suggest_challenge(ctx, difficulty, limit):
    """Get achievement challenge suggestions."""
    db = ctx.obj["db"]
    challenge = ChallengeMode(db)
    results = challenge.suggest_challenges(difficulty, limit)
    _output(results, ctx.obj["json"])


@achievements_cli.command("daily-challenge")
@click.pass_context
def daily_challenge(ctx):
    """Get today's achievement challenge."""
    db = ctx.obj["db"]
    challenge = ChallengeMode(db)
    result = challenge.get_daily_challenge()
    if result:
        _output(result, ctx.obj["json"])
    else:
        click.echo("No challenges available.")


@achievements_cli.command("add-game")
@click.argument("game_name")
@click.option("--platform", default="Manual", help="Platform name for manual entries")
@click.option("--game-id", default=None, help="Custom game ID")
@click.pass_context
def add_manual_game(ctx, game_name, platform, game_id):
    """Add a game for manual achievement tracking."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    gid = tracker.add_manual_game(platform, game_name, game_id)
    _output({"game_id": gid, "name": game_name, "platform": platform}, ctx.obj["json"])


@achievements_cli.command("add-achievement")
@click.argument("game_id", type=int)
@click.argument("name")
@click.option("--description", default="")
@click.option("--unlocked", is_flag=True)
@click.option("--unlock-time", default=None)
@click.option("--global-pct", default=50.0, type=float)
@click.option("--max-progress", default=0, type=int)
@click.option("--current-progress", default=0, type=int)
@click.pass_context
def add_manual_achievement(ctx, game_id, name, description, unlocked, unlock_time, global_pct, max_progress, current_progress):
    """Add a manual achievement entry."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    ach_id = tracker.add_manual_achievement(
        game_id, name, description, unlocked, unlock_time, global_pct, max_progress, current_progress,
    )
    _output({"achievement_id": ach_id, "name": name, "game_id": game_id}, ctx.obj["json"])


@achievements_cli.command("update-achievement")
@click.argument("achievement_id", type=int)
@click.option("--unlocked/--locked", default=None)
@click.option("--unlock-time", default=None)
@click.option("--progress", type=int, default=None)
@click.option("--name", default=None, help="New achievement name")
@click.option("--description", default=None, help="New description")
@click.option("--global-pct", type=float, default=None, help="New global completion %")
@click.pass_context
def update_achievement(ctx, achievement_id, unlocked, unlock_time, progress, name, description, global_pct):
    """Update a manual achievement's status or definition."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    tracker.update_manual_achievement(
        achievement_id, unlocked, unlock_time, progress,
        name=name, description=description, global_pct=global_pct,
    )
    click.echo(f"Achievement {achievement_id} updated.")


@achievements_cli.command("delete-achievement")
@click.argument("achievement_id", type=int)
@click.pass_context
def delete_achievement(ctx, achievement_id):
    """Delete a manually entered achievement."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    tracker.delete_achievement(achievement_id)
    click.echo(f"Achievement {achievement_id} deleted.")


@achievements_cli.command("recent")
@click.option("--limit", default=20)
@click.pass_context
def recent_unlocks(ctx, limit):
    """Show recently unlocked achievements."""
    db = ctx.obj["db"]
    tracker = AchievementTracker(db)
    results = tracker.get_recent_unlocks(limit)
    _output(results, ctx.obj["json"])


@achievements_cli.command("export")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.option("--output", "output_path", default=None, help="Output file path")
@click.option("--game-id", type=int, default=None)
@click.pass_context
def export_data(ctx, fmt, output_path, game_id):
    """Export achievement data to JSON or CSV."""
    db = ctx.obj["db"]
    exporter = AchievementExporter(db)
    if fmt == "json":
        result = exporter.export_json(output_path, game_id)
    else:
        result = exporter.export_csv(output_path, game_id)

    if output_path:
        click.echo(f"Exported to {output_path}")
    else:
        click.echo(result)


@achievements_cli.command("notifications")
@click.option("--unread-only", is_flag=True)
@click.option("--mark-read", is_flag=True)
@click.pass_context
def show_notifications(ctx, unread_only, mark_read):
    """Show achievement notifications."""
    db = ctx.obj["db"]
    notifications = NotificationManager(db)
    if unread_only:
        results = notifications.get_unread()
    else:
        results = notifications.get_all()
    _output(results, ctx.obj["json"])
    if mark_read:
        notifications.mark_all_read()
        click.echo("All notifications marked as read.")
