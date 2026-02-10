"""CLI commands for backup and restore operations.

Usage examples:
  playnite backup create --destination ~/backups
  playnite backup create --encrypted --destination ~/backups
  playnite backup create --incremental --parent-id 1
  playnite backup restore 3
  playnite backup restore 3 --categories database config
  playnite backup verify 3
  playnite backup list
  playnite backup delete 3
  playnite backup report 3
  playnite backup profile create --name daily --cron "0 2 * * *" --destination ~/backups
  playnite backup profile list
  playnite backup export ~/library.json
  playnite backup import ~/library.json
"""

from __future__ import annotations

import json
import sys
from getpass import getpass
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

from playnite.backup.manager import BackupManager
from playnite.backup.profiles import BackupProfileManager

if TYPE_CHECKING:
    from playnite.config import Config
    from playnite.database.connection import DatabaseManager

console = Console()


def _get_password(password: str | None, required: bool = False) -> str | None:
    """Prompt for password if not supplied on command line."""
    if password:
        return password
    if required:
        return getpass("Backup password: ")
    return None


@click.group("backup")
def backup_group() -> None:
    """Backup and restore commands."""


# ------------------------------------------------------------------
# create
# ------------------------------------------------------------------


@backup_group.command("create")
@click.option("--destination", "-d", default=None, help="Backup destination directory")
@click.option("--encrypted", "-e", is_flag=True, help="Encrypt the backup")
@click.option("--password", "-p", default=None, help="Encryption password (prompted if omitted)")
@click.option("--label", "-l", default=None, help="Human-readable label")
@click.option(
    "--incremental", "-i", is_flag=True, default=False, help="Create incremental backup",
)
@click.option("--parent-id", type=int, default=None, help="Parent backup ID (for incremental)")
@click.option("--profile", type=int, default=None, help="Backup profile ID")
@click.option(
    "--categories",
    "-c",
    multiple=True,
    help="Categories to include (repeat for multiple)",
)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def create_cmd(ctx, destination, encrypted, password, label, incremental, parent_id, profile, categories, output_json) -> None:
    """Create a full or incremental backup."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)

    pw = _get_password(password, required=encrypted)
    cats = set(categories) if categories else None

    if incremental:
        if parent_id is None:
            # Use most recent backup as parent
            backups = mgr.list_backups()
            if not backups:
                console.print("[red]No existing backups to use as parent.[/red]")
                sys.exit(1)
            parent_id = backups[0]["id"]
            console.print(f"Using most recent backup (id={parent_id}) as parent")
        result = mgr.create_incremental_backup(
            parent_backup_id=parent_id,
            destination=destination,
            password=pw,
            label=label,
        )
    else:
        result = mgr.create_full_backup(
            destination=destination,
            password=pw,
            label=label,
            profile_id=profile,
            categories=cats,
        )

    if output_json:
        click.echo(json.dumps(vars(result), indent=2, default=str))
        return

    if result.success:
        console.print("[green]Backup created successfully![/green]")
        console.print(f"  ID: {result.job_id}")
        console.print(f"  Path: {result.backup_path}")
        console.print(f"  Size: {result.compressed_size:,} bytes (original: {result.total_size:,})")
        console.print(f"  Encrypted: {result.encrypted}")
        console.print(f"  Checksum: {result.checksum[:16]}…")
    else:
        console.print(f"[red]Backup failed: {result.error}[/red]")
        sys.exit(1)


# ------------------------------------------------------------------
# restore
# ------------------------------------------------------------------


@backup_group.command("restore")
@click.argument("backup_id", type=int)
@click.option("--destination", "-d", default=None, help="Restore target directory")
@click.option(
    "--categories",
    "-c",
    multiple=True,
    help="Selectively restore only these categories",
)
@click.option("--password", "-p", default=None)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def restore_cmd(ctx, backup_id, destination, categories, password, output_json) -> None:
    """Restore from a backup."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)

    # Check if backup is encrypted to prompt for password
    backups = {b["id"]: b for b in mgr.list_backups()}
    backup_info = backups.get(backup_id)
    if backup_info and backup_info.get("encrypted") and not password:
        password = getpass(f"Password for backup {backup_id}: ")

    cats = set(categories) if categories else None
    result = mgr.restore_backup(
        backup_id=backup_id,
        destination=destination,
        categories=cats,
        password=password,
    )

    if output_json:
        click.echo(json.dumps(vars(result), indent=2, default=str))
        return

    if result.success:
        selective = f" (selective: {', '.join(sorted(cats))})" if cats else ""
        console.print(f"[green]Restore completed!{selective}[/green]")
        console.print(f"  Items restored: {result.items_restored}")
    else:
        console.print(f"[red]Restore failed: {result.error}[/red]")
        sys.exit(1)


# ------------------------------------------------------------------
# verify
# ------------------------------------------------------------------


@backup_group.command("verify")
@click.argument("backup_id", type=int)
@click.option("--password", "-p", default=None)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def verify_cmd(ctx, backup_id, password, output_json) -> None:
    """Verify backup integrity."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)

    # Prompt for password if backup is encrypted
    backups = {b["id"]: b for b in mgr.list_backups()}
    info = backups.get(backup_id)
    if info and info.get("encrypted") and not password:
        password = getpass(f"Password for backup {backup_id}: ")

    result = mgr.verify_backup(backup_id, password=password)

    if output_json:
        click.echo(json.dumps(result, indent=2))
        return

    status = "[green]PASSED[/green]" if result["passed"] else "[red]FAILED[/red]"
    console.print(f"\nVerification result: {status}")
    for check in result.get("checks", []):
        icon = "[green]✓[/green]" if check["passed"] else "[red]✗[/red]"
        console.print(f"  {icon} {check['name']}: {check['detail']}")

    if not result["passed"]:
        sys.exit(1)


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


@backup_group.command("list")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def list_cmd(ctx, output_json) -> None:
    """List all backups."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)
    backups = mgr.list_backups()

    if output_json:
        click.echo(json.dumps(backups, indent=2, default=str))
        return

    if not backups:
        console.print("[yellow]No backups found.[/yellow]")
        return

    t = Table(title="Backups")
    t.add_column("ID", justify="right")
    t.add_column("Type")
    t.add_column("Label")
    t.add_column("Created")
    t.add_column("Size", justify="right")
    t.add_column("Enc.")
    t.add_column("Status")
    for b in backups:
        t.add_row(
            str(b["id"]),
            b["type"],
            b.get("label") or "",
            (b["created_at"] or "")[:19],
            f"{(b['compressed_size'] or 0) // 1024}K",
            "Y" if b["encrypted"] else "N",
            b.get("status", ""),
        )
    console.print(t)


# ------------------------------------------------------------------
# delete
# ------------------------------------------------------------------


@backup_group.command("delete")
@click.argument("backup_id", type=int)
@click.option("--keep-file", is_flag=True, help="Keep the archive file on disk")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def delete_cmd(ctx, backup_id, keep_file, output_json) -> None:
    """Delete a backup record (and optionally its archive)."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)
    deleted = mgr.delete_backup(backup_id, delete_file=not keep_file)

    if output_json:
        click.echo(json.dumps({"deleted": deleted, "backup_id": backup_id}))
        return

    if deleted:
        console.print(f"[green]Backup {backup_id} deleted.[/green]")
    else:
        console.print(f"[red]Backup {backup_id} not found.[/red]")
        sys.exit(1)


# ------------------------------------------------------------------
# report
# ------------------------------------------------------------------


@backup_group.command("report")
@click.argument("backup_id", type=int)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def report_cmd(ctx, backup_id, output_json) -> None:
    """Generate a report for a backup."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)
    report = mgr.generate_report(backup_id)

    if output_json:
        click.echo(json.dumps(report, indent=2, default=str))
        return

    if not report:
        console.print(f"[red]Backup {backup_id} not found.[/red]")
        sys.exit(1)

    console.print(f"[bold]Backup Report — ID {backup_id}[/bold]")
    console.print(f"  Type: {report['type']}")
    console.print(f"  Label: {report.get('label') or 'none'}")
    console.print(f"  Created: {report.get('created_at', '')[:19]}")
    console.print(f"  Total size: {report['total_size']:,} bytes")
    console.print(f"  Compressed: {report['compressed_size']:,} bytes")
    ratio = report.get("compression_ratio")
    if ratio:
        console.print(f"  Compression ratio: {ratio:.1%}")
    console.print(f"  Encrypted: {report['encrypted']}")
    console.print(f"  Files: {report.get('file_count', 0)}")
    if report.get("categories"):
        console.print("\n  Categories:")
        for cat, info in report["categories"].items():
            console.print(f"    {cat}: {info['count']} files, {info['size']:,} bytes")


# ------------------------------------------------------------------
# export / import
# ------------------------------------------------------------------


@backup_group.command("export")
@click.argument("output_path", type=click.Path())
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def export_cmd(ctx, output_path, output_json) -> None:
    """Export the game library to a portable JSON file."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)
    checksum = mgr.export_library(Path(output_path))

    if output_json:
        click.echo(json.dumps({"path": output_path, "checksum": checksum}))
        return

    console.print(f"[green]Library exported to {output_path}[/green]")
    console.print(f"  SHA-256: {checksum[:32]}…")


@backup_group.command("import")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def import_cmd(ctx, input_path, output_json) -> None:
    """Import a library from a previously exported JSON file."""
    config: Config = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    mgr = BackupManager(config, db)
    count = mgr.import_library(Path(input_path))

    if output_json:
        click.echo(json.dumps({"imported": count, "source": input_path}))
        return

    console.print(f"[green]Imported {count} achievements from {input_path}[/green]")


# ------------------------------------------------------------------
# profile sub-group
# ------------------------------------------------------------------


@backup_group.group("profile")
def profile_group() -> None:
    """Manage backup profiles."""


@profile_group.command("create")
@click.option("--name", "-n", required=True)
@click.option("--cron", default=None, help="Cron schedule, e.g. '0 2 * * *'")
@click.option("--destination", "-d", multiple=True, help="Destination path (repeat for multiple)")
@click.option("--encrypt", is_flag=True)
@click.option("--retention-days", type=int, default=30, show_default=True)
@click.option("--max-count", type=int, default=10, show_default=True)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def profile_create_cmd(ctx, name, cron, destination, encrypt, retention_days, max_count, output_json) -> None:
    """Create a new backup profile."""
    db: DatabaseManager = ctx.obj["db"]
    pm = BackupProfileManager(db)
    profile_id = pm.create_profile(
        name=name,
        destinations=list(destination),
        schedule_cron=cron,
        encrypt=encrypt,
        max_retention_days=retention_days,
        max_backup_count=max_count,
    )

    if output_json:
        click.echo(json.dumps({"id": profile_id, "name": name}))
        return

    console.print(f"[green]Profile '{name}' created (id={profile_id})[/green]")


@profile_group.command("list")
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def profile_list_cmd(ctx, output_json) -> None:
    """List all backup profiles."""
    db: DatabaseManager = ctx.obj["db"]
    pm = BackupProfileManager(db)
    profiles = pm.list_profiles()

    if output_json:
        click.echo(json.dumps(profiles, indent=2, default=str))
        return

    if not profiles:
        console.print("[yellow]No profiles configured.[/yellow]")
        return

    t = Table(title="Backup Profiles")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Schedule")
    t.add_column("Destinations")
    t.add_column("Enc.")
    t.add_column("Retention")
    for p in profiles:
        t.add_row(
            str(p["id"]),
            p["name"],
            p.get("schedule_cron") or "manual",
            ", ".join(p.get("destinations", [])) or "default",
            "Y" if p["encrypt"] else "N",
            f"{p['max_retention_days']}d / {p['max_backup_count']} max",
        )
    console.print(t)


@profile_group.command("delete")
@click.argument("profile_id", type=int)
@click.option("--json", "output_json", is_flag=True)
@click.pass_context
def profile_delete_cmd(ctx, profile_id, output_json) -> None:
    """Delete a backup profile."""
    db: DatabaseManager = ctx.obj["db"]
    pm = BackupProfileManager(db)
    deleted = pm.delete_profile(profile_id)

    if output_json:
        click.echo(json.dumps({"deleted": deleted, "profile_id": profile_id}))
        return

    if deleted:
        console.print(f"[green]Profile {profile_id} deleted.[/green]")
    else:
        console.print(f"[red]Profile {profile_id} not found.[/red]")
        sys.exit(1)
