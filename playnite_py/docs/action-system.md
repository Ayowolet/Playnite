# Action System

The action system allows scripts and CLI users to inject custom actions that execute at specific points in a game's lifecycle. Actions are stored in the database and survive application restarts.

## Core Concepts

### Action Phases

Each action runs during a specific phase:

| Phase | Value | When |
|-------|-------|------|
| Pre-Launch | `pre_launch` | Before the game process starts |
| Launch | `launch` | When the game is being launched |
| Post-Exit | `post_exit` | After the game process exits |
| Pre-Install | `pre_install` | Before game installation |
| Post-Install | `post_install` | After game installation |
| Pre-Uninstall | `pre_uninstall` | Before game uninstallation |
| Post-Uninstall | `post_uninstall` | After game uninstallation |

### Priority

Actions within a phase execute in **descending priority** order (100 = first, 0 = last):

| Priority | Value | Typical Use |
|----------|-------|-------------|
| HIGHEST | 100 | Critical setup (VPN, prerequisites) |
| HIGH | 75 | Important preparation (close apps) |
| NORMAL | 50 | Standard actions (default) |
| LOW | 25 | Cosmetic/optional (Discord presence) |
| LOWEST | 0 | Cleanup/logging |

### Game-Specific vs Global Actions

- **Game-specific:** Set `game_id` to target one game
- **Global:** Leave `game_id` as `None` — runs for every game

Global actions and game-specific actions are merged and sorted by priority when a phase executes.

## Injecting Actions

### From a Script

```python
def on_loaded():
    playnite.actions.add_action(
        name="Backup Saves",
        script="print(f'Backing up saves for {game[\"name\"]}')",
        phase="pre_launch",
        priority=80,
        timeout=30,
    )
```

### From the CLI

```bash
playnite action-inject "Log Launch" \
  --script "print(f'Launching {game[\"name\"]}')" \
  --game-id abc-123 \
  --phase pre_launch \
  --priority 60
```

### From a Script File

```bash
playnite action-inject "Complex Setup" \
  --script /path/to/setup.py \
  --script-path \
  --phase pre_launch
```

## Executing Actions

### Via CLI

```bash
# Execute all pre-launch actions for a game
playnite --json action-execute <game-id> pre_launch

# Output:
{
  "game_id": "abc-123",
  "phase": "pre_launch",
  "results": [
    {"action_name": "Backup Saves", "success": true, "duration": 0.15},
    {"action_name": "Log Launch", "success": true, "duration": 0.02}
  ],
  "total_duration": 0.17,
  "all_succeeded": true
}
```

### Via Code

```python
from playnite_py.models.action import ActionPhase
result = action_manager.execute_phase(game_id, ActionPhase.PRE_LAUNCH)
```

## Conditional Actions

Actions can have conditions that must all pass before execution. If any condition fails, the action is skipped (not an error).

### Condition Format

```python
playnite.actions.add_action(
    name="Steam-Only Action",
    script="print('steam game')",
    conditions=[
        {"field": "game.source", "operator": "equals", "value": "Steam"},
        {"field": "game.is_installed", "operator": "is_true", "value": ""},
    ],
)
```

### Available Fields

**Game fields:** `game.id`, `game.name`, `game.source`, `game.install_directory`, `game.is_installed`, `game.playtime`, `game.play_count`, `game.completion_status`, `game.version`, `game.hidden`, `game.favorite`, `game.platform_ids`, `game.genre_ids`, `game.tag_ids`

**Environment fields:** `env.os` (linux/darwin/windows), `env.os_version`, `env.hostname`, `env.user`, `env.home`

**Built-in:** `now`, `date`, `time`

### Operators

| Operator | Description |
|----------|-------------|
| `equals` | Case-insensitive equality |
| `not_equals` | Case-insensitive inequality |
| `contains` | Substring match (case-insensitive) |
| `not_contains` | Substring not found |
| `matches` | Regex match (case-insensitive) |
| `gt`, `lt`, `gte`, `lte` | Numeric comparison |
| `is_true` | Value is "true", "1", or "yes" |
| `is_false` | Value is "false", "0", "no", or empty |

## Variable Resolution

Action scripts can contain `{variable}` placeholders that are resolved before execution:

```python
playnite.actions.add_action(
    name="Greeting",
    script="print('Playing {game.name} on {env.os}')",
    phase="pre_launch",
)
```

All fields listed above under "Available Fields" are valid variables. Custom variables can be set on the `VariableResolver` instance.

## Async Actions

Actions with `is_async=True` execute in background threads and don't block other actions in the chain:

```python
playnite.actions.add_action(
    name="Discord Presence",
    script="print('Setting presence...')",
    is_async=True,
    priority=20,
)
```

Sync actions execute first in priority order. Async actions start in background threads simultaneously.

## Action Templates

Built-in templates provide pre-written scripts for common patterns:

| Template | Category | Phase | Description |
|----------|----------|-------|-------------|
| Close Background Apps | Performance | pre_launch | Kill resource-intensive apps |
| Enable VPN | Network | pre_launch | Connect to VPN |
| Discord Rich Presence | Social | pre_launch | Set Discord status |
| Backup Save Files | Data | pre_launch | Copy save directory |
| Log Playtime | Tracking | post_exit | Record session to JSON log |
| Set CPU Affinity | Performance | pre_launch | Pin to specific CPU cores |

### Apply a Template

```bash
playnite action-apply-template "Discord Rich Presence" <game-id>
```

```python
action_manager.apply_template("Backup Save Files", game_id)
```

### Custom Templates

Register your own templates in code:

```python
from playnite_py.actions.templates import ActionTemplate
action_manager.templates.register(ActionTemplate(
    name="My Template",
    description="Does something useful",
    category="Custom",
    phase=ActionPhase.PRE_LAUNCH,
    script="print('template action')",
))
```

## Rollback

Actions can define a rollback script that executes if the action chain fails:

```python
playnite.actions.add_action(
    name="Enable Gaming Mode",
    script="print('gaming mode on')",
    rollback_script="print('gaming mode off')",
    phase="pre_launch",
    priority=90,
)
```

If any action in the chain fails, all previously completed actions are rolled back **in reverse order**. The `ActionManager.execute_phase()` method handles this automatically.

### Rollback Behavior

1. Actions execute in priority order (high to low)
2. If action N fails, actions N-1 through 1 are rolled back (reverse order)
3. Only actions that completed successfully are rolled back
4. Rollback results are tracked in `action_manager.get_rollback_log()`

## Action Profiles

Profiles apply a set of actions to all games matching criteria:

```bash
playnite profile-create "Steam Performance" \
  --criteria '{"sources": ["Steam"], "is_installed": true}' \
  --actions '[{"name": "Close Chrome", "script": "print(\"closing\")", "phase": "pre_launch"}]'
```

### Profile Criteria

| Field | Type | Description |
|-------|------|-------------|
| `platform_ids` | `list[str]` | Game has any of these platforms |
| `genre_ids` | `list[str]` | Game has any of these genres |
| `tag_ids` | `list[str]` | Game has any of these tags |
| `category_ids` | `list[str]` | Game has any of these categories |
| `sources` | `list[str]` | Game source is one of these |
| `name_pattern` | `str` | Regex match against game name |
| `is_installed` | `bool` | Game installation status |

## Event Triggers

Fire actions automatically when library events occur:

```python
from playnite_py.actions.triggers import EventTrigger, EventType

trigger = EventTrigger(
    name="Auto-tag on install",
    event_type=EventType.GAME_INSTALLED,
    action_id=my_action.id,
)
action_manager.add_trigger(trigger)
```

### Event Types

`game_added`, `game_removed`, `game_updated`, `game_started`, `game_stopped`, `game_installed`, `game_uninstalled`, `library_updated`, `app_started`, `app_stopped`, `custom`

## Action Scheduling

Schedule actions to run at specific times or recurring intervals:

```python
# Run once at a specific time
action_manager.scheduler.schedule_once(action.id, "2025-01-15T14:00:00+00:00")

# Run every hour
action_manager.scheduler.schedule_recurring(action.id, interval_seconds=3600)
```

## Process Monitoring

Track game processes and handle crashes:

```python
# Start monitoring
proc = action_manager.process_monitor.start_monitoring(
    game_id=game.id,
    process_name="game.exe",
    max_restarts=3,
)

# Check status
action_manager.process_monitor.is_running(game.id)

# Callbacks
action_manager.process_monitor.on_process_crashed.append(
    lambda p: print(f"Crash detected: {p.game_id}")
)
```

## Performance

The action system is designed for low overhead:
- Target: < 5 seconds total for 10 pre-launch scripts
- Integration tests verify this benchmark
- Action execution is measured with `time.perf_counter()` for accurate timing
- All durations are tracked in the action log
