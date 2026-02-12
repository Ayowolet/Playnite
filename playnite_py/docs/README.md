# Playnite-Py Documentation

Welcome to the Playnite-Py documentation. This guide covers all aspects of using and developing with the Python game library manager.

## Documentation Index

- [User Guide](user_guide.md) - Getting started and basic usage
- [CLI Reference](cli_reference.md) - Complete command-line interface documentation
- [API Documentation](api.md) - Python API reference for developers
- [Architecture Guide](architecture.md) - System design and architecture

## Quick Links

### For Users

- [Installation](#installation)
- [Creating Profiles](user_guide.md#creating-profiles)
- [Managing Games](user_guide.md#managing-games)
- [Platform Configurations](user_guide.md#platform-configurations)

### For Developers

- [API Overview](api.md#overview)
- [Profile Manager API](api.md#profilemanager)
- [Configuration Manager API](api.md#configurationmanager)
- [Database Layer](architecture.md#database-layer)

## Installation

```bash
# Install from source
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

## Basic Usage

```bash
# Create a profile
playnite profile create "Gaming"

# Switch to profile
playnite profile switch "Gaming"

# Add a game
playnite game add "My Game" --path "/path/to/game.exe"

# Create a configuration
playnite config create --game "My Game" --name "Desktop" --preset quality
```

## Support

For issues and feature requests, please visit:
https://github.com/playnite/playnite-py/issues
