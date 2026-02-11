# Lifecycle Hooks

Scripts define lifecycle hooks as top-level functions. The engine calls these functions at specific points during application and game lifecycle events. If a script doesn't define a particular hook, it is silently skipped.

## Hook Summary

| Hook | Signature | When it fires |
|------|-----------|---------------|
| `on_loaded` | `()` | Immediately after the script is loaded/reloaded |
| `on_application_started` | `()` | After all scripts are loaded and the app is ready |
| `on_application_stopped` | `()` | During graceful shutdown, before scripts are unloaded |
| `on_library_updated` | `()` | After a library refresh/import completes |
| `on_game_started` | `(game_id=None, **kwargs)` | When a game process starts |
| `on_game_stopped` | `(game_id=None, **kwargs)` | When a game process exits |
| `on_game_installed` | `(game_id=None, **kwargs)` | After a game installation completes |
| `on_game_uninstalled` | `(game_id=None, **kwargs)` | After a game is uninstalled |
| `on_game_selected` | `(game_id=None, **kwargs)` | When a user selects a game in the UI |

## Hook Details

### `on_loaded()`

Called once when the script is first loaded, and again on each hot-reload. Use this for:
- Registering menu items
- Injecting actions
- Initializing state
- Validating configuration

```python
def on_loaded():
    playnite.menus.add_main_menu_item("My Feature", my_callback)
    playnite.actions.add_action(
        name="My Pre-Launch",
        script="print('ready')",
        phase="pre_launch",
    )
    playnite.log.info("Script initialized")
```

**Important:** On reload, previous menu items and actions injected by the script are automatically cleaned up before `on_loaded` runs again.

### `on_application_started()`

Called after all scripts have finished loading. Use this for one-time setup that depends on the full library being available.

```python
def on_application_started():
    stats = playnite.database.get_stats()
    playnite.log.info("Library has %d games", stats["total_games"])
```

### `on_application_stopped()`

Called during graceful shutdown. Use this for cleanup, saving state, or sending final notifications.

```python
def on_application_stopped():
    playnite.log.info("Shutting down, saving state...")
```

### `on_library_updated()`

Called after a library refresh completes (e.g., re-scanning sources).

```python
def on_library_updated():
    games = playnite.database.get_games()
    playnite.log.info("Library updated: %d games", len(games))
```

### `on_game_started(game_id=None, **kwargs)`

Called when a game process starts. The `game_id` parameter identifies which game.

```python
def on_game_started(game_id=None, **kwargs):
    game = playnite.database.get_game(game_id)
    if game:
        playnite.notifications.show(f"Playing {game['name']}")
```

### `on_game_stopped(game_id=None, **kwargs)`

Called when a game process exits. Use this for playtime tracking, post-session tasks, etc.

```python
def on_game_stopped(game_id=None, **kwargs):
    game = playnite.database.get_game(game_id)
    if game:
        playnite.log.info("Session ended for %s", game["name"])
```

### `on_game_installed(game_id=None, **kwargs)`

Called after a game finishes installing.

### `on_game_uninstalled(game_id=None, **kwargs)`

Called after a game is uninstalled.

### `on_game_selected(game_id=None, **kwargs)`

Called when a user selects/focuses a game in the UI.

## Hook Execution Details

### Execution Order

When a hook fires, scripts execute in **directory name order** (alphabetical). Within a single script, execution is synchronous.

### Game-Specific Scripts

If a script's `config.yaml` has a non-empty `game_ids` list, its game hooks (`on_game_started`, `on_game_stopped`, etc.) only fire for those specific games:

```yaml
# config.yaml
game_ids:
  - "abc-123"
  - "def-456"
```

Global hooks (`on_loaded`, `on_application_started`, `on_library_updated`) always fire regardless of `game_ids`.

### Error Handling

If a hook raises an exception:
1. The error is captured and logged to the script's log file
2. The script's error count is incremented in metrics
3. Other scripts continue executing — one script's failure doesn't block others
4. The main application is never crashed by a script error

### Timeouts

Each hook call is subject to the script's configured timeout (default: 30 seconds). If a hook exceeds its timeout, execution is terminated and an error is logged.

### Metrics

Every hook invocation is tracked:
- Execution count
- Success/failure count
- Duration (min, max, average)
- Last execution timestamp
- Last error message

Query metrics via CLI:
```bash
playnite script-metrics --id my_script
```

Or in code:
```python
engine.metrics.get_script_stats("my_script")
```

## Triggering Hooks via CLI

You can manually fire any hook from the command line:

```bash
# Fire a global hook
playnite script-hook on_application_started

# Fire a game-specific hook
playnite script-hook on_game_started --game-id abc-123

# With JSON output
playnite --json script-hook on_game_stopped --game-id abc-123
```

This is useful for testing scripts without running the full application.
