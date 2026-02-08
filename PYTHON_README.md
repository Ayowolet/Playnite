# Playnite Python - Modern Game Library Manager

A Python implementation of a comprehensive game library management system with advanced organization features and a headless controller input system for Big Picture mode.

**Note**: This is a Python reimplementation focused on library organization and headless controller input. For the original C# Playnite application, see the main [README.md](README.md).

## Features

### 1. Advanced Library Organisation
- **Custom Categories, Tags, and Collections**: Organize your games with flexible metadata
- **Smart Collections**: Auto-updating collections based on rules (e.g., "All PC RPGs with 10+ hours playtime")
- **Powerful Filtering**: Filter by platform, genre, release year, playtime, completion status, rating, and more
- **Fuzzy Search**: Find games even with typos using intelligent matching
- **Custom Sorting**: Sort by any field (name, playtime, release date, rating, etc.)
- **Bulk Operations**: Apply changes to multiple games at once
- **Favourites System**: Quick access to your favourite games
- **Hide Games**: Hide games from library view without deleting them
- **View Presets**: Save and restore complete view configurations

### 2. Controller Input & Big Picture Navigation
- **Headless Controller System**: Fully testable controller input system decoupled from rendering
- **Controller Detection**: Automatically detect connected game controllers
- **Configurable Mappings**: JSON/YAML configuration for button mappings
- **Navigation State Machine**: Sophisticated UI navigation for Big Picture mode
- **Grid and List Navigation**: Navigate game libraries in multiple view modes
- **Controller Simulation**: Programmatically simulate controller input for automated testing
- **Rumble Support**: Controller vibration/rumble API

### 3. CLI-First Design
- **Complete CLI Interface**: All functionality accessible via command line
- **JSON Output**: Automation-friendly JSON output for all commands
- **Scriptable**: Perfect for CI/CD, automation, and scripting
- **Headless Testing**: Test all features without GUI

## Installation

```bash
# Navigate to the Python implementation directory
cd model_a

# Install dependencies
pip install -r requirements.txt

# Install in development mode (optional)
pip install -e .
```

## Quick Start

### Initialize Database

```bash
python -m playnite_py.cli.main init --db-path my_library.db
```

### Add Games

```bash
# Add a game with metadata
python -m playnite_py.cli.main --db-path my_library.db library add "The Witcher 3" \
    --platform PC \
    --genre RPG \
    --genre Action \
    --release-date 2015-05-19

# Add multiple games
python -m playnite_py.cli.main --db-path my_library.db library add "Portal 2" --platform PC --genre Puzzle
python -m playnite_py.cli.main --db-path my_library.db library add "Bloodborne" --platform PS4 --genre Action
```

### List and Search

```bash
# List all games
python -m playnite_py.cli.main --db-path my_library.db library list

# Search with fuzzy matching
python -m playnite_py.cli.main --db-path my_library.db library search "witcher"

# Filter games
python -m playnite_py.cli.main --db-path my_library.db library filter \
    --platform PC \
    --genre RPG \
    --playtime-min 600
```

### Smart Collections

```bash
# Create a smart collection
python -m playnite_py.cli.main --db-path my_library.db library create-smart-collection "Long RPGs" \
    --genre RPG \
    --playtime-min 600

# Collections auto-update when games match the rules
```

### Bulk Operations

```bash
# Add tags to multiple games
python -m playnite_py.cli.main --db-path my_library.db library bulk-edit 1 2 3 \
    --tag multiplayer \
    --tag online

# Mark games as favorites
python -m playnite_py.cli.main --db-path my_library.db library bulk-edit 1 2 --favorite
```

### Controller Testing

```bash
# Detect connected controllers
python -m playnite_py.cli.main controller detect

# Export default controller mappings
python -m playnite_py.cli.main controller export-mappings --format yaml --output my_mappings.yaml

# Test controller input (requires physical controller)
python -m playnite_py.cli.main controller test-input --controller-id 0

# Simulate controller input for testing
python -m playnite_py.cli.main controller simulate button-press --button 0
```

### Navigation Testing

```bash
# Test navigation state machine
python -m playnite_py.cli.main navigation test-navigation \
    --columns 4 \
    --rows 3 \
    --total-items 20 \
    --command right \
    --command down \
    --command select

# Show available states and commands
python -m playnite_py.cli.main navigation show-states
python -m playnite_py.cli.main navigation show-commands
```

### JSON Output for Automation

```bash
# Get JSON output for scripting
python -m playnite_py.cli.main --db-path my_library.db --json-output library list

# Example output:
# [
#   {
#     "id": 1,
#     "name": "The Witcher 3",
#     "platforms": ["PC"],
#     "genres": ["RPG", "Action"],
#     "playtime": 2400,
#     "is_favorite": true
#   }
# ]
```

## Architecture

### Headless Design

The entire system is designed to be headless and testable:

- **Database Layer**: SQLAlchemy models with efficient querying
- **Organisation Logic**: Pure Python filtering, searching, and collection management
- **Controller System**: pygame-based but can run in headless mode for testing
- **Navigation System**: State machine for UI navigation, completely decoupled from rendering
- **CLI Interface**: Complete command-line interface using Click

### Key Components

```
playnite_py/
├── models/              # SQLAlchemy data models
├── database/            # Database engine and operations
├── organisation/        # Filtering, search, collections, bulk ops
├── controller/          # Controller detection, input handling, simulation
├── navigation/          # Navigation state machine for UI
└── cli/                # Command-line interface
```

## Testing

### Run Unit Tests

```bash
# Install pytest
pip install pytest pytest-cov

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=playnite_py tests/

# Run specific test file
pytest tests/unit/test_database.py
```

### Run Integration Tests

```bash
# Test complete workflows
pytest tests/integration/
```

### Performance Testing

The system is designed for sub-second performance on 1000+ games:

```bash
# Install benchmark dependencies
pip install pytest-benchmark faker

# Run performance benchmarks
pytest tests/benchmarks/ --benchmark-only

# See tests/benchmarks/README.md for detailed benchmark documentation
```

## Configuration

### Controller Mappings

Controller button mappings are stored in `configs/controller_mappings.yaml`:

```yaml
default_mapping: xbox

mappings:
  xbox:
    buttons:
      '0': a
      '1': b
      '2': x
      '3': y
    actions:
      a: select
      b: back
      x: favorite
      y: search
```

You can create custom mappings and load them via CLI.

## Development

### Project Structure

- `playnite_py/` - Main package
  - `models/` - Database models
  - `database/` - Database operations
  - `organisation/` - Library organisation features
  - `controller/` - Controller input system
  - `navigation/` - Navigation state machine
  - `cli/` - Command-line interface
- `tests/` - Unit and integration tests
- `configs/` - Configuration files
- `requirements.txt` - Python dependencies

### Running in Development

```bash
# Install in editable mode
pip install -e .

# Run CLI in development
python -m playnite_py.cli.main --help
```

### Code Style

```bash
# Format code
black playnite_py/

# Lint
flake8 playnite_py/

# Type checking
mypy playnite_py/
```

## Advanced Usage

### Custom View Configurations

Save and restore view configurations including filters, sort order, and display settings:

```python
from playnite_py.database import init_database, get_session
from playnite_py.models import ViewConfig

engine = init_database('my_library.db')
session = get_session()

# Create view config
config = ViewConfig(
    name="My Grid View",
    view_mode="grid",
    grid_size="large",
    sort_field="playtime",
    sort_direction="desc"
)
config.set_display_settings({
    "show_covers": True,
    "show_playtime": True
})
session.add(config)
session.commit()
```

### Programmatic API

Use the library programmatically in your own Python code:

```python
from playnite_py.database import init_database, GameOperations
from playnite_py.organisation import GameFilter, GameSearch

# Initialize
engine = init_database('my_library.db')
session = engine.get_session()

# Add games
ops = GameOperations(session)
game = ops.create_game("New Game")
ops.add_platform_to_game(game.id, "PC")

# Search and filter
search = GameSearch(session)
results = search.search("witcher", fuzzy=True)

game_filter = GameFilter(session)
games = game_filter.filter_games({
    'platforms': ['PC'],
    'genres': ['RPG']
})
```

### Controller Event Handling

Register callbacks for controller events:

```python
from playnite_py.controller import ControllerManager, InputHandler, InputType

manager = ControllerManager()
manager.detect_controllers()

handler = InputHandler()

def on_button_press(event):
    print(f"Button {event.button_id} pressed!")

handler.register_listener(InputType.BUTTON_PRESS, on_button_press)

# Process events
while True:
    handler.process_events()
```

### Navigation State Management

Manage UI navigation state:

```python
from playnite_py.navigation import NavigationStateMachine, UIState, NavigationCommand

nav = NavigationStateMachine(UIState.GAME_GRID)
nav.set_grid_layout(columns=4, rows=3)
nav.set_total_items(100)

# Handle navigation
nav.handle_command(NavigationCommand.DOWN)
nav.handle_command(NavigationCommand.RIGHT)
nav.handle_command(NavigationCommand.SELECT)

# Get current state
print(nav.get_current_state())
print(nav.get_cursor_position())
```

## Implementation Status

Current completion: ~90%

### Core Features (Implemented ✅)

1. ✅ Filtering, search, and organisation
2. ✅ Full CRUD operations for tags, categories, and collections
3. ✅ Smart collections with event-driven auto-update
4. ✅ Efficient bulk operations (optimized batch SQL)
5. ✅ View presets save and restore correctly
6. ✅ Controller detection works
7. ✅ Controller input reading and mapping
8. ✅ Navigation state machine responds to input
9. ✅ Programmatic controller simulation
10. ✅ Button mappings load from configuration
11. ✅ All functionality accessible via CLI
12. ✅ JSON output support for automation
13. ✅ 101 passing unit tests (48% coverage)
14. ✅ Integration tests demonstrate workflows
15. ✅ Complete documentation
16. ✅ Shared backend logic (no duplication)

### Performance Validation (Pending 📋)

- Benchmark infrastructure complete
- Performance testing requires: `pip install pytest-benchmark faker`
- Target: Sub-second operations on 1000+ games
- See `tests/benchmarks/README.md` for details

## License

This Python implementation follows the same open source spirit as the original Playnite project. See LICENSE file for details.

## Acknowledgments

This is a Python reimplementation inspired by the original [Playnite](https://playnite.link/) project by Josef Nemec.

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.
