"""
Game management CLI commands for Playnite-Py.

This module provides CLI commands for managing games in the library.

Example:
    $ playnite game list
    $ playnite game add "My Game" --path "/path/to/game.exe"
    $ playnite game launch "My Game"
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import UUID

import click
from rich.table import Table

from playnite_py.cli.main import Context, pass_context, console
from playnite_py.core.models.game import Game, GameAction, GameActionType, GameSource


@click.group()
def game() -> None:
    """
    Manage games in the library.

    \b
    Commands for adding, listing, and launching games.

    \b
    Examples:
        playnite game list
        playnite game add "My Game" --path "/path/to/game.exe"
        playnite game launch "My Game"
    """
    pass


@game.command("list")
@click.option(
    "--source", "-s",
    type=click.Choice([s.value for s in GameSource]),
    help="Filter by source"
)
@click.option(
    "--favorites", "-f",
    is_flag=True,
    help="Show only favorites"
)
@click.option(
    "--search", "-q",
    help="Search by name"
)
@pass_context
def list_games(
    ctx: Context,
    source: Optional[str],
    favorites: bool,
    search: Optional[str],
) -> None:
    """
    List games in the current profile.

    \b
    Examples:
        playnite game list
        playnite game list --source steam
        playnite game list --favorites
        playnite game list --search "cyber"
    """
    try:
        config_manager = ctx.get_config_manager()
        game_repo = config_manager.game_repo

        if search:
            games = game_repo.search(search)
        elif source:
            games = game_repo.get_by_source(GameSource(source))
        elif favorites:
            games = game_repo.get_favorites()
        else:
            games = game_repo.get_all()

        if ctx.json_output:
            ctx.output([g.to_dict() for g in games])
        else:
            if not games:
                console.print("[dim]No games found.[/dim]")
                return

            table = Table(title=f"Games ({len(games)})")
            table.add_column("Name", style="cyan")
            table.add_column("Source")
            table.add_column("Status")
            table.add_column("Playtime", justify="right")

            for g in sorted(games, key=lambda x: x.get_display_name().lower()):
                status_parts = []
                if g.is_favorite:
                    status_parts.append("[yellow]★[/yellow]")
                status_parts.append(g.status.value)
                status = " ".join(status_parts)

                hours = g.statistics.total_playtime_minutes // 60
                playtime = f"{hours}h" if hours else "-"

                table.add_row(
                    g.get_display_name()[:50],
                    g.source.value,
                    status,
                    playtime,
                )

            ctx.output_table(table)

    except click.ClickException as e:
        if ctx.json_output:
            ctx.output({"error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@game.command("add")
@click.argument("name")
@click.option(
    "--path", "-p",
    type=click.Path(exists=True, path_type=Path),
    help="Path to game executable"
)
@click.option(
    "--source", "-s",
    type=click.Choice([s.value for s in GameSource]),
    default="manual",
    help="Game source"
)
@click.option(
    "--description", "-d",
    default="",
    help="Game description"
)
@click.option(
    "--install-dir",
    type=click.Path(path_type=Path),
    help="Game installation directory"
)
@pass_context
def add_game(
    ctx: Context,
    name: str,
    path: Optional[Path],
    source: str,
    description: str,
    install_dir: Optional[Path],
) -> None:
    """
    Add a game to the library.

    \b
    Arguments:
        NAME  Game name

    \b
    Examples:
        playnite game add "My Game" --path "/games/mygame.exe"
        playnite game add "Steam Game" --source steam
    """
    try:
        config_manager = ctx.get_config_manager()
        game_repo = config_manager.game_repo

        # Create game
        game_obj = Game(
            name=name,
            source=GameSource(source),
        )
        game_obj.metadata.description = description

        if install_dir:
            game_obj.install_directory = install_dir

        # Add action if path provided
        if path:
            action = GameAction(
                name="Play",
                type=GameActionType.FILE,
                path=str(path),
                working_directory=path.parent if path else None,
                is_default=True,
            )
            game_obj.actions.append(action)

        game_repo.create(game_obj)

        if ctx.json_output:
            ctx.output({
                "success": True,
                "game": game_obj.to_dict(),
            })
        else:
            ctx.success(f"Added game: {name}")

    except Exception as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@game.command("info")
@click.argument("name")
@pass_context
def game_info(ctx: Context, name: str) -> None:
    """
    Show detailed information about a game.

    \b
    Arguments:
        NAME  Game name

    \b
    Examples:
        playnite game info "Cyberpunk 2077"
    """
    try:
        config_manager = ctx.get_config_manager()
        game_repo = config_manager.game_repo

        game_obj = game_repo.get_by_name(name)
        if not game_obj:
            raise ValueError(f"Game not found: {name}")

        if ctx.json_output:
            ctx.output(game_obj.to_dict())
        else:
            table = Table(title=f"Game: {game_obj.name}", show_header=False)
            table.add_column("Property", style="cyan")
            table.add_column("Value")

            table.add_row("ID", str(game_obj.id))
            table.add_row("Source", game_obj.source.value)
            table.add_row("Status", game_obj.status.value)
            table.add_row("Favorite", "Yes" if game_obj.is_favorite else "No")
            table.add_row("Hidden", "Yes" if game_obj.is_hidden else "No")

            if game_obj.metadata.description:
                desc = game_obj.metadata.description[:100]
                if len(game_obj.metadata.description) > 100:
                    desc += "..."
                table.add_row("Description", desc)

            if game_obj.metadata.genres:
                table.add_row("Genres", ", ".join(game_obj.metadata.genres))

            if game_obj.metadata.developers:
                table.add_row("Developers", ", ".join(game_obj.metadata.developers))

            # Statistics
            stats = game_obj.statistics
            hours = stats.total_playtime_minutes // 60
            mins = stats.total_playtime_minutes % 60
            table.add_row("Playtime", f"{hours}h {mins}m")
            table.add_row("Sessions", str(stats.session_count))
            table.add_row(
                "Last Played",
                stats.last_played.strftime("%Y-%m-%d %H:%M") if stats.last_played else "-"
            )
            table.add_row("Added", game_obj.added_date.strftime("%Y-%m-%d"))

            # Actions
            if game_obj.actions:
                actions = ", ".join(a.name for a in game_obj.actions)
                table.add_row("Actions", actions)

            # Configurations
            configs = config_manager.get_configurations_for_game(game_obj.id)
            if configs:
                config_names = ", ".join(c.name for c in configs)
                table.add_row("Configurations", config_names)

            ctx.output_table(table)

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@game.command("delete")
@click.argument("name")
@click.option(
    "--yes", "-y",
    is_flag=True,
    help="Skip confirmation"
)
@pass_context
def delete_game(ctx: Context, name: str, yes: bool) -> None:
    """
    Delete a game from the library.

    \b
    Arguments:
        NAME  Game name

    \b
    Examples:
        playnite game delete "Old Game"
    """
    try:
        config_manager = ctx.get_config_manager()
        game_repo = config_manager.game_repo

        game_obj = game_repo.get_by_name(name)
        if not game_obj:
            raise ValueError(f"Game not found: {name}")

        if not yes and not ctx.json_output:
            if not click.confirm(f"Delete '{game_obj.name}' from library?"):
                raise SystemExit(0)

        game_repo.delete(game_obj.id)

        if ctx.json_output:
            ctx.output({"success": True, "deleted": name})
        else:
            ctx.success(f"Deleted game: {name}")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@game.command("launch")
@click.argument("name")
@click.option(
    "--config", "-c",
    help="Configuration to use"
)
@click.option(
    "--action", "-a",
    help="Action to execute"
)
@click.option(
    "--no-wait",
    is_flag=True,
    help="Don't wait for game to exit"
)
@pass_context
def launch_game(
    ctx: Context,
    name: str,
    config: Optional[str],
    action: Optional[str],
    no_wait: bool,
) -> None:
    """
    Launch a game.

    \b
    Arguments:
        NAME  Game name

    \b
    Examples:
        playnite game launch "Cyberpunk 2077"
        playnite game launch "My Game" --config "Desktop"
    """
    try:
        config_manager = ctx.get_config_manager()
        game_repo = config_manager.game_repo

        from playnite_py.configurations.launcher import GameLauncher

        game_obj = game_repo.get_by_name(name)
        if not game_obj:
            raise ValueError(f"Game not found: {name}")

        # Get configuration
        configuration = None
        if config:
            configs = config_manager.get_configurations_for_game(game_obj.id)
            for c in configs:
                if c.name.lower() == config.lower():
                    configuration = c
                    break
            if not configuration:
                raise ValueError(f"Configuration not found: {config}")
        else:
            # Try to get best configuration for current platform
            configuration = config_manager.get_configuration_for_platform(game_obj.id)

        # Get action
        game_action = None
        if action:
            for a in game_obj.actions:
                if a.name.lower() == action.lower():
                    game_action = a
                    break
            if not game_action:
                raise ValueError(f"Action not found: {action}")

        # Launch
        launcher = GameLauncher()
        result = launcher.launch_game(
            game=game_obj,
            config=configuration,
            action=game_action,
            wait_for_exit=not no_wait,
        )

        # Record statistics
        if configuration:
            config_manager.record_launch(
                configuration.id,
                success=result.success,
                session_minutes=result.duration_seconds // 60 if result.duration_seconds else None,
            )

        if ctx.json_output:
            ctx.output({
                "success": result.success,
                "duration_seconds": result.duration_seconds,
                "exit_code": result.exit_code,
                "error": result.error_message or None,
            })
        else:
            if result.success:
                if result.duration_seconds:
                    mins = result.duration_seconds // 60
                    ctx.success(f"Game session: {mins} minutes")
                else:
                    ctx.success("Game launched")
            else:
                ctx.error(f"Launch failed: {result.error_message}")
                raise SystemExit(1)

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@game.command("favorite")
@click.argument("name")
@click.option(
    "--remove", "-r",
    is_flag=True,
    help="Remove from favorites"
)
@pass_context
def toggle_favorite(ctx: Context, name: str, remove: bool) -> None:
    """
    Add or remove a game from favorites.

    \b
    Arguments:
        NAME  Game name

    \b
    Examples:
        playnite game favorite "Cyberpunk 2077"
        playnite game favorite "Old Game" --remove
    """
    try:
        config_manager = ctx.get_config_manager()
        game_repo = config_manager.game_repo

        game_obj = game_repo.get_by_name(name)
        if not game_obj:
            raise ValueError(f"Game not found: {name}")

        game_obj.is_favorite = not remove
        game_repo.update(game_obj)

        if ctx.json_output:
            ctx.output({"success": True, "favorite": game_obj.is_favorite})
        else:
            if game_obj.is_favorite:
                ctx.success(f"Added to favorites: {name}")
            else:
                ctx.success(f"Removed from favorites: {name}")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)
