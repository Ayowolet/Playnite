"""CLI commands for duplicate detection."""

from __future__ import annotations

import json
import sys
import time
import uuid
import click

from ..db.database import GameDatabase
from ..duplicates.config import DetectionConfig, DetectionFilter, ScoringWeights
from ..duplicates.detector import DuplicateDetector
from ..duplicates.history import ResolutionHistory
from ..duplicates.report import DuplicateReport


@click.group("duplicates")
def duplicates_group() -> None:
    """Duplicate detection commands."""


@duplicates_group.command("scan")
@click.option("--threshold", type=float, default=0.75, help="Match threshold (0.60-1.00)")
@click.option("--source-priority", multiple=True, help="Source priority order (e.g. Steam GOG Epic)")
@click.option("--exclude-source", multiple=True, help="Exclude games from these sources")
@click.option("--exclude-hidden", is_flag=True, help="Exclude hidden games")
@click.option("--exclude-uninstalled", is_flag=True, help="Exclude uninstalled games")
@click.option("--similarity-mode", is_flag=True, help="Check for similarity mode")
@click.option("--name-filter", type=str, default=None, help="Regex filter on game names")
@click.pass_context
def scan(ctx, threshold, source_priority, exclude_source, exclude_hidden,
         exclude_uninstalled, similarity_mode, name_filter) -> None:
    """Scan library for duplicate games."""
    db_path = ctx.obj.get("db_path")
    output_format = ctx.obj.get("format", "text")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    filters = DetectionFilter(
        include_hidden=not exclude_hidden,
        include_uninstalled=not exclude_uninstalled,
        name_pattern=name_filter,
    )

    config = DetectionConfig(
        threshold=threshold,
        source_priority=list(source_priority) if source_priority else ["Steam", "GOG", "Epic"],
        filters=filters,
        similarity_mode=similarity_mode,
    )

    with GameDatabase(db_path) as db:
        start = time.time()
        detector = DuplicateDetector(db, config)
        groups = detector.detect()
        duration = time.time() - start

        total_dups = sum(g.size - 1 for g in groups)
        report = DuplicateReport(
            total_games_scanned=db.game_count(),
            total_duplicates_found=total_dups,
            total_groups=len(groups),
            groups=groups,
            scan_duration_seconds=duration,
            config_used=config,
        )

        if output_format == "json":
            click.echo(report.to_json())
        elif output_format == "table":
            click.echo(report.to_table(db))
        else:
            click.echo(report.to_text())


@duplicates_group.command("report")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.pass_context
def report(ctx, output) -> None:
    """Generate duplicate detection report."""
    db_path = ctx.obj.get("db_path")
    output_format = ctx.obj.get("format", "text")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    with GameDatabase(db_path) as db:
        start = time.time()
        detector = DuplicateDetector(db)
        groups = detector.detect()
        duration = time.time() - start

        total_dups = sum(g.size - 1 for g in groups)
        rpt = DuplicateReport(
            total_games_scanned=db.game_count(),
            total_duplicates_found=total_dups,
            total_groups=len(groups),
            groups=groups,
            scan_duration_seconds=duration,
        )

        content = rpt.to_json() if output_format == "json" else rpt.to_text()
        if output:
            with open(output, "w") as f:
                f.write(content)
            click.echo(f"Report written to {output}")
        else:
            click.echo(content)


@duplicates_group.command("resolve")
@click.option("--action", type=click.Choice(["merge", "hide", "delete"]), required=True,
              help="Resolution action")
@click.option("--group-id", type=int, default=None, help="Specific group to resolve")
@click.option("--all", "resolve_all", is_flag=True, help="Resolve all groups")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.pass_context
def resolve(ctx, action, group_id, resolve_all, dry_run) -> None:
    """Resolve detected duplicates."""
    db_path = ctx.obj.get("db_path")
    output_format = ctx.obj.get("format", "text")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    with GameDatabase(db_path) as db:
        detector = DuplicateDetector(db)
        groups = detector.detect()
        history = ResolutionHistory(db)

        if group_id is not None:
            groups = [g for g in groups if g.group_id == group_id]

        if not groups:
            click.echo("No duplicate groups to resolve.")
            return

        if not resolve_all and group_id is None:
            click.echo("Error: specify --group-id or --all", err=True)
            sys.exit(1)

        results = []
        for group in groups:
            if dry_run:
                results.append({
                    "group_id": group.group_id,
                    "action": action,
                    "master": str(group.master_game_id),
                    "affected": [str(m) for m in group.member_game_ids],
                })
                continue

            if action == "hide":
                for mid in group.member_game_ids:
                    game = db.get_game(mid)
                    if game:
                        game.hidden = True
                        db.update_game(game)
                history.record("hide", group.master_game_id, group.member_game_ids)

            elif action == "delete":
                for mid in group.member_game_ids:
                    db.delete_game(mid)
                history.record("delete", group.master_game_id, group.member_game_ids)

            elif action == "merge":
                master = db.get_game(group.master_game_id)
                if not master:
                    continue
                for mid in group.member_game_ids:
                    dup = db.get_game(mid)
                    if not dup:
                        continue
                    # Merge metadata from duplicate into master
                    _merge_into_master(master, dup)
                    db.delete_game(mid)
                db.update_game(master)
                history.record("merge", group.master_game_id, group.member_game_ids)

            results.append({
                "group_id": group.group_id,
                "action": action,
                "master": str(group.master_game_id),
                "affected": len(group.member_game_ids),
            })

        if output_format == "json":
            click.echo(json.dumps(results, indent=2))
        else:
            for r in results:
                prefix = "[DRY RUN] " if dry_run else ""
                click.echo(f"{prefix}Group #{r['group_id']}: {r['action']} "
                          f"(master: {r['master']})")


@duplicates_group.command("override")
@click.argument("game_id")
@click.option("--set-master", is_flag=True, help="Set as master of its group")
@click.option("--not-duplicate", is_flag=True, help="Mark as not a duplicate")
@click.pass_context
def override(ctx, game_id, set_master, not_duplicate) -> None:
    """Manually override duplicate detection result."""
    db_path = ctx.obj.get("db_path")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    with GameDatabase(db_path) as db:
        history = ResolutionHistory(db)
        gid = uuid.UUID(game_id)

        if not_duplicate:
            history.record("manual_override", gid, [], {"action": "not_duplicate"})
            click.echo(f"Marked {game_id} as not a duplicate.")
        elif set_master:
            history.record("set_master", gid, [], {"action": "set_master"})
            click.echo(f"Set {game_id} as master.")


@duplicates_group.command("history")
@click.option("--limit", type=int, default=20, help="Number of records to show")
@click.pass_context
def history(ctx, limit) -> None:
    """Show duplicate resolution history."""
    db_path = ctx.obj.get("db_path")
    output_format = ctx.obj.get("format", "text")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    with GameDatabase(db_path) as db:
        hist = ResolutionHistory(db)
        records = hist.get_history(limit=limit)

        if output_format == "json":
            click.echo(json.dumps([
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat(),
                    "action": r.action,
                    "master_game_id": str(r.master_game_id),
                    "duplicate_game_ids": [str(d) for d in r.duplicate_game_ids],
                }
                for r in records
            ], indent=2))
        else:
            if not records:
                click.echo("No resolution history.")
                return
            for r in records:
                click.echo(f"#{r.id} [{r.timestamp:%Y-%m-%d %H:%M}] {r.action} "
                          f"master={r.master_game_id}")


@duplicates_group.command("undo")
@click.pass_context
def undo(ctx) -> None:
    """Undo the last resolution action."""
    db_path = ctx.obj.get("db_path")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    with GameDatabase(db_path) as db:
        hist = ResolutionHistory(db)
        record = hist.undo_last()
        if record:
            click.echo(f"Undone: #{record.id} {record.action}")
        else:
            click.echo("Nothing to undo.")


def _merge_into_master(master: object, duplicate: object) -> None:
    """Merge non-empty fields from duplicate into master."""
    from ..models.game import Game
    m: Game = master  # type: ignore[assignment]
    d: Game = duplicate  # type: ignore[assignment]
    # Fill in missing data from duplicate
    if not m.description and d.description:
        m.description = d.description
    if not m.cover_image and d.cover_image:
        m.cover_image = d.cover_image
    if not m.background_image and d.background_image:
        m.background_image = d.background_image
    if not m.icon and d.icon:
        m.icon = d.icon
    if m.critic_score is None and d.critic_score is not None:
        m.critic_score = d.critic_score
    if m.community_score is None and d.community_score is not None:
        m.community_score = d.community_score
    if not m.developer_ids and d.developer_ids:
        m.developer_ids = d.developer_ids
    if not m.publisher_ids and d.publisher_ids:
        m.publisher_ids = d.publisher_ids
    if not m.genre_ids and d.genre_ids:
        m.genre_ids = d.genre_ids
    if not m.release_date and d.release_date:
        m.release_date = d.release_date
    # Accumulate playtime
    m.playtime += d.playtime
    m.play_count += d.play_count
