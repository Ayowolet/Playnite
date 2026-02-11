# Actions Guide

This guide covers the Automated Game Action Injection system — how to register, chain, condition, schedule, and monitor actions for games.

## Contents

- [Overview](#overview)
- [Action Types](#action-types)
- [Executor Types](#executor-types)
- [Creating Actions](#creating-actions)
- [Priority and Ordering](#priority-and-ordering)
- [Conditions](#conditions)
- [Variable Substitution](#variable-substitution)
- [Action Chains](#action-chains)
- [Async Actions](#async-actions)
- [Rollback](#rollback)
- [Process Monitoring](#process-monitoring)
- [Scheduling](#scheduling)
- [Action Profiles](#action-profiles)
- [Templates](#templates)
- [Injection from Scripts](#injection-from-scripts)
- [Execution Logging](#execution-logging)

---

## Overview

An `Action` is a unit of work tied to a game event. Actions are stored in a registry and executed by the `ActionChainExecutor` in priority order. Any action can be injected at runtime — no application restart required.

```python
from playnite_python.actions import Action, ActionType, ActionRegistry, ActionInjector

registry = ActionRegistry("~/.playnite_python/config")
injector = ActionInjector(registry)

# Inject a pre-launch action
injector.inject_pre_launch(
    script="import subprocess; subprocess.Popen(['Discord'])",
    name="Start Discord",
    priority=10,
)
```

---

## Action Types

| Type | Value | Description |
|---|---|---|
| `ActionType.PLAY` | `"play"` | Replaces or supplements the default play action |
| `ActionType.INSTALL` | `"install"` | Overrides the install process |
| `ActionType.UNINSTALL` | `"uninstall"` | Overrides the uninstall process |
| `ActionType.PRE_LAUNCH` | `"pre_launch"` | Runs before the game starts |
| `ActionType.POST_EXIT` | `"post_exit"` | Runs after the game exits |
| `ActionType.CUSTOM` | `"custom"` | Custom / user-defined timing |

---

## Executor Types

| Type | Value | Description |
|---|---|---|
| `ActionExecutorType.SCRIPT` | `"script"` | Inline Python script (default) |
| `ActionExecutorType.EXECUTABLE` | `"executable"` | Launch an external process |
| `ActionExecutorType.URL` | `"url"` | Open a URL in the default browser |

---

## Creating Actions

### Via Python

```python
from playnite_python.actions.models import Action, ActionType, ActionExecutorType

# Script action
action = Action(
    name="Enable VPN",
    type=ActionType.PRE_LAUNCH,
    executor_type=ActionExecutorType.SCRIPT,
    script="import subprocess; subprocess.run(['vpn', 'connect'], check=True)",
    priority=5,
    timeout=30,
    game_id="some-game-uuid",   # None = global (applies to all games)
)

# Executable action
action = Action(
    name="Launch Helper",
    type=ActionType.PRE_LAUNCH,
    executor_type=ActionExecutorType.EXECUTABLE,
    executable="/usr/bin/my-helper",
    arguments="--game {game.name} --mode launch",
    working_dir="/usr/bin",
)

# URL action
action = Action(
    name="Open Game Page",
    type=ActionType.CUSTOM,
    executor_type=ActionExecutorType.URL,
    script="https://store.example.com/game/{game.id}",
)
```

### Via CLI

```bash
# Script action
playnite actions add \
  --name "Enable VPN" \
  --type pre_launch \
  --script "import subprocess; subprocess.run(['vpn', 'connect'])" \
  --game-id <uuid> \
  --priority 5 \
  --timeout 30

# Executable action
playnite actions add \
  --name "Launch Helper" \
  --type pre_launch \
  --executable /usr/bin/my-helper \
  --game-id <uuid>

# Quick inject shorthand
playnite actions inject \
  --script "print('hello')" \
  --name "Debug Action" \
  --type pre_launch
```

---

## Priority and Ordering

Actions execute in ascending `priority` order (lower number = first). The default priority is `100`.

```
priority=0    → runs first
priority=5    → runs second
priority=10   → runs third
priority=100  → default (runs last)
```

Global actions (no `game_id`) and game-specific actions are sorted together by priority.

Recommended priority conventions:

| Priority | Typical use |
|---|---|
| 0–10 | Critical setup (VPN, launcher override) |
| 10–30 | Service startup (Discord, overlay) |
| 30–60 | Environment prep (backup, notifications) |
| 60–90 | Logging and diagnostics |
| 90–100 | Non-critical post-launch work |

---

## Conditions

Actions can have one or more conditions that must be satisfied before the action runs. If conditions fail, the action is skipped (not counted as a failure).

```python
from playnite_python.actions.models import ActionCondition, ConditionType

action.conditions = [
    ActionCondition(type=ConditionType.FILE_EXISTS, value="/usr/bin/discord"),
    ActionCondition(type=ConditionType.PROCESS_RUNNING, value="Discord", negate=True),
]
```

### Condition Types

| Type | `value` field | Description |
|---|---|---|
| `FILE_EXISTS` | File path | Passes if path exists |
| `PROCESS_RUNNING` | Process name | Passes if process is running |
| `GAME_HAS_TAG` | Tag name | Passes if game has the tag |
| `GAME_IS_INSTALLED` | _(unused)_ | Passes if game is installed |
| `PLATFORM_IS` | Platform name | Passes if game's platform matches |
| `SCRIPT` | Python expression | Evaluates `eval(value)` with `game` in scope |
| `TIME_IS` | `"HH:MM"` | Passes if current time matches (within 1 minute) |
| `ALWAYS` | _(unused)_ | Always passes (default) |
| `NEVER` | _(unused)_ | Always fails (useful for disabling) |

### `negate`

Set `negate=True` to invert the condition:

```python
# Only run if Discord is NOT already running
ActionCondition(
    type=ConditionType.PROCESS_RUNNING,
    value="Discord",
    negate=True,
)
```

### `operator` (AND/OR)

When multiple conditions are present, the `operator` field on each condition determines how it combines with the previous:

```python
action.conditions = [
    ActionCondition(type=ConditionType.FILE_EXISTS, value="/usr/bin/vpn"),
    ActionCondition(type=ConditionType.GAME_HAS_TAG, value="Online", operator="and"),
    ActionCondition(type=ConditionType.PLATFORM_IS, value="PC", operator="or"),
]
```

The list is evaluated left-to-right: `cond1 AND cond2 OR cond3`.

---

## Variable Substitution

Action scripts, arguments, and executable paths support `{var}` placeholders that are expanded at execution time.

### Built-in Variables

| Variable | Value |
|---|---|
| `{game.name}` | Game name |
| `{game.id}` | Game UUID |
| `{game.install_dir}` | Installation directory |
| `{game.platform}` | First platform name |
| `{game.play_time}` | Total play time in seconds |
| `{timestamp}` | ISO timestamp at execution time |
| `{platform}` | OS name (`linux`, `darwin`, `win32`) |

### Custom Variables

Define additional variables on the action:

```python
from playnite_python.actions.models import ActionVariable

action.variables = [
    ActionVariable(name="backup_root", value="~/game_backups"),
    ActionVariable(name="max_backups", value="5"),
]

action.script = """
import shutil, pathlib
src = pathlib.Path('{game.install_dir}') / 'saves'
dst = pathlib.Path('{backup_root}') / '{game.name}'
shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
"""
```

---

## Action Chains

An `ActionChainExecutor` runs a list of actions in priority order against an optional game context.

```python
from playnite_python.actions import ActionChainExecutor, ActionRegistry

registry = ActionRegistry("~/.playnite_python/config")
executor = ActionChainExecutor()

# Get all pre-launch actions for a game (global + game-specific)
actions = registry.list_actions(game_id=game.id, action_type=ActionType.PRE_LAUNCH)

# Execute
logs, success = executor.execute(actions, game=game)
for log in logs:
    print(f"[{'OK' if log.success else 'FAIL'}] {log.action_name} ({log.duration_ms:.0f}ms)")
```

### Stop on Failure

```python
logs, success = executor.execute(
    actions,
    game=game,
    stop_on_failure=True,   # Abort chain if any action fails
)
```

### Completion Callback

```python
def on_done(log):
    print(f"Finished: {log.action_name}")

logs, success = executor.execute(actions, game=game, on_action_complete=on_done)
```

### Via CLI

```bash
playnite actions chain --game-id <uuid> --type pre_launch
playnite actions chain --game-id <uuid> --type post_exit --json
```

---

## Async Actions

Set `async_=True` on an action to dispatch it in a background thread. The chain continues immediately without waiting for the action to complete.

```python
action = Action(
    name="Send Session Notification",
    type=ActionType.PRE_LAUNCH,
    script="notify_send('Game Starting', game_name)",
    async_=True,
    priority=1,
)
```

Or via CLI:

```bash
playnite actions add --name "Notify" --type pre_launch --script "..." --async
```

Use async for non-critical work (notifications, analytics) that should not delay game launch.

---

## Rollback

An action can specify a `rollback_script` that runs if the action fails. Rollbacks are best-effort — a rollback failure is caught and logged, never propagated.

```python
action = Action(
    name="Enable VPN",
    type=ActionType.PRE_LAUNCH,
    script="subprocess.run(['vpn', 'connect'], check=True)",
    rollback_script="subprocess.run(['vpn', 'disconnect'])",
)
```

`RollbackManager` maintains a LIFO stack. Each successful action with a `rollback_script` is pushed. On chain failure, the stack can be replayed in reverse:

```python
from playnite_python.actions import RollbackManager

rm = RollbackManager()
rm.push(action, game)   # Called automatically by executor when rollback is configured

# Rollback last action
rm.rollback_last()

# Rollback all
rm.rollback_all()
```

---

## Process Monitoring

`ProcessMonitor` watches a running game process and fires callbacks on lifecycle events.

```python
from playnite_python.actions import ProcessMonitor

monitor = ProcessMonitor()

monitor.on_started = lambda info: print(f"Process started: {info.pid}")
monitor.on_stopped = lambda info: print(f"Stopped after {info.elapsed_seconds:.0f}s")
monitor.on_crashed = lambda info: print(f"Crashed! PID={info.pid}")

# Monitor by PID
monitor.start_monitoring(pid=12345, process_name="game.exe")

# Monitor by name (finds PID automatically)
monitor.start_monitoring(process_name="game.exe")
```

### Auto-Restart

```python
monitor.auto_restart = True
monitor.max_restarts = 3
monitor.launch_cmd = ["./game.exe", "--fullscreen"]
```

When `auto_restart=True` and the process crashes (unexpected exit), the monitor re-launches using `launch_cmd` up to `max_restarts` times.

### Stats Callback

```python
def on_stats(info):
    print(f"PID {info.pid} — running for {info.elapsed_seconds:.0f}s")

monitor.on_stats = on_stats
monitor.stats_interval = 60   # Fire every 60 seconds
```

`ProcessInfo` fields: `pid`, `process_name`, `started_at`, `launch_cmd`, `restart_count`, `elapsed_seconds` (property).

---

## Scheduling

`ActionScheduler` runs actions on a timer. It uses a daemon background thread polling every second.

```python
from playnite_python.actions import ActionScheduler, ActionChainExecutor
from datetime import timedelta

executor = ActionChainExecutor()

def run_action(action_id: str):
    action = registry.get_action(action_id)
    if action:
        logs, _ = executor.execute([action])
        return logs[0] if logs else None

scheduler = ActionScheduler(run_action)
scheduler.start()

# Run once after a delay
scheduler.schedule_once(action_id, delay=timedelta(seconds=30))

# Run every 5 minutes
scheduler.schedule_interval(action_id, interval=timedelta(minutes=5))

# Run daily at 02:00
scheduler.schedule_daily(action_id, hour=2)

# Run when an event fires
from playnite_python.actions.models import TriggerType
scheduler.schedule_on_event(action_id, TriggerType.GAME_STOPPED)

# Fire an event manually
scheduler.fire_event(TriggerType.GAME_STOPPED)
```

### Via CLI

```bash
# Schedule an action to run every 5 minutes
playnite actions schedule <action-id> --interval 300

# Schedule daily at 02:00
playnite actions schedule <action-id> --daily-hour 2
```

---

## Action Profiles

A `ActionProfile` applies a set of actions to **all games matching a filter expression**, rather than a specific `game_id`.

```python
from playnite_python.actions.models import ActionProfile

profile = ActionProfile(
    name="Online Games",
    filter_expr="'Online' in (game.tag_ids or [])",
    action_ids=[vpn_action_id, discord_action_id],
)
registry.add_profile(profile)
```

The `filter_expr` is evaluated with `game` in scope. Any Python expression returning a truthy value matches.

```python
# Examples
"game.is_installed"
"'RPG' in game.genre_ids"
"game.is_favorite and game.play_time > 3600"
```

---

## Templates

Built-in action factories for common tasks. List them:

```bash
playnite actions template-list
```

Available templates:

| Name | Type | Description |
|---|---|---|
| `discord_rich_presence` | `pre_launch` | Update Discord Rich Presence status |
| `discord_rich_presence_clear` | `post_exit` | Clear Discord Rich Presence |
| `close_background_apps` | `pre_launch` | Kill named background processes |
| `enable_vpn` | `pre_launch` | Connect VPN before launch |
| `disable_vpn` | `post_exit` | Disconnect VPN after exit |
| `game_backup` | `pre_launch` | Backup save directory |
| `screenshot_on_exit` | `post_exit` | Capture a screenshot on exit |
| `notify_session_start` | `pre_launch` | Desktop notification on game start (async) |
| `notify_session_end` | `post_exit` | Desktop notification on game stop (async) |
| `playtime_log` | `post_exit` | Append session info to a text log |

Apply a template via CLI:

```bash
playnite actions template-apply notify_session_start --game-id <uuid>
playnite actions template-apply game_backup --game-id <uuid>
```

Apply from Python:

```python
from playnite_python.actions.template import ALL_TEMPLATES

backup = ALL_TEMPLATES["game_backup"]()
backup.game_id = game.id
injector.inject(backup)
```

Templates that require arguments (e.g., `close_background_apps`, `enable_vpn`) must be created via Python:

```python
from playnite_python.actions.template import close_background_apps, enable_vpn, disable_vpn

injector.inject(close_background_apps(["Chrome.exe", "Slack.exe"]))
injector.inject(enable_vpn("openvpn --config /etc/vpn.conf"))
injector.inject(disable_vpn("openvpn --disconnect"))
```

---

## Injection from Scripts

Extension scripts can inject actions via the `ActionInjector`. Pass it in from the host application or the manager.

```python
# Inside an extension script (injector passed as a global)
from playnite_python.actions.models import Action, ActionType

def on_application_started():
    action = Action(
        name="Start Discord",
        type=ActionType.PRE_LAUNCH,
        script="import subprocess; subprocess.Popen(['Discord'])",
    )
    __injector__.inject(action)   # noqa: F821

def on_application_stopped():
    __injector__.revoke_by_source(__script_name__)   # noqa: F821
```

`ActionInjector` methods:

```python
injector.inject(action, game_id=None)           # Inject any action
injector.inject_play(game_id, script, name)     # Inject a PLAY action
injector.inject_pre_launch(script, name, game_id, priority)
injector.inject_post_exit(script, name, game_id, priority)
injector.override_launcher(game_id, script, name)   # Replace all PLAY actions
injector.modify_launch_params(game, arguments_append, env_vars)
injector.revoke(action_id)                      # Remove by ID
injector.revoke_by_source(source_script)        # Remove all from a script
injector.get_injected_actions(game_id, action_type)
injector.on_inject(callback)                    # Callback on every inject
```

---

## Execution Logging

Every action execution is recorded as an `ActionLog` entry.

```python
from playnite_python.actions import ActionExecutionLogger

logger = ActionExecutionLogger("~/.playnite_python/config/logs/actions.jsonl")

# Record logs returned by executor
logs, success = executor.execute(actions, game)
logger.record_many(logs)

# Query
recent = logger.get_recent(20)
failures = logger.get_failures(50)
game_logs = logger.get_for_game(game.id, limit=10)
action_logs = logger.get_for_action(action.id, limit=10)

# Stats
stats = logger.get_stats()
# {"total": 150, "success": 147, "failure": 3, "success_rate": 0.98,
#  "avg_duration_ms": 42.3, "max_duration_ms": 1200.0, "min_duration_ms": 1.1}

# Prune old entries
logger.rotate(keep_last=1000)
```

Via CLI:

```bash
# Recent 20 entries
playnite actions log

# Last 50 failures
playnite actions log --failures --limit 50

# All entries for a specific game
playnite actions log --game-id <uuid>

# Entries for a specific action
playnite actions log --action-id <uuid>

# JSON output
playnite actions log --json
```

`ActionLog` fields:

| Field | Type | Description |
|---|---|---|
| `id` | str | Entry UUID |
| `action_id` | str | The action that ran |
| `action_name` | str | Human-readable name |
| `game_id` | str \| None | Game context |
| `game_name` | str | Game name |
| `started_at` | datetime | When execution started |
| `finished_at` | datetime \| None | When execution finished |
| `success` | bool | Whether it succeeded |
| `error` | str | Error message if failed |
| `output` | str | Captured stdout |
| `duration_ms` | float | Wall-clock duration |
| `was_async` | bool | Whether run asynchronously |
| `rolled_back` | bool | Whether rollback was executed |
