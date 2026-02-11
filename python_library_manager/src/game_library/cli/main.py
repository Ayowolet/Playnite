"""
Main CLI entry-point for the game library manager.

Usage examples
--------------
  # Detect duplicates
  gamelibrary duplicates detect ~/playnite-db --playnite --threshold 0.80

  # Resolve them (hide non-master copies)
  gamelibrary duplicates resolve ~/playnite-db report.json --action hide

  # Preview a library merge
  gamelibrary merge preview ~/master-db ~/source-db --playnite

  # Execute a merge
  gamelibrary merge execute ~/master-db ~/source-db -s merge_prefer_master

  # Roll back a merge
  gamelibrary merge rollback ~/master-db merge_result.json

  # Export config for reuse
  gamelibrary merge export-config my_merge_config.json -s keep_master
"""
from __future__ import annotations

import click
from rich.console import Console

from .duplicate_cmds import duplicates_group
from .merge_cmds import merge_group

console = Console()

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"], "max_content_width": 120}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(package_name="game-library-manager")
def cli():
    """
    \b
    Game Library Manager
    ====================
    Python-based game library management with intelligent duplicate detection
    and smart library merging.

    All commands support --json-output for scripted / automated use.
    """


cli.add_command(duplicates_group)
cli.add_command(merge_group)


# ── Convenience top-level aliases ─────────────────────────────────────────────

@cli.command("stats")
@click.argument("library_path", type=click.Path(exists=True))
@click.option("--playnite", is_flag=True, default=False,
              help="Library path is a Playnite database directory.")
@click.option("--source-name", default="default", show_default=True)
@click.option("--json-output", is_flag=True, default=False)
def stats_cmd(library_path, playnite, source_name, json_output):
    """Show statistics for a library."""
    import json
    from ..storage.json_store import JsonStore

    lib = JsonStore(library_path, playnite=playnite).load(source_name=source_name)
    s = lib.stats()
    if json_output:
        click.echo(json.dumps(s, indent=2))
    else:
        console.print(f"\n[bold]Library Stats[/bold]  ({library_path})")
        for k, v in s.items():
            console.print(f"  {k:<28}: {v}")


if __name__ == "__main__":
    cli()
