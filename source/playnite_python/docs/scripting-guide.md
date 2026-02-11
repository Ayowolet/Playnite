# Scripting Guide

This guide covers everything needed to write, configure, and distribute Python extension scripts for Playnite Python.

## Contents

- [Overview](#overview)
- [Script Layout](#script-layout)
- [Configuration File](#configuration-file)
- [Injected Globals](#injected-globals)
- [Lifecycle Hooks](#lifecycle-hooks)
- [SDK Reference](#sdk-reference)
- [Exporting Menu Items](#exporting-menu-items)
- [Dependencies](#dependencies)
- [Sandbox Levels](#sandbox-levels)
- [Hot Reload](#hot-reload)
- [Metrics and Logging](#metrics-and-logging)
- [Marketplace Distribution](#marketplace-distribution)
- [Full Example](#full-example)

---

## Overview

A script is a plain `.py` file placed in the extensions directory (default: `~/.playnite_python/extensions/`). When loaded, the script manager executes the file and scans its global namespace for lifecycle hook functions. Hooks fire automatically when the corresponding application or game event occurs.

Scripts are isolated from each other. An exception in one script does not prevent others from receiving the same event.

---

## Script Layout

```
~/.playnite_python/extensions/
├── my_script.py          # Script file
└── my_script.yaml        # Optional configuration (same stem as script)
```

A minimal script:

```python
def on_application_started():
    __logger.Info("My script is running!")
```

A script with multiple hooks:

```python
def on_script_loaded():
    __logger.Info("Script loaded and ready.")

def on_game_starting(game):
    __logger.Info(f"Starting: {game.name}")

def on_game_stopped(game, elapsed_seconds):
    minutes = elapsed_seconds / 60
    __logger.Info(f"Played {game.name} for {minutes:.1f} minutes")
```

---

## Configuration File

Each script can have an optional `<script_name>.yaml` companion file in the same directory. Missing or invalid YAML falls back to safe defaults.

```yaml
enabled: true               # Load this script (default: true)
timeout: 30                 # Hook execution timeout in seconds (0 = no limit)
sandbox_level: standard     # none | standard | strict

# Required paths for filesystem access under 'strict' sandbox
allowed_paths:
  - /home/user/games
  - ~/game_backups

# pip-installable dependencies (installed into an isolated venv per script)
dependencies:
  - requests>=2.28
  - pypresence

# Arbitrary metadata (shown in marketplace listings)
metadata:
  author: Jane Doe
  version: 1.2
  description: Tracks play sessions and exports to CSV

# Marketplace registration (optional)
marketplace:
  id: jane.playtime-tracker
  repository: https://example.com/scripts.json
```

### Configuration Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Whether to load the script |
| `timeout` | int | `30` | Seconds before hook is timed out (0 = unlimited) |
| `sandbox_level` | string | `standard` | `none`, `standard`, or `strict` |
| `allowed_paths` | list | `[]` | Filesystem paths accessible under `strict` sandbox |
| `dependencies` | list | `[]` | pip specifiers for required packages |
| `metadata` | dict | `{}` | Arbitrary key/value pairs |
| `marketplace` | dict | `{}` | Marketplace registration info |

---

## Injected Globals

The script manager injects the following names into every script's global namespace before execution:

| Name | Type | Description |
|---|---|---|
| `__api__` | `PlayniteSDK` | Full SDK — database, notifications, dialogs, paths |
| `api` | `PlayniteSDK` | Alias for `__api__` |
| `__logger` | `ScriptLogger` | Per-script logger with `Info`, `Warning`, `Error`, `Debug` methods |
| `__logger__` | `ScriptLogger` | Alias for `__logger` |
| `__stop__` | `threading.Event` | Set when the script is being unloaded or timed out; check periodically in long-running code |
| `__script_name__` | str | Name of the current script (stem of filename) |
| `__script_path__` | str | Absolute path to the script file |

```python
# Using the logger
__logger.Info("Informational message")
__logger.Warning("Something unexpected happened")
__logger.Error("Something failed")
__logger.Debug("Verbose diagnostic info")

# Using the SDK
games = __api__.database.get_games()
__api__.notifications.show("Hello!", "info")

# Checking for stop signal in a loop
import time
while not __stop__.is_set():
    time.sleep(1)
    # do work
```

---

## Lifecycle Hooks

A script opts into a hook by defining a function with the exact name listed below at **module level**. All hooks are optional — define only the ones you need.

### Application Hooks

| Function | Signature | When it fires |
|---|---|---|
| `on_application_started` | `()` | After all scripts are loaded and the application is ready |
| `on_application_stopped` | `()` | Before the application exits |
| `on_library_updated` | `()` | After the game library is refreshed/imported |
| `on_script_loaded` | `(script_name: str)` | After any script (including this one) is loaded |
| `on_script_unloaded` | `(script_name: str)` | Before any script is unloaded |

### Game Hooks

| Function | Signature | When it fires |
|---|---|---|
| `on_game_starting` | `(game: Game)` | Just before a game's launch sequence begins |
| `on_game_started` | `(game: Game)` | After the game process is confirmed running |
| `on_game_stopped` | `(game: Game, elapsed_seconds: float)` | After the game process exits |
| `on_game_installed` | `(game: Game)` | After a game is installed |
| `on_game_uninstalled` | `(game: Game)` | After a game is uninstalled |
| `on_game_startup_cancelled` | `(game: Game)` | When a game launch is cancelled before it starts |
| `on_game_installation_cancelled` | `(game: Game)` | When an installation is cancelled mid-way |
| `on_game_selected` | `(game: Game \| None)` | When a game is selected in the UI; `None` on deselection |
| `on_settings_changed` | `()` | After application settings are saved |

### Game Object Fields

The `game` parameter passed to game-level hooks is a `Game` dataclass:

```python
game.id              # str — UUID
game.name            # str
game.is_installed    # bool
game.install_directory  # str
game.play_time       # int — total seconds played
game.is_favorite     # bool
game.platform_ids    # list[str]
game.genre_ids       # list[str]
game.tag_ids         # list[str]
game.last_activity   # datetime | None
```

---

## SDK Reference

The `PlayniteSDK` object (`__api__`) exposes sub-APIs:

### `__api__.database`

```python
# Get all games
games = __api__.database.get_games()

# Get a game by ID
game = __api__.database.get_game("some-uuid")

# Search by name
results = __api__.database.search_games("celeste")

# Update a game
game.is_favorite = True
__api__.database.update_game(game)

# Add a game
from playnite_python.models.game import Game
new_game = Game(name="My Game", is_installed=True)
__api__.database.add_game(new_game)

# Remove a game
__api__.database.remove_game(game.id)
```

### `__api__.notifications`

```python
# Rich notification with a unique ID (allows later removal)
__api__.notifications.add("sync-done", "Sync complete!", NotificationType.INFO)
__api__.notifications.add(
    "sync-fail", "Sync failed!", NotificationType.ERROR,
    action=lambda: open_log_viewer(),   # optional click callback
)

# Remove by ID
__api__.notifications.remove("sync-done")
__api__.notifications.remove_all()

# Inspect current notifications
msgs = __api__.notifications.messages   # List[NotificationMessage]
count = __api__.notifications.count

# Simple shorthand (backward-compatible)
__api__.notifications.show("Sync complete!", "info")
__api__.notifications.show("Critical error.", "error")
```

Notification types via `NotificationType`: `INFO`, `ERROR`.

### `__api__.dialogs`

All dialog methods are headless-compatible (they print to stdout when no UI is available).

```python
# Show a message
__api__.dialogs.show_message("Game saved!", "My Script")

# Get text input (returns str or None if cancelled)
name = __api__.dialogs.show_input("Enter a label:", "Backup")

# Yes/No prompt (returns bool)
if __api__.dialogs.show_yes_no("Create backup?"):
    do_backup()

# File/folder picker (returns str path or None)
path = __api__.dialogs.show_file_picker("Select save file")
folder = __api__.dialogs.show_folder_picker("Select backup folder")
```

### `__api__.paths`

```python
__api__.paths.application_path      # Root application directory
__api__.paths.config_path           # Config directory
__api__.paths.database_path         # Path to library.db
__api__.paths.extension_path        # Extensions directory
__api__.paths.extension_data_path   # Per-script data directory (auto-created)
__api__.paths.log_path              # Log directory
```

The `extension_data_path` is unique per script, so multiple scripts can write files without collisions.

### `__api__.addons`

```python
# Register items that appear in the application menu
__api__.addons.add_main_menu_item("Export Stats", my_export_function)

# Register items in the right-click context menu on a game
__api__.addons.add_game_menu_item("Backup Saves", my_backup_function)

# Retrieve registered items
main_items = __api__.addons.get_main_menu_items()
game_items = __api__.addons.get_game_menu_items()
```

---

## Exporting Menu Items

Scripts can declare menu entries using the `__exports__` module-level variable. This is the declarative alternative to calling `__api__.addons` directly.

```python
def export_csv():
    """Export playtime data to CSV."""
    ...

def restore_backup():
    """Restore the most recent save backup."""
    ...

__exports__ = [
    {"Name": "Export Playtime CSV", "Function": "export_csv"},
    {"Name": "Restore Save Backup", "Function": "restore_backup"},
]
```

The `"Function"` value is the name of the callable in the script's namespace (string, not the callable itself).

---

## Dependencies

Declare third-party packages in `<script>.yaml`:

```yaml
dependencies:
  - pypresence
  - requests>=2.28
```

Install them into an isolated virtual environment for the script:

```bash
playnite scripts load my_script.py
playnite scripts install-deps my_script
```

Or with `--force` to reinstall:

```bash
playnite scripts install-deps my_script --force
```

The venv is created under `~/.playnite_python/config/venvs/<script_name>/`. The script manager activates the correct venv automatically when executing a script's hooks.

---

## Sandbox Levels

Scripts run in one of three security modes set by `sandbox_level` in the config.

### `none`

No restrictions. Use only for fully trusted, locally-developed scripts.

### `standard` (default)

- Dangerous stdlib modules are blocked: `os`, `subprocess`, `sys`, `ctypes`, `shutil`, `signal`, `gc`, `marshal`, `pickle`, `inspect`, `importlib`, `asyncio`, `multiprocessing`, and others.
- Safe modules remain available: `math`, `datetime`, `json`, `re`, `pathlib`, `logging`, `threading`, `collections`, `dataclasses`, `typing`, `csv`, `zipfile`, `urllib`, `socket`, and others.
- Scripts are analyzed with an AST security visitor before execution.
- The execution timeout from config is enforced.

### `strict`

Everything in `standard`, plus:
- Network modules blocked: `urllib`, `http`, `socket`, `ssl`, `requests`, `httpx`, `aiohttp`, `ftplib`.
- Data modules blocked: `sqlite3`, `csv`, `zipfile`, `tarfile`, `hashlib`, `hmac`.
- Filesystem access restricted to the paths listed in `allowed_paths`.

### Bypassing the sandbox

If your script legitimately needs a blocked module (e.g., `subprocess` for calling an external tool), set `sandbox_level: none` in the YAML and keep the script in a trusted location.

---

## Hot Reload

Scripts can be reloaded at runtime without restarting the application:

```bash
# Reload a specific script
playnite scripts reload my_script

# Reload all scripts
# (start the file watcher to do this automatically on file save)
```

The script manager can also watch the extensions directory for file changes and reload automatically. The watcher runs as a daemon background thread.

When a script is reloaded:
1. The old script's hooks are unregistered.
2. The file is re-executed.
3. New hooks are registered from the updated namespace.

Global state the script stored in module-level variables is reset on reload.

---

## Metrics and Logging

### Execution Metrics

```bash
# Metrics for all scripts
playnite scripts metrics

# Metrics for a specific script
playnite scripts metrics my_script --json
```

Metrics per script:
- `call_count` — total hook invocations
- `error_count` — hooks that raised exceptions
- `timeout_count` — hooks that exceeded their timeout
- `avg_duration_ms` — average execution time

### Log Files

Each script gets a rotating log file at:

```
~/.playnite_python/config/logs/scripts/<script_name>.log
```

Write to it from the script using `__logger`:

```python
__logger.Info("Session started")
__logger.Warning("Save directory not found")
__logger.Error(f"Unexpected exception: {exc}")
```

---

## Marketplace Distribution

To publish a script to a marketplace index, add the `marketplace` section to the YAML:

```yaml
marketplace:
  id: author.script-name      # Unique identifier
  repository: https://example.com/scripts.json
```

Users can then find and install it:

```bash
playnite marketplace search "script-name"
playnite marketplace install author.script-name
```

The marketplace index is a JSON file with this structure:

```json
[
  {
    "id": "author.script-name",
    "name": "Human-Readable Name",
    "description": "What the script does.",
    "version": "1.2.0",
    "author": "Author Name",
    "download_url": "https://example.com/scripts/script_name.py",
    "tags": ["backup", "cloud"]
  }
]
```

---

## Full Example

```python
"""
playtime_tracker.py — Log session durations to a CSV file.

Config: playtime_tracker.yaml
  sandbox_level: standard
  metadata:
    author: Playnite Python Contributors
    version: 1.0
"""

import csv
from datetime import datetime
from pathlib import Path

# Session state (reset on reload)
_session_start: dict = {}

DATA_FILE = Path(__api__.paths.extension_data_path) / "sessions.csv"  # noqa: F821


def _ensure_csv():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        with open(DATA_FILE, "w", newline="") as fh:
            csv.writer(fh).writerow(["game_id", "game_name", "started", "stopped", "seconds"])


def on_script_loaded():
    _ensure_csv()
    __logger.Info("Playtime tracker ready.")  # noqa: F821


def on_game_started(game):
    _session_start[game.id] = datetime.now()
    __logger.Info(f"Session started: {game.name}")  # noqa: F821


def on_game_stopped(game, elapsed_seconds):
    started = _session_start.pop(game.id, None)
    if started is None:
        return
    stopped = datetime.now()
    with open(DATA_FILE, "a", newline="") as fh:
        csv.writer(fh).writerow([
            game.id,
            game.name,
            started.isoformat(),
            stopped.isoformat(),
            int(elapsed_seconds),
        ])
    __logger.Info(f"Logged {elapsed_seconds:.0f}s for {game.name}")  # noqa: F821


def show_stats():
    """Show total playtime per game."""
    totals: dict = {}
    try:
        with open(DATA_FILE, newline="") as fh:
            for row in csv.DictReader(fh):
                name = row["game_name"]
                totals[name] = totals.get(name, 0) + int(row.get("seconds", 0))
    except FileNotFoundError:
        __api__.dialogs.show_message("No sessions recorded yet.", "Playtime Tracker")  # noqa: F821
        return

    top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:10]
    lines = [f"{name}: {secs // 3600}h {(secs % 3600) // 60}m" for name, secs in top]
    __api__.dialogs.show_message("\n".join(lines) or "No data.", "Top Played Games")  # noqa: F821


__exports__ = [
    {"Name": "Show Playtime Stats", "Function": "show_stats"},
]

__attributes__ = {
    "Author": "Playnite Python Contributors",
    "Version": "1.0",
}
```
