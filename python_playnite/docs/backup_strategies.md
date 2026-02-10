# Backup Strategies Guide

## Backup Types

### Full Backup
A complete snapshot of all configured data. Use this as a baseline.

```bash
playnite backup create --destination ~/backups
playnite backup create --destination ~/backups --label "monthly"
```

### Incremental Backup
Only files changed since the last backup are stored. Smaller and faster than
a full backup.

```bash
# Automatically uses the most recent backup as parent
playnite backup create --incremental --destination ~/backups

# Specify parent explicitly
playnite backup create --incremental --parent-id 5 --destination ~/backups
```

### Pre-Update Backup
Automatically triggered before major changes:

```python
# In code
mgr.create_pre_update_backup()
```

---

## Backup Profiles

Profiles let you define named strategies with different schedules, destinations,
and retention policies.

```bash
# Daily backup at 02:00 UTC, kept for 30 days, max 10 copies
playnite backup profile create \
  --name "daily" \
  --cron "0 2 * * *" \
  --destination ~/backups/daily \
  --retention-days 30 \
  --max-count 10

# Weekly encrypted backup
playnite backup profile create \
  --name "weekly-encrypted" \
  --cron "0 3 * * 0" \
  --destination /mnt/external/backups \
  --encrypt \
  --retention-days 90 \
  --max-count 12

# List profiles
playnite backup profile list
```

---

## Encryption

All backups can be AES-256-GCM encrypted. The key is derived from a
user-supplied password using PBKDF2-HMAC-SHA256 (480,000 iterations).

```bash
# Encrypt at creation time
playnite backup create --encrypted --destination ~/backups
# Password is prompted interactively

# Or provide inline (less secure)
playnite backup create --encrypted --password "my_password" --destination ~/backups
```

Encrypted backups use the `.pnbe` file extension.
Plain (but compressed) backups use `.pnb`.

> **Important**: There is no password recovery. Store your password in a
> password manager.

---

## Recommended Strategies

### Strategy 1: Personal / Home Use

```
Weekly full backup  →  ~/backups/weekly/  (keep 4 weeks)
Daily incremental   →  ~/backups/daily/   (keep 7 days)
```

```bash
playnite backup profile create \
  --name weekly \
  --cron "0 2 * * 0" \
  --destination ~/backups/weekly \
  --retention-days 28 --max-count 4

playnite backup profile create \
  --name daily \
  --cron "0 3 * * *" \
  --destination ~/backups/daily \
  --retention-days 7 --max-count 7
```

### Strategy 2: Encrypted Off-Site

```bash
playnite backup profile create \
  --name offsite \
  --cron "0 4 * * 0" \
  --destination /mnt/nas/playnite \
  --encrypt \
  --retention-days 90
```

### Strategy 3: Minimal (manual only)

```bash
# Before any significant change
playnite backup create --destination ~/backups --label "before-plugin-update"
```

---

## What Gets Backed Up

| Category | Contents | Default |
|---|---|---|
| `database` | `playnite.db` SQLite library | ✓ |
| `config` | `config.json` and `configs/` | ✓ |
| `themes` | `themes/` directory | ✓ |
| `plugins` | `plugins/` directory | ✓ |
| `achievements` | Exported achievement data | ✓ |
| `controller_mappings` | `controller_mappings/` | ✓ |

Selective backups:

```bash
# Back up only the database and configs
playnite backup create \
  --categories database \
  --categories config \
  --destination ~/backups
```

---

## Verifying Backups

Always verify a backup after creation, especially before deleting old backups.

```bash
playnite backup verify 5
playnite backup verify 5 --password "my_password"  # for encrypted backups
```

The verifier checks:
1. Archive file exists on disk
2. SHA-256 checksum matches stored value
3. Archive is a valid ZIP file with no corrupt entries
4. `manifest.json` is present and parseable
5. All files in the manifest have matching checksums

---

## Storage Sizing Estimates

| Component | Typical Size |
|---|---|
| SQLite database (1,000 games) | 2–10 MB |
| Themes (default only) | < 1 MB |
| Plugin data | 1–50 MB |
| Achievement exports | 1–5 MB |
| **Total** | **~5–70 MB** |

After ZIP compression, expect 40–60% size reduction.
Encrypted backups add a small overhead (< 1 KB).
