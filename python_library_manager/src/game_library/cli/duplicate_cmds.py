"""
CLI commands for duplicate game detection and resolution.

Sub-commands:
  duplicates detect   – Scan a library for duplicate games.
  duplicates resolve  – Apply a resolution action to detected duplicates.
  duplicates report   – Print a formatted duplicate report.
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
from ..duplicate.detector import DuplicateDetector, DetectorConfig, DuplicateGroup, DuplicateReport
from ..duplicate.resolver import DuplicateResolver, ResolutionAction

console = Console()


def _load_library(library_path: str, playnite: bool, source_name: str, priority: int):
    """Load a library from *library_path*, optionally in Playnite directory layout."""
    store = JsonStore(library_path, playnite=playnite)
    return store.load(source_name=source_name, source_priority=priority)


@click.group("duplicates")
def duplicates_group():
    """Intelligent duplicate game detection and resolution."""


@duplicates_group.command("detect")
@click.argument("library_path", type=click.Path(exists=True))
@click.option("--threshold", "-t", default=0.85, show_default=True,
              help="Minimum similarity score to flag as duplicate (0.60-1.00).")
@click.option("--source-priority", "-p", multiple=True, metavar="SOURCE",
              help="Source names in priority order (repeat for multiple, e.g. -p Steam -p GOG).")
@click.option("--include-platform", multiple=True, metavar="PLATFORM",
              help="Only scan games on these platforms.")
@click.option("--exclude-platform", multiple=True, metavar="PLATFORM",
              help="Skip games on these platforms.")
@click.option("--include-source", multiple=True, metavar="SOURCE",
              help="Only scan games from these sources.")
@click.option("--exclude-source", multiple=True, metavar="SOURCE",
              help="Skip games from these sources.")
@click.option("--exclude-hidden/--include-hidden", default=False, show_default=True,
              help="Skip hidden games.")
@click.option("--similarity-mode", is_flag=True, default=False,
              help="Find near-duplicates with non-matching names.")
@click.option("--similarity-threshold", default=0.70, show_default=True,
              help="Score threshold used in similarity mode.")
@click.option("--playnite", is_flag=True, default=False,
              help="Library path is a Playnite database directory.")
@click.option("--source-name", default="default", show_default=True,
              help="Human-readable name for this library source.")
@click.option("--json-output", is_flag=True, default=False,
              help="Output raw JSON instead of formatted text.")
@click.option("--save-report", type=click.Path(), default=None,
              help="Write the report to this file (JSON).")
def detect_cmd(
    library_path, threshold, source_priority, include_platform, exclude_platform,
    include_source, exclude_source, exclude_hidden, similarity_mode,
    similarity_threshold, playnite, source_name, json_output, save_report,
):
    """Scan LIBRARY_PATH for duplicate games."""
    lib = _load_library(library_path, playnite, source_name, 0)

    cfg = DetectorConfig(
        threshold=threshold,
        source_priority=list(source_priority),
        include_platforms=list(include_platform),
        exclude_platforms=list(exclude_platform),
        include_sources=list(include_source),
        exclude_sources=list(exclude_source),
        exclude_hidden=exclude_hidden,
        similarity_mode=similarity_mode,
        similarity_threshold=similarity_threshold,
    )

    detector = DuplicateDetector(cfg)

    with console.status("Scanning for duplicates…"):
        report = detector.detect(lib)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report)

    if save_report:
        Path(save_report).write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if not json_output:
            console.print(f"\nReport saved to [bold]{save_report}[/bold]")

    sys.exit(0 if report.group_count == 0 else 1)


@duplicates_group.command("resolve")
@click.argument("library_path", type=click.Path(exists=True))
@click.argument("report_path", type=click.Path(exists=True))
@click.option("--action", "-a",
              type=click.Choice(["hide", "delete", "merge", "ignore"], case_sensitive=False),
              default="hide", show_default=True,
              help="Resolution action to apply to all duplicate groups.")
@click.option("--group-ids", "-g", multiple=True, metavar="GROUP_ID",
              help="Limit action to these group IDs (default: all groups).")
@click.option("--set-master", metavar="GAME_ID",
              help="Override the master game for all groups (use with --group-ids for single group).")
@click.option("--save-history", type=click.Path(), default=None,
              help="Write resolution history to this file.")
@click.option("--playnite", is_flag=True, default=False)
@click.option("--source-name", default="default")
@click.option("--output-path", "-o", type=click.Path(), default=None,
              help="Save the updated library here (default: overwrites input).")
@click.option("--json-output", is_flag=True, default=False)
def resolve_cmd(
    library_path, report_path, action, group_ids, set_master, save_history,
    playnite, source_name, output_path, json_output,
):
    """Apply a resolution action to duplicates identified in REPORT_PATH."""
    lib = _load_library(library_path, playnite, source_name, 0)
    report_data = json.loads(Path(report_path).read_text(encoding="utf-8"))

    # Rebuild DuplicateGroups from the report JSON (lightweight – no re-scan)
    groups = _groups_from_report(report_data, lib)

    if group_ids:
        groups = [g for g in groups if g.id in group_ids]

    resolver = DuplicateResolver(lib)

    if set_master:
        if len(groups) == 1:
            groups[0] = resolver.set_master(groups[0], set_master)
        else:
            console.print("[red]--set-master requires exactly one group (use --group-ids)[/red]")
            sys.exit(2)

    action_map = {
        "hide": ResolutionAction.HIDE_DUPLICATES,
        "delete": ResolutionAction.DELETE_DUPLICATES,
        "merge": ResolutionAction.MERGE_INTO_MASTER,
        "ignore": ResolutionAction.IGNORE_GROUP,
    }
    records = resolver.bulk_resolve(groups, action_map[action])

    # Save updated library
    out_path = output_path or library_path
    store = JsonStore(out_path, playnite=playnite)
    store.save(lib)

    if save_history:
        resolver.save_history(save_history)

    summary = {
        "action": action,
        "groups_processed": len(groups),
        "records": [r.to_dict() for r in records],
        "output_path": str(out_path),
    }
    if json_output:
        click.echo(json.dumps(summary, indent=2))
    else:
        console.print(f"\n[green]Resolved {len(groups)} duplicate group(s) with action '{action}'.[/green]")
        console.print(f"Library saved to [bold]{out_path}[/bold]")


@duplicates_group.command("report")
@click.argument("report_path", type=click.Path(exists=True))
@click.option("--json-output", is_flag=True, default=False)
def report_cmd(report_path, json_output):
    """Display a previously generated duplicate report."""
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if json_output:
        click.echo(json.dumps(data, indent=2))
    else:
        report = _report_from_dict(data)
        _print_report(report)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_report(report: DuplicateReport) -> None:
    console.print()
    console.print(f"[bold]Duplicate Detection Report[/bold]  "
                  f"({report.generated_at[:19]})")
    console.print(f"  Games scanned : {report.games_scanned} / {report.total_games}")
    console.print(f"  Groups found  : [yellow]{report.group_count}[/yellow]")
    console.print(f"  Duplicates    : [yellow]{report.duplicate_count}[/yellow]")
    console.print()

    for i, group in enumerate(report.groups, 1):
        table = Table(
            title=f"Group {i}: {group.master.Name}",
            box=box.SIMPLE_HEAVY,
            show_header=True,
        )
        table.add_column("Role", style="bold", width=8)
        table.add_column("Name")
        table.add_column("Platform")
        table.add_column("Source")
        table.add_column("Installed", justify="center")
        table.add_column("Hidden", justify="center")
        table.add_column("Confidence", justify="right")

        table.add_row(
            "[green]MASTER[/green]",
            group.master.Name,
            ", ".join(group.master._platform_names) or "—",
            group.master._source_name or "—",
            "✓" if group.master.IsInstalled else "",
            "✓" if group.master.Hidden else "",
            "100%",
        )
        for dup in group.duplicates:
            conf = round(group.scores.get(dup.Id, 0) * 100)
            table.add_row(
                "[red]DUP[/red]",
                dup.Name,
                ", ".join(dup._platform_names) or "—",
                dup._source_name or "—",
                "✓" if dup.IsInstalled else "",
                "✓" if dup.Hidden else "",
                f"{conf}%",
            )
        console.print(table)


def _groups_from_report(data: dict, lib) -> list[DuplicateGroup]:
    """Reconstruct :class:`DuplicateGroup` objects from a report dict."""
    from ..duplicate.detector import DuplicateGroup as DG
    groups: list[DG] = []
    for gd in data.get("groups", []):
        master_id = gd["master"]["id"]
        master_game = lib.get_game(master_id)
        if master_game is None:
            continue
        dups = []
        scores: dict[str, float] = {}
        for dd in gd.get("duplicates", []):
            dup_game = lib.get_game(dd["id"])
            if dup_game:
                dups.append(dup_game)
                scores[dd["id"]] = dd.get("confidence_pct", 0) / 100.0
        groups.append(DG(id=master_id, master=master_game, duplicates=dups, scores=scores, match_results=[]))
    return groups


def _report_from_dict(data: dict) -> DuplicateReport:
    """Reconstruct a :class:`DuplicateReport` from a previously saved JSON dict."""
    from ..models.game import Game as G
    from ..duplicate.detector import DuplicateGroup as DG, DuplicateReport as DR
    groups: list[DG] = []
    for gd in data.get("groups", []):
        master = G.from_dict({
            "Id": gd["master"]["id"],
            "Name": gd["master"]["name"],
            "IsInstalled": gd["master"].get("installed", False),
            "Hidden": gd["master"].get("hidden", False),
        })
        master._source_name = gd["master"].get("source", "")
        master._platform_names = [gd["master"].get("platform", "")] if gd["master"].get("platform") else []

        dups = []
        scores: dict[str, float] = {}
        for dd in gd.get("duplicates", []):
            dup = G.from_dict({
                "Id": dd["id"],
                "Name": dd["name"],
                "IsInstalled": dd.get("installed", False),
                "Hidden": dd.get("hidden", False),
            })
            dup._source_name = dd.get("source", "")
            dup._platform_names = [dd.get("platform", "")] if dd.get("platform") else []
            dups.append(dup)
            scores[dd["id"]] = dd.get("confidence_pct", 0) / 100.0

        groups.append(DG(id=gd["master"]["id"], master=master, duplicates=dups, scores=scores, match_results=[]))

    return DR(
        generated_at=data.get("generated_at", ""),
        total_games=data.get("total_games", 0),
        games_scanned=data.get("games_scanned", 0),
        groups=groups,
        config=data.get("config", {}),
    )
