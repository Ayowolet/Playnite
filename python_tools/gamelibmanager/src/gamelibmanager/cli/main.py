"""CLI entry point for the game library manager."""

from __future__ import annotations

import click

from .duplicates_cmd import duplicates_group
from .merge_cmd import merge_group


@click.group()
@click.option("--db", type=click.Path(), default=None,
              help="Path to game library database or Playnite library directory")
@click.option("--format", "output_format",
              type=click.Choice(["text", "json", "table"]),
              default="text", help="Output format")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.version_option(package_name="gamelibmanager")
@click.pass_context
def cli(ctx: click.Context, db: str, output_format: str, verbose: bool) -> None:
    """Game Library Manager - Duplicate detection and library merging."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db
    ctx.obj["format"] = output_format
    ctx.obj["verbose"] = verbose


cli.add_command(duplicates_group)
cli.add_command(merge_group)


if __name__ == "__main__":
    cli()
