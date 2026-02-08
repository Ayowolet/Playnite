"""Playnite CLI entry point."""
import pathlib

import click

from .library_commands import library
from .controller_commands import controller


@click.group()
@click.option(
    "--db",
    default="playnite.db",
    envvar="PLAYNITE_DB",
    show_default=True,
    help="Path to the SQLite database file.",
)
@click.pass_context
def cli(ctx: click.Context, db: str) -> None:
    """Playnite — Python game library manager."""
    ctx.ensure_object(dict)
    ctx.obj["db_url"] = f"sqlite:///{pathlib.Path(db).resolve()}"


cli.add_command(library)
cli.add_command(controller)
