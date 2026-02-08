# Playnite — Python Game Library Manager

A headless Python replacement for the Playnite game library manager.
Manage games, tags, categories, smart collections, and controller navigation
entirely from the command line or by importing the library directly.

## Table of Contents

- [Installation](#installation)
- [CLI Reference](#cli-reference)
  - [Library commands](#library-commands)
  - [Controller commands](#controller-commands)
- [Controller Setup](#controller-setup)
- [Smart Collection Rule Syntax](#smart-collection-rule-syntax)
- [Testing](#testing)
- [Architecture Overview](#architecture-overview)
- [Troubleshooting](#troubleshooting)

---

## Installation

```bash
pip install -e .
```

For hardware controller support (Linux/Windows via the `inputs` backend):

```bash
pip install -e ".[controller]"
```

---

## CLI Reference

All commands accept `--db <path>` to specify a SQLite database file
(defaults to `playnite.db` in the current directory). Every mutating
command supports `--json` to return machine-readable output.

### Library commands

#### Games

```bash
# Add a game
playnite --db lib.db library games add --name "Portal 2" \
    --platform PC --genre Puzzle --developer Valve --year 2011 --json

# List games (optional filters and sorting)
playnite library games list --platform PC --genre RPG \
    --sort name --order asc --json

# List games using a saved view preset
playnite library games list --preset my-view --json

# Get a single game
playnite library games get <id> --json

# Update a game
playnite library games update <id> --name "New Name" --year 2022 --json

# Delete a game
playnite library games delete <id> --json

# Search (fuzzy)
playnite library games search "portl" --json

# Favourites
playnite library games favorite <id>
playnite library games unfavorite <id>
playnite library games list --favorite --json

# Hide / unhide
playnite library games hide <id> --json
playnite library games unhide <id> --json

# Tags on a single game
playnite library games apply-tag <id> --tag "indie" --json
playnite library games remove-tag <id> --tag "indie" --json

# Bulk operations
playnite library games bulk-tag <id1> <id2> ... --tag "sale" --json
playnite library games bulk-delete <id1> <id2> ... --json
playnite library games bulk-hide <id1> <id2> ... --json
playnite library games bulk-unhide <id1> <id2> ... --json
```

#### Tags

```bash
playnite library tags add "indie" --json
playnite library tags list --json
playnite library tags get <id> --json
playnite library tags update <id> --name "indie-games" --json
playnite library tags delete <id> --json
```

#### Categories

```bash
playnite library categories add "Backlog" --json
playnite library categories list --json
playnite library categories get <id> --json
playnite library categories update <id> --name "Wishlist" --json
playnite library categories delete <id> --json
```

#### Genres and Platforms

```bash
playnite library genres list --json
playnite library platforms list --json
```

#### Smart Collections

```bash
# Create a smart collection with filter rules
playnite library collections create "All RPGs" \
    --rules '[{"field":"genre_names","operator":"contains","value":"RPG"}]' --json

# List games in a collection
playnite library collections games <collection-id> --json

# Delete a collection
playnite library collections delete <id> --json
```

#### View Presets

```bash
# Save a preset (sort + filter + view type)
playnite library presets save my-view \
    --sort playtime --order desc --view grid \
    --filters '{"genres":["RPG"]}' --json

# Load a preset
playnite library presets load my-view --json

# Apply a preset when listing games
playnite library games list --preset my-view --json

# Delete a preset
playnite library presets delete my-view --json
```

#### Stats

```bash
playnite library stats --json
```

---

### Controller commands

```bash
# Detect connected controllers
playnite controller detect --json

# Simulate a button press (returns press + release events)
playnite controller simulate BTN_SOUTH --json

# Navigate the UI state machine
playnite controller navigate select --json
playnite controller navigate back --state game_detail --json

# Query current navigation state
playnite controller state --json

# Show default button mapping
playnite controller mapping --show-default --json

# Save / load button mapping (JSON or YAML)
playnite controller mapping --save mapping.yaml
playnite controller mapping --load mapping.yaml --json

# Vibration
playnite controller vibrate --intensity 0.5 --duration 0.1 --json
```

---

## Controller Setup

Three backends are supported and probed automatically at startup:

| Backend | When available | Notes |
|---------|---------------|-------|
| `inputs` | Install `pip install -e ".[controller]"` | Linux/Windows raw device access |
| `pygame` | Always (base dependency) | Cross-platform joystick API |
| `simulation` | Always | Headless testing, no hardware required |

### Button codes

Standard Linux event codes are used: `BTN_SOUTH`, `BTN_EAST`, `BTN_NORTH`,
`BTN_WEST`, `BTN_SELECT`, `BTN_START`, `ABS_X`, `ABS_Y`, `ABS_HAT0X`,
`ABS_HAT0Y`, etc.

### Custom button mapping (YAML example)

```yaml
buttons:
  BTN_SOUTH: select
  BTN_EAST: back
  BTN_NORTH: options
  BTN_WEST: details
  BTN_SELECT: menu
  BTN_START: start
axes:
  ABS_X:
    negative: left
    positive: right
    threshold: 0.3
  ABS_Y:
    negative: up
    positive: down
    threshold: 0.3
```

Save with `playnite controller mapping --save mapping.yaml` and load
with `playnite controller mapping --load mapping.yaml`.

---

## Smart Collection Rule Syntax

Rules are a JSON array. Each rule object has three keys:

| Key | Description | Example values |
|-----|-------------|---------------|
| `field` | Which game attribute to match | `genre_names`, `platform_names`, `tag_names`, `release_year`, `playtime`, `completion_status`, `developer`, `publisher`, `user_score` |
| `operator` | Comparison operator | `contains`, `equals`, `gt`, `gte`, `lt`, `lte` |
| `value` | Value to compare against | `"RPG"`, `2015`, `"completed"` |

Multiple rules default to **AND** logic. Example — RPGs released after 2015:

```json
[
  {"field": "genre_names", "operator": "contains", "value": "RPG"},
  {"field": "release_year", "operator": "gte", "value": 2015}
]
```

---

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=playnite --cov-report=term-missing

# Run only unit tests
python -m pytest tests/unit/

# Run only integration tests
python -m pytest tests/integration/
```

The test suite uses SQLite in-memory databases for unit tests and
temporary files for integration tests — no external services required.

---

## Architecture Overview

```
src/playnite/
├── cli/
│   ├── main.py                 # Click CLI entry point
│   ├── library_commands.py     # library sub-commands
│   └── controller_commands.py  # controller sub-commands
├── library/
│   ├── organisation.py         # LibraryManager — CRUD, bulk ops, presets
│   ├── filters.py              # FilterSpec + FilterEngine (SQL query builder)
│   ├── search.py               # Fuzzy search via rapidfuzz
│   └── collections.py          # SmartCollection evaluation
├── controller/
│   ├── detection.py            # ControllerDetector — backend probing
│   ├── input_handler.py        # Event dispatch and history
│   ├── mapping.py              # ButtonMapping — JSON/YAML persistence
│   ├── navigation.py           # NavigationStateMachine (headless UI states)
│   └── simulation.py           # ControllerSimulator + VibrationController
└── database/                   # SQLAlchemy models and session factory
```

---

## Troubleshooting

### Installation

**`pip install -e .` fails with missing build tools**

```bash
pip install --upgrade pip setuptools wheel
pip install -e .
```

**`inputs` backend not found after installing `.[controller]`**

The `inputs` package requires kernel-level access on Linux. Ensure your user
is in the `input` group:

```bash
sudo usermod -aG input $USER
# log out and back in for the change to take effect
```

On Windows, no extra steps are needed — `inputs` uses the standard HID API.

---

### Controller Detection

**No controllers detected (`playnite controller detect` returns empty list)**

1. Check that a controller is physically connected and recognised by the OS:
   - Linux: `ls /dev/input/js*` or `cat /proc/bus/input/devices`
   - Windows: open "Game Controllers" (`joy.cpl`) in Control Panel
2. Verify at least one backend is available:
   ```bash
   playnite controller detect --json
   # look for "backends" in the output
   ```
3. If only `simulation` is listed, install `pygame` (already a base dep) or
   `pip install -e ".[controller]"` for the `inputs` backend.
4. On Linux, try running with `sudo` once to rule out permissions — then fix
   group membership as above rather than running as root permanently.

**pygame detects a controller but axis values are always 0**

Some controllers need the pygame event loop pumped. The CLI does this
automatically via `pygame.event.pump()` in the detection loop. If using the
library directly, call `pygame.event.pump()` before reading axis values.

---

### Button Mapping

**Custom mapping file not loading**

- Ensure the file extension is `.json`, `.yaml`, or `.yml` — the format is
  detected from the extension.
- Check the file path is correct; use an absolute path to avoid working
  directory confusion:
  ```bash
  playnite controller mapping --load /absolute/path/to/mapping.yaml
  ```
- Validate the YAML/JSON is well-formed. A minimal valid mapping:
  ```yaml
  buttons:
    BTN_SOUTH: select
  axes: {}
  ```

**Buttons fire the wrong action**

Run `playnite controller simulate <BTN_CODE>` to see which raw event code a
physical button emits, then update your mapping accordingly.

---

### Smart Collections

**`ValueError: Rule 0: unknown field …`**

Only allowlisted fields are permitted in rules. Valid fields:

`name`, `developer`, `publisher`, `release_year`, `playtime`,
`completion_status`, `user_score`, `is_favorite`, `is_hidden`, `is_installed`,
`genre_names`, `platform_names`, `tag_names`, `category_names`

**Collection returns no games despite matching data**

- String operators (`contains`, `equals`) are case-insensitive.
- Numeric comparisons (`gt`, `gte`, `lt`, `lte`) require numeric `value` — pass
  an integer, not a quoted string.
- Hidden games are excluded from collection results by default.

---

### Database

**`OperationalError: unable to open database file`**

Check that the directory exists and is writable:

```bash
mkdir -p /path/to/dir
playnite --db /path/to/dir/library.db library stats
```

**Database appears empty after upgrading**

Schema migrations are not automatic. Back up your existing `.db` file and
reinitialise if the schema changed:

```bash
cp library.db library.db.bak
rm library.db
playnite --db library.db library stats   # recreates schema
```

---

### Key design decisions

- **Headless first** — no GUI dependency anywhere in the core; the CLI and
  navigation state machine work equally well in tests and server environments.
- **SQLAlchemy 2.0 ORM** with `joinedload` on all relationship collections to
  eliminate N+1 queries during list operations.
- **Bulk SQL** — `UPDATE … WHERE id IN (…)` and `DELETE … WHERE id IN (…)`
  keep bulk operations O(1) round-trips regardless of batch size.
- **Optional backends** — controller hardware access (`inputs`, `pygame`) is
  probed at runtime; missing packages degrade gracefully to simulation.
