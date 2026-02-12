# Architecture Guide

This document describes the architecture and design decisions of Playnite-Py.

## Overview

Playnite-Py is designed as a modular, layered application with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                       CLI Layer                              │
│  (Click commands, rich output, JSON serialization)           │
├─────────────────────────────────────────────────────────────┤
│                    Manager Layer                             │
│  (ProfileManager, ConfigurationManager, GameLauncher)        │
├─────────────────────────────────────────────────────────────┤
│                   Repository Layer                           │
│  (ProfileRepository, GameRepository, ConfigurationRepository)│
├─────────────────────────────────────────────────────────────┤
│                    Database Layer                            │
│  (SQLAlchemy ORM, SQLite with WAL mode)                     │
├─────────────────────────────────────────────────────────────┤
│                     Model Layer                              │
│  (Pydantic models for validation and serialization)          │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
playnite_py/
├── __init__.py              # Package exports
├── core/                    # Core components
│   ├── models/              # Pydantic data models
│   │   ├── profile.py       # Profile, ProfileSettings, etc.
│   │   ├── game.py          # Game, GameAction, GameMetadata
│   │   └── configuration.py # PlatformConfiguration, templates
│   └── database/            # Database layer
│       ├── engine.py        # SQLAlchemy engine management
│       ├── models.py        # SQLAlchemy ORM models
│       └── repositories.py  # Data access repositories
├── profiles/                # Profile management
│   ├── manager.py           # ProfileManager
│   ├── templates.py         # Profile templates
│   ├── inheritance.py       # Settings inheritance
│   ├── security.py          # Password protection
│   ├── sharing.py           # Data sharing between profiles
│   ├── locking.py           # Profile locking
│   └── export.py            # Import/export functionality
├── configurations/          # Configuration management
│   ├── manager.py           # ConfigurationManager
│   ├── detection.py         # Platform/hardware detection
│   ├── templates.py         # Configuration templates
│   ├── launcher.py          # Game launching
│   └── compatibility.py     # Wine/Proton support
├── cli/                     # Command-line interface
│   ├── main.py              # Main CLI entry point
│   ├── profile_commands.py  # Profile commands
│   ├── config_commands.py   # Configuration commands
│   └── game_commands.py     # Game commands
└── utils/                   # Utilities
    ├── logging.py           # Logging configuration
    └── platform.py          # Cross-platform utilities
```

## Profile Isolation

### Design Goals

1. **Complete Data Isolation**: Each profile has its own:
   - SQLite database for game library
   - Media files directory
   - Plugin data directory
   - Cache directory

2. **No Cross-Contamination**: Data from one profile never affects another unless explicitly shared.

3. **Concurrent Access Prevention**: File-based locking prevents multiple instances from accessing the same profile.

### Data Directory Structure

```
~/.local/share/PlaynitePy/
├── master.db                # Profile metadata database
├── locks/                   # Profile lock files
├── shared/                  # Shared data (if enabled)
│   ├── cache/               # Shared metadata cache
│   └── media/               # Shared media files
└── profiles/
    ├── <uuid>/              # Profile 1
    │   ├── library.db       # Game library database
    │   ├── media/           # Cover images, icons
    │   ├── cache/           # Downloaded metadata
    │   └── plugins/         # Plugin data
    └── <uuid>/              # Profile 2
        └── ...
```

### Master Database

The master database (`master.db`) stores:
- Profile metadata (names, settings, statistics)
- Profile templates
- Access logs

### Profile Databases

Each profile has its own `library.db` containing:
- Games
- Platform configurations
- Configuration templates (user-created)

## Profile Inheritance

Profiles can inherit settings from a parent profile:

```
Parent Profile (Gaming)
├── theme: dark
├── language: en
├── enabled_sources: [steam, epic]
│
└── Child Profile (Laptop Gaming)
    ├── theme: (inherited: dark)
    ├── language: (inherited: en)
    └── enabled_sources: [steam]  # Override
```

The `ProfileInheritanceResolver` handles:
1. Building the inheritance chain
2. Detecting circular inheritance
3. Merging settings with proper precedence

## Configuration System

### Platform Detection

The `PlatformDetector` automatically identifies:
- Platform type (desktop, laptop, handheld, VM)
- CPU information
- RAM amount
- GPU(s) and vendor
- Display configuration
- Power source (AC/battery)
- Special devices (Steam Deck)

### Configuration Hierarchy

```
Game
└── Configurations
    ├── Desktop (default)
    │   ├── Display: 2560x1440, fullscreen
    │   ├── Graphics: Ultra
    │   └── VSync: On
    ├── Laptop
    │   ├── Display: 1920x1080, windowed
    │   ├── Graphics: Medium
    │   └── VSync: On
    └── TV/Couch
        ├── Display: 3840x2160, fullscreen
        ├── Graphics: High
        └── VSync: On
```

### Configuration Selection

When launching a game:
1. If configuration specified, use it
2. Otherwise, detect current platform
3. Find best matching configuration for platform
4. Fall back to default configuration

### Fallback Mechanism

Each configuration can specify a fallback:

```
Primary Config (Desktop)
├── Fallback → Balanced Config
│   └── Fallback → Performance Config
```

If primary fails, automatically tries fallback.

## Database Layer

### SQLite Configuration

Optimized SQLite settings for performance:
- WAL (Write-Ahead Logging) mode for concurrent reads
- Foreign key constraints enabled
- 64MB cache size
- Memory-mapped I/O (256MB)

### Repository Pattern

Repositories abstract database operations:

```python
class ProfileRepository:
    def create(self, profile: Profile) -> Profile
    def get_by_id(self, profile_id: UUID) -> Optional[Profile]
    def get_by_name(self, name: str) -> Optional[Profile]
    def update(self, profile: Profile) -> Profile
    def delete(self, profile_id: UUID) -> bool
```

### Model Mapping

Pydantic models ↔ SQLAlchemy models conversion:

```
Profile (Pydantic)          ProfileModel (SQLAlchemy)
├── id                  →   id (String)
├── name                →   name (String)
├── settings            →   settings_json (JSON)
├── statistics          →   statistics_json (JSON)
└── ...                     ...
```

## Security Features

### Password Protection

Uses PBKDF2-SHA256 with:
- 100,000 iterations
- 32-byte random salt
- Constant-time comparison

### Lockout Mechanism

- Tracks failed attempts
- Locks profile after N failures
- Configurable lockout duration

### Access Logging

Optional logging of:
- Profile access attempts
- Successful/failed logins
- Timestamps

## Compatibility Layers

### Wine/Proton Support

The `CompatibilityManager` handles:
- Wine configuration
- Proton detection and configuration
- Environment variable setup
- Prefix management

Supported layers:
- Wine
- Proton
- CrossOver (macOS)
- Whisky (macOS)
- Game Porting Toolkit (macOS)

## CLI Design

### Framework

Uses Click for command-line parsing with:
- Nested command groups
- Context passing
- Global options

### Output Modes

Two output modes:
1. **Human-readable**: Rich tables and formatted text
2. **JSON**: Machine-readable for scripting

```python
if ctx.json_output:
    ctx.output({"success": True, "data": ...})
else:
    console.print("[green]Success![/green]")
```

## Error Handling

### Exception Hierarchy

```
Exception
├── ValueError          # Invalid input
├── PermissionError     # Security/access issues
├── FileNotFoundError   # Missing files
└── RuntimeError        # Lock conflicts, etc.
```

### CLI Error Handling

```python
try:
    result = operation()
    if ctx.json_output:
        ctx.output({"success": True, ...})
except ValueError as e:
    if ctx.json_output:
        ctx.output({"success": False, "error": str(e)})
    else:
        ctx.error(str(e))
    raise SystemExit(1)
```

## Testing Strategy

### Unit Tests

Test individual components:
- Model validation
- Repository operations
- Manager methods

### Integration Tests

Test complete workflows:
- CLI commands
- Profile lifecycle
- Configuration application

### Test Fixtures

Shared fixtures in `conftest.py`:
- Temporary directories
- In-memory databases
- Sample data objects

## Performance Considerations

### Profile Switching

Target: <2 seconds
- Lazy database loading
- Connection pooling
- Minimal I/O

### Configuration Application

Target: <500ms
- Pre-validated configurations
- Cached templates
- Efficient environment setup

### Database Operations

- Indexed fields for common queries
- Batch operations where possible
- WAL mode for concurrent access

## Future Extensibility

### Plugin System

Planned architecture for plugins:
- Extension points for library sources
- Metadata providers
- Custom actions

### Remote Profiles

Planned support for:
- Cloud backup
- Profile synchronization
- Remote streaming configuration
