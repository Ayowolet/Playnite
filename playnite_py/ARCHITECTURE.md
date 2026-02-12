# Playnite-Py Architecture

## Overview

Playnite-Py is a cross-platform game library manager written in Python. It provides profile-based game organization, compatibility layer support, and platform-specific configuration management.

## Core Components

```
playnite_py/
├── core/                    # Core domain models and data access
│   ├── models/              # Pydantic models for all entities
│   │   ├── game.py          # Game, GameAction, GameMetadata
│   │   ├── profile.py       # Profile, ProfileSettings, ProfileSecurity
│   │   └── configuration.py # PlatformConfiguration, DisplayConfig
│   └── database/            # Data persistence layer
│       ├── engine.py        # SQLAlchemy engine management
│       ├── models.py        # SQLAlchemy ORM models
│       ├── repositories.py  # Repository pattern implementation
│       └── migrations.py    # Schema versioning and migrations
├── profiles/                # Profile management subsystem
│   ├── manager.py           # ProfileManager - main interface
│   ├── locking.py           # Cross-process file locking
│   ├── security.py          # Password hashing (PBKDF2-SHA256)
│   ├── inheritance.py       # Profile inheritance logic
│   ├── sharing.py           # Data sharing between profiles
│   ├── export.py            # Profile import/export (ZIP)
│   └── templates.py         # Profile templates
├── configurations/          # Game configuration subsystem
│   ├── manager.py           # ConfigurationManager
│   ├── launcher.py          # Game launching with security
│   ├── compatibility.py     # Wine/Proton/GPTK support
│   ├── display.py           # Display settings management
│   ├── detection.py         # Hardware/platform detection
│   ├── sandbox.py           # Script sandboxing
│   └── templates.py         # Configuration templates
├── cli/                     # Command-line interface
│   ├── main.py              # CLI entry point
│   ├── profile_commands.py  # Profile management commands
│   ├── game_commands.py     # Game management commands
│   └── config_commands.py   # Configuration commands
└── utils/                   # Shared utilities
    ├── logging.py           # Structured logging and metrics
    ├── settings.py          # Application settings (TOML config)
    ├── retry.py             # Retry logic and rate limiting
    └── platform.py          # Platform detection utilities
```

## Data Model

### Games
- `Game`: Core game entity with metadata, actions, and statistics
- `GameAction`: Launch actions (FILE, URL, EMULATOR, SCRIPT)
- `GameMetadata`: Descriptive metadata (description, genres, etc.)
- `PlatformConfiguration`: Platform-specific settings

### Profiles
- `Profile`: User profile with isolated game library
- `ProfileSettings`: Theme, language, view preferences
- `ProfileSecurity`: Password protection (PBKDF2-SHA256 hashing)
- `ProfileSharing`: Data sharing configuration

### Configurations
- `DisplayConfig`: Resolution, refresh rate, monitor targeting
- `AudioConfig`: Volume levels, output device
- `CompatibilityConfig`: Wine/Proton settings
- `LaunchArguments`: Command-line argument management

## Security Features

### Password Security
- PBKDF2-SHA256 with 100,000 iterations
- Random 32-byte salt per password
- Failed attempt tracking and lockout
- Constant-time comparison (timing attack prevention)

### Launch Security
- Path validation (no traversal, no metacharacters)
- URL protocol whitelist (steam, epic, gog, etc.)
- Argument sanitization (null bytes, newlines)
- Environment variable isolation (never modifies os.environ)
- Sensitive variable protection (no expansion of PASSWORD, API_KEY, etc.)

### Script Sandboxing
- Linux: bubblewrap or firejail
- macOS: sandbox-exec with custom profiles
- Windows: PowerShell constraints
- Network/filesystem restrictions

## Database Architecture

### Engine Management
- SQLite per profile (profile isolation)
- SQLAlchemy ORM with connection pooling
- Context manager for safe session handling
- Automatic rollback on exceptions

### Migration System
- Version tracking in `_migrations` table
- Automatic migration on database open
- Forward-only migrations (with optional rollback)

### Repositories
- `ProfileRepository`: Profile CRUD with pagination
- `GameRepository`: Game management
- `ConfigurationRepository`: Configuration management

## Profile System

### Isolation
- Separate SQLite database per profile
- File-based locking (filelock library)
- Lock info files with PID/hostname tracking

### Inheritance
- Parent-child profile relationships
- Settings cascade with explicit override tracking
- Circular dependency detection

### Data Sharing
- Modes: NONE, READ_ONLY, BIDIRECTIONAL, SELECTIVE
- Selective category/tag/media sharing
- Reference-based (no data duplication)

## Configuration System

### Platform Detection
- OS, CPU, RAM, GPU detection
- Power source (AC/battery)
- Display enumeration (multi-monitor)
- Compatibility layer detection

### Compatibility Layers
- Wine (standard Wine)
- Proton (Steam Play)
- CrossOver (commercial Wine)
- Whisky (macOS Wine wrapper)
- GPTK (Apple Game Porting Toolkit)

### Display Management
- Platform-specific APIs:
  - Linux: xrandr, gnome-randr, wlr-randr
  - Windows: ChangeDisplaySettingsEx
  - macOS: displayplacer
- Race condition prevention (threading lock)
- Rollback support (restore previous settings)

## Observability

### Structured Logging
- JSON format option for log aggregation
- Operation context tracking (request IDs)
- Performance metrics collection

### Metrics
- Operation duration tracking
- Success/failure rates
- Configurable history retention

## CLI Design

### Commands
```
playnite                     # Main entry point
├── profile                  # Profile management
│   ├── list                 # List profiles
│   ├── create               # Create profile
│   ├── switch               # Switch active profile
│   ├── delete               # Delete profile
│   └── export/import        # Backup/restore
├── game                     # Game management
│   ├── list                 # List games
│   ├── add                  # Add game
│   ├── info                 # Show details
│   └── launch               # Launch game
└── config                   # Configuration
    ├── list                 # List configurations
    ├── create               # Create configuration
    └── apply                # Apply to game
```

### Output Formats
- Rich terminal output (tables, colors)
- JSON output (`--json` flag)
- Exit codes for scripting

## Configuration Files

### Application Settings (`config.toml`)
```toml
data_dir = "~/.local/share/playnite-py"

[logging]
level = "INFO"
structured = false

[database]
pool_size = 5
max_overflow = 10

[launcher]
verify_paths = true
auto_rollback_display = true
```

### Environment Variables
- `PLAYNITE_DATA_DIR`: Data directory
- `PLAYNITE_LOG_LEVEL`: Logging level
- `PLAYNITE_LOG_STRUCTURED`: JSON logging
- `PLAYNITE_DB_POOL_SIZE`: Connection pool size

## Error Handling

### Retry Logic
- Configurable max attempts and backoff
- Exception type filtering
- Callback hooks for monitoring

### Circuit Breaker
- Failure threshold tracking
- Open/half-open/closed states
- Automatic recovery testing

### Rate Limiting
- Token bucket algorithm
- Burst capacity support
- Blocking and non-blocking acquisition
