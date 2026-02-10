"""CLI commands for game recommendations."""
import json
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from ..recommendations.engine import RecommendationEngine

app = typer.Typer(help="Generate game recommendations")
console = Console()


@app.command()
def generate(
    user_id: str = typer.Option(..., "--user-id", "-u", help="User ID"),
    library_file: Path = typer.Option(
        ..., "--library-file", "-l", help="Path to library JSON file"
    ),
    output: str = typer.Option(
        "text", "--output", "-o", help="Output format (text or json)"
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recommendations"),
    mood: str = typer.Option(
        None, "--mood", "-m", help="Mood filter (relaxing, challenging, story, etc.)"
    ),
):
    """
    Generate game recommendations from a library file.

    This command is useful for testing recommendations without running the full service.
    """
    # Load library file
    if not library_file.exists():
        console.print(f"[red]Error:[/red] Library file not found: {library_file}")
        raise typer.Exit(code=1)

    try:
        with open(library_file, "r", encoding="utf-8") as f:
            library = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON in library file: {e}")
        raise typer.Exit(code=1)

    if not library:
        console.print("[yellow]Warning:[/yellow] Library file is empty")
        raise typer.Exit(code=0)

    # Build context
    context = {}
    if mood:
        context["mood"] = mood

    # Generate recommendations
    console.print(f"[cyan]Generating {limit} recommendations for user {user_id}...[/cyan]")

    engine = RecommendationEngine()
    recommendations = engine.generate(
        user_id=user_id, library=library, play_histories=[], context=context, limit=limit
    )

    # Output results
    if output == "json":
        print(json.dumps(recommendations, indent=2))
    else:
        # Pretty text output
        if not recommendations:
            console.print("[yellow]No recommendations found![/yellow]")
            return

        console.print(f"\n[bold green]🎮 Top {len(recommendations)} Recommendations:[/bold green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=3)
        table.add_column("Game", style="cyan")
        table.add_column("Score", justify="right", style="green")
        table.add_column("Reason", style="white")

        for i, rec in enumerate(recommendations, 1):
            # Find game name
            game = next((g for g in library if g["game_id"] == rec["game_id"]), None)
            game_name = game["name"] if game else rec.get("game_name", "Unknown")

            table.add_row(
                str(i), game_name, f"{rec['score']:.2f}", rec["reason"][:60] + "..." if len(rec["reason"]) > 60 else rec["reason"]
            )

        console.print(table)


if __name__ == "__main__":
    app()
