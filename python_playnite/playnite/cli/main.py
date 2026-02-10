"""Main CLI entry point for Python Playnite.

Usage:
  playnite --help
  playnite achievements sync
  playnite backup create --destination ~/backups
  playnite config show
  playnite config set steam.api_key MYKEY

Pass --data-dir to use a non-default data directory.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from playnite.cli.achievement_cli import achievements_group
from playnite.cli.backup_cli import backup_group
from playnite.config import Config
from playnite.database.connection import DatabaseManager

console = Console(stderr=True)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(package_name="python-playnite", prog_name="playnite")
@click.option("--data-dir", default=None, help="Override default data directory")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, data_dir: str | None, verbose: bool) -> None:
    """Python Playnite — game library manager with achievement tracking and backup."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)

    config = Config.load()
    if data_dir:
        config.data_dir = data_dir
        config.database_path = str(Path(data_dir) / "playnite.db")

    config.ensure_dirs()

    db = DatabaseManager(config.database_path)
    db.init_db()

    ctx.obj["config"] = config
    ctx.obj["db"] = db


# Register sub-command groups
cli.add_command(achievements_group)
cli.add_command(backup_group)


# ------------------------------------------------------------------
# config commands
# ------------------------------------------------------------------


@cli.group("config")
def config_group() -> None:
    """Application configuration commands."""


@config_group.command("show")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def config_show(ctx, output_json) -> None:
    """Display current configuration."""
    from dataclasses import asdict

    config: Config = ctx.obj["config"]
    data = asdict(config)

    # Redact sensitive fields
    for section in ("steam", "xbox", "psn", "gog"):
        for key in ("api_key", "npsso_token", "client_secret", "access_token", "refresh_token"):
            if key in data.get(section, {}):
                v = data[section][key]
                data[section][key] = f"{'*' * max(0, len(v) - 4)}{v[-4:]}" if v else ""

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    for section, values in data.items():
        if isinstance(values, dict):
            console.print(f"\n[bold][{section}][/bold]")
            for k, v in values.items():
                console.print(f"  {k} = {v!r}")
        else:
            console.print(f"{section} = {values!r}")


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx, key, value) -> None:
    """Set a configuration value.

    KEY should be dot-separated, e.g. steam.api_key or steam.enabled
    """
    config: Config = ctx.obj["config"]
    parts = key.split(".", 1)
    if len(parts) == 2:
        section, attr = parts
        section_obj = getattr(config, section, None)
        if section_obj is None:
            console.print(f"[red]Unknown section: {section}[/red]")
            sys.exit(1)
        # Type coercion
        existing = getattr(section_obj, attr, None)
        if isinstance(existing, bool):
            value = value.lower() in ("true", "1", "yes")
        elif isinstance(existing, int):
            value = int(value)
        elif isinstance(existing, float):
            value = float(value)
        setattr(section_obj, attr, value)
    else:
        existing = getattr(config, key, None)
        if isinstance(existing, bool):
            value = value.lower() in ("true", "1", "yes")
        setattr(config, key, value)

    config.save()
    console.print(f"[green]Set {key} = {value!r}[/green]")


# ------------------------------------------------------------------
# db management
# ------------------------------------------------------------------


@cli.command("init-db")
@click.pass_context
def init_db_cmd(ctx) -> None:
    """Initialise the database schema (idempotent)."""
    db: DatabaseManager = ctx.obj["db"]
    db.init_db()
    console.print("[green]Database initialised.[/green]")


@cli.command("disaster-recovery")
@click.argument("backup_path", type=click.Path(exists=True))
@click.option("--destination", "-d", default=None)
@click.option("--password", "-p", default=None)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def disaster_recovery_cmd(ctx, backup_path, destination, password, output_json) -> None:
    """Disaster recovery mode: restore directly from a backup archive file.

    Use this when the database is corrupt or missing and standard restore
    cannot find the backup record.
    """
    import json as _json
    import shutil
    import tempfile
    import zipfile

    config: Config = ctx.obj["config"]
    dest = Path(destination or config.data_dir)
    dest.mkdir(parents=True, exist_ok=True)

    archive = Path(backup_path)
    pw = password

    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = Path(tmp) / "extracted"
        archive_to_use = archive

        # Decrypt if needed
        if archive.suffix == ".pnbe":
            if pw is None:
                from getpass import getpass
                pw = getpass("Backup password: ")
            from playnite.backup.encryption import decrypt_file
            plain_zip = Path(tmp) / "backup.zip"
            decrypt_file(archive, plain_zip, pw)
            archive_to_use = plain_zip

        try:
            from playnite.backup.utils import safe_extract_zip
            with zipfile.ZipFile(archive_to_use, "r") as zf:
                try:
                    safe_extract_zip(zf, extract_dir)
                except ValueError as path_exc:
                    console.print(f"[red]Security error: {path_exc}[/red]")
                    sys.exit(1)
        except zipfile.BadZipFile as exc:
            console.print(f"[red]Invalid archive: {exc}[/red]")
            sys.exit(1)

        # Restore all available content
        items_restored = 0
        for item_dir in sorted(extract_dir.iterdir()):
            if item_dir.name == "manifest.json":
                continue
            if item_dir.is_dir():
                dst_dir = dest / item_dir.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                for src_file in sorted(item_dir.rglob("*")):
                    if src_file.is_file():
                        rel = src_file.relative_to(item_dir)
                        dst_file = dst_dir / rel
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        items_restored += 1

    if output_json:
        click.echo(_json.dumps({"success": True, "items_restored": items_restored, "destination": str(dest)}))
        return

    console.print("[green]Disaster recovery complete![/green]")
    console.print(f"  Items restored: {items_restored}")
    console.print(f"  Target: {dest}")
    console.print("\n[yellow]Re-run 'playnite init-db' to re-initialise the database.[/yellow]")


if __name__ == "__main__":
    cli()
