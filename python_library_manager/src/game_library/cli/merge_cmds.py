"""
CLI commands for library merging.

Sub-commands:
  merge preview        – Dry-run: show what would change.
  merge execute        – Actually perform the merge.
  merge rollback       – Restore library from the last backup.
  merge export-config  – Save the current merge config to a file.
  merge list-backups   – List available backups.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

from ..storage.json_store import JsonStore
from ..merger.merger import LibraryMerger, MergeConfig, MergePreview
from ..merger.strategies import MergeStrategy
from ..merger.backup import BackupManager

console = Console()
_DEFAULT_BACKUP_DIR = "./backups"


def _load_lib(path: str, playnite: bool, name: str, priority: int):
    """Load a library from *path*, optionally in Playnite directory layout."""
    return JsonStore(path, playnite=playnite).load(source_name=name, source_priority=priority)


def _save_lib(lib, path: str, playnite: bool):
    """Persist *lib* to *path*, optionally in Playnite directory layout."""
    JsonStore(path, playnite=playnite).save(lib)


@click.group("merge")
def merge_group():
    """Smart library merging with conflict resolution."""


# ── preview ───────────────────────────────────────────────────────────────────

@merge_group.command("preview")
@click.argument("master_path", type=click.Path(exists=True))
@click.argument("source_path", type=click.Path(exists=True))
@click.option("--strategy", "-s",
              type=click.Choice([s.value for s in MergeStrategy], case_sensitive=False),
              default=MergeStrategy.MERGE_PREFER_MASTER.value, show_default=True)
@click.option("--threshold", "-t", default=0.85, show_default=True)
@click.option("--incremental-since", default=None, metavar="ISO_DATE",
              help="Only merge source games modified after this date (ISO-8601).")
@click.option("--exclude-hidden/--include-hidden", default=False)
@click.option("--exclude-platform", multiple=True)
@click.option("--playnite", is_flag=True, default=False)
@click.option("--master-name", default="master", show_default=True)
@click.option("--source-name", default="source", show_default=True)
@click.option("--json-output", is_flag=True, default=False)
@click.option("--save-preview", type=click.Path(), default=None)
@click.option("--config-file", type=click.Path(exists=True), default=None,
              help="Load merge config from a previously exported JSON file.")
def preview_cmd(
    master_path, source_path, strategy, threshold, incremental_since,
    exclude_hidden, exclude_platform, playnite, master_name, source_name,
    json_output, save_preview, config_file,
):
    """Show what a merge of SOURCE_PATH into MASTER_PATH would change."""
    if config_file:
        merger = LibraryMerger.load_config(config_file)
    else:
        cfg = MergeConfig(
            strategy=MergeStrategy(strategy),
            match_threshold=threshold,
            incremental_since=incremental_since,
            exclude_hidden=exclude_hidden,
            exclude_platforms=list(exclude_platform),
        )
        merger = LibraryMerger(cfg)

    master = _load_lib(master_path, playnite, master_name, 0)
    source = _load_lib(source_path, playnite, source_name, 1)

    with console.status("Computing merge preview…"):
        preview = merger.preview(master, source)

    if json_output:
        click.echo(json.dumps(preview.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_preview(preview)

    if save_preview:
        Path(save_preview).write_text(
            json.dumps(preview.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        console.print(f"\nPreview saved to [bold]{save_preview}[/bold]")


# ── execute ───────────────────────────────────────────────────────────────────

@merge_group.command("execute")
@click.argument("master_path", type=click.Path(exists=True))
@click.argument("source_path", type=click.Path(exists=True))
@click.option("--strategy", "-s",
              type=click.Choice([s.value for s in MergeStrategy], case_sensitive=False),
              default=MergeStrategy.MERGE_PREFER_MASTER.value, show_default=True)
@click.option("--threshold", "-t", default=0.85, show_default=True)
@click.option("--incremental-since", default=None, metavar="ISO_DATE")
@click.option("--exclude-hidden/--include-hidden", default=False)
@click.option("--exclude-platform", multiple=True)
@click.option("--include-game-id", multiple=True, metavar="GAME_ID",
              help="Only merge these specific game IDs from source.")
@click.option("--backup-dir", default=_DEFAULT_BACKUP_DIR, show_default=True)
@click.option("--output-path", "-o", type=click.Path(), default=None,
              help="Save merged library here (default: overwrites master).")
@click.option("--playnite", is_flag=True, default=False)
@click.option("--master-name", default="master", show_default=True)
@click.option("--source-name", default="source", show_default=True)
@click.option("--json-output", is_flag=True, default=False)
@click.option("--save-result", type=click.Path(), default=None)
@click.option("--config-file", type=click.Path(exists=True), default=None)
@click.option("--field-override", multiple=True, metavar="FIELD=STRATEGY",
              help="Per-field strategy override, e.g. Description=keep_source")
def execute_cmd(
    master_path, source_path, strategy, threshold, incremental_since,
    exclude_hidden, exclude_platform, include_game_id, backup_dir,
    output_path, playnite, master_name, source_name, json_output,
    save_result, config_file, field_override,
):
    """Merge SOURCE_PATH into MASTER_PATH (creates backup first)."""
    if config_file:
        merger = LibraryMerger.load_config(config_file, backup_dir=backup_dir)
    else:
        field_overrides = {}
        for fo in field_override:
            parts = fo.split("=", 1)
            if len(parts) == 2:
                field_overrides[parts[0]] = parts[1]
        cfg = MergeConfig(
            strategy=MergeStrategy(strategy),
            match_threshold=threshold,
            incremental_since=incremental_since,
            exclude_hidden=exclude_hidden,
            exclude_platforms=list(exclude_platform),
            include_game_ids=list(include_game_id),
            backup_dir=backup_dir,
            field_strategy_overrides=field_overrides,
        )
        merger = LibraryMerger(cfg, backup_dir=backup_dir)

    master = _load_lib(master_path, playnite, master_name, 0)
    source = _load_lib(source_path, playnite, source_name, 1)

    with console.status("Executing merge…"):
        result = merger.execute(master, source)

    if result.success:
        out = output_path or master_path
        _save_lib(master, out, playnite)
        result_dict = result.to_dict()
        result_dict["output_path"] = str(out)
        if json_output:
            click.echo(json.dumps(result_dict, indent=2, ensure_ascii=False))
        else:
            _print_result(result, str(out))
    else:
        console.print(f"[red bold]Merge failed![/red bold]")
        for err in result.errors:
            console.print(f"  [red]• {err}[/red]")
        if not json_output:
            console.print(f"\n[yellow]Backup available: {result.backup_record.id if result.backup_record else 'none'}[/yellow]")
        sys.exit(1)

    if save_result:
        Path(save_result).write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )


# ── rollback ──────────────────────────────────────────────────────────────────

@merge_group.command("rollback")
@click.argument("master_path", type=click.Path(exists=True))
@click.argument("result_path", type=click.Path(exists=True))
@click.option("--backup-dir", default=_DEFAULT_BACKUP_DIR, show_default=True)
@click.option("--playnite", is_flag=True, default=False)
@click.option("--master-name", default="master", show_default=True)
@click.option("--json-output", is_flag=True, default=False)
def rollback_cmd(master_path, result_path, backup_dir, playnite, master_name, json_output):
    """Rollback a merge using the backup recorded in RESULT_PATH."""
    result_data = json.loads(Path(result_path).read_text(encoding="utf-8"))
    backup_id = result_data.get("backup_id")
    if not backup_id:
        console.print("[red]No backup_id found in result file.[/red]")
        sys.exit(1)

    bm = BackupManager(backup_dir)
    backup_data = bm.restore(backup_id)

    # Write backup data back to master path
    Path(master_path).write_text(
        json.dumps(backup_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {"rolled_back": True, "backup_id": backup_id, "master_path": master_path}
    if json_output:
        click.echo(json.dumps(summary, indent=2))
    else:
        console.print(f"[green]Rolled back to backup [bold]{backup_id}[/bold][/green]")
        console.print(f"Library restored to [bold]{master_path}[/bold]")


# ── export-config ─────────────────────────────────────────────────────────────

@merge_group.command("export-config")
@click.argument("output_path", type=click.Path())
@click.option("--strategy", "-s",
              type=click.Choice([s.value for s in MergeStrategy], case_sensitive=False),
              default=MergeStrategy.MERGE_PREFER_MASTER.value, show_default=True)
@click.option("--threshold", "-t", default=0.85, show_default=True)
@click.option("--backup-dir", default=_DEFAULT_BACKUP_DIR, show_default=True)
@click.option("--field-override", multiple=True, metavar="FIELD=STRATEGY")
def export_config_cmd(output_path, strategy, threshold, backup_dir, field_override):
    """Export a merge configuration to OUTPUT_PATH for reuse on another system."""
    field_overrides = {}
    for fo in field_override:
        parts = fo.split("=", 1)
        if len(parts) == 2:
            field_overrides[parts[0]] = parts[1]
    cfg = MergeConfig(
        strategy=MergeStrategy(strategy),
        match_threshold=threshold,
        backup_dir=backup_dir,
        field_strategy_overrides=field_overrides,
    )
    merger = LibraryMerger(cfg)
    merger.export_config(output_path)
    console.print(f"Config exported to [bold]{output_path}[/bold]")


# ── list-backups ──────────────────────────────────────────────────────────────

@merge_group.command("list-backups")
@click.option("--backup-dir", default=_DEFAULT_BACKUP_DIR, show_default=True)
@click.option("--json-output", is_flag=True, default=False)
def list_backups_cmd(backup_dir, json_output):
    """List available library backups."""
    bm = BackupManager(backup_dir)
    backups = bm.list_backups()
    if json_output:
        click.echo(json.dumps([b.to_dict() for b in backups], indent=2, ensure_ascii=False))
    else:
        if not backups:
            console.print("[yellow]No backups found.[/yellow]")
            return
        table = Table("ID", "Created", "Description", "Games", box=box.SIMPLE)
        for b in backups:
            table.add_row(b.id[:8] + "…", b.created_at[:19], b.description, str(b.game_count))
        console.print(table)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_preview(preview: MergePreview) -> None:
    """Render a human-readable merge preview to the console."""
    cfg = preview.config
    console.print()
    console.print("[bold]Merge Preview[/bold]")
    console.print(f"  Strategy        : {cfg.strategy.value}")
    console.print(f"  Match threshold : {cfg.match_threshold:.0%}")
    console.print(f"  Source games    : {len(preview.plans)}")
    console.print(f"  New games       : [green]{len(preview.new_games)}[/green]")
    console.print(f"  Updated games   : [yellow]{len(preview.updated_games)}[/yellow]")
    console.print(f"  With conflicts  : [red]{len(preview.games_with_conflicts)}[/red]")

    if preview.new_games:
        console.print("\n[bold]New games to be added:[/bold]")
        for plan in preview.new_games[:20]:
            console.print(f"  + {plan.source_game.Name}")
        if len(preview.new_games) > 20:
            console.print(f"  … and {len(preview.new_games) - 20} more")

    if preview.games_with_conflicts:
        console.print("\n[bold]Games with conflicts:[/bold]")
        table = Table("Game", "Conflicts", box=box.SIMPLE)
        for plan in preview.games_with_conflicts[:30]:
            conflict_fields = ", ".join(c.field for c in plan.conflicts[:5])
            if len(plan.conflicts) > 5:
                conflict_fields += f" (+{len(plan.conflicts) - 5} more)"
            table.add_row(plan.source_game.Name, conflict_fields)
        console.print(table)


def _print_result(result, output_path: str) -> None:
    """Render a human-readable merge result summary to the console."""
    console.print()
    console.print("[bold green]Merge completed successfully.[/bold green]")
    console.print(f"  Games added     : [green]{result.games_added}[/green]")
    console.print(f"  Games updated   : [yellow]{result.games_updated}[/yellow]")
    console.print(f"  Conflicts fixed : {result.conflicts_resolved}")
    console.print(f"  Output          : {output_path}")
    if result.backup_record:
        console.print(f"  Backup ID       : {result.backup_record.id[:8]}…")
    if result.errors:
        console.print(f"\n[yellow]Warnings ({len(result.errors)}):[/yellow]")
        for err in result.errors[:10]:
            console.print(f"  [yellow]• {err}[/yellow]")
