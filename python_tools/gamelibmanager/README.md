# Game Library Manager

A Python CLI tool for managing game libraries with intelligent duplicate detection and smart library merging with conflict resolution. Designed to work with [Playnite](https://playnite.link/) library directories.

## Installation

```bash
# From source
cd python_tools/gamelibmanager
pip install -e .

# With development dependencies (pytest, coverage)
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Quick Start

```bash
# Scan a library for duplicates
gamelibmanager --db ~/Playnite/library duplicates scan

# Preview a merge between two libraries
gamelibmanager merge preview --source ~/LibraryA --target ~/LibraryB

# Execute a merge with automatic backup
gamelibmanager merge execute --source ~/LibraryA --target ~/LibraryB
```

## Duplicate Detection

### Scanning for Duplicates

Scan your library and display duplicate groups with confidence scores:

```bash
gamelibmanager --db ~/Playnite/library duplicates scan
```

Adjust the similarity threshold (0.60 to 1.00, default 0.75):

```bash
# Stricter matching — only very similar titles
gamelibmanager --db ~/library duplicates scan --threshold 0.90

# Looser matching — catch more potential duplicates
gamelibmanager --db ~/library duplicates scan --threshold 0.65
```

Filter what gets scanned:

```bash
# Skip hidden and uninstalled games
gamelibmanager --db ~/library duplicates scan --exclude-hidden --exclude-uninstalled

# Only scan games matching a name pattern
gamelibmanager --db ~/library duplicates scan --name-filter "Witcher"

# Exclude specific sources
gamelibmanager --db ~/library duplicates scan --exclude-source "Epic"
```

Control which source is preferred as "master" when duplicates are found:

```bash
gamelibmanager --db ~/library duplicates scan --source-priority Steam GOG Epic
```

Get JSON output for scripting:

```bash
gamelibmanager --db ~/library --format json duplicates scan
```

### Generating Reports

Save a duplicate report to a file:

```bash
gamelibmanager --db ~/library --format json duplicates report -o duplicates.json
```

### Resolving Duplicates

Preview what a resolution would do before committing:

```bash
gamelibmanager --db ~/library duplicates resolve --action hide --all --dry-run
```

Resolve all duplicate groups by hiding the non-master copies:

```bash
gamelibmanager --db ~/library duplicates resolve --action hide --all
```

Merge metadata from duplicates into the master game, then delete the duplicates:

```bash
gamelibmanager --db ~/library duplicates resolve --action merge --all
```

Delete all duplicate copies (irreversible):

```bash
gamelibmanager --db ~/library duplicates resolve --action delete --all
```

Resolve a single group by ID:

```bash
gamelibmanager --db ~/library duplicates resolve --action hide --group-id 0
```

### Manual Overrides

Designate a specific game as the master of its group:

```bash
gamelibmanager --db ~/library duplicates override <game-uuid> --set-master
```

Mark a game as not a duplicate:

```bash
gamelibmanager --db ~/library duplicates override <game-uuid> --not-duplicate
```

### History and Undo

View past resolution actions:

```bash
gamelibmanager --db ~/library duplicates history
gamelibmanager --db ~/library duplicates history --limit 50
```

Undo the most recent resolution (works for "hide" actions):

```bash
gamelibmanager --db ~/library duplicates undo
```

## Library Merging

### Previewing a Merge

See what would happen before making any changes:

```bash
gamelibmanager merge preview --source ~/LibraryA --target ~/LibraryB
```

Preview with a specific conflict resolution strategy:

```bash
gamelibmanager merge preview \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --strategy keep_newest
```

Get structured JSON output:

```bash
gamelibmanager --format json merge preview \
  --source ~/LibraryA \
  --target ~/LibraryB
```

### Executing a Merge

Basic merge with automatic backup:

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB
```

Specify a backup directory:

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --backup-dir ~/backups
```

Skip backup (not recommended):

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --no-backup
```

Dry-run to see what would happen without modifying anything:

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --dry-run
```

Exclude media files (icons, covers, backgrounds):

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --no-media
```

Incremental merge (only games changed since the last merge):

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --incremental
```

Selective merge by game IDs or categories:

```bash
# Merge only specific games
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --games "abc-123-uuid" "def-456-uuid"

# Merge only games in specific categories
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --categories "Favorites" "Completed"
```

Use a saved configuration file:

```bash
gamelibmanager merge execute \
  --source ~/LibraryA \
  --target ~/LibraryB \
  --config-file merge_config.json
```

### Validating a Library

Check a library for integrity issues (duplicate IDs, missing names):

```bash
gamelibmanager merge validate ~/LibraryB
gamelibmanager --format json merge validate ~/LibraryB
```

### Rolling Back a Merge

Restore a library from a backup created during merge:

```bash
gamelibmanager merge rollback \
  --backup-file ~/backups/PlayniteLibMergeBackup_2024-06-15-14-30-45.zip \
  --target ~/LibraryB
```

### Exporting Merge Configuration

Save a merge configuration for reuse:

```bash
gamelibmanager merge export-config \
  -o merge_config.json \
  --strategy keep_newest \
  --source ~/LibraryA \
  --target ~/LibraryB
```

### Viewing Merge History

Show recent merge reports:

```bash
gamelibmanager --db ~/LibraryB merge report
gamelibmanager --db ~/LibraryB merge report --latest
```

## Merge Strategies

| Strategy | Behavior |
|----------|----------|
| `merge_all` (default) | Union lists, prefer non-empty values, use newest on conflicts |
| `keep_newest` | Use values from the game with the most recent modification date |
| `keep_oldest` | Use values from the game with the oldest modification date |
| `keep_source` | Always use the source library values |
| `keep_target` | Always use the target library values |
| `interactive` | Prompt for each conflict (falls back to source in non-interactive mode) |

## Output Formats

All commands support `--format` with three options:

**Text** (default) — human-readable output:

```bash
gamelibmanager --db ~/library duplicates scan
```

**JSON** — machine-readable structured data:

```bash
gamelibmanager --db ~/library --format json duplicates scan
```

```json
{
  "total_games_scanned": 150,
  "total_duplicates_found": 12,
  "total_groups": 5,
  "groups": [...]
}
```

**Table** — tabulated format with aligned columns:

```bash
gamelibmanager --db ~/library --format table duplicates scan
```

```
Group  Master  Name                          Platform  Source  Installed  Hidden  Confidence
-----  ------  ----------------------------  --------  ------  ---------  ------  ----------
    0  *       The Witcher 3: Wild Hunt      PC        Steam   Yes        No          -
    0          The Witcher 3 Wild Hunt       PC        GOG     No         No         92%
```

## Python API

### Database Operations

```python
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.models.game import Game
from gamelibmanager.models.lookup_tables import Platform, GameSource

# Open or create a database
db = GameDatabase("my_library.db")
db.open()

# Add lookup entries
db.add_lookup(GameSource(name="Steam"))
db.add_lookup(Platform(name="PC"))

# Add a game
game = Game(name="DOOM Eternal", game_id="782330", is_installed=True)
db.add_game(game)

# Query games
all_games = db.get_all_games()
single = db.get_game(game.id)
count = db.game_count()

# Update
game.hidden = True
db.update_game(game)

# Batch insert
games = [Game(name=f"Game {i}") for i in range(100)]
db.add_games_batch(games)

# Transactions
db.begin_transaction()
db.add_game(Game(name="Inside Transaction"))
db.commit()  # or db.rollback()

# Context manager
with GameDatabase("library.db") as db:
    db.add_game(Game(name="Auto-managed"))

db.close()
```

### Duplicate Detection

```python
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.duplicates.config import DetectionConfig, DetectionFilter
from gamelibmanager.duplicates.detector import DuplicateDetector
from gamelibmanager.duplicates.report import DuplicateReport

db = GameDatabase("library.db")
db.open()

# Configure detection
config = DetectionConfig(
    threshold=0.80,
    source_priority=["Steam", "GOG"],
    filters=DetectionFilter(
        include_hidden=False,
        include_uninstalled=True,
        name_pattern="Witcher",
    ),
)

# Run detection
detector = DuplicateDetector(db, config)
groups = detector.detect()

# Inspect results
for group in groups:
    print(f"Group: master={group.master_game_id}, "
          f"members={len(group.member_game_ids)}, "
          f"total={group.size}")
    for mid, score in group.confidence_scores.items():
        print(f"  {mid}: {score:.0%}")

# Generate report
report = DuplicateReport(
    total_games_scanned=db.game_count(),
    total_duplicates_found=sum(g.size - 1 for g in groups),
    total_groups=len(groups),
    groups=groups,
)
print(report.to_text())       # Human-readable
print(report.to_json())       # JSON
print(report.to_table(db))    # Tabulated

# Check similarity for a single game
target = Game(name="The Witcher 3")
similar = detector.check_similarity(target)

db.close()
```

### Library Merging

```python
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.merger.config import MergeConfig
from gamelibmanager.merger.engine import LibraryMerger
from gamelibmanager.merger.strategy import MergeStrategyType

source_db = GameDatabase("source.db")
source_db.open()
target_db = GameDatabase("target.db")
target_db.open()

# Configure merge
config = MergeConfig(
    strategy_type=MergeStrategyType.KEEP_NEWEST,
    backup_dir="/tmp/backups",
    include_media=True,
    incremental=False,
    source_library_path="/path/to/source",
    target_library_path="/path/to/target",
)

merger = LibraryMerger(source_db, target_db, config)

# Preview without changes
preview = merger.preview()
print(f"Games to add: {len(preview.games_to_add)}")
print(f"Games to update: {len(preview.games_to_update)}")
print(f"Games to skip: {len(preview.games_to_skip)}")
print(f"Total conflicts: {preview.total_conflicts}")
print(f"Media files to copy: {preview.media_files_to_copy}")

# Execute merge
report = merger.execute()
print(f"Added: {report.games_added}")
print(f"Updated: {report.games_updated}")
print(f"Skipped: {report.games_skipped}")
print(f"Conflicts resolved: {report.conflicts_resolved}")
print(f"Errors: {report.errors}")

# Validate library after merge
issues = merger.validate_library(target_db)
if issues:
    for issue in issues:
        print(f"Issue: {issue}")

# Export/import configuration
json_str = config.to_json()
restored = MergeConfig.from_json(json_str)

source_db.close()
target_db.close()
```

### Playnite Library I/O

```python
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.db.playnite_io import PlayniteLibraryReader, PlayniteLibraryWriter

# Read a Playnite library directory
reader = PlayniteLibraryReader("/path/to/Playnite/library")
games = reader.read_all_games()
platforms = reader.read_all_platforms()
sources = reader.read_all_sources()

# Import entire library into a database
db = GameDatabase("imported.db")
db.open()
count = reader.import_to_database(db)
print(f"Imported {count} games")

# Write games back to Playnite format
PlayniteLibraryWriter.write_game(games[0], "/path/to/output/library")
PlayniteLibraryWriter.write_all(db, "/path/to/output/library")

db.close()
```

### Resolution History

```python
from gamelibmanager.duplicates.history import ResolutionHistory

history = ResolutionHistory(db)

# Record a resolution action
history.record("hide", master_game_id, member_game_ids)

# View past actions
records = history.get_history(limit=20)
for r in records:
    print(f"{r.timestamp}: {r.action} master={r.master_id}")

# Undo the last action
undone = history.undo_last()
if undone:
    print(f"Undid: {undone.action}")
```

## Configuration Reference

### DetectionConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `threshold` | float | 0.75 | Minimum match score (0.60-1.00) |
| `weights` | ScoringWeights | see below | Component weights for scoring |
| `source_priority` | list[str] | `["Steam","GOG","Epic"]` | Source preference for master selection |
| `filters` | DetectionFilter | include all | Filtering rules |
| `similarity_mode` | bool | False | Single-game similarity check mode |
| `blocking_prefix_length` | int | 3 | Characters used for blocking optimization |
| `max_group_size` | int | 50 | Maximum games per duplicate group |

**Default scoring weights:**

| Signal | Weight | Method |
|--------|--------|--------|
| Title | 0.45 | `token_sort_ratio` on normalized titles |
| Year | 0.15 | 1.0 exact, 0.5 if +/-1, 0.0 otherwise |
| Developer | 0.15 | Best pairwise fuzzy match |
| Publisher | 0.10 | Best pairwise fuzzy match |
| Platform | 0.10 | Jaccard similarity of platform sets |
| GameId | 0.05 | 1.0 if same GameId+PluginId, else 0.0 |

Exact GameId+PluginId match auto-promotes confidence to 1.0 regardless of weights.

### MergeConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy_type` | MergeStrategyType | `MERGE_ALL` | Conflict resolution strategy |
| `backup_dir` | str | `""` | Backup directory (empty = no backup) |
| `include_media` | bool | True | Copy media files during merge |
| `add_new_games` | bool | True | Add source-only games to target |
| `update_existing` | bool | True | Update matched games with conflicts |
| `preserve_target_ids` | bool | True | Keep target game UUIDs |
| `fuzzy_match_threshold` | float | 0.85 | Title similarity threshold for matching |
| `incremental` | bool | False | Only merge games changed since last merge |
| `selective_game_ids` | set[UUID] | None | Limit merge to specific game IDs |
| `selective_categories` | set[str] | None | Limit merge to specific categories |

## How It Works

### Title Normalization

Before comparing, game titles are normalized:
1. Unicode NFKD decomposition (strip diacritics)
2. Lowercase
3. Remove leading articles ("the", "a", "an")
4. Strip edition suffixes (GOTY, Remastered, Deluxe, Definitive, Director's Cut, etc.)
5. Convert roman numerals to arabic (II -> 2, III -> 3, IV -> 4, etc.)
6. Remove punctuation
7. Collapse whitespace

Example: `"The Witcher III: Wild Hunt - Game of the Year Edition"` becomes `"witcher 3 wild hunt"`.

### Duplicate Detection Algorithm

1. **Blocking**: Group games by the first 3 characters of their normalized title. This reduces comparisons from O(n^2) to manageable block sizes.
2. **Scoring**: Within each block, compute a weighted confidence score for every pair using title similarity, release year, developer/publisher match, platform overlap, and provider ID match.
3. **Grouping**: Use union-find to merge pairs scoring above the threshold into transitive groups.
4. **Master selection**: For each group, pick the master based on source priority, then metadata completeness, then most recent modification date.

### Game Matching During Merge

Games are matched between source and target in two passes:
1. **Exact match**: Same `GameId` + `PluginId` (e.g., same Steam app ID)
2. **Fuzzy match**: Normalized title similarity above the configured threshold (default 0.85)

Unmatched source games are added as new entries. Matched games have their conflicts resolved using the selected strategy.

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=gamelibmanager --cov-report=term-missing
```

## License

See the repository root for license information.
