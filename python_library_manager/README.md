# Game Library Manager

Python game library manager with **intelligent duplicate detection** and
**smart library merging**, designed as a replacement for the C# Playnite
application's equivalent features.

Supports reading and writing libraries in Playnite's JSON database format as
well as a standalone flat-JSON layout.

---

## Installation

```bash
cd python_library_manager
pip install -e ".[dev]"
```

This installs the `gamelibrary` CLI command and all development/test dependencies.

---

## Quick Start

```bash
# Show library statistics
gamelibrary stats ~/playnite-db --playnite

# Detect duplicates (Playnite DB layout)
gamelibrary duplicates detect ~/playnite-db --playnite \
    --threshold 0.85 \
    --source-priority Steam --source-priority GOG \
    --save-report report.json

# Resolve duplicates (hide non-master copies)
gamelibrary duplicates resolve ~/playnite-db report.json \
    --action hide --output-path ~/playnite-db-deduped

# Preview a merge
gamelibrary merge preview ~/master-db ~/source-db --playnite \
    --strategy merge_prefer_master

# Execute a merge (creates backup automatically)
gamelibrary merge execute ~/master-db ~/source-db --playnite \
    --strategy merge_prefer_master \
    --backup-dir ~/backups \
    --save-result result.json

# Roll back a merge
gamelibrary merge rollback ~/master-db result.json --backup-dir ~/backups
```

All commands accept `--json-output` for scripted / automated use.

---

## Architecture

```
python_library_manager/
├── src/game_library/
│   ├── models/
│   │   ├── game.py          Game dataclass (Playnite-compatible JSON)
│   │   └── library.py       Library + NamedEntity reference tables
│   ├── storage/
│   │   └── json_store.py    Playnite-layout and flat-JSON persistence
│   ├── duplicate/
│   │   ├── matcher.py       GameMatcher – weighted fuzzy scoring
│   │   ├── detector.py      DuplicateDetector – blocking + Union-Find
│   │   └── resolver.py      DuplicateResolver – hide/delete/merge/undo
│   ├── merger/
│   │   ├── strategies.py    MergeStrategy enum + field-level helpers
│   │   ├── conflict.py      ConflictResolver – per-field conflict logic
│   │   ├── backup.py        BackupManager – create/restore/list backups
│   │   └── merger.py        LibraryMerger – orchestration + rollback
│   ├── utils/
│   │   ├── text_utils.py    normalize_title, normalize_company_name
│   │   └── report.py        Plain-text / table report helpers
│   └── cli/
│       ├── main.py          Top-level Click group + stats command
│       ├── duplicate_cmds.py  detect / resolve / report sub-commands
│       └── merge_cmds.py    preview / execute / rollback / export-config
└── tests/
    ├── conftest.py          Shared fixtures (make_game, make_library)
    ├── unit/                Unit tests per module
    └── integration/         End-to-end CLI workflow tests
```

---

## Duplicate Detection

### Matching Criteria

Each pair of games is scored on five weighted signals:

| Signal | Default weight | Notes |
|--------|---------------|-------|
| Title similarity | 50% | Best of `token_sort_ratio`, `token_set_ratio`, `partial_ratio` (rapidfuzz) applied to **normalised** titles |
| Release year | 20% | 1.0 for exact match, 0.5 for ±1 year, 0.0 otherwise; unknown → 0.5 |
| Platform overlap | 15% | Jaccard similarity of platform sets |
| Developer overlap | 10% | Jaccard similarity of normalised company names |
| Publisher overlap | 5% | Jaccard similarity of normalised company names |

### Title Normalisation

`normalize_title` applies these transforms in order:

1. NFD unicode decomposition → strip accent combining characters
2. Lowercase
3. Strip edition/version suffixes *before* punctuation removal
   (GOTY, Definitive Edition, Remastered, Remake, HD, v2.0, …)
4. Strip punctuation (keep alphanumerics and spaces)
5. Remove leading articles (The, A, An)
6. Convert Roman numerals to Arabic (I–XII)
7. Collapse whitespace

So `"The Witcher 3: Wild Hunt – Game of the Year Edition"` and
`"The Witcher 3: Wild Hunt"` both normalise to `"witcher 3 wild hunt"`.

### Similarity threshold

Configurable via `--threshold` (CLI) or `DetectorConfig.threshold` (API).
Range: 0.60–1.00.  Default: **0.85**.

### Similarity mode

`--similarity-mode` lowers the effective threshold to
`--similarity-threshold` (default 0.70) to surface potential duplicates even
when their titles do not closely match.

### Source priority

Pass `--source-priority` (repeatable) to declare a preferred source order.
The game from the highest-priority source becomes the *master*.  Ties are
broken by metadata completeness score, then by total playtime.

### Performance

The detector uses **title-prefix blocking**: games are grouped by the first
3 normalised characters of their title before pairwise comparison, keeping the
effective comparison count manageable.  A fast `quick_candidate` pre-filter
(single `token_sort_ratio` call) rejects pairs that cannot possibly meet the
threshold before the full weighted score is computed.

Benchmark: **5,000 unique games in < 1 second** on a modern laptop.

---

## Library Merging

### Merge Strategies

| Strategy | Description |
|----------|-------------|
| `keep_master` | Master library values always win |
| `keep_source` | Source library values always win |
| `merge_prefer_master` | Fill empty master fields from source; master wins conflicts *(default)* |
| `merge_prefer_source` | Fill empty master fields from source; source wins conflicts |
| `most_complete` | For each field, use the richer value (longer string, larger score, union of lists) |
| `most_played` | Like `merge_prefer_master` but play-stats (`Playtime`, `PlayCount`, `LastActivity`) use the higher value |

Per-field overrides are supported via `--field-override FIELD=STRATEGY` (CLI)
or `MergeConfig.field_strategy_overrides` (API).

### Conflict Types

- `SCALAR_MISMATCH` – both sides have a different non-empty value for a scalar field
- `LIST_MISMATCH` – both sides have different non-empty lists
- `MISSING_IN_MASTER` – field is populated in source but absent in master
- `MISSING_IN_SOURCE` – field is populated in master but absent in source

### Backup and Rollback

`merge execute` automatically creates a timestamped JSON backup of the master
library before any modification.  The backup ID is written to the result file.

```bash
gamelibrary merge rollback ~/master.json result.json --backup-dir ~/backups
```

### Incremental Merge

`--incremental-since ISO_DATE` skips source games whose `Modified` timestamp
predates the given date.  Use this to re-run a merge and only pick up changes
since the last run.

### Config Export / Import

Export a merge configuration for repeating the same merge on another machine:

```bash
gamelibrary merge export-config my_config.json \
    --strategy most_complete \
    --threshold 0.80

gamelibrary merge execute master.json source.json \
    --config-file my_config.json
```

---

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=game_library --cov-report=term-missing

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Specific test file
pytest tests/unit/test_detector.py -v
```

---

## CLI Reference

```
gamelibrary [OPTIONS] COMMAND [ARGS]...

Commands:
  duplicates  Intelligent duplicate game detection and resolution.
    detect    Scan a library for duplicate games.
    resolve   Apply a resolution action to detected duplicates.
    report    Display a previously generated duplicate report.

  merge       Smart library merging with conflict resolution.
    preview   Show what a merge would change (dry-run).
    execute   Perform the merge (creates backup first).
    rollback  Restore library from a backup.
    export-config  Export merge configuration to a JSON file.
    list-backups   List available library backups.

  stats       Show statistics for a library.
```

Use `gamelibrary COMMAND --help` for per-command documentation.
