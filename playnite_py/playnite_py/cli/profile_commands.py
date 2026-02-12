"""
Profile management CLI commands for Playnite-Py.

This module provides CLI commands for managing library profiles.

Example:
    $ playnite profile create "Gaming"
    $ playnite profile list
    $ playnite profile switch "Gaming"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
from rich.table import Table

from playnite_py.cli.main import Context, pass_context, console


@click.group()
def profile() -> None:
    """
    Manage library profiles.

    \b
    Commands for creating, switching, and managing game library profiles.
    Each profile maintains its own isolated game library and settings.

    \b
    Examples:
        playnite profile create "Personal"
        playnite profile list
        playnite profile switch "Personal"
        playnite profile delete "Old Profile"
    """
    pass


# Alias for standalone use
profile_cli = profile


@profile.command("create")
@click.argument("name")
@click.option(
    "--description", "-d",
    default="",
    help="Profile description"
)
@click.option(
    "--template", "-t",
    help="Template to base profile on (default, kids, work, testing, family)"
)
@click.option(
    "--parent", "-p",
    help="Parent profile for inheritance"
)
@click.option(
    "--default",
    "set_default",
    is_flag=True,
    help="Set as default startup profile"
)
@pass_context
def create_profile(
    ctx: Context,
    name: str,
    description: str,
    template: Optional[str],
    parent: Optional[str],
    set_default: bool,
) -> None:
    """
    Create a new profile.

    Creates a new isolated game library profile with its own database,
    settings, and media files.

    \b
    Arguments:
        NAME  Name for the new profile

    \b
    Examples:
        playnite profile create "Gaming"
        playnite profile create "Kids" --template kids
        playnite profile create "Work" --description "Work-related games"
    """
    try:
        profile = ctx.profile_manager.create_profile(
            name=name,
            description=description,
            template=template,
            parent_profile=parent,
            set_as_default=set_default,
        )

        if ctx.json_output:
            ctx.output({
                "success": True,
                "profile": profile.to_dict(),
            })
        else:
            ctx.success(f"Created profile: {name}")
            if template:
                console.print(f"  Based on template: {template}")
            if set_default:
                console.print("  Set as default profile")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@profile.command("list")
@click.option(
    "--all", "-a",
    "show_all",
    is_flag=True,
    help="Show all details"
)
@pass_context
def list_profiles(ctx: Context, show_all: bool) -> None:
    """
    List all profiles.

    \b
    Examples:
        playnite profile list
        playnite profile list --all
        playnite --json profile list
    """
    profiles = ctx.profile_manager.list_profiles()

    if ctx.json_output:
        ctx.output([p.to_dict() for p in profiles])
    else:
        if not profiles:
            console.print("[dim]No profiles found. Create one with 'playnite profile create'[/dim]")
            return

        table = Table(title="Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Games", justify="right")
        table.add_column("Status")

        if show_all:
            table.add_column("Last Used")
            table.add_column("Playtime")

        for p in profiles:
            status_parts = []
            if p.is_active:
                status_parts.append("[green]active[/green]")
            if p.is_default:
                status_parts.append("[blue]default[/blue]")
            if p.security.password_protected:
                status_parts.append("[yellow]🔒[/yellow]")
            status = " ".join(status_parts) or "-"

            try:
                game_count = str(ctx.profile_manager.get_profile_game_count(p.name))
            except Exception:
                game_count = "-"

            row = [
                p.name,
                p.description[:40] + "..." if len(p.description) > 40 else p.description or "-",
                game_count,
                status,
            ]

            if show_all:
                last_used = p.statistics.last_used
                row.append(last_used.strftime("%Y-%m-%d") if last_used else "-")
                hours = p.statistics.total_playtime_minutes // 60
                row.append(f"{hours}h" if hours else "-")

            table.add_row(*row)

        ctx.output_table(table)


@profile.command("switch")
@click.argument("name")
@click.option(
    "--password", "-p",
    help="Password for protected profiles",
    hide_input=True,
)
@click.option(
    "--force", "-f",
    is_flag=True,
    help="Force switch even if profile is locked"
)
@pass_context
def switch_profile(
    ctx: Context,
    name: str,
    password: Optional[str],
    force: bool,
) -> None:
    """
    Switch to a different profile.

    Activates the specified profile without restarting the application.

    \b
    Arguments:
        NAME  Profile name to switch to

    \b
    Examples:
        playnite profile switch "Gaming"
        playnite profile switch "Personal" --password
    """
    try:
        profile = ctx.profile_manager.switch_profile(
            name=name,
            password=password,
            force=force,
        )

        if ctx.json_output:
            ctx.output({
                "success": True,
                "profile": profile.to_dict(),
            })
        else:
            ctx.success(f"Switched to profile: {name}")

    except (ValueError, PermissionError, RuntimeError) as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@profile.command("delete")
@click.argument("name")
@click.option(
    "--delete-data",
    is_flag=True,
    help="Also delete all profile data files"
)
@click.option(
    "--password", "-p",
    help="Password for protected profiles",
    hide_input=True,
)
@click.option(
    "--yes", "-y",
    is_flag=True,
    help="Skip confirmation prompt"
)
@pass_context
def delete_profile(
    ctx: Context,
    name: str,
    delete_data: bool,
    password: Optional[str],
    yes: bool,
) -> None:
    """
    Delete a profile.

    \b
    Arguments:
        NAME  Profile name to delete

    \b
    Examples:
        playnite profile delete "Old Profile"
        playnite profile delete "Test" --delete-data --yes
    """
    if not yes and not ctx.json_output:
        if delete_data:
            console.print(
                f"[red]Warning:[/red] This will permanently delete profile '{name}' "
                "and all its data."
            )
        if not click.confirm("Are you sure?"):
            raise SystemExit(0)

    try:
        ctx.profile_manager.delete_profile(
            name=name,
            delete_data=delete_data,
            password=password,
        )

        if ctx.json_output:
            ctx.output({"success": True, "deleted": name})
        else:
            ctx.success(f"Deleted profile: {name}")

    except (ValueError, PermissionError) as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@profile.command("info")
@click.argument("name")
@pass_context
def profile_info(ctx: Context, name: str) -> None:
    """
    Show detailed information about a profile.

    \b
    Arguments:
        NAME  Profile name

    \b
    Examples:
        playnite profile info "Gaming"
    """
    profile = ctx.profile_manager.get_profile(name)
    if not profile:
        if ctx.json_output:
            ctx.output({"error": f"Profile not found: {name}"})
        else:
            ctx.error(f"Profile not found: {name}")
        raise SystemExit(1)

    if ctx.json_output:
        ctx.output(profile.to_dict())
    else:
        table = Table(title=f"Profile: {profile.name}", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("ID", str(profile.id))
        table.add_row("Description", profile.description or "-")
        table.add_row("Active", "Yes" if profile.is_active else "No")
        table.add_row("Default", "Yes" if profile.is_default else "No")
        table.add_row("Password Protected", "Yes" if profile.security.password_protected else "No")
        table.add_row("Created", profile.statistics.created_at.strftime("%Y-%m-%d %H:%M"))
        table.add_row(
            "Last Used",
            profile.statistics.last_used.strftime("%Y-%m-%d %H:%M")
            if profile.statistics.last_used else "-"
        )
        table.add_row("Sessions", str(profile.statistics.session_count))
        table.add_row("Games", str(profile.statistics.game_count))
        table.add_row(
            "Playtime",
            f"{profile.statistics.total_playtime_minutes // 60}h "
            f"{profile.statistics.total_playtime_minutes % 60}m"
        )
        table.add_row("Theme", profile.settings.theme)
        table.add_row("Language", profile.settings.language)

        ctx.output_table(table)


@profile.command("export")
@click.argument("name")
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output file path"
)
@click.option(
    "--no-games",
    is_flag=True,
    help="Exclude game library"
)
@click.option(
    "--no-media",
    is_flag=True,
    help="Exclude media files"
)
@click.option(
    "--password", "-p",
    help="Encrypt export with password",
    hide_input=True,
)
@pass_context
def export_profile(
    ctx: Context,
    name: str,
    output: Path,
    no_games: bool,
    no_media: bool,
    password: Optional[str],
) -> None:
    """
    Export a profile for backup or migration.

    \b
    Arguments:
        NAME  Profile name to export

    \b
    Examples:
        playnite profile export "Gaming" --output ~/backup/gaming.ppf
        playnite profile export "Personal" -o backup.ppf --no-media
    """
    try:
        export_path = ctx.profile_manager.export_profile(
            name=name,
            output_path=output,
            include_games=not no_games,
            include_media=not no_media,
            password=password,
        )

        if ctx.json_output:
            ctx.output({
                "success": True,
                "path": str(export_path),
                "size_bytes": export_path.stat().st_size,
            })
        else:
            size_mb = export_path.stat().st_size / (1024 * 1024)
            ctx.success(f"Exported profile to: {export_path}")
            console.print(f"  Size: {size_mb:.1f} MB")

    except (ValueError, FileNotFoundError) as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@profile.command("import")
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--name", "-n",
    help="Override profile name"
)
@click.option(
    "--password", "-p",
    help="Decryption password",
    hide_input=True,
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing profile with same name"
)
@pass_context
def import_profile(
    ctx: Context,
    path: Path,
    name: Optional[str],
    password: Optional[str],
    overwrite: bool,
) -> None:
    """
    Import a profile from an export file.

    \b
    Arguments:
        PATH  Path to the export file (.ppf)

    \b
    Examples:
        playnite profile import ~/backup/gaming.ppf
        playnite profile import backup.ppf --name "New Gaming"
    """
    try:
        profile = ctx.profile_manager.import_profile(
            import_path=path,
            new_name=name,
            password=password,
            overwrite=overwrite,
        )

        if ctx.json_output:
            ctx.output({
                "success": True,
                "profile": profile.to_dict(),
            })
        else:
            ctx.success(f"Imported profile: {profile.name}")

    except (ValueError, FileNotFoundError) as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@profile.command("set-password")
@click.argument("name")
@click.option(
    "--current-password",
    help="Current password (if already protected)",
    hide_input=True,
)
@pass_context
def set_password(
    ctx: Context,
    name: str,
    current_password: Optional[str],
) -> None:
    """
    Set or change password for a profile.

    \b
    Arguments:
        NAME  Profile name

    \b
    Examples:
        playnite profile set-password "Personal"
    """
    new_password = click.prompt("New password", hide_input=True, confirmation_prompt=True)

    try:
        ctx.profile_manager.set_profile_password(
            name=name,
            password=new_password,
            current_password=current_password,
        )

        if ctx.json_output:
            ctx.output({"success": True})
        else:
            ctx.success(f"Password set for profile: {name}")

    except (ValueError, PermissionError) as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)


@profile.command("templates")
@pass_context
def list_templates(ctx: Context) -> None:
    """
    List available profile templates.

    \b
    Examples:
        playnite profile templates
    """
    from playnite_py.profiles.templates import ProfileTemplateManager

    templates = ctx.profile_manager.template_manager.list_templates()

    if ctx.json_output:
        ctx.output([{
            "name": t.name,
            "description": t.description,
            "is_builtin": t.is_builtin,
        } for t in templates])
    else:
        table = Table(title="Profile Templates")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Type")

        for t in templates:
            table.add_row(
                t.name,
                t.description,
                "[blue]builtin[/blue]" if t.is_builtin else "custom",
            )

        ctx.output_table(table)


@profile.command("set-default")
@click.argument("name")
@pass_context
def set_default_cmd(ctx: Context, name: str) -> None:
    """
    Set a profile as the default startup profile.

    \b
    Arguments:
        NAME  Profile name

    \b
    Examples:
        playnite profile set-default "Personal"
    """
    try:
        ctx.profile_manager.set_default_profile(name)

        if ctx.json_output:
            ctx.output({"success": True, "default": name})
        else:
            ctx.success(f"Set default profile: {name}")

    except ValueError as e:
        if ctx.json_output:
            ctx.output({"success": False, "error": str(e)})
        else:
            ctx.error(str(e))
        raise SystemExit(1)
