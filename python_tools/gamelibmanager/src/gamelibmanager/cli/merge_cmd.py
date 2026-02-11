"""CLI commands for library merging."""

from __future__ import annotations

import json
import sys
from pathlib import Path
import click

from ..db.concurrency import DatabaseLockedError
from ..db.database import GameDatabase
from ..db.playnite_io import PlayniteLibraryReader
from ..merger.backup import MergeBackup
from ..merger.config import MergeConfig
from ..merger.engine import LibraryMerger
from ..merger.strategy import MergeStrategyType


@click.group("merge")
def merge_group() -> None:
    """Library merge commands."""


def _open_library(path: str) -> GameDatabase:
    """Open a library path — either a SQLite DB or a Playnite directory."""
    p = Path(path)
    if p.is_file() and p.suffix in (".db", ".sqlite"):
        db = GameDatabase(path)
        db.open()
        return db

    # Assume Playnite directory — import into a temp SQLite DB
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = GameDatabase(tmp.name)
    db.open()
    reader = PlayniteLibraryReader(path)
    reader.import_to_database(db)
    return db


@merge_group.command("preview")
@click.option("--source", "source_path", required=True, type=click.Path(exists=True),
              help="Source Playnite library path")
@click.option("--target", "target_path", required=True, type=click.Path(exists=True),
              help="Target Playnite library path")
@click.option("--strategy", type=click.Choice([s.value for s in MergeStrategyType]),
              default="merge_all", help="Merge strategy")
@click.option("--incremental", is_flag=True, help="Only merge new/changed games")
@click.pass_context
def preview(ctx, source_path, target_path, strategy, incremental) -> None:
    """Preview merge without executing."""
    output_format = ctx.obj.get("format", "text")

    config = MergeConfig(
        strategy_type=MergeStrategyType(strategy),
        source_library_path=source_path,
        target_library_path=target_path,
        incremental=incremental,
    )

    source_db = _open_library(source_path)
    target_db = _open_library(target_path)
    try:
        merger = LibraryMerger(source_db, target_db, config)
        result = merger.preview()

        if output_format == "json":
            click.echo(result.to_json())
        else:
            click.echo(result.to_text())
    finally:
        source_db.close()
        target_db.close()


@merge_group.command("execute")
@click.option("--source", "source_path", required=True, type=click.Path(exists=True))
@click.option("--target", "target_path", required=True, type=click.Path(exists=True))
@click.option("--strategy", type=click.Choice([s.value for s in MergeStrategyType]),
              default="merge_all")
@click.option("--backup-dir", type=click.Path(), default=None, help="Backup directory")
@click.option("--no-backup", is_flag=True, help="Skip pre-merge backup")
@click.option("--include-media/--no-media", default=True, help="Include media files")
@click.option("--incremental", is_flag=True)
@click.option("--games", multiple=True, help="Specific game IDs to merge")
@click.option("--categories", multiple=True, help="Specific categories to merge")
@click.option("--config-file", type=click.Path(exists=True),
              help="Load merge configuration from file")
@click.option("--dry-run", is_flag=True, help="Preview only")
@click.pass_context
def execute(ctx, source_path, target_path, strategy, backup_dir, no_backup,
            include_media, incremental, games, categories, config_file, dry_run) -> None:
    """Execute library merge."""
    output_format = ctx.obj.get("format", "text")

    if config_file:
        with open(config_file, "r") as f:
            config = MergeConfig.from_json(f.read())
        # Override paths
        config.source_library_path = source_path
        config.target_library_path = target_path
    else:
        import uuid
        config = MergeConfig(
            strategy_type=MergeStrategyType(strategy),
            backup_dir=backup_dir or "",
            include_media=include_media,
            incremental=incremental,
            source_library_path=source_path,
            target_library_path=target_path,
        )
        if games:
            config.selective_game_ids = {uuid.UUID(g) for g in games}
        if categories:
            config.selective_categories = set(categories)

    if no_backup:
        config.backup_dir = ""
    elif not config.backup_dir:
        config.backup_dir = str(Path(target_path) / "_backups")

    source_db = _open_library(source_path)
    target_db = _open_library(target_path)
    try:
        # Pre-flight: verify we can write to the target database.
        try:
            target_db.check_write_access()
        except DatabaseLockedError:
            click.echo(
                "Error: Target database is locked by another process.",
                err=True,
            )
            click.echo(
                "Tip: Close Playnite (or any other application using the "
                "library) and retry.",
                err=True,
            )
            sys.exit(1)

        merger = LibraryMerger(source_db, target_db, config)

        if dry_run:
            result = merger.preview()
            if output_format == "json":
                click.echo(result.to_json())
            else:
                click.echo(result.to_text())
            return

        report = merger.execute()

        if output_format == "json":
            click.echo(report.to_json())
        else:
            click.echo(report.to_text())

        if report.errors:
            sys.exit(1)
    finally:
        source_db.close()
        target_db.close()


@merge_group.command("validate")
@click.argument("library_path", type=click.Path(exists=True))
@click.pass_context
def validate(ctx, library_path) -> None:
    """Validate library integrity."""
    output_format = ctx.obj.get("format", "text")

    db = _open_library(library_path)
    try:
        merger = LibraryMerger(db, db, MergeConfig())
        issues = merger.validate_library(db)

        if output_format == "json":
            click.echo(json.dumps({"valid": len(issues) == 0, "issues": issues}, indent=2))
        else:
            if issues:
                click.echo(f"Found {len(issues)} issues:")
                for issue in issues:
                    click.echo(f"  ! {issue}")
            else:
                click.echo("Library is valid.")
    finally:
        db.close()


@merge_group.command("rollback")
@click.option("--backup-file", required=True, type=click.Path(exists=True),
              help="Backup ZIP file")
@click.option("--target", "target_path", required=True, type=click.Path(exists=True),
              help="Target library to restore")
@click.pass_context
def rollback(ctx, backup_file, target_path) -> None:
    """Rollback a merge using a backup file."""
    backup = MergeBackup(target_path, Path(backup_file).parent)
    backup.restore_backup(backup_file)
    click.echo(f"Restored {target_path} from {backup_file}")


@merge_group.command("export-config")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output file path")
@click.option("--source", "source_path", default="", help="Source library path")
@click.option("--target", "target_path", default="", help="Target library path")
@click.option("--strategy", type=click.Choice([s.value for s in MergeStrategyType]),
              default="merge_all")
@click.pass_context
def export_config(ctx, output, source_path, target_path, strategy) -> None:
    """Export merge configuration to a file."""
    config = MergeConfig(
        strategy_type=MergeStrategyType(strategy),
        source_library_path=source_path,
        target_library_path=target_path,
    )
    with open(output, "w") as f:
        f.write(config.to_json())
    click.echo(f"Configuration exported to {output}")


@merge_group.command("report")
@click.option("--merge-id", type=int, default=None, help="Specific merge ID")
@click.option("--latest", is_flag=True, help="Show latest merge report")
@click.pass_context
def report(ctx, merge_id, latest) -> None:
    """View merge report."""
    db_path = ctx.obj.get("db_path")
    output_format = ctx.obj.get("format", "text")
    if not db_path:
        click.echo("Error: --db is required", err=True)
        sys.exit(1)

    with GameDatabase(db_path) as db:
        assert db.conn is not None
        if merge_id is not None:
            row = db.conn.execute(
                "SELECT * FROM merge_history WHERE id = ?", (merge_id,)
            ).fetchone()
        elif latest:
            row = db.conn.execute(
                "SELECT * FROM merge_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            rows = db.conn.execute(
                "SELECT * FROM merge_history ORDER BY id DESC LIMIT 10"
            ).fetchall()
            if output_format == "json":
                click.echo(json.dumps([dict(r) for r in rows], indent=2))
            else:
                for r in rows:
                    click.echo(
                        f"#{r['id']} [{r['timestamp']}] {r['source_library']} -> "
                        f"{r['target_library']} | +{r['games_added']} "
                        f"~{r['games_updated']} ={r['games_skipped']}"
                    )
            return

        if row is None:
            click.echo("No merge report found.")
            return

        if output_format == "json":
            click.echo(json.dumps(dict(row), indent=2))
        else:
            click.echo(f"Merge #{row['id']}")
            click.echo(f"  Timestamp: {row['timestamp']}")
            click.echo(f"  Source: {row['source_library']}")
            click.echo(f"  Target: {row['target_library']}")
            click.echo(f"  Strategy: {row['strategy']}")
            click.echo(f"  Added: {row['games_added']}")
            click.echo(f"  Updated: {row['games_updated']}")
            click.echo(f"  Skipped: {row['games_skipped']}")
            click.echo(f"  Conflicts: {row['conflicts_resolved']}")
            click.echo(f"  Backup: {row['backup_path']}")
