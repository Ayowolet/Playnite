# Playnite-Py: Modern Python Game Library Manager

A modern, cross-platform Python game library manager designed to replace legacy applications with comprehensive multi-profile support and platform-specific configurations.

## Features

### Multi-Library Profile System
- **Independent Profiles**: Create isolated library profiles (Personal, Family, Kids, Testing)
- **Profile Switching**: Switch profiles without restarting the application
- **Profile Templates**: Create profiles from predefined templates or existing profiles
- **Profile Inheritance**: Child profiles inherit settings from parent profiles with override capability
- **Selective Data Sharing**: Share categories, tags, metadata cache, and media files across profiles
- **Profile Import/Export**: Backup and migrate profiles between machines
- **Profile Locking**: Prevent concurrent access to the same profile
- **Profile Security**: Optional password protection and access logging
- **Profile Shortcuts**: Quick-launch directly into specific profiles
- **Usage Statistics**: Track last used date, playtime, and game count per profile
- **Cleanup Tools**: Identify and remove unused profiles, merge duplicate data

### Platform-Specific Game Configuration
- **Platform Configurations**: Different settings for Desktop, Laptop, TV/Couch modes
- **Automatic Detection**: Detect current platform/hardware and apply appropriate configuration
- **Configuration Templates**: Presets like Performance, Quality, Battery Saver
- **Launch Arguments**: Per-configuration argument overrides
- **Environment Variables**: Set/restore environment variables per configuration
- **Compatibility Layers**: Wine/Proton on Linux, compatibility mode on Windows
- **Display Configuration**: Target monitor, resolution, refresh rate per platform
- **Audio Configuration**: Different audio output per configuration
- **Pre/Post Launch Scripts**: Platform-specific scripts before/after game launch
- **Configuration Fallback**: Automatic fallback on configuration failure
- **Batch Configuration**: Apply settings to multiple games matching criteria

## Installation

```bash
# Install from source
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

## Quick Start

### CLI Usage

```bash
# Create a new profile
playnite profile create "Personal" --template default

# List all profiles
playnite profile list

# Switch to a profile
playnite profile switch "Personal"

# Create a platform configuration
playnite config create --game "Cyberpunk 2077" --platform desktop --preset quality

# Apply configuration
playnite config apply --game "Cyberpunk 2077" --platform desktop

# Export profile for backup
playnite profile export "Personal" --output ~/backup/personal_profile.zip

# Import profile on new machine
playnite profile import ~/backup/personal_profile.zip --name "Personal"
```

### Python API

```python
from playnite_py import ProfileManager, ConfigurationManager

# Profile Management
profile_manager = ProfileManager()
profile = profile_manager.create_profile("Gaming", template="default")
profile_manager.switch_profile("Gaming")

# Platform Configuration
config_manager = ConfigurationManager()
config = config_manager.create_configuration(
    game_id="game-123",
    platform="desktop",
    preset="quality"
)
config_manager.apply_configuration(config)
```

## Architecture

```
playnite_py/
├── core/               # Core data models and business logic
│   ├── models/         # Pydantic models for profiles, games, configs
│   ├── database/       # SQLAlchemy database layer
│   └── services/       # Business logic services
├── profiles/           # Multi-profile management system
│   ├── manager.py      # Profile lifecycle management
│   ├── templates.py    # Profile templates
│   ├── inheritance.py  # Profile inheritance system
│   ├── security.py     # Password protection and access control
│   └── sharing.py      # Selective data sharing
├── configurations/     # Platform-specific configurations
│   ├── manager.py      # Configuration management
│   ├── detection.py    # Platform/hardware detection
│   ├── templates.py    # Configuration presets
│   ├── launcher.py     # Game launching with configurations
│   └── compatibility.py # Wine/Proton compatibility layers
├── cli/                # Command-line interface
│   ├── main.py         # Main CLI entry point
│   ├── profile_commands.py
│   └── config_commands.py
└── utils/              # Utility functions
    ├── logging.py      # Logging utilities
    └── platform.py     # Cross-platform utilities
```

## Documentation

- [User Guide](docs/user_guide.md)
- [CLI Reference](docs/cli_reference.md)
- [API Documentation](docs/api.md)
- [Architecture Guide](docs/architecture.md)
- [Contributing Guide](CONTRIBUTING.md)

## Requirements

- Python 3.10+
- Supported platforms: Windows, macOS, Linux

## License

MIT License - see [LICENSE](LICENSE) for details.
