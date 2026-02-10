"""Main CLI entry point for the game library manager."""

import click

from .achievements.cli import achievements_cli
from .backup.cli import backup_cli


@click.group()
@click.version_option(version="1.0.0", prog_name="gamelibrary")
def main():
    """Game Library Manager - Achievement tracking and backup/restore."""
    pass


main.add_command(achievements_cli)
main.add_command(backup_cli)


if __name__ == "__main__":
    main()
