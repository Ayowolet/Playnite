"""CLI commands for media capture."""
import asyncio
import typer
from rich.console import Console
from rich.table import Table

from ..capture.storage import CaptureStorage

app = typer.Typer(help="Manage media capture")
console = Console()


@app.command()
def storage():
    """
    Show storage usage for captured media.

    Displays total storage used by screenshots and videos.
    """
    storage_mgr = CaptureStorage()
    usage = storage_mgr.get_storage_usage()

    console.print(f"\n[bold cyan]Capture Storage Usage[/bold cyan]\n")
    console.print(f"Total Size: [green]{usage['total_size_gb']:.2f} GB[/green] ({usage['total_size_mb']:.1f} MB)")
    console.print(f"Games: [cyan]{usage['game_count']}[/cyan]")
    console.print(f"Screenshots: [yellow]{usage['total_screenshots']}[/yellow]")
    console.print(f"Videos: [magenta]{usage['total_videos']}[/magenta]")
    console.print(f"\nStorage Path: [dim]{storage_mgr.base_path}[/dim]\n")


@app.command()
def list_game(game_id: str = typer.Argument(..., help="Game ID")):
    """
    List all captures for a specific game.

    Shows all screenshots and videos captured for the given game.
    """
    storage_mgr = CaptureStorage()
    captures = storage_mgr.list_captures(game_id)

    console.print(f"\n[bold cyan]Captures for Game: {game_id}[/bold cyan]\n")

    # Screenshots table
    if captures["screenshots"]:
        console.print("[bold yellow]Screenshots:[/bold yellow]")
        screenshot_table = Table(show_header=True, header_style="bold magenta")
        screenshot_table.add_column("#", style="dim", width=4)
        screenshot_table.add_column("Filename", style="cyan")
        screenshot_table.add_column("Size", justify="right", style="green")

        for i, screenshot in enumerate(captures["screenshots"][:20], 1):  # Show first 20
            size_mb = screenshot.stat().st_size / 1024 / 1024
            screenshot_table.add_row(
                str(i),
                screenshot.name,
                f"{size_mb:.2f} MB"
            )

        console.print(screenshot_table)

        if len(captures["screenshots"]) > 20:
            console.print(f"[dim]... and {len(captures['screenshots']) - 20} more[/dim]")
    else:
        console.print("[yellow]No screenshots found[/yellow]")

    # Videos table
    console.print()
    if captures["videos"]:
        console.print("[bold magenta]Videos:[/bold magenta]")
        video_table = Table(show_header=True, header_style="bold magenta")
        video_table.add_column("#", style="dim", width=4)
        video_table.add_column("Filename", style="cyan")
        video_table.add_column("Size", justify="right", style="green")

        for i, video in enumerate(captures["videos"][:20], 1):  # Show first 20
            size_mb = video.stat().st_size / 1024 / 1024
            video_table.add_row(
                str(i),
                video.name,
                f"{size_mb:.2f} MB"
            )

        console.print(video_table)

        if len(captures["videos"]) > 20:
            console.print(f"[dim]... and {len(captures['videos']) - 20} more[/dim]")
    else:
        console.print("[yellow]No videos found[/yellow]")

    console.print()


@app.command()
def cleanup(
    game_id: str = typer.Argument(..., help="Game ID"),
    keep_count: int = typer.Option(100, "--keep", "-k", help="Number of recent captures to keep"),
    max_age_days: int = typer.Option(90, "--max-age", "-a", help="Maximum age in days"),
):
    """
    Clean up old captures for a game.

    Removes captures older than the specified age, keeping at least
    the specified number of recent captures.
    """
    storage_mgr = CaptureStorage()

    console.print(f"[cyan]Cleaning up captures for game {game_id}...[/cyan]")
    console.print(f"Keeping: {keep_count} recent captures")
    console.print(f"Max age: {max_age_days} days\n")

    deleted = storage_mgr.cleanup_old_captures(game_id, keep_count, max_age_days)

    if deleted > 0:
        console.print(f"[green]✓[/green] Deleted {deleted} old captures")
    else:
        console.print("[yellow]No captures needed cleanup[/yellow]")


@app.command()
def delete_all(
    game_id: str = typer.Argument(..., help="Game ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """
    Delete ALL captures for a game.

    Warning: This permanently deletes all screenshots and videos!
    """
    if not confirm:
        console.print(f"[red bold]WARNING:[/red bold] This will permanently delete ALL captures for game {game_id}")
        response = typer.confirm("Are you sure you want to continue?")
        if not response:
            console.print("[yellow]Cancelled[/yellow]")
            return

    storage_mgr = CaptureStorage()
    success = storage_mgr.delete_game_captures(game_id)

    if success:
        console.print(f"[green]✓[/green] Deleted all captures for game {game_id}")
    else:
        console.print(f"[red]✗[/red] Failed to delete captures (game may not exist)")


if __name__ == "__main__":
    app()
