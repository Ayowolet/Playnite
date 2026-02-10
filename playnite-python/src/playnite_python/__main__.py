"""Main entry point for the Playnite Python CLI."""
import typer
from rich.console import Console

from .cli import capture, recommend, serve

console = Console()
app = typer.Typer(
    name="playnite-python",
    help="Playnite Python Integration - Game recommendations and media capture",
    add_completion=False,
)

# Add sub-commands
app.add_typer(serve.app, name="serve", help="Start the Playnite Python service")
app.add_typer(
    recommend.app, name="recommend", help="Generate game recommendations"
)
app.add_typer(capture.app, name="capture", help="Manage media capture")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version information"
    ),
):
    """
    Playnite Python Integration CLI.

    Provides game recommendations and media capture capabilities for Playnite.
    """
    if version:
        console.print("[bold green]Playnite Python[/bold green] version [cyan]1.0.0[/cyan]")
        console.print("\nPython integration for Playnite game library manager")
        console.print("Features: Game recommendations • Media capture")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        console.print("[bold]Playnite Python[/bold] - Use --help for usage information")
        console.print("\nAvailable commands:")
        console.print("  • [cyan]serve[/cyan]     - Start the service")
        console.print("  • [cyan]recommend[/cyan] - Generate recommendations")
        console.print("  • [cyan]capture[/cyan]   - Manage media capture")


if __name__ == "__main__":
    app()
