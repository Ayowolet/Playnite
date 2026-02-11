# Script SDK Reference

Every script receives a `playnite` object as a global variable when executed. This object is an instance of `PlayniteAPI` and provides access to the game library, notifications, dialogs, menus, actions, paths, and logging.

## `playnite.database` — DatabaseAPI

Read and write access to the game library.

### Methods

#### `get_games() -> list[dict]`
Returns all games in the library as dictionaries.

```python
games = playnite.database.get_games()
for game in games:
    print(game["name"], game["playtime"])
```

#### `get_game(game_id: str) -> dict | None`
Returns a single game by ID, or `None` if not found.

```python
game = playnite.database.get_game("abc-123")
if game:
    print(game["name"])
```

#### `query_games(**filters) -> list[dict]`
Filter games by field values. Supported filters:
- `name` — substring match (case-insensitive)
- `source` — exact match (e.g. `"Steam"`, `"GOG"`)
- `is_installed` — `True` / `False`
- `hidden`, `favorite` — `True` / `False`
- `completion_status` — e.g. `"completed"`, `"playing"`
- `platform_id`, `genre_id`, `tag_id`, `developer_id`, `publisher_id`, `category_id`, `feature_id` — ID present in the game's list

```python
installed_steam = playnite.database.query_games(source="Steam", is_installed=True)
```

#### `update_game(game_id: str, **fields) -> bool`
Update one or more fields on a game. Returns `True` on success.

```python
playnite.database.update_game(game_id, playtime=7200, play_count=5)
```

#### `add_game(**fields) -> dict`
Create a new game and add it to the library. Returns the new game dict.

```python
new_game = playnite.database.add_game(name="My Game", source="Manual")
```

#### `remove_game(game_id: str) -> bool`
Remove a game from the library. Returns `True` if found and removed.

#### `add_tag_to_game(game_id: str, tag_name: str) -> bool`
Add a tag to a game. Creates the tag if it doesn't exist. Idempotent.

#### `remove_tag_from_game(game_id: str, tag_name: str) -> bool`
Remove a tag from a game.

#### `get_platforms() -> list[dict]`
#### `get_genres() -> list[dict]`
#### `get_tags() -> list[dict]`
Return all metadata entities.

#### `get_stats() -> dict`
Returns library statistics:
```python
{
    "total_games": 150,
    "installed_games": 42,
    "total_playtime_seconds": 360000,
    "total_actions": 5,
    "by_completion_status": {"not_played": 80, "completed": 30, ...}
}
```

---

## `playnite.notifications` — NotificationAPI

Display notifications to the user. In CLI/headless mode, notifications are logged and collected.

### Methods

#### `show(message: str, title: str = "") -> None`
Show an informational notification.

#### `show_error(message: str, title: str = "Error") -> None`
Show an error notification.

#### `show_warning(message: str, title: str = "Warning") -> None`
Show a warning notification.

#### `get_pending() -> list[dict]`
Retrieve and clear all pending notifications. Each entry has `type`, `title`, and `message`.

```python
playnite.notifications.show("Import complete!", "Library Update")
```

---

## `playnite.dialogs` — DialogAPI

Create dialogs and prompts. In headless mode, dialogs return sensible defaults or pre-set responses.

### Methods

#### `show_message(message: str, title: str = "", buttons: list[str] | None = None) -> str | None`
Show a message dialog. Returns the selected button label.

```python
result = playnite.dialogs.show_message(
    "Delete save files?", "Confirm", buttons=["Yes", "No"]
)
```

#### `show_input(message: str, title: str = "", default: str = "") -> str | None`
Show a text input dialog. Returns the entered string.

```python
name = playnite.dialogs.show_input("Enter profile name:", default="Default")
```

#### `show_select(message: str, options: list[str]) -> str | None`
Show a selection dialog. Returns the chosen option.

#### `set_response(dialog_type: str, response: Any) -> None`
Pre-set a response for a dialog type (`"message"`, `"input"`, `"select"`). Useful for testing.

#### `get_history() -> list[dict]`
Returns all dialog interactions since last call.

---

## `playnite.menus` — MenuAPI

Register custom entries in the main menu and game context menus.

### Methods

#### `add_main_menu_item(name: str, callback: Callable, icon: str = "", description: str = "") -> str`
Add an entry to the main application menu. Returns the item ID.

```python
def my_action():
    playnite.notifications.show("Menu clicked!")

item_id = playnite.menus.add_main_menu_item("My Action", my_action)
```

#### `add_game_menu_item(name: str, callback: Callable, icon: str = "", description: str = "") -> str`
Add an entry to the per-game context menu. The callback receives `game_id` as a keyword argument.

```python
def tag_game(game_id=None, **kwargs):
    playnite.database.add_tag_to_game(game_id, "Played")

playnite.menus.add_game_menu_item("Mark as Played", tag_game)
```

#### `remove_menu_item(item_id: str) -> bool`
Remove a previously registered menu item.

#### `get_main_menu_items() -> list[dict]`
#### `get_game_menu_items() -> list[dict]`
List registered menu items (without callback references).

#### `invoke_menu_item(item_id: str, *args, **kwargs) -> Any`
Programmatically invoke a menu item's callback.

---

## `playnite.actions` — ActionAPI

Inject game actions from scripts. Actions persist in the database and execute during game phases.

### Methods

#### `add_action(...) -> str`
Inject a new action. Returns the action ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Action display name |
| `script` | `str` | required | Python code or file path |
| `game_id` | `str \| None` | `None` | Target game (None = global) |
| `action_type` | `str` | `"custom"` | `play`, `install`, `uninstall`, `custom` |
| `phase` | `str` | `"pre_launch"` | When to run (see [Action System](action-system.md)) |
| `priority` | `int` | `50` | Execution order (higher = earlier, 0-100) |
| `is_async` | `bool` | `False` | Run without blocking the chain |
| `timeout` | `int` | `30` | Max execution time in seconds |
| `conditions` | `list[dict]` | `[]` | Conditions that must pass (see below) |
| `is_script_path` | `bool` | `False` | If `True`, `script` is a file path |
| `rollback_script` | `str` | `""` | Code to run if rollback is triggered |

**Condition dict format:**
```python
{"field": "game.is_installed", "operator": "is_true", "value": ""}
```

```python
playnite.actions.add_action(
    name="Pre-launch Check",
    script="print('ready to launch')",
    game_id=game_id,
    phase="pre_launch",
    priority=80,
    conditions=[
        {"field": "game.is_installed", "operator": "is_true", "value": ""}
    ],
)
```

#### `remove_action(action_id: str) -> bool`
Remove an action by ID.

#### `get_actions(game_id: str | None = None, phase: str | None = None) -> list[dict]`
Query injected actions with optional filters.

---

## `playnite.paths` — PathsAPI

Read-only access to application paths.

| Property | Description |
|----------|-------------|
| `extensions_dir` | Extensions directory |
| `data_dir` | Application data directory |
| `log_dir` | Log files directory |

---

## `playnite.log` — Logger

A standard Python `logging.Logger` scoped to the current script. Output goes to both a per-script log file and the combined log.

```python
playnite.log.info("Processing %d games", count)
playnite.log.warning("Save directory not found: %s", path)
playnite.log.error("Failed to connect: %s", error)
```

---

## `playnite.app_version` — str

The current application version string (e.g. `"0.1.0"`).

---

## Script Globals

In addition to `playnite`, scripts have access to:

| Variable | Description |
|----------|-------------|
| `__script_dir__` | Absolute path to the script's directory |

---

## Action Script Globals

When an action's script executes (via the action chain), these globals are available:

| Variable | Type | Description |
|----------|------|-------------|
| `game` | `dict` | The target game's data (same format as `get_game()`) |
| `args` | `dict` | The action's `arguments` dict with variables resolved |
| `action` | `dict` | The action's own metadata |
