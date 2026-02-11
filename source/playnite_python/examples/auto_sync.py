"""
Auto Sync extension script.

Demonstrates a global action profile: after any game session ends, the script
runs an optional cloud sync command for configured games.

Also shows how to use the scheduler to run a periodic sync every hour.

Config (auto_sync.yaml)
------------------------
enabled: true
timeout: 60
sandbox_level: standard
metadata:
  author: Playnite Python Contributors
  version: 1.0
  description: Cloud sync after game sessions
"""

import subprocess
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration — customise sync commands per game fragment
# ---------------------------------------------------------------------------

SYNC_COMMANDS = {
    # Game name fragment → shell command to run
    # "Stardew Valley": "rclone sync ~/SaveGames/StardewValley gdrive:backups/stardew/",
    # "Celeste": "rsync -avz ~/celeste_saves/ user@server:backups/celeste/",
}

SYNC_LOG = __api__.paths.extension_data_path + "/sync.log"  # noqa: F821

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sync(command: str, game_name: str) -> bool:
    """Execute *command* and return True on success."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=55,
        )
        ts = datetime.now().isoformat(timespec="seconds")
        with open(SYNC_LOG, "a") as fh:
            fh.write(f"{ts} | {game_name} | exit={result.returncode}\n")
            if result.stdout:
                fh.write(f"  STDOUT: {result.stdout[:500]}\n")
            if result.stderr:
                fh.write(f"  STDERR: {result.stderr[:500]}\n")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        __logger.Warning(f"Sync timed out for '{game_name}'")  # noqa: F821
        return False
    except Exception as exc:
        __logger.Error(f"Sync error for '{game_name}': {exc}")  # noqa: F821
        return False


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

def on_script_loaded():
    __logger.Info("Auto Sync script loaded.")  # noqa: F821
    if not SYNC_COMMANDS:
        __logger.Info("No sync commands configured. Edit SYNC_COMMANDS in auto_sync.py.")  # noqa: F821


def on_game_stopped(game, elapsed_seconds):
    """Trigger sync after the game session ends."""
    matched_cmd = None
    for fragment, cmd in SYNC_COMMANDS.items():
        if fragment.lower() in game.name.lower():
            matched_cmd = cmd
            break

    if not matched_cmd:
        return  # Not a configured game

    __logger.Info(f"Running sync for '{game.name}'…")  # noqa: F821
    api.notifications.show(f"Syncing save data for {game.name}…", "info")  # noqa: F821

    success = _run_sync(matched_cmd, game.name)
    if success:
        api.notifications.show(f"Sync complete: {game.name}", "info")  # noqa: F821
        __logger.Info("Sync complete.")  # noqa: F821
    else:
        api.notifications.show(f"Sync failed for {game.name}!", "warning")  # noqa: F821
        __logger.Warning("Sync failed.")  # noqa: F821


def on_application_started():
    """Perform an initial sync sweep on startup."""
    count = sum(1 for _ in SYNC_COMMANDS)
    if count > 0:
        __logger.Info(f"Auto Sync ready — monitoring {count} game(s).")  # noqa: F821


# ---------------------------------------------------------------------------
# Menu entry: manual sync all
# ---------------------------------------------------------------------------

def sync_all():
    """Manually trigger sync for all configured games."""
    if not SYNC_COMMANDS:
        api.dialogs.show_message("No sync commands configured.", "Auto Sync")  # noqa: F821
        return
    results = []
    for fragment, cmd in SYNC_COMMANDS.items():
        ok = _run_sync(cmd, fragment)
        results.append(f"{fragment}: {'OK' if ok else 'FAILED'}")
    api.notifications.show("\n".join(results), "info")  # noqa: F821


__attributes__ = {
    "Author": "Playnite Python Contributors",
    "Version": "1.0",
}

__exports__ = [
    {"Name": "Sync All Games", "Function": "sync_all"},
]
