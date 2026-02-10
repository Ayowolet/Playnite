# CLI Reference

## Global Options

These options apply to every command and must be placed before the subcommand.

```
playnite [OPTIONS] COMMAND [ARGS]...
```

| Option | Short | Description |
|--------|-------|-------------|
| `--data-dir DIR` | | Override the default data directory |
| `--verbose` | `-v` | Enable debug-level logging to stderr |
| `--version` | | Print the version and exit |
| `--help` | | Show help and exit |

**Default data directory:** `~/.config/playnite` (Linux/macOS) / `%APPDATA%\playnite` (Windows)

---

## Top-Level Commands

### `playnite init-db`

Initialise (or re-initialise) the database schema. Safe to run multiple times — it is idempotent.

```bash
playnite init-db
playnite --data-dir /tmp/testdb init-db
```

---

### `playnite disaster-recovery BACKUP_PATH`

Restore directly from a backup archive file, bypassing the database. Use this when the database is corrupt or missing.

```bash
playnite disaster-recovery /path/to/playnite_full_20240315.pnb
playnite disaster-recovery /path/to/backup.pnbe            # prompts for password
playnite disaster-recovery /path/to/backup.pnb --destination /tmp/recovery
playnite disaster-recovery /path/to/backup.pnb --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--destination DIR` | `-d` | Target directory (default: configured data dir) |
| `--password PW` | `-p` | Decryption password (prompted if omitted for `.pnbe` files) |
| `--json` | | Output result as JSON |

After disaster recovery, run `playnite init-db` to re-initialise the schema.

---

## `config` Commands

### `playnite config show`

Display the current configuration. Sensitive fields (API keys, tokens) are masked.

```bash
playnite config show
playnite config show --json
```

| Option | Description |
|--------|-------------|
| `--json` | Output as JSON |

---

### `playnite config set KEY VALUE`

Set a single configuration value. `KEY` uses dot notation to address nested fields.

```bash
playnite config set steam.api_key YOUR_KEY
playnite config set steam.enabled true
playnite config set steam.steam_id 76561198000000001
playnite config set xbox.api_key YOUR_OPENXBL_KEY
playnite config set xbox.xuid YOUR_XUID
playnite config set psn.npsso_token YOUR_TOKEN
playnite config set gog.access_token YOUR_TOKEN
playnite config set gog.refresh_token YOUR_REFRESH_TOKEN
```

Boolean values accept `true/false`, `1/0`, or `yes/no`.

---

## `backup` Commands

### `playnite backup create`

Create a full or incremental backup.

```bash
# Full backup
playnite backup create --destination ~/backups

# Full backup with label
playnite backup create --destination ~/backups --label "before-update"

# Encrypted backup (password prompted interactively)
playnite backup create --destination ~/backups --encrypted

# Encrypted with inline password (less secure)
playnite backup create --destination ~/backups --encrypted --password "s3cr3t"

# Incremental (auto-detects most recent backup as parent)
playnite backup create --incremental --destination ~/backups

# Incremental with explicit parent
playnite backup create --incremental --parent-id 5 --destination ~/backups

# Back up only selected categories
playnite backup create --categories database --categories config --destination ~/backups

# Use a saved profile
playnite backup create --profile 2

# JSON output
playnite backup create --destination ~/backups --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--destination DIR` | `-d` | Destination directory (default: configured backup dir) |
| `--encrypted` | `-e` | Encrypt the archive with AES-256-GCM |
| `--password PW` | `-p` | Encryption password (prompted if omitted) |
| `--label TEXT` | `-l` | Human-readable label |
| `--incremental` | `-i` | Create incremental backup |
| `--parent-id INT` | | Parent backup ID for incremental |
| `--profile INT` | | Apply settings from a saved profile |
| `--categories TEXT` | `-c` | Categories to include (repeatable) |
| `--json` | | Output result as JSON |

**Available categories:** `database`, `config`, `themes`, `plugins`, `achievements`, `controller_mappings`

---

### `playnite backup restore BACKUP_ID`

Restore from a backup. If the backup is encrypted, password is prompted automatically.

```bash
# Full restore
playnite backup restore 5

# Restore to a different directory
playnite backup restore 5 --destination /tmp/restore-test

# Selective restore
playnite backup restore 5 --categories database
playnite backup restore 5 --categories database --categories config

# Provide password inline
playnite backup restore 5 --password "s3cr3t"

# JSON output
playnite backup restore 5 --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--destination DIR` | `-d` | Restore target directory |
| `--categories TEXT` | `-c` | Restore only these categories (repeatable) |
| `--password PW` | `-p` | Decryption password |
| `--json` | | Output result as JSON |

---

### `playnite backup verify BACKUP_ID`

Verify backup integrity. Checks file existence, SHA-256 checksum, ZIP validity, manifest, and all file checksums.

```bash
playnite backup verify 5
playnite backup verify 5 --password "s3cr3t"   # encrypted backups
playnite backup verify 5 --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--password PW` | `-p` | Decryption password |
| `--json` | | Output result as JSON |

Exits with code `1` if verification fails.

---

### `playnite backup list`

List all backups in a table.

```bash
playnite backup list
playnite backup list --json
```

| Option | Description |
|--------|-------------|
| `--json` | Output as JSON array |

---

### `playnite backup delete BACKUP_ID`

Delete a backup record. By default the archive file is also deleted.

```bash
playnite backup delete 5
playnite backup delete 5 --keep-file   # removes DB record but keeps the .pnb file
```

| Option | Description |
|--------|-------------|
| `--keep-file` | Keep the archive file on disk |
| `--json` | Output result as JSON |

---

### `playnite backup report BACKUP_ID`

Show a detailed report for a backup (size, categories, compression ratio).

```bash
playnite backup report 5
playnite backup report 5 --json
```

---

### `playnite backup export OUTPUT_PATH`

Export the full game library to a portable JSON file.

```bash
playnite backup export ~/playnite_library.json
playnite backup export ~/playnite_library.json --json
```

---

### `playnite backup import INPUT_PATH`

Import a library from a previously exported JSON file.

```bash
playnite backup import ~/playnite_library.json
```

---

### `playnite backup profile create`

Create a named backup profile for reuse and scheduling.

```bash
# Daily backup at 02:00 UTC, 30-day retention
playnite backup profile create \
  --name daily \
  --cron "0 2 * * *" \
  --destination ~/backups/daily \
  --retention-days 30 \
  --max-count 10

# Weekly encrypted off-site backup
playnite backup profile create \
  --name offsite \
  --cron "0 3 * * 0" \
  --destination /mnt/nas/playnite \
  --encrypt \
  --retention-days 90 \
  --max-count 12
```

| Option | Short | Description |
|--------|-------|-------------|
| `--name TEXT` | `-n` | Profile name (required) |
| `--cron TEXT` | | 5-field cron schedule (e.g. `"0 2 * * *"`) |
| `--destination DIR` | `-d` | Destination path (repeatable for multiple) |
| `--encrypt` | | Encrypt backups made by this profile |
| `--retention-days INT` | | Delete backups older than N days (default: 30) |
| `--max-count INT` | | Maximum number of backups to keep (default: 10) |
| `--json` | | Output result as JSON |

---

### `playnite backup profile list`

List all configured backup profiles.

```bash
playnite backup profile list
playnite backup profile list --json
```

---

### `playnite backup profile delete PROFILE_ID`

Delete a backup profile (does not delete existing backups made by the profile).

```bash
playnite backup profile delete 2
```

---

## `achievements` Commands

### `playnite achievements sync`

Sync achievements from all configured platforms (or a specific one).

```bash
playnite achievements sync
playnite achievements sync --platform steam
playnite achievements sync --platform psn
playnite achievements sync --force          # ignore recent-sync cache
playnite achievements sync --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--platform TEXT` | `-p` | Platform to sync: `steam`, `xbox`, `psn`, `gog` |
| `--force` | | Force re-sync even if recently synced |
| `--json` | | Output results as JSON |

---

### `playnite achievements stats`

Show overall achievement statistics.

```bash
playnite achievements stats
playnite achievements stats --platform steam
playnite achievements stats --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--platform TEXT` | `-p` | Filter statistics to a single platform |
| `--json` | | Output as JSON |

---

### `playnite achievements list`

List achievements with optional filtering.

```bash
playnite achievements list
playnite achievements list --game "Dark Souls"
playnite achievements list --platform steam --unlocked-only
playnite achievements list --game-id 42
playnite achievements list --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--game TEXT` | `-g` | Filter by game name (partial, case-insensitive) |
| `--game-id INT` | | Filter by game database ID |
| `--platform TEXT` | `-p` | Filter by platform |
| `--unlocked-only` | | Show only unlocked achievements |
| `--json` | | Output as JSON |

---

### `playnite achievements hunt`

Find games that are good candidates for achievement hunting (partially complete, not too difficult).

```bash
playnite achievements hunt
playnite achievements hunt --max-difficulty 0.5 --max-remaining 15 --limit 5
playnite achievements hunt --platform steam --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--max-difficulty FLOAT` | `-d` | Max difficulty score 0.0–1.0 (default: 0.7) |
| `--max-remaining INT` | `-r` | Max remaining achievements (default: 30) |
| `--platform TEXT` | `-p` | Filter to a single platform |
| `--limit INT` | `-n` | Max results to show (default: 10) |
| `--json` | | Output as JSON |

---

### `playnite achievements challenge`

Generate a personal challenge: a curated set of games to complete.

```bash
playnite achievements challenge
playnite achievements challenge --max-difficulty 0.4 --max-hours 20 --count 3
playnite achievements challenge --platform xbox --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--max-difficulty FLOAT` | `-d` | Max difficulty 0.0–1.0 (default: 0.5) |
| `--max-hours FLOAT` | `-h` | Max estimated hours per game (default: 10.0) |
| `--count INT` | `-n` | Number of games in challenge (default: 5) |
| `--platform TEXT` | `-p` | Restrict to a single platform |
| `--json` | | Output as JSON |

---

### `playnite achievements rare`

List unlocked rare achievements sorted by rarity (lowest global percentage first).

```bash
playnite achievements rare
playnite achievements rare --platform psn
playnite achievements rare --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--platform TEXT` | `-p` | Filter to a single platform |
| `--json` | | Output as JSON |

---

### `playnite achievements export`

Export achievement data to a JSON or CSV file.

```bash
playnite achievements export --format json --output ~/achievements.json
playnite achievements export --format csv  --output ~/achievements.csv
playnite achievements export --format json --output ~/unlocked.json --unlocked-only
playnite achievements export --format json --output ~/game42.json --game-id 42
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format TEXT` | `-f` | Output format: `json` or `csv` (default: `json`) |
| `--output PATH` | `-o` | Output file path (required) |
| `--unlocked-only` | | Export only unlocked achievements |
| `--game-id INT` | | Limit to specific game IDs (repeatable) |

---

### `playnite achievements import`

Import achievements from a previously exported JSON file.

```bash
playnite achievements import --input ~/achievements.json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--input PATH` | `-i` | Path to exported JSON file (required) |
| `--json` | | Output result as JSON |

---

### `playnite achievements report`

Generate a comprehensive achievement report with summary statistics.

```bash
playnite achievements report
playnite achievements report --output ~/report.json
playnite achievements report --json
```

| Option | Short | Description |
|--------|-------|-------------|
| `--output PATH` | `-o` | Save report to a JSON file |
| `--json` | | Print report JSON to stdout |

---

### `playnite achievements timeline`

Show a monthly bar chart of achievement unlocks over time.

```bash
playnite achievements timeline
playnite achievements timeline --start 2024-01-01 --end 2024-12-31
playnite achievements timeline --json
```

| Option | Description |
|--------|-------------|
| `--start DATE` | Start date in `YYYY-MM-DD` format |
| `--end DATE` | End date in `YYYY-MM-DD` format |
| `--json` | Output as JSON |

---

### `playnite achievements notifications`

Show pending achievement unlock notifications.

```bash
playnite achievements notifications
playnite achievements notifications --mark-read
playnite achievements notifications --json
```

| Option | Description |
|--------|-------------|
| `--mark-read` | Dismiss all pending notifications after displaying |
| `--json` | Output as JSON |

---

### `playnite achievements add-manual`

Add a game achievement manually (for platforms without API support).

```bash
# Add a locked achievement
playnite achievements add-manual --game "Retro Game" --name "First Clear"

# Add an already-unlocked achievement
playnite achievements add-manual --game "Retro Game" --name "Speed Run" --unlocked

# Add with unlock date and description
playnite achievements add-manual \
  --game "Retro Game" \
  --name "All Bosses" \
  --description "Defeat every boss" \
  --unlocked \
  --unlock-date 2024-03-15

# Add to an existing game by DB id
playnite achievements add-manual --game-id 7 --name "Collector" \
  --max-value 100 --current-value 42

# Progress-based achievement
playnite achievements add-manual --game "RPG" --name "Collector" \
  --description "Collect 100 items" \
  --max-value 100 --current-value 42
```

| Option | Short | Description |
|--------|-------|-------------|
| `--game TEXT` | `-g` | Game name (creates game if it doesn't exist) |
| `--game-id INT` | | Existing game database ID |
| `--name TEXT` | `-n` | Achievement name (required) |
| `--description TEXT` | `-d` | Achievement description |
| `--unlocked` | | Mark as already unlocked |
| `--unlock-date DATE` | | Unlock date in `YYYY-MM-DD` format |
| `--max-value FLOAT` | | Maximum progress value |
| `--current-value FLOAT` | | Current progress value |

---

### `playnite achievements edit-manual`

Edit a previously added manual achievement.

```bash
playnite achievements edit-manual --achievement-id 12 --name "New Name"
playnite achievements edit-manual --achievement-id 12 --current-value 75
playnite achievements edit-manual --achievement-id 12 --unlock-date 2024-06-01
```

| Option | Short | Description |
|--------|-------|-------------|
| `--achievement-id INT` | `-a` | Achievement database ID (required) |
| `--name TEXT` | `-n` | New name |
| `--description TEXT` | `-d` | New description |
| `--current-value FLOAT` | | Updated progress value |
| `--max-value FLOAT` | | Updated maximum progress value |
| `--unlock-date DATE` | | Override unlock date (`YYYY-MM-DD`) |

---

### `playnite achievements mark-unlocked`

Mark a manual achievement as unlocked.

```bash
playnite achievements mark-unlocked --achievement-id 12
playnite achievements mark-unlocked --achievement-id 12 --unlock-date 2024-06-01
```

| Option | Short | Description |
|--------|-------|-------------|
| `--achievement-id INT` | `-a` | Achievement database ID (required) |
| `--unlock-date DATE` | | Override unlock timestamp (`YYYY-MM-DD`) |
| `--json` | | Output result as JSON |

---

### `playnite achievements delete-manual`

Delete a manually-entered achievement.

```bash
playnite achievements delete-manual --achievement-id 12
playnite achievements delete-manual --achievement-id 12 --yes   # skip confirmation
```

| Option | Short | Description |
|--------|-------|-------------|
| `--achievement-id INT` | `-a` | Achievement database ID (required) |
| `--yes` | `-y` | Skip confirmation prompt |

---

## JSON Output and Scripting

All commands that display data support `--json` for machine-readable output. The exit code is `0` on success and `1` on failure, making them suitable for use in shell scripts.

```bash
# Get the ID of the most recent backup
LATEST=$(playnite backup list --json | python3 -c \
  "import sys, json; print(json.load(sys.stdin)[0]['id'])")

# Verify it
playnite backup verify "$LATEST" && echo "OK"

# Sync and capture results
playnite achievements sync --json | python3 -c \
  "import sys, json; [print(r['platform'], r['new_unlocks']) for r in json.load(sys.stdin)]"
```
