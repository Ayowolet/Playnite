# Playnite Python

A modern Python game library manager — a full replacement for the legacy C# Playnite application.

## Overview

Playnite Python provides two major systems on top of a SQLite game library:

- **Script Extension System** — Load Python scripts from an extensions directory. Scripts receive a clean SDK for database access, notifications, and dialogs. They opt into lifecycle events (game starting, game stopped, etc.) by defining matching hook functions and run in a configurable sandbox.
- **Automated Action Injection** — Register pre-launch, post-exit, and play actions against games at runtime without restarting. Actions support conditions, priority ordering, async execution, variable substitution, rollback, logging, and scheduling.

Both systems are accessible through a CLI with `--json` output for programmatic use.

## Requirements

- Python 3.10+
- `click>=8.1.0`
- `PyYAML>=6.0`

Optional:
- `requests>=2.28.0` — marketplace/script installation
- `psutil>=5.9.0` — enhanced process monitoring

## Installation

```bash
pip install -e ".[all]"
```

After installation the `playnite` command is available:

```bash
playnite --help
```

To install only the optional extras separately:

```bash
pip install -e ".[marketplace]"   # requests
pip install -e ".[monitor]"       # psutil
```

## Quick Start

### Manage the game library

```bash
# Add a game
playnite games add "Celeste" --installed --install-dir ~/games/celeste

# List installed games
playnite games list --installed

# Search
playnite games list --search "cel"

# Full details as JSON
playnite games get <game-id> --json
```

### Load and run a script

```bash
# Auto-discover all scripts in ~/.playnite_python/extensions/
playnite scripts discover

# Load a specific script
playnite scripts load ~/scripts/my_script.py

# Fire a hook manually
playnite scripts run-hook on_application_started
playnite scripts run-hook on_game_stopped --game-id <id> --elapsed 3600
```

### Inject and run actions

```bash
# Inject a global pre-launch action
playnite actions inject \
  --script "import subprocess; subprocess.Popen(['Discord'])" \
  --name "Start Discord" \
  --type pre_launch

# Run the full pre-launch chain for a game
playnite actions chain --game-id <id> --type pre_launch

# View execution history
playnite actions log --limit 20
playnite actions log --failures

# Apply a built-in template
playnite actions template-list
playnite actions template-apply notify_session_start --game-id <id>
```

### Browse the marketplace

```bash
playnite marketplace search "discord"
playnite marketplace install author.script-id
playnite marketplace check-updates
```

## Default Paths

| Purpose | Path |
|---|---|
| Library database | `~/.playnite_python/library.db` |
| Config directory | `~/.playnite_python/config/` |
| Extensions directory | `~/.playnite_python/extensions/` |
| Script logs | `~/.playnite_python/config/logs/scripts/` |
| Action log | `~/.playnite_python/config/logs/actions.jsonl` |
| Actions registry | `~/.playnite_python/config/actions.json` |

Override with CLI options or environment variables:

```bash
playnite --db /path/to/library.db --config-dir /path/to/config games list

# Or via environment variables
export PLAYNITE_DB=/path/to/library.db
export PLAYNITE_CONFIG=/path/to/config
export PLAYNITE_EXTENSIONS=/path/to/extensions
```

## Project Layout

```
playnite_python/
├── models/          # Game, GameAction, Platform, etc.
├── database/        # SQLite-backed GameDatabase
├── extensions/      # Script loading, sandbox, SDK, lifecycle, marketplace
├── actions/         # Action models, registry, chain executor, injector, scheduler
├── cli/             # Click CLI (playnite command)
├── examples/        # Ready-to-use example scripts
└── tests/           # 166 unit + integration tests
```

## Documentation

| Document | Description |
|---|---|
| [Scripting Guide](docs/scripting-guide.md) | Writing and configuring extension scripts |
| [Actions Guide](docs/actions-guide.md) | Injecting and chaining game actions |
| [CLI Reference](docs/cli-reference.md) | All commands, options, and examples |
| [API Reference](docs/api-reference.md) | Python library API for programmatic use |

## Example Scripts

The `examples/` directory contains ready-to-use scripts:

| Script | Description |
|---|---|
| `discord_rich_presence.py` | Updates Discord status while playing |
| `playtime_tracker.py` | Logs sessions to CSV with per-game totals |
| `game_backup.py` | Backs up save directories before each session |
| `auto_sync.py` | Runs cloud sync commands after sessions end |

Copy any example into `~/.playnite_python/extensions/` and run `playnite scripts discover` to activate it.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

All 166 tests must pass:

```
166 passed in 3.61s
```

## License

MIT License — see LICENSE for details.
