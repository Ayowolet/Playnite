# API Documentation

Python API reference for Playnite-Py.

## Overview

```python
from playnite_py import ProfileManager, ConfigurationManager
from playnite_py import Profile, ProfileSettings, ProfileTemplate
from playnite_py import Game, GameAction, GameSource
from playnite_py import PlatformConfiguration, DisplayConfig, PlatformType
```

## ProfileManager

Central manager for profile operations.

### Initialization

```python
from playnite_py import ProfileManager
from pathlib import Path

# Default data directory
manager = ProfileManager()

# Custom data directory
manager = ProfileManager(data_dir=Path("/custom/path"))

# As context manager
with ProfileManager() as manager:
    profile = manager.create_profile("Gaming")
```

### Creating Profiles

```python
# Basic profile
profile = manager.create_profile("Gaming")

# With options
profile = manager.create_profile(
    name="Kids Gaming",
    description="Safe games for children",
    template="Kids",
    set_as_default=True,
)

# With parent for inheritance
profile = manager.create_profile(
    name="Laptop Gaming",
    parent_profile="Gaming",
)
```

### Retrieving Profiles

```python
# By name
profile = manager.get_profile("Gaming")

# By ID
from uuid import UUID
profile = manager.get_profile_by_id(UUID("..."))

# All profiles
profiles = manager.list_profiles()

# Active profile
current = manager.get_current_profile()

# Default profile
default = manager.get_default_profile()
```

### Switching Profiles

```python
# Simple switch
profile = manager.switch_profile("Gaming")

# With password
profile = manager.switch_profile("Personal", password="secret")

# Force (ignore lock)
profile = manager.switch_profile("Gaming", force=True)
```

### Profile Operations

```python
# Rename
manager.rename_profile("Old Name", "New Name")

# Duplicate
copy = manager.duplicate_profile("Original", "Copy")

# Delete
manager.delete_profile("Old Profile")
manager.delete_profile("Test", delete_data=True)

# Set default
manager.set_default_profile("Gaming")
```

### Profile Settings

```python
from playnite_py import ProfileSettings

# Update settings
new_settings = ProfileSettings(
    theme="dark",
    language="en",
    default_view="grid",
)
manager.update_profile_settings("Gaming", new_settings)

# Get effective settings (with inheritance)
effective = manager.get_effective_settings("Laptop Gaming")
```

### Security

```python
# Set password
manager.set_profile_password("Personal", "secret123")

# Change password
manager.set_profile_password(
    "Personal",
    "new_password",
    current_password="old_password"
)

# Remove password
manager.remove_profile_password("Personal", "current_password")
```

### Export/Import

```python
from pathlib import Path

# Export
manager.export_profile(
    "Gaming",
    output_path=Path("~/backup/gaming.ppf"),
    include_games=True,
    include_media=True,
)

# Import
profile = manager.import_profile(
    import_path=Path("~/backup/gaming.ppf"),
    new_name="Imported Gaming",
)
```

### Callbacks

```python
def on_profile_switch(old_profile, new_profile):
    print(f"Switched to {new_profile.name}")

manager.add_switch_callback(on_profile_switch)
manager.remove_switch_callback(on_profile_switch)
```

### Cleanup

```python
# Find unused profiles
unused = manager.cleanup_unused_profiles(days_unused=90, dry_run=True)

# Delete unused profiles
manager.cleanup_unused_profiles(days_unused=90, dry_run=False)

# Close manager
manager.close()
```

---

## ConfigurationManager

Manager for platform-specific game configurations.

### Initialization

```python
from playnite_py import ConfigurationManager

# Get database from profile manager
db = profile_manager.get_profile_database()
config_manager = ConfigurationManager(db)
```

### Creating Configurations

```python
from playnite_py import PlatformType, DisplayConfig

# Basic configuration
config = config_manager.create_configuration(
    game_id=game.id,
    name="Desktop",
)

# With preset
config = config_manager.create_configuration(
    game_id=game.id,
    name="High Quality",
    preset="Quality",
)

# Full configuration
config = config_manager.create_configuration(
    game_id=game.id,
    name="Custom",
    platform_type=PlatformType.DESKTOP,
    display=DisplayConfig(
        width=2560,
        height=1440,
        fullscreen=True,
        vsync=True,
    ),
    is_default=True,
)
```

### Retrieving Configurations

```python
# By ID
config = config_manager.get_configuration(config_id)

# For a game
configs = config_manager.get_configurations_for_game(game.id)

# Default for game
default = config_manager.get_default_configuration(game.id)

# Best for current platform
best = config_manager.get_configuration_for_platform(game.id)

# For specific platform
laptop = config_manager.get_configuration_for_platform(
    game.id,
    platform_type=PlatformType.LAPTOP
)
```

### Configuration Operations

```python
# Update
config_manager.update_configuration(
    config.id,
    display=DisplayConfig(width=1920, height=1080),
)

# Delete
config_manager.delete_configuration(config.id)

# Set as default
config_manager.set_default_configuration(game.id, config.id)

# Duplicate
copy = config_manager.duplicate_configuration(config.id, "Copy")

# Apply preset
config_manager.apply_preset_to_configuration(config.id, "Performance")
```

### Validation

```python
is_valid, errors = config_manager.validate_configuration(config.id)
if not is_valid:
    for error in errors:
        print(f"Error: {error}")
```

### Batch Operations

```python
# Create same configuration for multiple games
results = config_manager.batch_create_configurations(
    game_ids=[game1.id, game2.id, game3.id],
    name="Performance",
    preset="performance",
)
```

### Statistics

```python
# Record launch
config_manager.record_launch(
    config.id,
    success=True,
    session_minutes=60,
)

# Get statistics
stats = config_manager.get_configuration_statistics(config.id)
print(f"Success rate: {stats['success_rate']}")
```

---

## Models

### Profile

```python
from playnite_py import Profile, ProfileSettings

profile = Profile(
    name="Gaming",
    description="Main gaming profile",
    settings=ProfileSettings(
        theme="dark",
        language="en",
        default_view="grid",
    ),
)

# Serialization
data = profile.to_dict()
restored = Profile.from_dict(data)

# From template
from playnite_py import ProfileTemplate
template = ProfileTemplate(name="Gaming Template")
profile = Profile.from_template(template, "My Profile")
```

### Game

```python
from playnite_py import Game, GameAction, GameActionType, GameSource

game = Game(
    name="Cyberpunk 2077",
    source=GameSource.GOG,
)

# Add action
game.actions.append(GameAction(
    name="Play",
    type=GameActionType.FILE,
    path="/games/cyberpunk/Cyberpunk2077.exe",
    is_default=True,
))

# Get default action
action = game.get_default_action()

# Record playtime
game.statistics.record_session(playtime_minutes=60)
```

### PlatformConfiguration

```python
from playnite_py import (
    PlatformConfiguration,
    DisplayConfig,
    AudioConfig,
    LaunchArguments,
    EnvironmentConfig,
    PlatformType,
    GraphicsQuality,
)

config = PlatformConfiguration(
    name="Desktop",
    game_id=game.id,
    platform_type=PlatformType.DESKTOP,
    graphics_quality=GraphicsQuality.ULTRA,
    display=DisplayConfig(
        width=2560,
        height=1440,
        fullscreen=True,
        vsync=True,
    ),
    audio=AudioConfig(
        volume=100,
        speaker_config="5.1",
    ),
    launch_args=LaunchArguments(
        add_arguments=["-dx12", "-high"],
    ),
    environment=EnvironmentConfig(
        set_variables={"DXVK_HUD": "fps"},
    ),
)

# Validation
errors = config.validate_configuration()
```

---

## Platform Detection

```python
from playnite_py.configurations.detection import (
    PlatformDetector,
    detect_current_platform,
)

# Quick detection
platform = detect_current_platform()
print(platform)  # PlatformType.DESKTOP

# Full hardware profile
detector = PlatformDetector()
profile = detector.get_hardware_profile()

print(f"Platform: {profile.platform}")
print(f"CPU: {profile.cpu_name}")
print(f"RAM: {profile.ram_mb} MB")
print(f"GPUs: {[g.name for g in profile.gpus]}")
print(f"Displays: {[(d.width, d.height) for d in profile.displays]}")
print(f"Power: {profile.power_source}")
print(f"Is laptop: {profile.is_laptop}")
print(f"Is Steam Deck: {profile.is_steam_deck}")
```

---

## Game Launching

```python
from playnite_py.configurations.launcher import GameLauncher

launcher = GameLauncher()

# Launch with configuration
result = launcher.launch_game(
    game=game,
    config=config,
    wait_for_exit=True,
)

if result.success:
    print(f"Played for {result.duration_seconds // 60} minutes")
else:
    print(f"Launch failed: {result.error_message}")

# Validate before launch
valid, errors = launcher.validate_launch(game)
```

---

## Templates

### Profile Templates

```python
from playnite_py.profiles.templates import (
    ProfileTemplateManager,
    get_builtin_templates,
)

# Get builtin templates
templates = get_builtin_templates()
for t in templates:
    print(f"{t.name}: {t.description}")

# Use template manager
template_manager = ProfileTemplateManager(repo)

# Get template
template = template_manager.get_template("Kids")

# Create custom template
custom = template_manager.create_template(
    name="My Template",
    description="Custom settings",
    settings=ProfileSettings(theme="dark"),
)

# Create from existing profile
template = template_manager.create_template_from_profile(
    profile=existing_profile,
    template_name="Backup Template",
)
```

### Configuration Templates

```python
from playnite_py.configurations.templates import (
    ConfigTemplateManager,
    get_builtin_config_templates,
)

# Get builtin templates
templates = get_builtin_config_templates()

# List templates by platform
laptop_templates = template_manager.list_templates_by_platform(
    PlatformType.LAPTOP
)
```

---

## Error Handling

```python
from playnite_py import ProfileManager

manager = ProfileManager()

try:
    manager.create_profile("Test")
except ValueError as e:
    print(f"Invalid input: {e}")

try:
    manager.switch_profile("Protected", password="wrong")
except PermissionError as e:
    print(f"Access denied: {e}")

try:
    manager.switch_profile("Locked")
except RuntimeError as e:
    print(f"Profile locked: {e}")
```

---

## Database Access

```python
from playnite_py.core.database import DatabaseEngine
from playnite_py.core.database.repositories import GameRepository

# Create database
db = DatabaseEngine.create_for_profile(Path("/path/to/profile"))

# Use repository
game_repo = GameRepository(db)
games = game_repo.get_all()
game = game_repo.get_by_name("Cyberpunk 2077")

# Search
results = game_repo.search("cyber")

# Close
db.close()
```
