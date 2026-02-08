"""Main CLI entry point."""

import click

from ..database import init_database
from .library_commands import library
from .controller_commands import controller
from .navigation_commands import navigation
from .view_commands import view


@click.group()
@click.option('--db-path', type=click.Path(), default='playnite.db',
              help='Path to database file')
@click.option('--json-output', is_flag=True, help='Output results as JSON')
@click.pass_context
def cli(ctx, db_path, json_output):
    """Playnite Python - Game Library Manager CLI."""
    ctx.ensure_object(dict)
    ctx.obj['db_path'] = db_path
    ctx.obj['json_output'] = json_output

    # Initialize database
    try:
        engine = init_database(db_path)
        ctx.obj['engine'] = engine
    except Exception as e:
        click.echo(f"Error initializing database: {e}", err=True)
        ctx.exit(1)


# Add command groups
cli.add_command(library)
cli.add_command(controller)
cli.add_command(navigation)
cli.add_command(view)


@cli.command()
def version():
    """Show version information."""
    from .. import __version__
    click.echo(f"Playnite Python v{__version__}")


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize a new library database."""
    db_path = ctx.obj['db_path']
    click.echo(f"Initializing database at {db_path}...")
    engine = init_database(db_path)
    engine.create_tables()
    click.echo("Database initialized successfully!")


if __name__ == '__main__':
    cli()
