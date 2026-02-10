# Troubleshooting Guide

## Quick Diagnostics

Run with `--verbose` to see debug-level logs for any command:

```bash
playnite --verbose achievements sync
playnite --verbose backup create --destination ~/backups
```

Check configuration is correct (sensitive fields are masked):

```bash
playnite config show
```

---

## Authentication and Token Errors

### Steam: "API key rejected (HTTP 401 / 403)"

**Symptom:** Sync fails with `Steam: API key rejected (HTTP 4xx) — verify your Steam API key.`

**Causes and fixes:**
- The key has been revoked or regenerated. Go to <https://steamcommunity.com/dev/apikey> and copy the current key.
- The key was entered incorrectly. Re-run `playnite config set steam.api_key YOUR_KEY`.
- The Steam ID is wrong. Re-run `playnite config set steam.steam_id YOUR_STEAMID64`.

---

### Xbox: "API key rejected (HTTP 401 / 403)"

**Symptom:** Sync fails with `Xbox: API key rejected (HTTP 4xx) — verify your OpenXBL API key.`

**Fix:** Log in to <https://xapi.us>, copy your current API key, and run:

```bash
playnite config set xbox.api_key YOUR_KEY
```

The free tier has a rate limit (200 requests/hour). If you hit it, wait an hour and re-sync.

---

### PSN: "NPSSO token rejected (HTTP 401 / 403)"

**Symptom:** `PSN: NPSSO token rejected (HTTP 4xx) — obtain a fresh npsso token from playstation.com.`

**Cause:** NPSSO tokens expire after approximately 60 days, or are invalidated when you sign out.

**Fix:**
1. Open a browser and sign in at <https://www.playstation.com>
2. Navigate to <https://ca.account.sony.com/api/v1/ssocookie>
3. Copy the `"npsso"` value from the JSON
4. Run:

```bash
playnite config set psn.npsso_token YOUR_NEW_TOKEN
```

---

### PSN: "access token rejected" mid-sync

**Symptom:** Authentication succeeds but trophy fetching fails with `PSN: access token rejected (HTTP 401)`.

**Cause:** The OAuth access token derived from the NPSSO token expired during a long sync. The NPSSO itself may also be near expiry.

**Fix:** Obtain a fresh NPSSO token as described above and re-run the sync.

---

### GOG: "refresh token rejected (HTTP 401 / 403)"

**Symptom:** `GOG: refresh token rejected (HTTP 4xx) — re-authenticate via browser.`

**Cause:** The OAuth refresh token has expired or been revoked. GOG refresh tokens are long-lived but not permanent.

**Fix:** Re-extract a valid `access_token` and `refresh_token` from the GOG Galaxy client's local database and update your config:

```bash
playnite config set gog.access_token NEW_ACCESS_TOKEN
playnite config set gog.refresh_token NEW_REFRESH_TOKEN
```

---

## Sync Failures

### "No platforms synced (check configuration)"

No platform adapters are registered because none are enabled or configured.

```bash
playnite config show    # check that at least one platform has api_key/token set
playnite config set steam.enabled true
```

---

### Sync returns 0 games / 0 achievements

- **Steam:** Profile or game library may be set to private. In Steam → Privacy Settings, set "Game details" to Public.
- **Xbox:** Confirm the XUID matches the account whose achievements you want. Use `playnite config show` to verify.
- **PSN:** Trophies for a title may not have synced to the server yet. Open the game on your PlayStation and wait for the trophy sync sound.

---

### Partial sync (some platforms fail, others succeed)

Run `--verbose` to see per-platform errors:

```bash
playnite --verbose achievements sync
```

Failed platforms are reported individually. Resolve each one using the platform-specific sections above.

---

## Backup Errors

### "Backup file not found" / `file_exists: FAILED`

The archive file recorded in the database no longer exists on disk.

- Check that the destination path is still mounted (external drives, NAS).
- Use `playnite backup list` to find a backup at a path that still exists.
- If no valid backups exist, see [Disaster Recovery](restore_procedures.md#disaster-recovery-mode).

---

### "Checksum mismatch"

The archive file was modified or corrupted after the backup was created.

- Do not use this backup. Restore from an older backup.
- If the destination is a network share, check for filesystem or transmission errors.

---

### "Invalid ZIP archive" / `zip_valid: FAILED`

The archive is corrupt. Possible causes: incomplete write, disk failure, or bit rot.

- Run `playnite backup verify BACKUP_ID` to confirm.
- Restore from a different backup.

---

### "Decryption failed"

- Confirm you are using the exact password supplied at backup creation time. Passwords are case-sensitive.
- Run `playnite backup verify BACKUP_ID --password "..."` to test.
- There is no password recovery. If the password is lost, the backup cannot be decrypted.

---

### "Path traversal detected in archive member"

The backup archive contains a file path that would escape the restore destination (`../`). This indicates a corrupted or malicious archive. Do not restore it.

---

### Restore succeeded but app shows no games

The database file was replaced but the schema needs to be re-created:

```bash
playnite init-db
playnite backup import ~/playnite_library.json   # if you have an export
```

---

### "Parent backup not found" (incremental restore)

The parent backup referenced by an incremental backup has been deleted.

- Find the nearest full backup with `playnite backup list` and restore from that instead.
- To avoid this in future, set `--retention-days` high enough that full backups are retained as long as their incremental children.

---

## Scheduler Issues

### Scheduled backups are not running

1. Confirm the profile has a cron expression:

   ```bash
   playnite backup profile list
   ```

2. The scheduler runs within the application process. If the application is not running, scheduled backups will not fire.

3. For OS-level scheduling (always-on), add a cron entry instead:

   ```bash
   # Run a backup every day at 03:00
   0 3 * * * /usr/local/bin/playnite backup create --destination ~/backups >> ~/.playnite/backup.log 2>&1
   ```

4. Check for errors in logs. Run the backup manually to reproduce:

   ```bash
   playnite --verbose backup create --destination ~/backups
   ```

---

### Scheduled backup ran but no archive was created

- Check that the destination directory is writable.
- Check available disk space.
- Run the backup manually with `--verbose` to see the full error.

---

## Database Issues

### "OperationalError: no such table"

The database schema has not been initialised, or a migration is required.

```bash
playnite init-db
```

If you have Alembic configured:

```bash
alembic upgrade head
```

---

### "database is locked"

Another process is holding a write lock on the SQLite database. Ensure only one `playnite` process runs at a time.

---

### Database is corrupt / missing entirely

Use disaster recovery mode:

```bash
playnite disaster-recovery /path/to/latest/backup.pnb --destination ~/.config/playnite
playnite init-db
```

See [Disaster Recovery](restore_procedures.md#disaster-recovery-mode) for full steps.

---

## Configuration Issues

### `Unknown section: <name>`

The section name in `playnite config set` is not valid. Valid top-level sections:

- `steam` — fields: `api_key`, `steam_id`, `enabled`
- `xbox` — fields: `api_key`, `xuid`, `enabled`
- `psn` — fields: `npsso_token`, `enabled`
- `gog` — fields: `client_id`, `client_secret`, `access_token`, `refresh_token`, `user_id`, `enabled`

```bash
playnite config set steam.api_key YOUR_KEY    # correct
playnite config set Steam.api_key YOUR_KEY    # wrong — section names are lowercase
```

---

### Config changes are not persisted

- `config.json` is written to the data directory. Check `playnite config show` to confirm the path.
- If `--data-dir` is set, a separate config file is used in that directory.

---

## Export / Import Issues

### "Imported 0 achievements"

- Confirm the JSON file was created by `playnite achievements export` or `playnite backup export`.
- Check that the file is valid JSON: `python3 -m json.tool ~/achievements.json`

---

### Export produces an empty file

Run with `--verbose` to check for database query errors. Confirm the database has achievements:

```bash
playnite achievements stats
playnite achievements list | head -20
```

If `stats` shows 0 achievements, run a sync first:

```bash
playnite achievements sync
```

---

## Getting More Help

- Run any command with `--help` to see all options: `playnite backup create --help`
- Enable debug logging with `playnite --verbose <command>`
- File issues at <https://github.com/anthropics/claude-code/issues>
