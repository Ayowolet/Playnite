"""
Game Save Backup extension script.

Automatically backs up a game's save directory before each play session.
Keeps the last N backups per game and cleans up older ones automatically.

Config (game_backup.yaml)
--------------------------
enabled: true
timeout: 30
sandbox_level: standard
metadata:
  author: Playnite Python Contributors
  version: 1.0
  description: Automatic save backup before launch
"""

import shutil
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKUP_ROOT = Path.home() / ".playnite_python" / "backups"
MAX_BACKUPS_PER_GAME = 5

# Mapping of game name fragment → save directory (customise for your games)
SAVE_DIRS = {
    # "Celeste": "~/AppData/Local/Celeste/Saves",
    # "Stardew Valley": "~/AppData/Roaming/StardewValley",
    # Add your games here or use install_directory fallback
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_save_dir(game) -> Path | None:
    """Attempt to locate the game's save directory."""
    # Check explicit mapping first
    for fragment, path_str in SAVE_DIRS.items():
        if fragment.lower() in game.name.lower():
            p = Path(path_str).expanduser()
            if p.exists():
                return p

    # Fallback: look for a "saves" or "savegames" folder in install dir
    if game.install_directory:
        install = Path(game.install_directory)
        for candidate in ("saves", "savegames", "save", "SaveGames"):
            p = install / candidate
            if p.exists():
                return p
    return None


def _prune_old_backups(game_backup_dir: Path) -> None:
    """Remove oldest backups exceeding MAX_BACKUPS_PER_GAME."""
    backups = sorted(game_backup_dir.glob("*"), key=lambda p: p.stat().st_mtime)
    while len(backups) > MAX_BACKUPS_PER_GAME:
        oldest = backups.pop(0)
        try:
            shutil.rmtree(str(oldest))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

def on_script_loaded():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    __logger.Info(f"Game Backup script ready — root: {BACKUP_ROOT}")  # noqa: F821


def on_game_starting(game):
    """Back up saves before the game starts."""
    save_dir = _find_save_dir(game)
    if save_dir is None:
        __logger.Debug(f"No save directory found for '{game.name}', skipping backup.")  # noqa: F821
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in game.name)
    dest = BACKUP_ROOT / safe_name / ts

    try:
        shutil.copytree(str(save_dir), str(dest))
        __logger.Info(f"Backed up saves: {save_dir} → {dest}")  # noqa: F821
        # Prune old backups
        _prune_old_backups(BACKUP_ROOT / safe_name)
        api.notifications.show(f"Saves backed up for {game.name}", "info")  # noqa: F821
    except Exception as exc:
        __logger.Warning(f"Backup failed for '{game.name}': {exc}")  # noqa: F821


# ---------------------------------------------------------------------------
# Menu: restore latest backup
# ---------------------------------------------------------------------------

def restore_latest_backup():
    """Prompt user to choose a game and restore its most recent backup."""
    games = api.database.get_installed_games()  # noqa: F821
    if not games:
        api.notifications.show("No installed games found.", "warning")  # noqa: F821
        return

    game_name = api.dialogs.show_input("Enter game name to restore backup for:")  # noqa: F821
    if not game_name:
        return

    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in game_name)
    game_backup_dir = BACKUP_ROOT / safe_name
    if not game_backup_dir.exists():
        api.notifications.show(f"No backups found for '{game_name}'.", "warning")  # noqa: F821
        return

    backups = sorted(game_backup_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        api.notifications.show("No backups available.", "warning")  # noqa: F821
        return

    latest = backups[0]
    # Find the game and its save dir
    matching = [g for g in games if game_name.lower() in g.name.lower()]
    if not matching:
        api.notifications.show(f"Game '{game_name}' not found in library.", "warning")  # noqa: F821
        return

    save_dir = _find_save_dir(matching[0])
    if save_dir is None:
        api.notifications.show("Cannot determine save directory.", "warning")  # noqa: F821
        return

    confirm = api.dialogs.show_yes_no(  # noqa: F821
        f"Restore '{latest.name}' to {save_dir}? This will overwrite current saves!"
    )
    if not confirm:
        return

    try:
        if save_dir.exists():
            shutil.rmtree(str(save_dir))
        shutil.copytree(str(latest), str(save_dir))
        api.notifications.show(f"Restored backup: {latest.name}", "info")  # noqa: F821
        __logger.Info(f"Restored {latest} → {save_dir}")  # noqa: F821
    except Exception as exc:
        api.notifications.show(f"Restore failed: {exc}", "error")  # noqa: F821
        __logger.Error(f"Restore error: {exc}")  # noqa: F821


__exports = [
    {"Name": "Restore Latest Backup", "Function": "restore_latest_backup"},
]
