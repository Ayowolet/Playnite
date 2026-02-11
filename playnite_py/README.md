# Playnite Python

A cross-platform Python game library manager with a script extension system and automated game action injection. Designed as a modern Python replacement for Playnite's PowerShell scripting capabilities.

## Features

- **Game Library Management** - Add, update, query, and remove games with full metadata support
- **Python Script Extensions** - Load user scripts from an extensions directory with a clean SDK/API
- **Sandboxed Execution** - Three sandbox levels (none, basic, strict) restricting imports and file access
- **Lifecycle Hooks** - 9 hook points from application start to game stop
- **Automated Game Actions** - Inject pre-launch, post-exit, install, and uninstall actions per game or globally
- **Action Chains** - Priority-ordered execution with condition evaluation, variable resolution, and rollback
- **Process Monitoring** - Track game processes, detect crashes, and auto-restart
- **Action Templates** - Built-in patterns for common tasks (close apps, enable VPN, backup saves, etc.)
- **Event Triggers** - Fire actions based on library events (game added, started, stopped)
- **Script Marketplace** - Discover and install community scripts from a repository
- **CLI First** - Every feature is accessible via CLI with JSON output for automation

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Add a game and run an action

```bash
# Add a game
playnite --json game-add "Half-Life 2" --source Steam --installed

# Inject a pre-launch action
playnite action-inject "Show Greeting" \
  --script "print(f'Launching {game[\"name\"]}!')" \
  --game-id <game-id> \
  --phase pre_launch

# Execute pre-launch phase
playnite --json action-execute <game-id> pre_launch
```

### Load and run scripts

Place a script directory in `~/.playnite_py/extensions/`:

```
extensions/
  my_script/
    config.yaml
    script.py
```

```bash
# List discovered scripts
playnite script-list

# Load all scripts and fire a lifecycle hook
playnite script-load
playnite script-hook on_application_started

# View script logs
playnite script-log my_script --tail 50
```

## Documentation

| Document | Description |
|----------|-------------|
| [SDK Reference](docs/sdk-reference.md) | Complete API available to scripts via the `playnite` object |
| [Lifecycle Hooks](docs/lifecycle-hooks.md) | All hook points, signatures, and when they fire |
| [Action System](docs/action-system.md) | Action injection, chains, conditions, templates, rollback |
| [Examples Guide](docs/examples.md) | Walkthrough of the three included example scripts |

## CLI Commands

### Game Management

| Command | Description |
|---------|-------------|
| `game-list` | List all games in the library |
| `game-add <name>` | Add a game (`--source`, `--installed`) |
| `game-show <id>` | Show game details |
| `game-update <id>` | Update game fields (`--name`, `--set-installed`, `--notes`) |
| `game-remove <id>` | Remove a game |
| `db-stats` | Show library statistics |

### Script Management

| Command | Description |
|---------|-------------|
| `script-list` | List all discovered scripts and their status |
| `script-load` | Load all scripts from extensions directory |
| `script-reload <id>` | Hot-reload a specific script |
| `script-info <id>` | Show script config and state |
| `script-hook <hook>` | Execute a lifecycle hook across all scripts |
| `script-log <id>` | View a script's log file |
| `script-metrics` | View execution stats (`--id` for specific script) |
| `script-deps <id>` | List installed packages in script's venv |
| `script-install-deps <id>` | Install script's declared dependencies |

### Action Management

| Command | Description |
|---------|-------------|
| `action-list` | List injected actions (`--game-id`, `--phase`) |
| `action-inject <name>` | Inject a new action (`--script`, `--phase`, `--game-id`) |
| `action-remove <id>` | Remove an action |
| `action-execute <game-id> <phase>` | Run all actions for a game phase |
| `action-log` | View action execution history |
| `action-templates` | List built-in action templates |
| `action-apply-template <name> <game-id>` | Apply a template to a game |

### Other

| Command | Description |
|---------|-------------|
| `profile-list` | List action profiles |
| `profile-create <name>` | Create a profile (`--criteria`, `--actions` as JSON) |
| `monitor-status` | Show monitored game processes |
| `monitor-start <game-id>` | Start monitoring a process |
| `marketplace-search` | Search script marketplace (`--query`, `--refresh`) |
| `marketplace-install <id>` | Install a script from marketplace |

All commands support `--json` for machine-readable output.

## Project Structure

```
playnite_py/
├── models/          # Game, Action, Database data models
├── scripting/       # Script engine, sandbox, SDK, config, logging, deps, marketplace, metrics
├── actions/         # Action manager, chains, conditions, variables, monitor, templates,
│                    #   scheduler, triggers, profiles, rollback
├── cli.py           # CLI entry point
└── docs/            # Documentation
extensions/examples/ # Example scripts
tests/               # Unit + integration tests (119 tests)
```

## Running Tests

```bash
python -m pytest tests/ -v
```
