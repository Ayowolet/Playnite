"""
Configuration management CLI commands for Playnite-Py.

This module provides CLI commands for managing platform-specific
game configurations.

Example:
    $ playnite config create --game "Cyberpunk 2077" --preset quality
    $ playnite config list --game "Cyberpunk 2077"
    $ playnite config apply --game "Cyberpunk 2077" --config "Desktop"
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import UUID

import click
from rich.table import Table

from playnite_py.cli.main import Context, pass_context, console
from playnite_py.core.models.configuration import PlatformType, GraphicsQuality


@click.group()
def config() -> None:
    """
    Manage platform configurations.

    \b
    Commands for creating and managing platform-specific game
    configurations (Desktop, Laptop, TV/Couch modes, etc.).

    \b
    Examples:
        playnite config create --game "My Game" --name "Desktop" --preset quality
        playnite config list --game "My Game"
        playnite config apply --game "My Game" --config "Desktop"
    """
    pass


# Alias for standalone use
config_cli = config


@config.command("create")
@click.option(
    "--game", "-g",
    required=True,
    help="Game name or ID"
)
@click.option(
    "--name", "-n",
    required=True,
    help="Configuration name (e.g., Desktop, Laptop, TV)"
)
@click.option(
    "--description", "-d",
    default="",
    help="Configuration description"
)
@click.option(
    "--preset", "-p",
    type=click.Choice([
        "performance", "quality", "balanced",
        "battery-saver", "streaming", "handheld", "debug"
    ], case_sensitive=False),
    help="Use a preset template"
)
@click.option(
    "--platform",
    type=click.Choice(["desktop", "laptop", "htpc", "handheld", "vm", "remote"]),
    default="desktop",
    help="Target platform type"
)
@click.option(
    "--default",
    "set_default",
    is_flag=True,
    help="Set as default configuration for this game"
)
@pass_context
def create_config(
    ctx: Context,
    game: str,
    name: str,
    description: str,
    preset: Optional[str],
    platform: str,
    set_default: bool,
) -> None:
    """
    Create a new platform configuration for a game.

    \b
    Examples:
        playnite config create --game "Cyberpunk 2077" --name "Desktop High" --preset quality
        playnite config create -g "My Game" -n "Laptop" --platform laptop --preset battery-saver
    """
    try:
        config_manager = ctx.get_config_manager()

        # Find game by name or ID
        game_repo = config_manager.game_repo
        game_obj = game_repo.get_by_name(game)
        if not game_obj:
            # Try as UUID
            try:
                game_obj = game_repo.get_by_id(UUID(game))
            except ValueError:
                pass

        if not game_obj:
            raise ValueError(f"Game not found: {game}")

        # Map preset name to template name
        preset_map = {
            "performance": "Performance",
            "quality": "Quality",
            "balanced": "Balanced",
            "battery-saver": "Battery Saver",
            "streaming": "Streaming",
            "handheld": "Handheld",
            "debug": "Debug",
        }

        configuration = config_manager.create_configuration(
            game_id=game_obj.id,
            name=name,
            description=description,
            platform_type=PlatformType(platform),
            preset=preset_map.get(preset.lower()) if preset else None,
            is_default=set_default,
        )

        if ctx.json_output:
            ctx.output({
                "success": True,
                "configuration": configuration.to_dict(),
            })
        else:
            ctx.success(f"Created configuration '{name}' for '{game_obj.name}'")
            if preset:
                console.print(f"  Based on preset: {preset}")
            if set_default:
                console.print("  Set as default configuration")

    except (ValueError, click.ClickException) as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("list")
@click.option(
    "--game", "-g",
    help="Filter by game name or ID"
)
@pass_context
def list_configs(ctx: Context, game: Optional[str]) -> None:
    """
    List platform configurations.

    \b
    Examples:
        playnite config list
        playnite config list --game "Cyberpunk 2077"
    """
    try:
        config_manager = ctx.get_config_manager()

        if game:
            # Find game
            game_repo = config_manager.game_repo
            game_obj = game_repo.get_by_name(game)
            if not game_obj:
                try:
                    game_obj = game_repo.get_by_id(UUID(game))
                except ValueError:
                    pass
            if not game_obj:
                raise ValueError(f"Game not found: {game}")

            configs = config_manager.get_configurations_for_game(game_obj.id)
        else:
            configs = config_manager.config_repo.get_all()

        if ctx.json_output:
            ctx.output([c.to_dict() for c in configs])
        else:
            if not configs:
                console.print("[dim]No configurations found.[/dim]")
                return

            table = Table(title="Platform Configurations")
            table.add_column("Name", style="cyan")
            table.add_column("Game")
            table.add_column("Platform")
            table.add_column("Quality")
            table.add_column("Status")

            for c in configs:
                # Get game name
                game_obj = config_manager.game_repo.get_by_id(c.game_id)
                game_name = game_obj.name if game_obj else str(c.game_id)[:8]

                status_parts = []
                if c.is_default:
                    status_parts.append("[blue]default[/blue]")
                if not c.is_enabled:
                    status_parts.append("[red]disabled[/red]")
                status = " ".join(status_parts) or "-"

                table.add_row(
                    c.name,
                    game_name[:30] + "..." if len(game_name) > 30 else game_name,
                    c.platform_type.value,
                    c.graphics_quality.value,
                    status,
                )

            ctx.output_table(table)

    except (ValueError, click.ClickException) as e:
        if ctx.json_output:
            ctx.output({"error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("info")
@click.option(
    "--game", "-g",
    required=True,
    help="Game name or ID"
)
@click.option(
    "--config", "-c",
    required=True,
    help="Configuration name"
)
@pass_context
def config_info(ctx: Context, game: str, config: str) -> None:
    """
    Show detailed information about a configuration.

    \b
    Examples:
        playnite config info --game "Cyberpunk 2077" --config "Desktop"
    """
    try:
        config_manager = ctx.get_config_manager()

        # Find game
        game_repo = config_manager.game_repo
        game_obj = game_repo.get_by_name(game)
        if not game_obj:
            raise ValueError(f"Game not found: {game}")

        # Find configuration
        configs = config_manager.get_configurations_for_game(game_obj.id)
        configuration = None
        for c in configs:
            if c.name.lower() == config.lower():
                configuration = c
                break

        if not configuration:
            raise ValueError(f"Configuration not found: {config}")

        if ctx.json_output:
            ctx.output(configuration.to_dict())
        else:
            table = Table(
                title=f"Configuration: {configuration.name}",
                show_header=False
            )
            table.add_column("Property", style="cyan")
            table.add_column("Value")

            table.add_row("ID", str(configuration.id))
            table.add_row("Game", game_obj.name)
            table.add_row("Platform", configuration.platform_type.value)
            table.add_row("Graphics", configuration.graphics_quality.value)
            table.add_row("Default", "Yes" if configuration.is_default else "No")
            table.add_row("Enabled", "Yes" if configuration.is_enabled else "No")

            # Display settings
            if configuration.display.width:
                table.add_row(
                    "Resolution",
                    f"{configuration.display.width}x{configuration.display.height}"
                )
            table.add_row("Fullscreen", "Yes" if configuration.display.fullscreen else "No")
            table.add_row("VSync", "Yes" if configuration.display.vsync else "No")

            # Statistics
            stats = configuration.statistics
            table.add_row("Uses", str(stats.use_count))
            table.add_row("Success Rate", f"{stats.success_rate * 100:.0f}%")
            table.add_row(
                "Last Used",
                stats.last_used.strftime("%Y-%m-%d %H:%M") if stats.last_used else "-"
            )

            ctx.output_table(table)

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("delete")
@click.option(
    "--game", "-g",
    required=True,
    help="Game name or ID"
)
@click.option(
    "--config", "-c",
    required=True,
    help="Configuration name"
)
@click.option(
    "--yes", "-y",
    is_flag=True,
    help="Skip confirmation"
)
@pass_context
def delete_config(
    ctx: Context,
    game: str,
    config: str,
    yes: bool,
) -> None:
    """
    Delete a configuration.

    \b
    Examples:
        playnite config delete --game "Cyberpunk 2077" --config "Old Config"
    """
    try:
        config_manager = ctx.get_config_manager()

        # Find game and configuration
        game_repo = config_manager.game_repo
        game_obj = game_repo.get_by_name(game)
        if not game_obj:
            raise ValueError(f"Game not found: {game}")

        configs = config_manager.get_configurations_for_game(game_obj.id)
        configuration = None
        for c in configs:
            if c.name.lower() == config.lower():
                configuration = c
                break

        if not configuration:
            raise ValueError(f"Configuration not found: {config}")

        if not yes and not ctx.json_output:
            if not click.confirm(f"Delete configuration '{config}' for '{game_obj.name}'?"):
                raise SystemExit(0)

        config_manager.delete_configuration(configuration.id)

        if ctx.json_output:
            ctx.output({"success": True, "deleted": config})
        else:
            ctx.success(f"Deleted configuration: {config}")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("set-default")
@click.option(
    "--game", "-g",
    required=True,
    help="Game name or ID"
)
@click.option(
    "--config", "-c",
    required=True,
    help="Configuration name"
)
@pass_context
def set_default_config(ctx: Context, game: str, config: str) -> None:
    """
    Set a configuration as the default for a game.

    \b
    Examples:
        playnite config set-default --game "Cyberpunk 2077" --config "Desktop"
    """
    try:
        config_manager = ctx.get_config_manager()

        # Find game and configuration
        game_repo = config_manager.game_repo
        game_obj = game_repo.get_by_name(game)
        if not game_obj:
            raise ValueError(f"Game not found: {game}")

        configs = config_manager.get_configurations_for_game(game_obj.id)
        configuration = None
        for c in configs:
            if c.name.lower() == config.lower():
                configuration = c
                break

        if not configuration:
            raise ValueError(f"Configuration not found: {config}")

        config_manager.set_default_configuration(game_obj.id, configuration.id)

        if ctx.json_output:
            ctx.output({"success": True, "default": config})
        else:
            ctx.success(f"Set default configuration: {config}")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("templates")
@pass_context
def list_config_templates(ctx: Context) -> None:
    """
    List available configuration templates.

    \b
    Examples:
        playnite config templates
    """
    try:
        config_manager = ctx.get_config_manager()
        templates = config_manager.template_manager.list_templates()

        if ctx.json_output:
            ctx.output([{
                "name": t.name,
                "description": t.description,
                "platform": t.platform_type.value,
                "graphics": t.graphics_quality.value,
                "is_builtin": t.is_builtin,
            } for t in templates])
        else:
            table = Table(title="Configuration Templates")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            table.add_column("Platform")
            table.add_column("Graphics")

            for t in templates:
                table.add_row(
                    t.name,
                    t.description[:40] + "..." if len(t.description) > 40 else t.description,
                    t.platform_type.value,
                    t.graphics_quality.value,
                )

            ctx.output_table(table)

    except click.ClickException as e:
        if ctx.json_output:
            ctx.output({"error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("validate")
@click.option(
    "--game", "-g",
    required=True,
    help="Game name or ID"
)
@click.option(
    "--config", "-c",
    required=True,
    help="Configuration name"
)
@pass_context
def validate_config(ctx: Context, game: str, config: str) -> None:
    """
    Validate a configuration.

    Checks for common issues like invalid paths or incompatible settings.

    \b
    Examples:
        playnite config validate --game "Cyberpunk 2077" --config "Desktop"
    """
    try:
        config_manager = ctx.get_config_manager()

        # Find game and configuration
        game_repo = config_manager.game_repo
        game_obj = game_repo.get_by_name(game)
        if not game_obj:
            raise ValueError(f"Game not found: {game}")

        configs = config_manager.get_configurations_for_game(game_obj.id)
        configuration = None
        for c in configs:
            if c.name.lower() == config.lower():
                configuration = c
                break

        if not configuration:
            raise ValueError(f"Configuration not found: {config}")

        is_valid, errors = config_manager.validate_configuration(configuration.id)

        if ctx.json_output:
            ctx.output({
                "valid": is_valid,
                "errors": errors,
            })
        else:
            if is_valid:
                ctx.success(f"Configuration '{config}' is valid")
            else:
                ctx.error(f"Configuration '{config}' has issues:")
                for error in errors:
                    console.print(f"  - {error}")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@config.command("detect")
@pass_context
def detect_platform(ctx: Context) -> None:
    """
    Detect current platform and hardware.

    Shows detected hardware profile that would be used for
    automatic configuration selection.

    \b
    Examples:
        playnite config detect
    """
    from playnite_py.configurations.detection import PlatformDetector

    detector = PlatformDetector()
    profile = detector.get_hardware_profile()

    if ctx.json_output:
        ctx.output({
            "platform": profile.platform.value,
            "os": f"{profile.os_name} {profile.os_version}",
            "cpu": profile.cpu_name,
            "cpu_cores": profile.cpu_cores,
            "cpu_threads": profile.cpu_threads,
            "ram_mb": profile.ram_mb,
            "gpus": [{"name": g.name, "vendor": g.vendor.value} for g in profile.gpus],
            "displays": [
                {"name": d.name, "width": d.width, "height": d.height}
                for d in profile.displays
            ],
            "power_source": profile.power_source.value,
            "is_laptop": profile.is_laptop,
            "is_steam_deck": profile.is_steam_deck,
        })
    else:
        table = Table(title="Hardware Profile", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Detected Platform", f"[green]{profile.platform.value}[/green]")
        table.add_row("OS", f"{profile.os_name} {profile.os_version}")
        table.add_row("CPU", profile.cpu_name or "Unknown")
        table.add_row("Cores/Threads", f"{profile.cpu_cores} / {profile.cpu_threads}")
        table.add_row("RAM", f"{profile.ram_mb // 1024} GB")
        table.add_row("Power Source", profile.power_source.value)

        if profile.gpus:
            for i, gpu in enumerate(profile.gpus):
                table.add_row(f"GPU {i + 1}", f"{gpu.name} ({gpu.vendor.value})")

        if profile.displays:
            for i, display in enumerate(profile.displays):
                table.add_row(
                    f"Display {i + 1}",
                    f"{display.width}x{display.height} ({display.name})"
                )

        if profile.is_laptop:
            table.add_row("Type", "[yellow]Laptop[/yellow]")
        if profile.is_steam_deck:
            table.add_row("Device", "[blue]Steam Deck[/blue]")

        ctx.output_table(table)
