"""
CLI commands for the recommendation engine.

playnite recommend --help
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..config import AppConfig
from ..library.manager import LibraryManager
from ..models.user_profile import Mood
from ..recommendations.engine import RecommendationEngine
from ..recommendations.feed import DiscoveryFeed
from ..recommendations.mood_filter import MoodFilter

console = Console()


def _get_engine(cfg: AppConfig) -> tuple:
    mgr = LibraryManager(cfg)
    profile = mgr.get_or_create_profile(cfg.default_profile_id)
    engine = RecommendationEngine(mgr, cfg)
    return mgr, profile, engine


@click.group("recommend")
def recommend() -> None:
    """Intelligent game recommendation commands."""


# ================================================================== #
# analyse                                                              #
# ================================================================== #

@recommend.command("analyse")
@click.pass_context
def rec_analyse(ctx: click.Context) -> None:
    """Analyse the library and build preference profile."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    mgr, profile, engine = _get_engine(cfg)

    console.print("[cyan]Analysing library and building preference profile…[/cyan]")
    profile = engine.analyse_library(profile)

    fmt = ctx.obj.get("output_format", "table")
    if fmt == "json":
        click.echo(json.dumps({
            "user_id": profile.id,
            "top_genres": profile.get_top_genres(10),
            "top_mechanics": profile.get_top_mechanics(10),
            "genre_weights": profile.genre_weights,
        }, indent=2))
        return

    console.print(f"\n[bold]Profile:[/bold] {profile.username} ({profile.id[:8]}…)")
    console.print(f"\n[bold]Top genres:[/bold] {', '.join(profile.get_top_genres(8))}")
    console.print(f"[bold]Top mechanics:[/bold] {', '.join(profile.get_top_mechanics(5))}")

    if profile.genre_weights:
        table = Table(title="Genre Preferences", show_lines=False)
        table.add_column("Genre", style="cyan")
        table.add_column("Weight", justify="right")
        for genre, weight in sorted(profile.genre_weights.items(), key=lambda x: x[1], reverse=True)[:10]:
            bar = "█" * int(weight * 20)
            table.add_row(genre, f"{weight:.2f} {bar}")
        console.print(table)


# ================================================================== #
# generate                                                             #
# ================================================================== #

@recommend.command("generate")
@click.option("--mood", type=str, default=None,
              help="Mood for filtering. One of: " + ", ".join(m.value for m in Mood))
@click.option("-n", "--count", default=10, show_default=True, help="Number of recommendations.")
@click.option("--genre", default=None, help="Restrict to a specific genre.")
@click.option("--platform", default=None, help="Restrict to a specific platform.")
@click.option("--session", type=click.Choice(["quick", "deep"], case_sensitive=False),
              default=None,
              help="Filter by session length: 'quick' (< 1 h) or 'deep' (3+ h).")
@click.option("--max-hours", default=None, type=float,
              help="Max main-story completion time in hours.")
@click.option("--min-hours", default=None, type=float,
              help="Min main-story completion time in hours.")
@click.option("--difficulty",
              type=click.Choice(["easy", "medium", "hard", "very hard"], case_sensitive=False),
              default=None, help="Filter by difficulty level.")
@click.option("--multiplayer/--no-multiplayer", default=None,
              help="Require (--multiplayer) or exclude (--no-multiplayer) multiplayer support.")
@click.option("--vr", is_flag=True, default=False,
              help="Only recommend VR-compatible games.")
@click.option("--include-unowned", is_flag=True, default=False,
              help="Include games not in your library.")
@click.option("--no-save", is_flag=True, default=False,
              help="Do not save this batch to history.")
@click.pass_context
def rec_generate(ctx: click.Context, mood: Optional[str], count: int,
                 genre: Optional[str], platform: Optional[str],
                 session: Optional[str],
                 max_hours: Optional[float], min_hours: Optional[float],
                 difficulty: Optional[str], multiplayer: Optional[bool], vr: bool,
                 include_unowned: bool, no_save: bool) -> None:
    """Generate personalised game recommendations."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")
    mgr, profile, engine = _get_engine(cfg)

    with console.status("[cyan]Building recommendation engine…"):
        engine.fit()

    with console.status(f"[cyan]Generating {count} recommendations…"):
        recs = engine.generate(
            profile,
            n=count,
            mood=mood,
            genre_filter=genre,
            platform_filter=platform,
            session_type=session,
            max_completion_hours=max_hours,
            min_completion_hours=min_hours,
            difficulty_filter=difficulty,
            multiplayer_filter=multiplayer,
            vr_only=vr,
            include_unowned=include_unowned,
            save_to_db=not no_save,
        )

    if not recs:
        console.print("[yellow]No recommendations found. Try adding more games to your library.[/yellow]")
        return

    if fmt == "json":
        click.echo(json.dumps([r.to_dict() for r in recs], indent=2, default=str))
        return

    title = "Game Recommendations"
    if mood:
        title += f" (mood: {mood})"
    if session:
        title += f" (session: {session})"
    if max_hours is not None:
        title += f" (max {max_hours}h)"
    if min_hours is not None:
        title += f" (min {min_hours}h)"
    if difficulty:
        title += f" (difficulty: {difficulty})"
    if multiplayer is True:
        title += " (multiplayer)"
    elif multiplayer is False:
        title += " (single-player)"
    if vr:
        title += " (VR)"

    table = Table(title=title, show_lines=True, expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Game", style="bold cyan", min_width=25)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Why recommended", style="green")

    for rec in recs:
        score_bar = "▓" * int(rec.final_score * 10) + "░" * (10 - int(rec.final_score * 10))
        reason = rec.explanation.primary_reason if rec.explanation else ""
        table.add_row(
            str(rec.rank),
            rec.game.name,
            score_bar,
            reason,
        )

    console.print(table)
    console.print(f"\n[dim]Generated {len(recs)} recommendations. "
                  f"Use 'playnite recommend feedback' to improve future suggestions.[/dim]")


# ================================================================== #
# what-next                                                            #
# ================================================================== #

@recommend.command("what-next")
@click.option("-n", "--count", default=5, show_default=True)
@click.pass_context
def rec_what_next(ctx: click.Context, count: int) -> None:
    """Quick 'what to play next' based on recent activity."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")
    mgr, profile, engine = _get_engine(cfg)
    engine.fit()
    recs = engine.generate_what_to_play_next(profile, n=count)

    if fmt == "json":
        click.echo(json.dumps([r.to_dict() for r in recs], indent=2, default=str))
        return

    console.print("\n[bold cyan]What to play next:[/bold cyan]\n")
    for i, rec in enumerate(recs, 1):
        reason = rec.explanation.primary_reason if rec.explanation else ""
        console.print(f"  {i}. [cyan]{rec.game.name}[/cyan]")
        console.print(f"     [dim]{reason}[/dim]")


# ================================================================== #
# mood                                                                 #
# ================================================================== #

@recommend.command("mood")
@click.argument("mood_value", required=False,
                type=click.Choice([m.value for m in Mood] + ["clear"]))
@click.option("--list", "list_moods", is_flag=True, default=False,
              help="Show all available moods.")
@click.pass_context
def rec_mood(ctx: click.Context, mood_value: Optional[str], list_moods: bool) -> None:
    """Set or clear the current mood for recommendations."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")

    mf = MoodFilter()

    if list_moods or not mood_value:
        moods = mf.list_moods()
        if fmt == "json":
            click.echo(json.dumps(moods, indent=2))
            return
        table = Table(title="Available Moods")
        table.add_column("Mood", style="cyan")
        table.add_column("Description", style="green")
        for m in moods:
            table.add_row(m["mood"], m["description"])
        console.print(table)
        return

    mgr, profile, _ = _get_engine(cfg)
    if mood_value == "clear":
        profile.set_mood(None)
        mgr.save_profile(profile)
        console.print("[green]Mood cleared.[/green]")
    else:
        profile.set_mood(mood_value)
        mgr.save_profile(profile)
        desc = mf.get_mood_description(mood_value)
        console.print(f"[green]Mood set to '{mood_value}':[/green] {desc}")


# ================================================================== #
# clear-filters                                                        #
# ================================================================== #

@recommend.command("clear-filters")
@click.pass_context
def rec_clear_filters(ctx: click.Context) -> None:
    """Clear the persistent mood filter from the current profile.

    Genre, platform, session, hours, difficulty, multiplayer, and VR
    filters are per-call — simply omit the flag to stop using them.
    """
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    mgr, profile, _ = _get_engine(cfg)
    if profile.current_mood is None:
        console.print("[yellow]No persistent filters are currently set.[/yellow]")
    else:
        profile.set_mood(None)
        mgr.save_profile(profile)
        console.print("[green]Mood filter cleared.[/green]")
    console.print(
        "[dim]Note: genre, platform, session, hours, difficulty, multiplayer, "
        "and VR filters are per-call — omit the flag to clear them.[/dim]"
    )


# ================================================================== #
# feedback                                                             #
# ================================================================== #

@recommend.command("feedback")
@click.argument("game_name_or_id")
@click.argument("action", type=click.Choice(
    ["played", "liked", "disliked", "dismissed", "added_to_wishlist", "ignored"]
))
@click.option("--notes", default=None, help="Optional notes.")
@click.pass_context
def rec_feedback(ctx: click.Context, game_name_or_id: str, action: str,
                 notes: Optional[str]) -> None:
    """Record feedback on a recommendation. ACTION: played|liked|disliked|dismissed|added_to_wishlist"""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    mgr, profile, engine = _get_engine(cfg)
    engine.fit()

    # Find the game
    game = mgr.get_game(game_name_or_id)
    if game is None:
        matches = mgr.search(game_name_or_id)
        if not matches:
            console.print(f"[red]Game not found: {game_name_or_id}[/red]")
            return
        game = matches[0]

    # Create a synthetic recommendation to pass to feedback recorder
    from ..recommendations.engine import Recommendation
    rec = Recommendation(game=game, batch_id="manual")
    engine.record_feedback(profile, rec, action, notes=notes)
    console.print(f"[green]Feedback recorded:[/green] {action} → {game.name}")


# ================================================================== #
# stats                                                                #
# ================================================================== #

@recommend.command("stats")
@click.pass_context
def rec_stats(ctx: click.Context) -> None:
    """Show recommendation accuracy statistics."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")
    mgr, profile, engine = _get_engine(cfg)
    stats = engine.get_accuracy_stats(profile)

    if fmt == "json":
        click.echo(json.dumps(stats, indent=2))
        return

    if not stats.get("accuracy"):
        console.print("[yellow]Not enough feedback data yet.[/yellow]")
        return

    acc = stats["accuracy"]
    console.print(f"\n[bold cyan]Recommendation Accuracy[/bold cyan]")
    console.print(f"  Total feedback:     {acc.get('total_feedback', 0)}")
    console.print(f"  Acceptance rate:    {acc.get('acceptance_rate', 0):.1%}")
    console.print(f"  Play conversion:    {acc.get('play_conversion_rate', 0):.1%}")

    if stats.get("by_action"):
        console.print("\n[bold]By action:[/bold]")
        for action, count in stats["by_action"].items():
            console.print(f"  {action}: {count}")


# ================================================================== #
# history                                                              #
# ================================================================== #

@recommend.command("history")
@click.option("--limit", default=5, show_default=True, help="Number of past batches to show.")
@click.pass_context
def rec_history(ctx: click.Context, limit: int) -> None:
    """Show recommendation history."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")
    mgr, profile, engine = _get_engine(cfg)
    history = engine.get_history(profile, limit=limit)

    if fmt == "json":
        click.echo(json.dumps(history, indent=2, default=str))
        return

    if not history:
        console.print("[yellow]No recommendation history found.[/yellow]")
        return

    for batch in history:
        console.print(f"\n[bold cyan]Batch:[/bold cyan] {batch['id'][:8]}… "
                      f"[dim]({batch['generated_at']}, mood={batch.get('mood', 'none')})[/dim]")
        for i, rec in enumerate(batch.get("recommendations", [])[:5], 1):
            console.print(f"  {i}. {rec.get('game_name', '?')}  "
                          f"[dim]score={rec.get('final_score', 0):.2f}[/dim]")


# ================================================================== #
# export                                                               #
# ================================================================== #

@recommend.command("export")
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Output JSON file path.")
@click.pass_context
def rec_export(ctx: click.Context, output: Optional[str]) -> None:
    """Export full recommendation history and reasoning to JSON."""
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    mgr, profile, engine = _get_engine(cfg)
    out_path = Path(output) if output else None
    result = engine.export_history(profile, output_path=out_path)
    console.print(f"[green]Exported recommendation history to:[/green] {result}")


# ================================================================== #
# test (synthetic data)                                                #
# ================================================================== #

@recommend.command("test")
@click.option("--library-file", default=None, type=click.Path(),
              help="Path to a JSON game library fixture.")
@click.option("-n", default=10, show_default=True)
@click.pass_context
def rec_test(ctx: click.Context, library_file: Optional[str], n: int) -> None:
    """Test the recommendation engine with sample or fixture data."""
    import tempfile

    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")

    # Use temp database to avoid polluting real library
    with tempfile.TemporaryDirectory() as tmpdir:
        test_cfg = AppConfig()
        test_cfg.data_dir = tmpdir

        mgr = LibraryManager(test_cfg)

        fixture = Path(library_file) if library_file else None
        if fixture and fixture.exists():
            count = mgr.import_from_json(fixture)
        else:
            # Generate synthetic library
            count = _seed_synthetic_library(mgr)

        profile = mgr.get_or_create_profile()
        profile = mgr.build_user_preference_weights(profile)
        mgr.save_profile(profile)

        engine = RecommendationEngine(mgr, test_cfg)
        engine.fit()
        recs = engine.generate(profile, n=n, save_to_db=False)

        if fmt == "json":
            click.echo(json.dumps([r.to_dict() for r in recs], indent=2, default=str))
            return

        console.print(f"[cyan]Test library:[/cyan] {count} games loaded")
        console.print(f"[cyan]Recommendations generated:[/cyan] {len(recs)}\n")

        for rec in recs:
            reason = rec.explanation.primary_reason if rec.explanation else ""
            console.print(f"  {rec.rank}. [cyan]{rec.game.name}[/cyan]  "
                          f"[dim]score={rec.final_score:.2f}  {reason}[/dim]")


# ================================================================== #
# feed                                                                 #
# ================================================================== #

@recommend.command("feed")
@click.option("-n", "--count", default=5, show_default=True,
              help="Recommendations per shelf.")
@click.option("--mood", type=str, default=None,
              help="Mood applied to the Top Picks shelf.")
@click.pass_context
def rec_feed(ctx: click.Context, count: int, mood: Optional[str]) -> None:
    """Generate a multi-shelf personalised discovery feed.

    Surfaces games from five different angles at once:
    Top Picks, Because You Played X, From Your Backlog,
    Discover Something New, and Seasonal Picks.
    """
    cfg: AppConfig = ctx.obj.get("config", AppConfig())
    fmt = ctx.obj.get("output_format", "table")
    mgr, profile, engine = _get_engine(cfg)
    engine.fit()

    feed = DiscoveryFeed(engine, mgr)
    shelves = feed.generate(profile, n_per_shelf=count, mood=mood)

    if fmt == "json":
        click.echo(json.dumps([s.to_dict() for s in shelves], indent=2, default=str))
        return

    if not shelves:
        console.print("[yellow]No feed results. Add more games to your library.[/yellow]")
        return

    for shelf in shelves:
        console.print(f"\n[bold cyan]{shelf.name}[/bold cyan]")
        console.print(f"[dim]{shelf.description}[/dim]")
        for rec in shelf.recommendations:
            reason = rec.explanation.primary_reason if rec.explanation else ""
            score_str = f"  [dim]score={rec.final_score:.2f}[/dim]" if rec.final_score else ""
            console.print(f"  • [cyan]{rec.game.name}[/cyan]{score_str}")
            if reason:
                console.print(f"    [dim]{reason}[/dim]")


def _seed_synthetic_library(mgr: LibraryManager) -> int:
    """Create a minimal synthetic game library for testing."""
    from ..models.game import Game
    import uuid

    GAMES = [
        dict(name="The Witcher 3", genres=["RPG"], themes=["fantasy", "dark"],
             mechanics=["open world", "quest"], developers=["CD Projekt Red"],
             playtime_seconds=180000, play_count=5, is_owned=True),
        dict(name="Hollow Knight", genres=["Action", "Metroidvania"],
             themes=["dark", "atmospheric"], mechanics=["platformer", "exploration"],
             developers=["Team Cherry"], playtime_seconds=72000, play_count=3, is_owned=True),
        dict(name="Hades", genres=["Action", "Roguelike"],
             themes=["mythology", "dark"], mechanics=["roguelite", "action"],
             developers=["Supergiant Games"], playtime_seconds=90000, play_count=10, is_owned=True),
        dict(name="Celeste", genres=["Platformer", "Indie"],
             themes=["mental health"], mechanics=["precision platformer"],
             developers=["Maddy Thorson"], playtime_seconds=36000, play_count=2, is_owned=True),
        dict(name="Stardew Valley", genres=["Simulation", "RPG"],
             themes=["farming", "cozy"], mechanics=["farming sim", "life sim"],
             developers=["ConcernedApe"], playtime_seconds=0, play_count=0, is_owned=True),
        dict(name="Disco Elysium", genres=["RPG", "Adventure"],
             themes=["dark", "political"], mechanics=["dialogue", "skill check"],
             developers=["ZA/UM"], playtime_seconds=0, play_count=0, is_owned=True),
        dict(name="Factorio", genres=["Strategy", "Simulation"],
             themes=["sci-fi"], mechanics=["factory", "automation"],
             developers=["Wube Software"], playtime_seconds=0, play_count=0, is_owned=True),
        dict(name="Noita", genres=["Action", "Roguelike"],
             themes=["magic", "dark"], mechanics=["pixel simulation", "roguelite"],
             developers=["Nolla Games"], playtime_seconds=0, play_count=0, is_owned=True),
        dict(name="Slay the Spire", genres=["Roguelike", "Strategy"],
             themes=["fantasy"], mechanics=["deck building", "turn-based"],
             developers=["MegaCrit"], playtime_seconds=0, play_count=0, is_owned=True),
        dict(name="Elden Ring", genres=["Action", "RPG"],
             themes=["dark", "fantasy", "souls-like"], mechanics=["open world", "action rpg"],
             developers=["FromSoftware"], playtime_seconds=0, play_count=0, is_owned=True),
    ]

    for gd in GAMES:
        g = Game(id=str(uuid.uuid4()), **gd)  # type: ignore[arg-type]
        mgr.add_game(g)
    return len(GAMES)
