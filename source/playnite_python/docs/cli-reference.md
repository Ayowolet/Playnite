# CLI Reference

The `playnite` command provides full access to the game library, script extensions, game actions, and marketplace.

## Global Options

These options are accepted by every command:

```
playnite [OPTIONS] COMMAND [ARGS]...

Options:
  --db PATH            Path to the SQLite library database.
                       Default: ~/.playnite_python/library.db
                       Env: PLAYNITE_DB

  --config-dir PATH    Configuration directory.
                       Default: ~/.playnite_python/config
                       Env: PLAYNITE_CONFIG

  --extensions-dir PATH  Extensions directory.
                         Default: ~/.playnite_python/extensions
                         Env: PLAYNITE_EXTENSIONS
```

### JSON Output

Every command accepts `--json` to emit machine-readable JSON instead of formatted text:

```bash
playnite games list --json
playnite actions log --json | jq '.[] | select(.success == false)'
```

---

## `games` — Game Library

### `games list`

List games in the library.

```
playnite games list [OPTIONS]

Options:
  --installed     Only show installed games.
  --search TEXT   Filter by name (case-insensitive substring match).
  --limit N       Maximum number of results.  Default: 50.
  --json          Output as JSON.
```

```bash
# All games
playnite games list

# Installed only
playnite games list --installed

# Search
playnite games list --search "ste"

# First 10 results as JSON
playnite games list --limit 10 --json
```

**JSON shape** (array):
```json
[
  {
    "id": "uuid",
    "name": "Game Name",
    "installed": true,
    "play_time_hours": 12.5,
    "favorite": false
  }
]
```

---

### `games get`

Show all fields for a single game.

```
playnite games get GAME_ID [--json]
```

```bash
playnite games get abc123
playnite games get abc123 --json
```

Returns the full `Game.to_dict()` output.

---

### `games add`

Add a game to the library.

```
playnite games add NAME [OPTIONS]

Options:
  --installed       Mark the game as installed.
  --install-dir PATH  Set the installation directory.
  --json
```

```bash
playnite games add "Celeste"
playnite games add "Celeste" --installed --install-dir ~/games/celeste
```

**JSON shape**:
```json
{"ok": true, "message": "Added 'Celeste' with id=...", "id": "uuid"}
```

---

### `games update`

Update a field on an existing game.

```
playnite games update GAME_ID FIELD VALUE [--json]
```

Boolean values (`true`/`false`) and integers are coerced automatically.

```bash
playnite games update abc123 is_favorite true
playnite games update abc123 play_time 7200
playnite games update abc123 notes "Great platformer"
```

---

### `games remove`

Remove a game from the library.

```
playnite games remove GAME_ID [--confirm] [--json]
```

Prompts for confirmation unless `--confirm` or `--json` is set.

```bash
playnite games remove abc123
playnite games remove abc123 --confirm
```

---

### `games stats`

Show library statistics.

```
playnite games stats [--json]
```

```bash
playnite games stats
playnite games stats --json
```

**JSON shape**:
```json
{
  "total_games": 243,
  "installed": 51,
  "favorites": 12,
  "total_play_time_hours": 1842.3
}
```

---

## `scripts` — Script Extensions

### `scripts discover`

Auto-discover and load all `.py` files in the extensions directory.

```
playnite scripts discover [--json]
```

```bash
playnite scripts discover
```

**JSON shape**:
```json
{"ok": true, "message": "Loaded 3 script(s)", "scripts": ["discord_rpc", "tracker", "backup"]}
```

---

### `scripts list`

List all `.py` files found in the extensions directory and their load status.

```
playnite scripts list [--json]
```

```bash
playnite scripts list
```

**JSON shape** (array):
```json
[
  {
    "name": "discord_rpc",
    "path": "/home/user/.playnite_python/extensions/discord_rpc.py",
    "loaded": true,
    "enabled": true,
    "hooks": ["on_game_starting", "on_game_stopped"]
  }
]
```

---

### `scripts load`

Load a script from an explicit file path.

```
playnite scripts load PATH [--json]
```

```bash
playnite scripts load ~/my_script.py
playnite scripts load ~/my_script.py --json
```

---

### `scripts reload`

Hot-reload a script by name (re-executes the file, re-registers hooks).

```
playnite scripts reload NAME [--json]
```

```bash
playnite scripts reload discord_rpc
```

---

### `scripts unload`

Unload a script (deregisters hooks, frees namespace).

```
playnite scripts unload NAME [--json]
```

---

### `scripts enable`

Re-enable a previously disabled script.

```
playnite scripts enable NAME [--json]
```

---

### `scripts disable`

Disable a script's hooks without unloading it. The script stays in memory but won't receive lifecycle events.

```
playnite scripts disable NAME [--json]
```

---

### `scripts install-deps`

Install a script's declared dependencies into its isolated virtual environment.

```
playnite scripts install-deps NAME [--force] [--json]
```

```bash
playnite scripts install-deps discord_rpc
playnite scripts install-deps discord_rpc --force   # Reinstall
```

Dependencies must be declared in `<script>.yaml` under `dependencies:`.

---

### `scripts run-hook`

Manually fire a lifecycle hook across all loaded scripts. Useful for testing.

```
playnite scripts run-hook HOOK_NAME [OPTIONS]

Options:
  --game-id ID       Game UUID (required for game-level hooks).
  --elapsed SECONDS  Elapsed seconds passed to on_game_stopped.  Default: 0.
  --json
```

Valid hook names:
- `on_application_started`
- `on_application_stopped`
- `on_library_updated`
- `on_script_loaded`
- `on_script_unloaded`
- `on_game_starting`
- `on_game_started`
- `on_game_stopped`
- `on_game_installed`
- `on_game_uninstalled`

```bash
playnite scripts run-hook on_application_started
playnite scripts run-hook on_game_stopped --game-id abc123 --elapsed 3600
```

---

### `scripts metrics`

Show execution metrics for scripts.

```
playnite scripts metrics [NAME] [--json]
```

```bash
# All scripts
playnite scripts metrics

# One script
playnite scripts metrics discord_rpc --json
```

**JSON shape**:
```json
{
  "discord_rpc": {
    "call_count": 42,
    "error_count": 1,
    "timeout_count": 0,
    "avg_duration_ms": 12.4
  }
}
```

---

## `actions` — Game Actions

### `actions list`

List registered actions.

```
playnite actions list [OPTIONS]

Options:
  --game-id ID    Filter by game UUID.
  --type TYPE     Filter by action type: play, install, uninstall, pre_launch, post_exit, custom.
  --json
```

```bash
playnite actions list
playnite actions list --game-id abc123
playnite actions list --type pre_launch --json
```

---

### `actions add`

Register a new action.

```
playnite actions add [OPTIONS]

Options:
  --name TEXT        Action name.  Default: "Custom Action".
  --type TYPE        Action type.  Default: pre_launch.
  --script CODE      Inline Python script.
  --executable PATH  Executable path (sets executor type to EXECUTABLE).
  --game-id ID       Game-specific action.  Omit for global.
  --priority N       Execution priority.  Default: 100.
  --async            Run asynchronously (non-blocking).
  --timeout N        Timeout in seconds.  Default: 60.
  --json
```

```bash
playnite actions add \
  --name "Enable VPN" \
  --type pre_launch \
  --script "import subprocess; subprocess.run(['vpn', 'connect'])" \
  --priority 5 \
  --timeout 30

playnite actions add \
  --name "Launch Helper" \
  --executable /usr/bin/helper \
  --game-id abc123
```

**JSON shape**:
```json
{"ok": true, "message": "Added action 'Enable VPN'", "id": "uuid"}
```

---

### `actions remove`

Remove an action by its UUID.

```
playnite actions remove ACTION_ID [--json]
```

```bash
playnite actions remove abc123
```

---

### `actions run`

Execute a single action immediately.

```
playnite actions run ACTION_ID [--game-id ID] [--json]
```

```bash
playnite actions run abc123
playnite actions run abc123 --game-id game-uuid --json
```

**JSON shape** (array of ActionLog entries).

---

### `actions inject`

Shorthand to inject an inline script action at runtime.

```
playnite actions inject [OPTIONS]

Required:
  --script CODE

Options:
  --name TEXT      Default: "Injected Action".
  --type TYPE      Default: pre_launch.
  --priority N     Default: 100.
  --game-id ID     Game-specific.  Omit for global.
  --json
```

```bash
playnite actions inject \
  --script "print('hello world')" \
  --name "Debug Print" \
  --type pre_launch

playnite actions inject \
  --script "import subprocess; subprocess.Popen(['Discord'])" \
  --name "Start Discord" \
  --priority 10
```

---

### `actions chain`

Execute the full sorted action chain for a game and action type.

```
playnite actions chain [OPTIONS]

Options:
  --game-id ID    Target game UUID.
  --type TYPE     Action type.  Default: pre_launch.
  --json
```

```bash
playnite actions chain --game-id abc123 --type pre_launch
playnite actions chain --game-id abc123 --type post_exit --json
```

**JSON shape**:
```json
{
  "success": true,
  "logs": [
    {
      "action_name": "Enable VPN",
      "success": true,
      "duration_ms": 215.4,
      ...
    }
  ]
}
```

---

### `actions log`

View action execution history.

```
playnite actions log [OPTIONS]

Options:
  --limit N        Number of recent entries.  Default: 20.
  --game-id ID     Filter by game.
  --action-id ID   Filter by action.
  --failures       Only show failed executions.
  --json
```

```bash
playnite actions log
playnite actions log --failures --limit 50
playnite actions log --game-id abc123 --json
```

---

### `actions template-list`

List available built-in action templates.

```
playnite actions template-list [--json]
```

```bash
playnite actions template-list
```

---

### `actions template-apply`

Apply a built-in template that requires no arguments.

```
playnite actions template-apply TEMPLATE_NAME [--game-id ID] [--json]
```

```bash
playnite actions template-apply notify_session_start
playnite actions template-apply game_backup --game-id abc123
```

Templates requiring arguments (`close_background_apps`, `enable_vpn`, `disable_vpn`, `discord_rich_presence`) must be applied via Python — see the [Actions Guide](actions-guide.md#templates).

---

### `actions schedule`

Schedule an existing action to run automatically.

```
playnite actions schedule ACTION_ID [OPTIONS]

Options (one required):
  --interval SECONDS   Run every N seconds.
  --daily-hour HOUR    Run daily at this hour (0–23).
  --json
```

```bash
# Every 5 minutes
playnite actions schedule abc123 --interval 300

# Daily at 3am
playnite actions schedule abc123 --daily-hour 3
```

---

## `marketplace` — Community Scripts

### `marketplace list`

List all scripts in the configured marketplace index.

```
playnite marketplace list [--refresh] [--json]
```

`--refresh` forces re-downloading the index even if cached.

---

### `marketplace search`

Search the marketplace by keyword.

```
playnite marketplace search QUERY [--json]
```

```bash
playnite marketplace search "discord"
playnite marketplace search "backup" --json
```

---

### `marketplace install`

Install a script from the marketplace by its unique ID.

```
playnite marketplace install SCRIPT_ID [--overwrite] [--json]
```

```bash
playnite marketplace install author.discord-rpc
playnite marketplace install author.discord-rpc --overwrite   # Replace if exists
```

---

### `marketplace update`

Update an installed script to its latest version.

```
playnite marketplace update SCRIPT_ID [--json]
```

---

### `marketplace check-updates`

Check all installed scripts against the marketplace for available updates.

```
playnite marketplace check-updates [--json]
```

**JSON shape** (dict):
```json
{
  "author.discord-rpc": "1.3.0",
  "author.backup": "2.1.0"
}
```

An empty object means all scripts are up to date.

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Command error (item not found, invalid argument, execution failure) |

---

## Environment Variables

| Variable | CLI equivalent | Description |
|---|---|---|
| `PLAYNITE_DB` | `--db` | Library database path |
| `PLAYNITE_CONFIG` | `--config-dir` | Config directory |
| `PLAYNITE_EXTENSIONS` | `--extensions-dir` | Extensions directory |
