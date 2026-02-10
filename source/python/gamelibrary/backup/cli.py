"""CLI commands for backup and restore."""

from __future__ import annotations

import json
import click

from ..database import Database
from .engine import BackupEngine
from .restore import RestoreEngine
from .profiles import BackupProfileManager
from .scheduler import BackupScheduler
from .verification import verify_backup
from .disaster_recovery import DisasterRecovery
from .destinations import DestinationManager


def _output(data, as_json: bool):
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for k, v in item.items():
                        click.echo(f"  {k}: {v}")
                    click.echo("  ---")
                else:
                    click.echo(f"  {item}")


@click.group("backup")
@click.option("--db", "db_path", default=None, help="Database path")
@click.option("--backup-dir", default=None, help="Backup directory")
@click.option("--data-dir", default=None, help="Data directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def backup_cli(ctx, db_path, backup_dir, data_dir, as_json):
    """Backup and restore commands."""
    ctx.ensure_object(dict)
    db = Database(db_path) if db_path else Database()
    ctx.obj["db"] = db
    ctx.obj["json"] = as_json
    ctx.obj["backup_dir"] = backup_dir or str(db.get_db_path().parent / "backups")
    ctx.obj["data_dir"] = data_dir or str(db.get_db_path().parent / "data")


@backup_cli.command("create")
@click.option("--password", default=None, help="Encryption password")
@click.option("--profile", default=None, help="Backup profile name")
@click.option("--components", default=None, help="Comma-separated component list")
@click.option("--destinations", default=None, help="Comma-separated destination names")
@click.pass_context
def create_backup(ctx, password, profile, components, destinations):
    """Create a full backup."""
    db = ctx.obj["db"]
    engine = BackupEngine(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    comp_list = components.split(",") if components else None
    dest_list = destinations.split(",") if destinations else None

    if profile:
        profiles = BackupProfileManager(db)
        p = profiles.get_profile(profile)
        if not p:
            click.echo(f"Profile '{profile}' not found.")
            return
        record = engine.create_full_backup(
            password=password if p.encrypt else None,
            profile_id=p.id,
            components=comp_list,
            destinations=dest_list,
        )
    else:
        record = engine.create_full_backup(
            password=password, components=comp_list, destinations=dest_list,
        )

    _output(record.to_dict(), ctx.obj["json"])


@backup_cli.command("create-incremental")
@click.argument("parent_id", type=int)
@click.option("--password", default=None)
@click.option("--components", default=None, help="Comma-separated component list")
@click.pass_context
def create_incremental(ctx, parent_id, password, components):
    """Create an incremental backup based on a parent backup."""
    db = ctx.obj["db"]
    engine = BackupEngine(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    comp_list = components.split(",") if components else None
    record = engine.create_incremental_backup(parent_id, password, components=comp_list)
    _output(record.to_dict(), ctx.obj["json"])


@backup_cli.command("list")
@click.option("--limit", default=20)
@click.pass_context
def list_backups(ctx, limit):
    """List all backups."""
    db = ctx.obj["db"]
    engine = BackupEngine(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    backups = engine.list_backups(limit)
    _output([b.to_dict() for b in backups], ctx.obj["json"])


@backup_cli.command("report")
@click.argument("backup_id", type=int)
@click.pass_context
def backup_report(ctx, backup_id):
    """Show backup report with contents and size."""
    db = ctx.obj["db"]
    engine = BackupEngine(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    report = engine.get_backup_report(backup_id)
    _output(report.to_dict(), ctx.obj["json"])


@backup_cli.command("verify")
@click.argument("backup_path")
@click.pass_context
def verify_backup_cmd(ctx, backup_path):
    """Verify backup integrity."""
    result = verify_backup(backup_path)
    _output(result, ctx.obj["json"])


@backup_cli.command("restore")
@click.argument("backup_path")
@click.option("--password", default=None, help="Decryption password")
@click.option("--components", default=None, help="Comma-separated components to restore")
@click.pass_context
def restore_backup(ctx, backup_path, password, components):
    """Restore from a backup file."""
    db = ctx.obj["db"]
    restore = RestoreEngine(db, ctx.obj["data_dir"])
    comp_list = components.split(",") if components else None
    if comp_list:
        result = restore.restore_selective(backup_path, comp_list, password)
    else:
        result = restore.restore_full(backup_path, password)
    _output(result, ctx.obj["json"])


@backup_cli.command("contents")
@click.argument("backup_path")
@click.option("--password", default=None)
@click.pass_context
def list_contents(ctx, backup_path, password):
    """List backup contents without restoring."""
    db = ctx.obj["db"]
    restore = RestoreEngine(db, ctx.obj["data_dir"])
    result = restore.list_backup_contents(backup_path, password)
    _output(result, ctx.obj["json"])


@backup_cli.command("delete")
@click.argument("backup_id", type=int)
@click.confirmation_option(prompt="Delete this backup?")
@click.pass_context
def delete_backup(ctx, backup_id):
    """Delete a backup."""
    db = ctx.obj["db"]
    engine = BackupEngine(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    engine.delete_backup(backup_id)
    click.echo(f"Backup {backup_id} deleted.")


@backup_cli.command("cleanup")
@click.option("--max-age", default=30, help="Max age in days")
@click.option("--max-count", default=10, help="Max number of backups to keep")
@click.pass_context
def cleanup_backups(ctx, max_age, max_count):
    """Clean up old backups beyond retention policy."""
    db = ctx.obj["db"]
    engine = BackupEngine(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    engine.cleanup_old_backups(max_age, max_count)
    click.echo("Cleanup complete.")


# --- Profile commands ---

@backup_cli.group("profile")
@click.pass_context
def profile_group(ctx):
    """Manage backup profiles."""
    pass


@profile_group.command("create")
@click.argument("name")
@click.option("--description", default="")
@click.option("--schedule", default=None, help="Cron expression for schedule")
@click.option("--retention-days", default=30)
@click.option("--max-backups", default=10)
@click.option("--encrypt", is_flag=True)
@click.pass_context
def create_profile(ctx, name, description, schedule, retention_days, max_backups, encrypt):
    """Create a backup profile."""
    db = ctx.obj["db"]
    profiles = BackupProfileManager(db)
    profile = profiles.create_profile(
        name=name,
        description=description,
        schedule_cron=schedule,
        retention_days=retention_days,
        max_backups=max_backups,
        encrypt=encrypt,
    )
    _output(profile.to_dict(), ctx.obj["json"])


@profile_group.command("list")
@click.pass_context
def list_profiles(ctx):
    """List backup profiles."""
    db = ctx.obj["db"]
    profiles = BackupProfileManager(db)
    data = [p.to_dict() for p in profiles.list_profiles()]
    _output(data, ctx.obj["json"])


@profile_group.command("delete")
@click.argument("profile_id", type=int)
@click.pass_context
def delete_profile(ctx, profile_id):
    """Delete a backup profile."""
    db = ctx.obj["db"]
    profiles = BackupProfileManager(db)
    profiles.delete_profile(profile_id)
    click.echo(f"Profile {profile_id} deleted.")


@profile_group.command("run")
@click.argument("name")
@click.option("--password", default=None)
@click.pass_context
def run_profile(ctx, name, password):
    """Manually run a backup profile."""
    db = ctx.obj["db"]
    scheduler = BackupScheduler(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = scheduler.run_profile_backup(name, password)
    _output(result, ctx.obj["json"])


# --- Disaster recovery commands ---

@backup_cli.group("recovery")
@click.pass_context
def recovery_group(ctx):
    """Disaster recovery commands."""
    pass


@recovery_group.command("check")
@click.pass_context
def check_health(ctx):
    """Check database health."""
    db = ctx.obj["db"]
    dr = DisasterRecovery(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = dr.check_database_health()
    _output(result, ctx.obj["json"])


@recovery_group.command("recover")
@click.option("--password", default=None)
@click.pass_context
def recover(ctx, password):
    """Recover from most recent valid backup."""
    db = ctx.obj["db"]
    dr = DisasterRecovery(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = dr.recover_from_backup(password)
    _output(result, ctx.obj["json"])


@recovery_group.command("rebuild")
@click.confirmation_option(prompt="This will rebuild the database from scratch. Continue?")
@click.pass_context
def rebuild(ctx):
    """Rebuild database schema (last resort)."""
    db = ctx.obj["db"]
    dr = DisasterRecovery(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = dr.rebuild_database()
    _output(result, ctx.obj["json"])


@recovery_group.command("export")
@click.argument("output_path")
@click.option("--password", default=None)
@click.pass_context
def export_migration(ctx, output_path, password):
    """Export library data for migration."""
    db = ctx.obj["db"]
    dr = DisasterRecovery(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = dr.export_for_migration(output_path, password)
    _output(result, ctx.obj["json"])


@recovery_group.command("import")
@click.argument("import_path")
@click.option("--password", default=None)
@click.pass_context
def import_migration(ctx, import_path, password):
    """Import library data from a backup file."""
    db = ctx.obj["db"]
    dr = DisasterRecovery(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = dr.import_from_backup(import_path, password)
    _output(result, ctx.obj["json"])


@backup_cli.command("pre-update")
@click.option("--password", default=None)
@click.pass_context
def pre_update_backup(ctx, password):
    """Create automatic pre-update backup."""
    db = ctx.obj["db"]
    scheduler = BackupScheduler(db, ctx.obj["backup_dir"], ctx.obj["data_dir"])
    result = scheduler.create_pre_update_backup(password)
    _output(result, ctx.obj["json"])


# --- Destination management commands ---

@backup_cli.group("destination")
@click.pass_context
def destination_group(ctx):
    """Manage backup destinations."""
    pass


@destination_group.command("add")
@click.argument("name")
@click.option("--type", "dest_type", required=True, type=click.Choice(["local", "cloud"]),
              help="Destination type")
@click.option("--path", default=None, help="Filesystem path (for local destinations)")
@click.option("--provider", default=None, help="Cloud provider name (for cloud destinations)")
@click.option("--config", "extra_config", default="{}", help="Extra config JSON")
@click.pass_context
def add_destination(ctx, name, dest_type, path, provider, extra_config):
    """Register a backup destination."""
    import json as _json
    db = ctx.obj["db"]
    dest_mgr = DestinationManager(db)

    config = _json.loads(extra_config)
    if path:
        config["path"] = path
    if provider:
        config["provider"] = provider

    dest_id = dest_mgr.register_destination(name, dest_type, config)
    _output({"destination_id": dest_id, "name": name, "type": dest_type}, ctx.obj["json"])


@destination_group.command("list")
@click.pass_context
def list_destinations(ctx):
    """List registered backup destinations."""
    db = ctx.obj["db"]
    dest_mgr = DestinationManager(db)
    data = dest_mgr.list_destinations()
    _output(data, ctx.obj["json"])


@destination_group.command("remove")
@click.argument("name")
@click.pass_context
def remove_destination(ctx, name):
    """Remove a backup destination."""
    db = ctx.obj["db"]
    dest_mgr = DestinationManager(db)
    dest_mgr.remove_destination(name)
    click.echo(f"Destination '{name}' removed.")
