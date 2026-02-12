# Playnite-Py User Guide

This guide covers the basic usage of Playnite-Py for managing your game library.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Managing Profiles](#managing-profiles)
3. [Managing Games](#managing-games)
4. [Platform Configurations](#platform-configurations)
5. [Profile Security](#profile-security)
6. [Export and Import](#export-and-import)

## Getting Started

### Installation

```bash
pip install playnite-py
```

Or install from source:

```bash
git clone https://github.com/playnite/playnite-py.git
cd playnite-py
pip install -e .
```

### First Steps

1. Create your first profile:
   ```bash
   playnite profile create "Personal"
   ```

2. Switch to the profile:
   ```bash
   playnite profile switch "Personal"
   ```

3. Add a game:
   ```bash
   playnite game add "My Game" --path "/path/to/game.exe"
   ```

## Managing Profiles

Profiles provide isolated game libraries with their own databases, settings, and configurations.

### Creating Profiles

```bash
# Basic profile
playnite profile create "Gaming"

# With description
playnite profile create "Work" --description "Games for work breaks"

# From template
playnite profile create "Kids" --template Kids

# With parent for inheritance
playnite profile create "Laptop Gaming" --parent "Gaming"
```

### Available Templates

- **Default**: Standard balanced settings
- **Kids**: Safe profile with restricted content
- **Work**: Minimal distractions
- **Testing**: Full access for testing
- **Family**: Shared family profile
- **Streaming**: Optimized for streaming

View templates:
```bash
playnite profile templates
```

### Switching Profiles

```bash
# Switch to a profile
playnite profile switch "Gaming"

# Force switch (if locked)
playnite profile switch "Gaming" --force
```

### Listing Profiles

```bash
# List all profiles
playnite profile list

# Detailed list
playnite profile list --all

# JSON output
playnite --json profile list
```

### Profile Information

```bash
playnite profile info "Gaming"
```

### Deleting Profiles

```bash
# Delete profile (keeps data)
playnite profile delete "Old Profile"

# Delete with all data
playnite profile delete "Old Profile" --delete-data --yes
```

## Managing Games

### Adding Games

```bash
# Add with executable path
playnite game add "Cyberpunk 2077" --path "/games/cyberpunk/Cyberpunk2077.exe"

# Specify source
playnite game add "My Game" --source manual

# With installation directory
playnite game add "Game" --path "/game.exe" --install-dir "/games/mygame"
```

### Listing Games

```bash
# All games
playnite game list

# Filter by source
playnite game list --source steam

# Favorites only
playnite game list --favorites

# Search
playnite game list --search "cyber"
```

### Game Information

```bash
playnite game info "Cyberpunk 2077"
```

### Launching Games

```bash
# Launch with default configuration
playnite game launch "Cyberpunk 2077"

# With specific configuration
playnite game launch "Cyberpunk 2077" --config "Desktop"

# Without waiting for exit
playnite game launch "My Game" --no-wait
```

### Managing Favorites

```bash
# Add to favorites
playnite game favorite "Cyberpunk 2077"

# Remove from favorites
playnite game favorite "Old Game" --remove
```

## Platform Configurations

Configurations allow different settings for the same game on different platforms.

### Creating Configurations

```bash
# Basic configuration
playnite config create --game "Cyberpunk 2077" --name "Desktop"

# With preset
playnite config create --game "My Game" --name "Laptop" --preset battery-saver

# For specific platform
playnite config create --game "My Game" --name "TV" --platform htpc --preset quality
```

### Available Presets

- **performance**: Maximum FPS, reduced quality
- **quality**: Maximum visual quality
- **balanced**: Balance of performance and quality
- **battery-saver**: Optimized for laptop battery life
- **streaming**: Optimized for streaming/recording
- **handheld**: Optimized for Steam Deck and similar
- **debug**: For troubleshooting

View presets:
```bash
playnite config templates
```

### Listing Configurations

```bash
# All configurations
playnite config list

# For specific game
playnite config list --game "Cyberpunk 2077"
```

### Configuration Details

```bash
playnite config info --game "Cyberpunk 2077" --config "Desktop"
```

### Validating Configurations

```bash
playnite config validate --game "My Game" --config "Desktop"
```

### Platform Detection

See what platform Playnite-Py detects:

```bash
playnite config detect
```

## Profile Security

### Password Protection

Set a password:
```bash
playnite profile set-password "Personal"
```

Switch with password:
```bash
playnite profile switch "Personal" --password
```

Remove password:
```bash
# You'll be prompted for the current password
playnite profile set-password "Personal" --current-password
```

## Export and Import

### Exporting Profiles

```bash
# Full export
playnite profile export "Gaming" --output ~/backup/gaming.ppf

# Without media files
playnite profile export "Gaming" -o backup.ppf --no-media
```

### Importing Profiles

```bash
# Import with original name
playnite profile import ~/backup/gaming.ppf

# Import with new name
playnite profile import ~/backup/gaming.ppf --name "Imported Gaming"

# Overwrite existing
playnite profile import backup.ppf --overwrite
```

## JSON Output

All commands support JSON output for scripting:

```bash
# List profiles as JSON
playnite --json profile list

# Create and get JSON response
playnite --json profile create "Test"

# Platform detection as JSON
playnite --json config detect
```

## Verbose Mode

Enable verbose logging:

```bash
playnite -v profile create "Test"
playnite --verbose game launch "My Game"
```

## Environment Variables

- `PLAYNITE_DATA_DIR`: Override data directory location

Example:
```bash
export PLAYNITE_DATA_DIR=/custom/path
playnite profile list
```
