"""
Main CLI entry point for Playnite-Py.

This module provides the main CLI application using Click, with
subcommands for profile and configuration management.

Example:
    $ playnite --help
    $ playnite profile list
    $ playnite config create --game "My Game" --preset quality
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from playnite_py import __version__

# Initialize console for rich output
console = Console()
console_stderr = Console(stderr=True)

# Configure logging
def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False)],
    )


class Context:
    """
    CLI context object for sharing state between commands.

    Attributes:
        data_dir: Data directory path
        json_output: Whether to output JSON
        verbose: Verbose logging enabled
        profile_manager: Active ProfileManager instance
        config_manager: Active ConfigurationManager instance
    """

    def __init__(self) -> None:
        self.data_dir: Optional[Path] = None
        self.json_output: bool = False
        self.verbose: bool = False
        self._profile_manager = None
        self._config_manager = None

    @property
    def profile_manager(self):
        """Get or create ProfileManager."""
        if self._profile_manager is None:
            from playnite_py.profiles import ProfileManager
            self._profile_manager = ProfileManager(self.data_dir)
        return self._profile_manager

    def get_config_manager(self):
        """Get ConfigurationManager for current profile."""
        if self._config_manager is None:
            db = self.profile_manager.get_profile_database()
            if db is None:
                raise click.ClickException("No active profile. Use 'playnite profile switch' first.")
            from playnite_py.configurations import ConfigurationManager
            self._config_manager = ConfigurationManager(db)
        return self._config_manager

    def output(self, data: Any, message: Optional[str] = None) -> None:
        """Output data in JSON or human-readable format."""
        if self.json_output:
            click.echo(json.dumps(data, indent=2, default=str))
        elif message:
            console.print(message)
        else:
            console.print(data)

    def output_table(self, table: Table) -> None:
        """Output a table (skipped in JSON mode)."""
        if not self.json_output:
            console.print(table)

    def success(self, message: str) -> None:
        """Print success message."""
        if not self.json_output:
            console.print(f"[green]✓[/green] {message}")

    def error(self, message: str) -> None:
        """Print error message."""
        if not self.json_output:
            console_stderr.print(f"[red]✗[/red] {message}")

    def warning(self, message: str) -> None:
        """Print warning message."""
        if not self.json_output:
            console.print(f"[yellow]![/yellow] {message}")


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.version_option(version=__version__, prog_name="playnite-py")
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path),
    envvar="PLAYNITE_DATA_DIR",
    help="Data directory path (default: platform-specific user data dir)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format for scripting",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
@pass_context
def cli(ctx: Context, data_dir: Optional[Path], json_output: bool, verbose: bool) -> None:
    """
    Playnite-Py: Modern Python Game Library Manager

    Manage game library profiles and platform-specific configurations.

    \b
    Examples:
        playnite profile create "Gaming"
        playnite profile switch "Gaming"
        playnite config create --game "Cyberpunk 2077" --preset quality
        playnite --json profile list
    """
    ctx.data_dir = data_dir
    ctx.json_output = json_output
    ctx.verbose = verbose
    setup_logging(verbose)


# Import and register subcommands
from playnite_py.cli.profile_commands import profile
from playnite_py.cli.config_commands import config
from playnite_py.cli.game_commands import game

cli.add_command(profile)
cli.add_command(config)
cli.add_command(game)


@cli.command()
@pass_context
def status(ctx: Context) -> None:
    """
    Show current status of the application.

    Displays information about the active profile and system.

    \b
    Example:
        playnite status
    """
    from playnite_py.configurations.detection import PlatformDetector

    detector = PlatformDetector()
    profile = detector.get_hardware_profile()
    current_profile = None

    try:
        current_profile = ctx.profile_manager.get_current_profile()
    except Exception:
        pass

    if ctx.json_output:
        data = {
            "platform": profile.platform.value,
            "os": f"{profile.os_name} {profile.os_version}",
            "cpu": profile.cpu_name,
            "ram_gb": profile.ram_mb // 1024,
            "current_profile": current_profile.name if current_profile else None,
        }
        ctx.output(data)
    else:
        table = Table(title="Playnite-Py Status", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Platform", profile.platform.value)
        table.add_row("OS", f"{profile.os_name} {profile.os_version}")
        table.add_row("CPU", profile.cpu_name or "Unknown")
        table.add_row("RAM", f"{profile.ram_mb // 1024} GB")
        table.add_row("GPUs", ", ".join(g.name for g in profile.gpus) or "Unknown")
        table.add_row(
            "Active Profile",
            current_profile.name if current_profile else "[dim]None[/dim]"
        )

        ctx.output_table(table)


@cli.command()
@pass_context
def version(ctx: Context) -> None:
    """
    Show version information.

    \b
    Example:
        playnite version
    """
    if ctx.json_output:
        ctx.output({"version": __version__})
    else:
        console.print(f"Playnite-Py version {__version__}")


def main() -> None:
    """Main entry point."""
    try:
        cli()
    except Exception as e:
        console_stderr.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
