# API Reference

This document covers the public Python API for programmatic use of the Playnite Python library.

## Contents

- [Game Models](#game-models)
- [GameDatabase](#gamedatabase)
- [Extensions](#extensions)
  - [ScriptManager](#scriptmanager)
  - [PlayniteSDK](#playnitesdk)
  - [ScriptConfig / SandboxLevel](#scriptconfig--sandboxlevel)
  - [LifecycleDispatcher](#lifecycledispatcher)
  - [ScriptLogger](#scriptlogger)
- [Plugins](#plugins)
  - [Plugin](#plugin)
  - [LibraryPlugin](#libraryplugin)
  - [MetadataPlugin](#metadataplugin)
  - [PluginManager](#pluginmanager)
- [Actions](#actions)
  - [Action / ActionType](#action--actiontype)
  - [ActionRegistry](#actionregistry)
  - [ActionInjector](#actioninjector)
  - [ActionChainExecutor](#actionchainexecutor)
  - [ActionExecutionLogger](#actionexecutionlogger)
  - [ActionScheduler](#actionscheduler)
  - [ProcessMonitor](#processmonitor)
  - [RollbackManager](#rollbackmanager)
  - [Templates](#templates)

---

## Game Models

```python
from playnite_python.models import (
    Game, GameAction, GameActionType, TrackingMode,
    Link, Platform, Genre, Company, Tag, Category,
    Series, AgeRating, Region, GameFeature, GameSource, CompletionStatus,
    ScoreRating, ScoreGroup, PastTimeSegment, PlaytimeCategory,
    InstallSizeGroup, InstallationStatus, GameField,
)
```

### `Game`

The primary entity representing a game in the library.

```python
@dataclass
class Game:
    id: str                      # UUID (auto-generated)
    name: str                    # Display name
    sorting_name: str            # Custom sort override (empty = use name)
    description: str
    notes: str
    is_installed: bool           # Whether the game is installed locally
    is_favorite: bool
    is_hidden: bool
    play_time: int               # Total playtime in seconds
    play_count: int
    install_directory: str       # Path to installation
    install_size: int            # Bytes
    game_id: str                 # External ID (e.g. Steam App ID)
    game_image_path: str         # Cover image path
    background_image_path: str
    platform_ids: List[str]
    genre_ids: List[str]
    developer_ids: List[str]
    publisher_ids: List[str]
    tag_ids: List[str]
    feature_ids: List[str]
    category_ids: List[str]
    series_ids: List[str]
    age_rating_ids: List[str]
    region_ids: List[str]
    source_id: str
    completion_status_id: str
    links: List[Link]
    game_actions: List[GameAction]
    added: datetime
    modified: datetime
    last_activity: Optional[datetime]
    release_date: Optional[datetime]
    last_size_scan_date: Optional[datetime]
    user_score: Optional[int]    # 0–100
    critic_score: Optional[int]
    community_score: Optional[int]
    roms: List[str]
    include_library_plugin_action: bool  # Whether to include the default library action
    is_installing: bool
    is_uninstalling: bool

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def release_year(self) -> Optional[int]: ...          # release_date.year or None

    @property
    def recent_activity(self) -> Optional[datetime]: ...  # max(last_activity, modified if installed)

    @property
    def is_custom_game(self) -> bool: ...                 # True when plugin_id is None

    @property
    def installation_status(self) -> InstallationStatus: ...

    @property
    def user_score_rating(self) -> ScoreRating: ...
    @property
    def community_score_rating(self) -> ScoreRating: ...
    @property
    def critic_score_rating(self) -> ScoreRating: ...

    @property
    def user_score_group(self) -> ScoreGroup: ...
    @property
    def community_score_group(self) -> ScoreGroup: ...
    @property
    def critic_score_group(self) -> ScoreGroup: ...

    @property
    def last_activity_segment(self) -> PastTimeSegment: ...
    @property
    def added_segment(self) -> PastTimeSegment: ...
    @property
    def modified_segment(self) -> PastTimeSegment: ...
    @property
    def recent_activity_segment(self) -> PastTimeSegment: ...

    @property
    def playtime_category(self) -> PlaytimeCategory: ...

    @property
    def install_size_group(self) -> InstallSizeGroup: ...

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]: ...
    def get_play_action(self) -> Optional[GameAction]: ...
    def get_copy(self) -> "Game": ...                     # Deep copy via to_dict/from_dict
    def get_name_group(self) -> str: ...                  # First letter or "#" for non-alpha
    def get_install_drive(self) -> str: ...               # Drive/mount point of install_directory
    def get_install_drive_group(self) -> str: ...         # Drive letter stripped of separators
    def get_install_size_group(self) -> InstallSizeGroup: ...
    def get_differences(self, other: "Game") -> List[GameField]: ...   # Changed fields
    def copy_diff_to(self, target: "Game") -> None: ...   # Copy non-default fields onto target

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Game": ...
```

### `GameAction`

A launchable action associated with a game (play, install, etc.).

```python
@dataclass
class GameAction:
    id: str
    name: str
    type: GameActionType
    path: str             # Executable path or URL
    arguments: str
    working_dir: str
    emulator_id: str
    emulator_profile_id: str
    override_default_args: bool
    tracking_mode: TrackingMode
    tracking_path: str
    initial_tracking_delay: int
    tracking_frequency: int
    is_play_action: bool
```

### `GameActionType`

```python
class GameActionType(Enum):
    FILE = "file"
    URL = "url"
    SCRIPT = "script"
    EMULATOR = "emulator"
```

### `TrackingMode`

```python
class TrackingMode(Enum):
    DEFAULT = "default"
    PROCESS = "process"
    DIRECTORY = "directory"
    PROCESS_NAME = "process_name"
    ORIGINAL_PROCESS = "OriginalProcess"
    NONE = "none"
```

### New Classification Enums

```python
class ScoreRating(Enum):
    NONE = "None"
    NEGATIVE = "Negative"   # 0–39
    MIXED = "Mixed"         # 40–74
    POSITIVE = "Positive"   # 75–100

class ScoreGroup(Enum):
    NONE = "None"           # no score
    O0x = "0x"              # 0–9
    O1x = "1x"              # 10–19
    # … O2x through O9x for 20–100

class PastTimeSegment(Enum):
    NEVER = "Never"
    TODAY = "Today"
    YESTERDAY = "Yesterday"
    PAST_WEEK = "PastWeek"
    PAST_MONTH = "PastMonth"
    PAST_YEAR = "PastYear"
    MORE_THAN_YEAR = "MoreThanYear"

class PlaytimeCategory(Enum):
    NOT_PLAYED = "NotPlayed"
    LESS_THAN_HOUR = "LessThanHour"
    O1_10 = "1_10"         # 1–10 hours
    O10_100 = "10_100"     # 10–100 hours
    O100_500 = "100_500"
    O500_1000 = "500_1000"
    O1000PLUS = "1000plus"

class InstallSizeGroup(Enum):
    NONE = "None"           # unknown / 0
    S0 = "S0"               # < 100 MB
    S1 = "S1"               # 100 MB – 1 GB
    S2 = "S2"               # 1–5 GB
    S3 = "S3"               # 5–10 GB
    S4 = "S4"               # 10–20 GB
    S5 = "S5"               # 20–40 GB
    S6 = "S6"               # 40–80 GB
    S7 = "S7"               # > 80 GB

class InstallationStatus(Enum):
    INSTALLED = "Installed"
    UNINSTALLED = "Uninstalled"

class GameField(Enum):
    """Identifies a field on the Game dataclass (used by get_differences / copy_diff_to)."""
    Name = "Name"; SortingName = "SortingName"; Description = "Description"
    # … 47 values total, one per Game field
```

---

## GameDatabase

```python
from playnite_python.database import GameDatabase
```

SQLite-backed game library. Uses WAL mode for concurrent reads.

```python
db = GameDatabase("/path/to/library.db")
db.open()

# Access collections
db.games          # GamesCollection
db.platforms      # Collection[Platform]
db.genres         # Collection[Genre]
db.companies      # Collection[Company]
db.tags           # Collection[Tag]
db.categories     # Collection[Category]
db.series         # Collection[Series]
db.age_ratings    # Collection[AgeRating]
db.regions        # Collection[Region]
db.features       # Collection[GameFeature]
db.sources        # Collection[GameSource]
db.completion_statuses  # Collection[CompletionStatus]

db.close()
```

### `Collection[T]`

Base class for all entity collections.

```python
# CRUD
collection.get(id: str) -> Optional[T]
collection.all() -> List[T]
collection.add(item: T) -> None
collection.update(item: T) -> None
collection.remove(id: str) -> None
collection.count() -> int
collection.exists(id: str) -> bool
```

### `GamesCollection`

Extends `Collection[Game]` with additional query methods:

```python
db.games.get_installed() -> List[Game]
db.games.search(query: str) -> List[Game]          # Name substring match
db.games.get_recently_played(limit=10) -> List[Game]
db.games.get_favorites() -> List[Game]
```

### Batch Operations

```python
with db.buffered_update():
    for game in games:
        db.games.add(game)
# Commits once at end of block
```

### Import / Export

```python
db.export_json("/path/to/backup.json")
db.import_json("/path/to/backup.json")
```

### Stats

```python
db.get_stats() -> Dict[str, Any]
# {"total_games": 243, "installed": 51, "favorites": 12, "total_play_time_hours": 1842.3}
```

---

## Extensions

```python
from playnite_python.extensions import (
    ScriptManager, PlayniteSDK, LifecycleDispatcher,
    ScriptConfig, SandboxLevel, ScriptLogger,
)
```

### ScriptManager

Manages the full lifecycle of extension scripts: discovery, loading, unloading, hot-reload, and hook dispatch.

```python
manager = ScriptManager(
    extensions_dir="~/.playnite_python/extensions",
    db=db,                      # GameDatabase (passed to script SDK)
    app_paths={                 # Paths exposed via __api__.paths
        "app": "/path/to/app",
        "config": "/path/to/config",
        "database": "/path/to/library.db",
        "logs": "/path/to/logs/scripts",
    },
)
```

#### Loading and Unloading

```python
# Load a specific file
script = manager.load_script("/path/to/my_script.py")

# Auto-discover and load all *.py in extensions_dir
loaded_names = manager.discover_and_load()   # List[str]

# Reload (re-execute file, re-register hooks)
script = manager.reload_script("my_script")

# Reload all
manager.reload_all()

# Unload
manager.unload_script("my_script")

# Enable / Disable (hooks only)
manager.enable_script("my_script")
manager.disable_script("my_script")
```

#### Querying

```python
script = manager.get_script("my_script")   # LoadedScript | None
all_scripts = manager.list_scripts()       # List[LoadedScript]
```

#### Lifecycle Dispatch

```python
# The dispatcher is accessible
manager.lifecycle.on_application_started()
manager.lifecycle.on_game_starting(game)
manager.lifecycle.on_game_stopped(game, elapsed_seconds=3600.0)

# Or through the manager's shorthand
manager.call_hook("on_game_stopped", game, 3600.0)
```

#### Hot Reload File Watcher

```python
# Start watching extensions_dir for *.py changes (daemon thread)
manager.start_file_watcher(interval=2.0)
```

#### Script namespace access

```python
# Call a function defined inside a loaded script
result = manager.invoke_function("my_script", "some_function", arg1, arg2)
# Raises KeyError if the script is not loaded
# Raises AttributeError if the function is not found or not callable

# Inject a variable into a loaded script's namespace
manager.set_variable("my_script", "config", {"key": "value"})
```

#### Metrics

```python
# All scripts
metrics = manager.get_metrics()   # Dict[str, dict]

# One script
metrics = manager.get_metrics("my_script")
# {"my_script": {"call_count": 42, "error_count": 1, "timeout_count": 0, "avg_duration_ms": 12.4}}
```

#### `LoadedScript`

The object returned by `load_script` and `get_script`:

```python
script.name             # str — script stem
script.path             # str — absolute file path
script.config           # ScriptConfig
script.namespace        # Dict[str, Any] — script globals after exec
script.registered_hooks # List[str] — hook names registered
script.api              # PlayniteSDK instance for this script
script.exec_history     # List[dict] — recent execution records
```

---

### PlayniteSDK

The API object exposed to scripts as `__api__` and `api`.

```python
sdk = PlayniteSDK(db=db, paths=paths_dict, script_name="my_script")
```

#### `sdk.database`

```python
# Game CRUD
sdk.database.get_games() -> List[Game]
sdk.database.get_game(id: str) -> Optional[Game]
sdk.database.search_games(query: str) -> List[Game]
sdk.database.update_game(game: Game) -> None
sdk.database.add_game(game: Game) -> None
sdk.database.remove_game(id: str) -> None

# Entity collections (read-only pass-throughs to GameDatabase collections)
sdk.database.platforms           # Collection[Platform]
sdk.database.genres              # Collection[Genre]
sdk.database.tags                # Collection[Tag]
sdk.database.categories          # Collection[Category]
sdk.database.series              # Collection[Series]
sdk.database.age_ratings         # Collection[AgeRating]
sdk.database.regions             # Collection[Region]
sdk.database.features            # Collection[GameFeature]
sdk.database.sources             # Collection[GameSource]
sdk.database.completion_statuses # Collection[CompletionStatus]
sdk.database.companies           # Collection[Company]

sdk.database.database_path -> str   # Path to the underlying SQLite file

# Batch writes — defers all commits until the block exits
with sdk.database.buffered_update():
    for game in games:
        sdk.database.add_game(game)
```

#### `sdk.notifications`

```python
# Rich notification (preferred)
sdk.notifications.add(
    notification_id: str,
    text: str,
    ntype: NotificationType = NotificationType.INFO,
    action: Optional[Callable[[], None]] = None,
) -> None

sdk.notifications.remove(notification_id: str) -> None
sdk.notifications.remove_all() -> None

sdk.notifications.messages -> List[NotificationMessage]   # Current notifications
sdk.notifications.count -> int

# Backward-compatible shorthand
sdk.notifications.show(message: str, type: str = "info") -> None
# type: "info" | "error"
```

`NotificationType` and `NotificationMessage`:

```python
class NotificationType(Enum):
    INFO = "info"
    ERROR = "error"

@dataclass
class NotificationMessage:
    id: str
    text: str
    type: NotificationType
    activation_action: Optional[Callable[[], None]]   # callback when user clicks
```

#### `sdk.dialogs`

```python
sdk.dialogs.show_message(message: str, title: str = "") -> None
sdk.dialogs.show_input(prompt: str, default: str = "") -> Optional[str]
sdk.dialogs.show_yes_no(message: str, title: str = "") -> bool
sdk.dialogs.show_file_picker(title: str = "") -> Optional[str]
sdk.dialogs.show_folder_picker(title: str = "") -> Optional[str]
```

All dialog methods print to stdout/stderr in headless mode.

#### `sdk.paths`

```python
sdk.paths.application_path      # str
sdk.paths.config_path           # str
sdk.paths.database_path         # str
sdk.paths.extension_path        # str
sdk.paths.extension_data_path   # str — per-script data dir (auto-created)
sdk.paths.log_path              # str
```

#### `sdk.addons`

```python
sdk.addons.add_main_menu_item(name: str, callback: Callable) -> None
sdk.addons.add_game_menu_item(name: str, callback: Callable) -> None
sdk.addons.get_main_menu_items() -> List[Dict]
sdk.addons.get_game_menu_items() -> List[Dict]
```

#### Game control helpers

```python
# Replace {game.<field>} placeholders in a template string
sdk.expand_game_variables(game: Game, template: str) -> str
# e.g. sdk.expand_game_variables(game, "Playing {game.name}") -> "Playing Half-Life 2"

# Fire lifecycle hooks (raises ValueError if game_id is not in the database)
sdk.start_game(game_id: str) -> None      # fires on_game_starting
sdk.install_game(game_id: str) -> None    # fires on_game_installed
sdk.uninstall_game(game_id: str) -> None  # fires on_game_uninstalled
```

---

### ScriptConfig / SandboxLevel

```python
from playnite_python.extensions import ScriptConfig, SandboxLevel

class SandboxLevel(Enum):
    NONE = "none"
    STANDARD = "standard"
    STRICT = "strict"

config = ScriptConfig.from_file("/path/to/script.yaml")
config = ScriptConfig.from_dict({"enabled": True, "timeout": 30})
config = ScriptConfig.default()

config.enabled          # bool
config.timeout          # int (seconds; 0 = unlimited)
config.sandbox_level    # SandboxLevel
config.allowed_paths    # List[str]
config.dependencies     # List[str]
config.metadata         # Dict[str, Any]

config.to_dict() -> Dict[str, Any]
config.save("/path/to/script.yaml") -> None
config.is_path_allowed(path: str) -> bool
```

---

### LifecycleDispatcher

```python
from playnite_python.extensions.lifecycle import LifecycleDispatcher

dispatcher = LifecycleDispatcher()

# Register a callback manually
dispatcher.register("on_game_stopped", my_callback, script_name="my_script")

# Auto-register all hooks found in a namespace
registered = dispatcher.register_from_namespace(namespace_dict, "my_script")

# Unregister all hooks from a script
dispatcher.unregister_script("my_script")

# Fire events
dispatcher.on_application_started()
dispatcher.on_application_stopped()
dispatcher.on_library_updated()
dispatcher.on_script_loaded(script_name)
dispatcher.on_script_unloaded(script_name)
dispatcher.on_game_starting(game)
dispatcher.on_game_started(game)
dispatcher.on_game_stopped(game, elapsed_seconds)
dispatcher.on_game_installed(game)
dispatcher.on_game_uninstalled(game)
dispatcher.on_game_startup_cancelled(game)
dispatcher.on_game_installation_cancelled(game)
dispatcher.on_game_selected(game)        # game may be None (deselection)
dispatcher.on_settings_changed()

# Introspection
dispatcher.list_handlers()    # Dict[str, List[str]]  hook→[script_names]
dispatcher.handler_count()    # int — total handlers
dispatcher.handler_count("on_game_stopped")  # handlers for one hook
```

All hook dispatches are exception-isolated: an error in one handler does not prevent others from receiving the event.

---

### ScriptLogger

```python
from playnite_python.extensions.logger import ScriptLogger

logger = ScriptLogger(script_name="my_script", log_dir="/path/to/logs")

logger.Info("Informational message")
logger.Warning("Something unexpected")
logger.Error("Something failed")
logger.Debug("Verbose diagnostic info")

# Pythonic aliases
logger.info("...")
logger.warning("...")
logger.error("...")
logger.debug("...")

# In-memory history (last 1000 entries)
history = logger.get_history()   # List[Dict]
```

Log files are written to `<log_dir>/<script_name>.log` with rotation at 1 MB, keeping 5 backups.

---

## Plugins

```python
from playnite_python.plugins import (
    Plugin, PluginProperties,
    MainMenuItem, GameMenuItem, GetMainMenuItemsArgs, GetGameMenuItemsArgs,
    LibraryPlugin, LibraryPluginProperties, LibraryGetGamesArgs, GameMetadata,
    MetadataPlugin, MetadataField, OnDemandMetadataProvider,
    MetadataRequestOptions, GetMetadataFieldArgs,
    PluginManager,
)
```

### `Plugin`

Abstract base class for all plugins.

```python
class Plugin(ABC):
    def __init__(self, api: PlayniteSDK) -> None: ...

    @property
    @abstractmethod
    def plugin_id(self) -> str: ...   # Unique reverse-DNS identifier

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def properties(self) -> PluginProperties: ...   # Capabilities flags

    # Lifecycle hooks — all default to no-op; override as needed
    def on_application_started(self) -> None: ...
    def on_application_stopped(self) -> None: ...
    def on_library_updated(self) -> None: ...
    def on_game_starting(self, game: Game) -> None: ...
    def on_game_started(self, game: Game) -> None: ...
    def on_game_stopped(self, game: Game, elapsed_seconds: float) -> None: ...
    def on_game_installed(self, game: Game) -> None: ...
    def on_game_uninstalled(self, game: Game) -> None: ...
    def on_game_startup_cancelled(self, game: Game) -> None: ...
    def on_game_installation_cancelled(self, game: Game) -> None: ...
    def on_game_selected(self, game: Optional[Game]) -> None: ...
    def on_settings_changed(self) -> None: ...

    # Menu integration
    def get_main_menu_items(self, args: GetMainMenuItemsArgs) -> List[MainMenuItem]: ...
    def get_game_menu_items(self, args: GetGameMenuItemsArgs) -> List[GameMenuItem]: ...

    # Action providers
    def get_play_actions(self, game: Game) -> List[Dict]: ...
    def get_install_actions(self, game: Game) -> List[Dict]: ...
    def get_uninstall_actions(self, game: Game) -> List[Dict]: ...

    # Settings persistence
    def load_plugin_settings(self) -> Optional[Dict]: ...   # Reads settings.json from data dir
    def save_plugin_settings(self, settings: Dict) -> None: ...
    def get_plugin_user_data_path(self) -> str: ...         # <extension_data_path>/<plugin_id>
```

### `LibraryPlugin`

Discovers games from an external source and imports them.

```python
class LibraryPlugin(Plugin):
    @abstractmethod
    def get_games(self, args: LibraryGetGamesArgs) -> List[GameMetadata]: ...

    @property
    def library_icon(self) -> str: ...         # Path or resource key
    @property
    def library_background(self) -> str: ...

    def import_games(
        self, args: Optional[LibraryGetGamesArgs] = None
    ) -> List[Game]: ...
    # Calls get_games() and converts each GameMetadata to a Game object
```

`GameMetadata` fields:

```python
@dataclass
class GameMetadata:
    game_id: str; name: str
    platform_ids: List[str]; developer_ids: List[str]; publisher_ids: List[str]
    genre_ids: List[str]; tag_ids: List[str]; feature_ids: List[str]
    description: str; release_date: Optional[datetime]; links: List
    icon: str; cover_image: str; background_image: str
    community_score: Optional[int]; critic_score: Optional[int]
```

### `MetadataPlugin`

Downloads metadata from an external source (e.g. IGDB, MobyGames).

```python
class MetadataPlugin(Plugin):
    @property
    @abstractmethod
    def supported_fields(self) -> List[MetadataField]: ...

    @abstractmethod
    def get_metadata_provider(
        self, options: MetadataRequestOptions
    ) -> OnDemandMetadataProvider: ...

    def download_metadata(
        self,
        game: Game,
        fields: Optional[List[MetadataField]] = None,
    ) -> Dict[str, Any]: ...
    # Returns {MetadataField.value: value} for each requested field
```

`MetadataField` values: `Name`, `Genres`, `ReleaseDate`, `Developers`, `Publishers`,
`Tags`, `Description`, `Links`, `CriticScore`, `CommunityScore`, `Icon`, `CoverImage`,
`BackgroundImage`, `Features`, `Series`, `AgeRating`, `Region`, `Platform`, `InstallSize`.

`OnDemandMetadataProvider` — override the field getters you support (all return `None` by default):

```python
class OnDemandMetadataProvider:
    def get_name(self, args: GetMetadataFieldArgs) -> Optional[str]: ...
    def get_genres(self, args: GetMetadataFieldArgs) -> Optional[List]: ...
    def get_cover_image(self, args: GetMetadataFieldArgs) -> Optional[str]: ...
    # … one getter per MetadataField
```

### `PluginManager`

Registers plugins and wires their lifecycle hooks into a `LifecycleDispatcher`.

```python
lifecycle = LifecycleDispatcher()
mgr = PluginManager(lifecycle)

# Register / unregister
mgr.register_plugin(plugin: Plugin) -> None
mgr.unregister_plugin(plugin_id: str) -> None   # raises KeyError if not found

# Dynamic loading
plugin = mgr.load_plugin_from_file(path: str, api: PlayniteSDK) -> Plugin
# Finds first Plugin subclass in the .py file, instantiates and registers it

# Introspection
mgr.get_plugins() -> List[Plugin]
mgr.get_plugin(plugin_id: str) -> Optional[Plugin]

# Aggregated menu items from all registered plugins
mgr.get_all_main_menu_items() -> List[MainMenuItem]
mgr.get_all_game_menu_items(games: List[Game]) -> List[GameMenuItem]
```

---

## Actions

```python
from playnite_python.actions import (
    Action, ActionType, ActionCondition, ActionChainDef,
    ActionLog, ActionVariable, ActionProfile,
    ActionRegistry, ActionChainExecutor, ActionInjector,
    ProcessMonitor, ActionScheduler, ActionExecutionLogger,
    RollbackManager, ALL_TEMPLATES,
)
```

### Action / ActionType

```python
class ActionType(Enum):
    PLAY = "play"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    PRE_LAUNCH = "pre_launch"
    POST_EXIT = "post_exit"
    CUSTOM = "custom"

class ActionExecutorType(Enum):
    SCRIPT = "script"
    EXECUTABLE = "executable"
    URL = "url"

@dataclass
class Action:
    id: str                              # UUID
    name: str
    type: ActionType
    executor_type: ActionExecutorType
    script: str                          # Inline Python (SCRIPT executor)
    executable: str                      # Path (EXECUTABLE executor)
    arguments: str                       # Args (supports {var} substitution)
    working_dir: str
    conditions: List[ActionCondition]
    priority: int                        # Lower = runs first
    async_: bool
    timeout: int                         # Seconds; 0 = unlimited
    game_id: Optional[str]              # None = global
    enabled: bool
    rollback_script: str
    source_script: Optional[str]
    variables: List[ActionVariable]
    triggers: List[TriggerType]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]: ...

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Action": ...
```

---

### ActionRegistry

Persistent registry for actions, chains, and profiles. Backed by a JSON file.

```python
registry = ActionRegistry(config_dir="/path/to/config")
```

#### Actions

```python
registry.add_action(action: Action) -> Action
registry.get_action(action_id: str) -> Optional[Action]
registry.remove_action(action_id: str) -> None
registry.update_action(action: Action) -> None

# Query
registry.list_actions(
    game_id: Optional[str] = None,
    action_type: Optional[ActionType] = None,
    enabled_only: bool = True,
) -> List[Action]    # sorted by priority

registry.get_actions_for_game(game_id: str, action_type: ActionType) -> List[Action]
registry.list_global_actions(action_type: ActionType) -> List[Action]
```

#### Chains

```python
registry.add_chain(chain: ActionChainDef) -> ActionChainDef
registry.get_chain(chain_id: str) -> Optional[ActionChainDef]
registry.remove_chain(chain_id: str) -> None
registry.list_chains(game_id: Optional[str] = None) -> List[ActionChainDef]
```

#### Profiles

```python
registry.add_profile(profile: ActionProfile) -> ActionProfile
registry.get_profile(profile_id: str) -> Optional[ActionProfile]
registry.remove_profile(profile_id: str) -> None
registry.list_profiles() -> List[ActionProfile]
registry.get_profile_actions(game: Game) -> List[Action]
```

---

### ActionInjector

High-level interface for runtime action injection.

```python
injector = ActionInjector(registry)

# General injection
action = injector.inject(action: Action, game_id: Optional[str] = None) -> Action

# Typed convenience methods
injector.inject_play(game_id: str, script: str, name: str = "Custom Play", **kwargs) -> Action
injector.inject_pre_launch(script: str, name: str = "Pre-Launch Action",
                            game_id: Optional[str] = None, priority: int = 100, **kwargs) -> Action
injector.inject_post_exit(script: str, name: str = "Post-Exit Action",
                           game_id: Optional[str] = None, priority: int = 100, **kwargs) -> Action

# Replace all PLAY actions for a game
injector.override_launcher(game_id: str, script: str, name: str = "Custom Launcher") -> Action

# Mutate launch parameters via a pre-launch script
injector.modify_launch_params(
    game: Game,
    arguments_append: str = "",
    env_vars: Optional[Dict[str, str]] = None,
) -> None

# Removal
injector.revoke(action_id: str) -> None
injector.revoke_by_source(source_script: str) -> int   # returns count removed

# Query
injector.get_injected_actions(game_id: Optional[str] = None,
                               action_type: Optional[ActionType] = None) -> List[Action]

# Callback on every inject
injector.on_inject(callback: Callable[[Action], None]) -> None

# Access the underlying registry
injector.registry -> ActionRegistry
```

---

### ActionChainExecutor

Executes a list of actions in priority order.

```python
executor = ActionChainExecutor()

logs, success = executor.execute(
    actions: List[Action],
    game: Optional[Game] = None,
    stop_on_failure: bool = False,
    on_action_complete: Optional[Callable[[ActionLog], None]] = None,
) -> Tuple[List[ActionLog], bool]
```

- Actions with `async_=True` are dispatched in a background thread and do not block.
- Actions whose conditions fail produce a log entry with `output="Skipped: ..."` and `success=True`.
- If `stop_on_failure=True`, the chain aborts on the first non-async failure.

---

### ActionExecutionLogger

JSONL-backed execution log.

```python
logger = ActionExecutionLogger("/path/to/actions.jsonl")

# Write
logger.record(log: ActionLog) -> None
logger.record_many(logs: List[ActionLog]) -> None

# Read
logger.get_recent(limit: int = 100) -> List[ActionLog]
logger.get_for_action(action_id: str, limit: int = 50) -> List[ActionLog]
logger.get_for_game(game_id: str, limit: int = 50) -> List[ActionLog]
logger.get_failures(limit: int = 50) -> List[ActionLog]
logger.query(
    action_id: Optional[str] = None,
    game_id: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = 100,
) -> List[ActionLog]

# Stats
logger.get_stats() -> Dict[str, Any]
# {"total", "success", "failure", "success_rate",
#  "avg_duration_ms", "max_duration_ms", "min_duration_ms"}

# Prune
logger.rotate(keep_last: int = 1000) -> None
```

---

### ActionScheduler

Runs actions on timers or in response to events. Uses a daemon background thread.

```python
def run_action(action_id: str) -> Optional[ActionLog]:
    action = registry.get_action(action_id)
    if not action:
        return None
    logs, _ = executor.execute([action])
    return logs[0] if logs else None

scheduler = ActionScheduler(execute_fn=run_action)
scheduler.start()
scheduler.stop()

# Schedule
from datetime import timedelta

job_id = scheduler.schedule_once(action_id: str, delay: timedelta) -> str
job_id = scheduler.schedule_interval(action_id: str, interval: timedelta) -> str
job_id = scheduler.schedule_daily(action_id: str, hour: int, minute: int = 0) -> str
job_id = scheduler.schedule_on_event(action_id: str, trigger: TriggerType) -> str

# Fire an event (dispatches all on_event jobs registered for that trigger)
scheduler.fire_event(trigger: TriggerType) -> None

# Job management
scheduler.cancel(job_id: str) -> None
scheduler.enable(job_id: str) -> None
scheduler.disable(job_id: str) -> None
scheduler.list_jobs() -> List[ScheduledJob]
```

---

### ProcessMonitor

Monitors a running game process and fires callbacks on lifecycle events.

```python
monitor = ProcessMonitor()

# Callbacks (set before starting)
monitor.on_started: Optional[Callable[[ProcessInfo], None]]
monitor.on_stopped: Optional[Callable[[ProcessInfo], None]]
monitor.on_crashed: Optional[Callable[[ProcessInfo], None]]
monitor.on_stats: Optional[Callable[[ProcessInfo], None]]

# Auto-restart on crash
monitor.auto_restart: bool = False
monitor.max_restarts: int = 3
monitor.launch_cmd: Optional[List[str]] = None

# Stats interval (seconds between on_stats callbacks)
monitor.stats_interval: float = 60.0

# Start monitoring
monitor.start_monitoring(
    pid: Optional[int] = None,
    process_name: Optional[str] = None,
    launch_cmd: Optional[List[str]] = None,
) -> None

monitor.stop() -> None
monitor.is_running() -> bool
```

`ProcessInfo` fields: `pid`, `process_name`, `started_at`, `launch_cmd`, `restart_count`, `elapsed_seconds` (property).

Process detection tries `psutil` first, then falls back to `pgrep` (macOS/Linux) or `tasklist` (Windows).

---

### RollbackManager

LIFO stack of rollback entries.

```python
from playnite_python.actions import RollbackManager

rm = RollbackManager()

rm.push(action: Action, game: Optional[Game] = None) -> None
# Only pushed if action.rollback_script is non-empty

rm.rollback_last() -> Optional[str]    # Returns output/error string
rm.rollback_all() -> List[str]         # Returns list of output strings
rm.clear() -> None
rm.depth -> int                         # Current stack depth
```

Rollback scripts execute with `action` and `game` in scope. Exceptions are caught and returned as strings; they never propagate.

---

### Templates

Pre-built action factories for common tasks.

```python
from playnite_python.actions import ALL_TEMPLATES
from playnite_python.actions.template import (
    discord_rich_presence,
    discord_rich_presence_clear,
    close_background_apps,
    enable_vpn,
    disable_vpn,
    game_backup,
    screenshot_on_exit,
    notify_session_start,
    notify_session_end,
    playtime_log,
)

# No-arg templates (also in ALL_TEMPLATES dict)
action = notify_session_start()
action = notify_session_end()
action = discord_rich_presence_clear()
action = screenshot_on_exit(output_dir="~/screenshots")
action = playtime_log(log_file="~/playtime.log")

# Templates requiring args
action = discord_rich_presence(game_name_expr="{game.name}")
action = close_background_apps(["Chrome.exe", "Slack.exe"])
action = enable_vpn("openvpn --config /etc/vpn.conf")
action = disable_vpn("openvpn --disconnect")
action = game_backup(
    save_dir_expr="{game.install_dir}/saves",
    backup_root="~/game_backups",
)

# ALL_TEMPLATES contains no-arg templates only (suitable for CLI application)
ALL_TEMPLATES: Dict[str, Callable[[], Action]]
```

All factory functions return an `Action` instance ready for injection.
