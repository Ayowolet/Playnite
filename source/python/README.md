# Game Library Manager

A Python game library manager with cross-platform achievement tracking and comprehensive backup/restore capabilities. Designed as a modern replacement for the C# Playnite application.

## Installation

```bash
pip install -e ".[dev]"
```

Requirements: Python 3.10+

## Quick Start

```bash
# Register a platform and start tracking
gamelibrary achievements register-platform "My Steam" steam --api-key YOUR_KEY --user-id YOUR_STEAM_ID

# Import achievements
gamelibrary achievements import 1

# View stats
gamelibrary achievements --json stats

# Create a backup
gamelibrary backup create

# Restore from backup
gamelibrary backup restore /path/to/backup.zip
```

## Platform API Setup

### Steam

1. Get a Steam Web API key at https://steamcommunity.com/dev/apikey
2. Find your Steam ID (64-bit) at https://steamid.io
3. Register:

```bash
gamelibrary achievements register-platform "Steam" steam \
  --api-key YOUR_STEAM_API_KEY \
  --user-id YOUR_STEAM_ID_64
```

The Steam integration uses three API endpoints:
- `IPlayerService/GetOwnedGames` - fetches your game library
- `ISteamUserStats/GetSchemaForGame` + `GetPlayerAchievements` - fetches achievement definitions and unlock status
- `ISteamUserStats/GetGlobalAchievementPercentagesForApp` - fetches global completion percentages

### Xbox Live

1. Create an account at https://xbl.io
2. Get your API key from the dashboard
3. Your XUID is auto-detected on first use, or find it on your profile
4. Register:

```bash
gamelibrary achievements register-platform "Xbox" xbox \
  --api-key YOUR_OPENXBL_API_KEY \
  --user-id YOUR_XUID
```

### PlayStation Network

PSN requires an NPSSO token from an authenticated browser session:

1. Log in to https://store.playstation.com in your browser
2. Visit https://ca.account.sony.com/api/v1/ssocookie and copy the `npsso` value
3. Register:

```bash
gamelibrary achievements register-platform "PSN" psn \
  --extra '{"npsso": "YOUR_NPSSO_TOKEN"}'
```

The NPSSO token is exchanged for an OAuth access token automatically. Tokens expire; re-register with a fresh NPSSO when needed.

### GOG Galaxy

GOG requires OAuth credentials:

1. Obtain `client_id` and `client_secret` from GOG Galaxy's authentication flow
2. Get a `refresh_token` through the OAuth code grant flow
3. Register:

```bash
gamelibrary achievements register-platform "GOG" gog \
  --extra '{"client_id": "...", "client_secret": "...", "refresh_token": "..."}'
```

The access token is refreshed automatically using the refresh token.

### Manual Entry (Unsupported Platforms)

For platforms without API support (e.g., Nintendo, retro games):

```bash
# Add a game
gamelibrary achievements add-game "Zelda: BOTW" --platform "Nintendo Switch"

# Add achievements
gamelibrary achievements add-achievement 1 "Defeat Ganon" --unlocked --global-pct 35.0
gamelibrary achievements add-achievement 1 "All Shrines" --global-pct 8.0 --max-progress 120 --current-progress 80

# Update progress later
gamelibrary achievements update-achievement 2 --progress 100
gamelibrary achievements update-achievement 2 --unlocked
```

## Achievement Tracking

### Syncing

```bash
# Sync all platforms
gamelibrary achievements sync

# Sync a specific platform
gamelibrary achievements sync --platform-id 1

# View sync history
gamelibrary achievements sync-history
```

Auto-sync runs on a configurable interval (default 60 minutes) when started programmatically via `SyncScheduler.start()`. New unlocks detected during sync trigger notifications.

### Statistics

```bash
# Overall stats across all platforms
gamelibrary achievements stats

# Per-game stats
gamelibrary achievements stats --game-id 1

# Unlock velocity (achievements per day over time periods)
gamelibrary achievements velocity

# Daily unlock timeline (for visualization)
gamelibrary achievements timeline --days 365

# Difficulty distribution across tiers
gamelibrary achievements difficulty

# Per-platform breakdown
gamelibrary achievements platform-stats

# Milestone tracking
gamelibrary achievements milestones
```

### Achievement Hunting

```bash
# Games near 100% completion (default threshold: 80%)
gamelibrary achievements hunt-near-complete --threshold 90

# Easiest locked achievements across all games
gamelibrary achievements hunt-easiest --limit 20

# Easiest locked achievements for a specific game
gamelibrary achievements hunt-easiest --game-id 1

# Rare achievements (below 10% global completion)
gamelibrary achievements hunt-rare --threshold 5

# Achievements with partial progress
gamelibrary achievements hunt-progress

# Games with few achievements remaining
gamelibrary achievements hunt-completable --max-remaining 5
```

### Challenge Mode

```bash
# Get challenge suggestions by difficulty
gamelibrary achievements challenge --difficulty easy
gamelibrary achievements challenge --difficulty medium
gamelibrary achievements challenge --difficulty hard

# Daily challenge - random achievable achievement
gamelibrary achievements daily-challenge
```

### Export

```bash
# Export all achievements to JSON
gamelibrary achievements export --format json --output achievements.json

# Export to CSV
gamelibrary achievements export --format csv --output achievements.csv

# Export a specific game
gamelibrary achievements export --format json --game-id 1

# Print to stdout (pipe to other tools)
gamelibrary achievements --json export --format json | jq '.games[0].achievements | length'
```

### Notifications

```bash
# View all notifications
gamelibrary achievements notifications

# View unread only, then mark as read
gamelibrary achievements notifications --unread-only --mark-read
```

## Backup & Restore

### Backup Strategies

There are two backup types:

- **Full backup**: Captures all components (database, config, categories, tags, view presets, controller mappings, theme settings, plugin configs) into a compressed ZIP
- **Incremental backup**: Compares checksums against a parent backup and only includes changed files, saving space

A recommended strategy:

1. Create a weekly full backup
2. Create daily incremental backups referencing the latest full
3. Use profiles to automate this with retention policies

### Creating Backups

```bash
# Full backup of everything
gamelibrary backup create

# Full backup of specific components only
gamelibrary backup create --components database,config,tags

# Encrypted backup (AES-256-GCM)
gamelibrary backup create --password "your-secure-password"

# Incremental backup (reference a parent backup ID)
gamelibrary backup create-incremental 1

# Pre-update safety backup (database + config only)
gamelibrary backup pre-update
```

### Backup Profiles

Profiles define reusable backup strategies with scheduling and retention:

```bash
# Create a profile
gamelibrary backup profile create "nightly" \
  --description "Nightly full backup" \
  --schedule "0 2 * * *" \
  --retention-days 30 \
  --max-backups 10 \
  --encrypt

# List profiles
gamelibrary backup profile list

# Run a profile manually
gamelibrary backup profile run "nightly" --password "your-password"

# Delete a profile
gamelibrary backup profile delete 1
```

Schedule format is standard cron: `minute hour day-of-month month day-of-week`.

### Managing Backups

```bash
# List all backups
gamelibrary backup list

# View backup report (contents, size, verification)
gamelibrary backup report 1

# View backup contents without restoring
gamelibrary backup contents /path/to/backup.zip

# Verify backup integrity
gamelibrary backup verify /path/to/backup.zip

# Delete a backup
gamelibrary backup delete 1

# Clean up old backups (retention policy)
gamelibrary backup cleanup --max-age 30 --max-count 10
```

### Restore Procedures

#### Full Restore

Restores all components from a backup:

```bash
gamelibrary backup restore /path/to/backup.zip
```

For encrypted backups:

```bash
gamelibrary backup restore /path/to/backup.zip.enc --password "your-password"
```

#### Selective Restore

Restore only specific components (e.g., restore tags without overwriting the database):

```bash
gamelibrary backup restore /path/to/backup.zip --components tags,categories
```

Available components: `database`, `config`, `categories`, `tags`, `view_presets`, `controller_mappings`, `theme_settings`, `plugin_configs`.

#### Disaster Recovery

When the database is corrupted:

```bash
# Check database health
gamelibrary backup recovery check

# Attempt automatic recovery from most recent backup
gamelibrary backup recovery recover --password "your-password"

# Last resort: rebuild empty database schema
gamelibrary backup recovery rebuild
```

#### Migration

Export and import library data between systems:

```bash
# Export for migration
gamelibrary backup recovery export /path/to/migration.zip --password "optional-password"

# Import on new system
gamelibrary backup recovery import /path/to/migration.zip --password "optional-password"
```

### Encryption Details

Backups are encrypted using AES-256-GCM:
- Key derivation: PBKDF2-HMAC-SHA256 with 600,000 iterations
- A random 16-byte salt and 12-byte nonce are generated per encryption
- The encrypted file format is: `[salt(16 bytes)][nonce(12 bytes)][ciphertext+GCM tag]`

Keep your password safe - there is no recovery mechanism for forgotten passwords.

## Troubleshooting

### Authentication Errors

**Symptom:** `AuthenticationError: Authentication failed for Steam` or similar during sync/import.

- **Steam/Xbox:** Your API key is invalid or revoked. Generate a new one and re-register the platform:
  ```bash
  gamelibrary achievements register-platform "Steam" steam --api-key NEW_KEY --user-id YOUR_ID
  ```
- **PSN:** NPSSO tokens expire after a few hours. Log in again at https://store.playstation.com, grab a fresh token from https://ca.account.sony.com/api/v1/ssocookie, and re-register.
- **GOG:** If the refresh token has expired, you need to re-authenticate through the OAuth flow and re-register with new credentials.

Check sync history for details on past failures:

```bash
gamelibrary achievements sync-history --limit 5
```

Auth failures are recorded with status `auth_failed` and generate a notification visible via:

```bash
gamelibrary achievements notifications --unread-only
```

### Sync Returns Empty Data

If a sync completes successfully but reports 0 achievements found:

1. Verify the platform credentials are correct by checking `gamelibrary achievements platforms`
2. Confirm the user ID / Steam ID is correct for the account that owns the games
3. For Steam, ensure your game library visibility is set to **Public** in Steam privacy settings

### Corrupt or Missing Database

If the database file is damaged or accidentally deleted:

```bash
# Check database health
gamelibrary backup recovery check

# Recover from the most recent backup
gamelibrary backup recovery recover

# If no backup exists, rebuild an empty database
gamelibrary backup recovery rebuild
```

To prevent data loss, set up a backup profile with automatic retention:

```bash
gamelibrary backup profile create "safety-net" \
  --schedule "0 3 * * *" \
  --retention-days 14 \
  --max-backups 5
```

### Encrypted Backup Cannot Be Restored

- `InvalidTag` or decryption error: The password is wrong. There is no recovery mechanism for forgotten passwords.
- If you have multiple backups, try each with the password you used at the time — passwords are not stored anywhere.

### Backup Verification Fails

```bash
gamelibrary backup verify /path/to/backup.zip
```

If verification reports checksum mismatches, the backup file was modified or corrupted during transfer. Re-copy from the original source or create a new backup.

### Import Errors for Specific Games

Some games may fail to import due to API quirks (delisted games, region restrictions). Import a single game to isolate the issue:

```bash
gamelibrary achievements import 1 --game-id EXTERNAL_GAME_ID
```

### Missing `cryptography` Dependency

If you see `ModuleNotFoundError: No module named 'cryptography'`, install the dependency:

```bash
pip install cryptography
```

Or reinstall the project with all dependencies:

```bash
pip install -e ".[dev]"
```

## JSON Output

All commands support `--json` for machine-readable output:

```bash
# Use with achievements
gamelibrary achievements --json stats
gamelibrary achievements --json list 1

# Use with backup
gamelibrary backup --json list
gamelibrary backup --json report 1
```

This enables scripting and integration with other tools:

```bash
# Count total unlocked achievements
gamelibrary achievements --json stats | python -c "import sys,json; print(json.load(sys.stdin)['total_unlocked'])"

# Get latest backup path
gamelibrary backup --json list | python -c "import sys,json; print(json.load(sys.stdin)[0]['file_path'])"
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# Achievement tests only
pytest tests/test_achievements/ -v

# Backup tests only
pytest tests/test_backup/ -v

# Integration tests only
pytest tests/test_integration/ -v

# With coverage
pytest tests/ --cov=gamelibrary --cov-report=term-missing
```

## Project Structure

```
gamelibrary/
  cli.py                          # Main CLI entry point
  database.py                     # SQLite database schema and management
  models.py                       # Data models (Platform, Game, Achievement, Backup, etc.)
  config.py                       # Configuration management
  achievements/
    cli.py                        # Achievement CLI commands
    tracker.py                    # Core import/tracking engine
    sync.py                       # Automatic sync scheduler
    stats.py                      # Statistics and analytics
    hunting.py                    # Achievement hunting filters
    challenge.py                  # Challenge mode suggestions
    notifications.py              # Unlock notifications
    export.py                     # JSON/CSV export
    platforms/
      base.py                     # Abstract platform provider interface
      steam.py                    # Steam Web API integration
      xbox.py                     # Xbox Live (OpenXBL) integration
      psn.py                      # PlayStation Network integration
      gog.py                      # GOG Galaxy integration
      manual.py                   # Manual achievement entry
  backup/
    cli.py                        # Backup CLI commands
    engine.py                     # Full and incremental backup creation
    encryption.py                 # AES-256-GCM encryption
    verification.py               # Backup integrity verification
    restore.py                    # Restore with selective component support
    profiles.py                   # Backup profile management
    scheduler.py                  # Scheduled backup execution
    disaster_recovery.py          # Database health checks and recovery
tests/
  conftest.py                     # Shared pytest fixtures
  test_achievements/              # Achievement unit tests
  test_backup/                    # Backup/restore unit tests
  test_integration/               # End-to-end CLI workflow tests
```
