# Example Scripts

Three example scripts are included in `extensions/examples/` demonstrating key features of the scripting system.

## 1. Playtime Tracker

**Location:** `extensions/examples/playtime_tracker/`

Tracks game sessions by recording start/end times and updating playtime in the database.

### What It Demonstrates

- `on_loaded` hook for initialization and menu registration
- `on_game_started` / `on_game_stopped` hooks for session tracking
- `playnite.database` for reading and updating games
- `playnite.menus` for adding main menu and game context menu items
- `playnite.dialogs` for displaying information
- `playnite.notifications` for user feedback

### Config

```yaml
name: Playtime Tracker
enabled: true
timeout: 10
sandbox_level: basic
game_ids: []  # Global — tracks all games
```

### Key Code

```python
def on_game_started(game_id=None, **kwargs):
    import time
    _sessions[game_id] = time.time()

def on_game_stopped(game_id=None, **kwargs):
    import time
    elapsed = int(time.time() - _sessions.pop(game_id))
    game = playnite.database.get_game(game_id)
    playnite.database.update_game(
        game_id,
        playtime=game["playtime"] + elapsed,
        play_count=game["play_count"] + 1,
    )
```

### Try It

```bash
# Copy to extensions directory
cp -r extensions/examples/playtime_tracker ~/.playnite_py/extensions/

# Load and test
playnite script-list
playnite script-hook on_application_started
playnite --json script-metrics --id playtime_tracker
```

---

## 2. Auto Tagger

**Location:** `extensions/examples/auto_tagger/`

Automatically tags games with playtime-based labels: Unplayed, Tried (>1h), Casual (>5h), Regular (>20h), Dedicated (>100h).

### What It Demonstrates

- Bulk database modifications via `query_games` and `update_game`
- Tag management with `add_tag_to_game` / `remove_tag_from_game`
- Action injection from within a script
- Main menu items for batch operations
- Game context menu items for per-game operations

### Config

```yaml
name: Auto Tagger
enabled: true
timeout: 15
sandbox_level: basic
```

### Key Code

```python
PLAYTIME_TAGS = [
    (0, "Unplayed"),
    (3600, "Tried"),
    (18000, "Casual"),
    (72000, "Regular"),
    (360000, "Dedicated"),
]

def _apply_playtime_tag(game_id):
    game = playnite.database.get_game(game_id)
    playtime = game.get("playtime", 0)
    tag_name = "Unplayed"
    for threshold, name in PLAYTIME_TAGS:
        if playtime >= threshold:
            tag_name = name
    # Remove old tags, apply new one
    for _, old_tag in PLAYTIME_TAGS:
        playnite.database.remove_tag_from_game(game_id, old_tag)
    playnite.database.add_tag_to_game(game_id, tag_name)
```

### Try It

```bash
cp -r extensions/examples/auto_tagger ~/.playnite_py/extensions/

# Add some games with playtime
playnite game-add "Quick Game"
playnite game-update <id> --set-installed true

# Load scripts and fire hooks
playnite script-load
playnite script-hook on_application_started
```

---

## 3. Game Save Backup

**Location:** `extensions/examples/game_backup/`

Injects a pre-launch action that creates backup manifests for game save directories before each play session. Includes rollback support.

### What It Demonstrates

- Action injection with conditions (only runs for installed games)
- Rollback scripts (undo on failure)
- `allowed_paths` configuration for sandbox file access
- Configuration dialogs via `playnite.dialogs`
- Inline multi-line scripts stored as module-level constants

### Config

```yaml
name: Game Save Backup
enabled: true
timeout: 30
sandbox_level: basic
allowed_paths:
  - /tmp/game_backups
```

### Key Code

```python
def on_loaded():
    playnite.actions.add_action(
        name="Backup Saves Before Launch",
        script=BACKUP_SCRIPT,
        phase="pre_launch",
        priority=80,
        conditions=[
            {"field": "game.is_installed", "operator": "is_true", "value": ""},
        ],
        rollback_script=ROLLBACK_SCRIPT,
    )
```

The `BACKUP_SCRIPT` creates a JSON manifest recording what was backed up. The `ROLLBACK_SCRIPT` removes that manifest if the launch fails.

### Try It

```bash
cp -r extensions/examples/game_backup ~/.playnite_py/extensions/

playnite script-load
playnite --json action-list  # See the injected backup action
playnite --json action-execute <game-id> pre_launch
```

---

## Writing Your Own Script

### Minimal Script

Create a directory with two files:

**`my_script/config.yaml`:**
```yaml
name: My Script
enabled: true
timeout: 10
sandbox_level: basic
```

**`my_script/script.py`:**
```python
def on_loaded():
    playnite.log.info("My script loaded!")
    playnite.notifications.show("Hello from my script!")

def on_game_started(game_id=None, **kwargs):
    game = playnite.database.get_game(game_id)
    if game:
        playnite.log.info("Starting: %s", game["name"])
```

### Script with Dependencies

If your script needs third-party packages, list them in `config.yaml`:

```yaml
dependencies:
  - requests
  - beautifulsoup4
```

The engine creates an isolated virtual environment per script and installs dependencies automatically on first load. Install manually with:

```bash
playnite script-install-deps my_script
```

### Game-Specific Script

To restrict a script to specific games:

```yaml
game_ids:
  - "abc-123"
  - "def-456"
```

Global hooks (`on_loaded`, `on_application_started`) still fire, but game hooks only fire for the listed games.

### Strict Sandbox

For untrusted scripts, use strict mode:

```yaml
sandbox_level: strict
```

This disables `open()`, network access, subprocess, and limits imports to safe standard library modules (json, math, re, datetime, etc.).

### Testing Your Script

```bash
# Load and check for errors
playnite --json script-info my_script

# View the log
playnite script-log my_script

# Manually fire hooks
playnite script-hook on_loaded
playnite script-hook on_game_started --game-id <id>

# Check metrics
playnite --json script-metrics --id my_script
```
