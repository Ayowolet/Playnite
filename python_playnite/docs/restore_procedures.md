# Restore Procedures

## Standard Restore

Restore everything from a backup:

```bash
# List available backups
playnite backup list

# Full restore (all categories) to default data directory
playnite backup restore 5

# Restore to a custom directory
playnite backup restore 5 --destination /tmp/restored

# Restore encrypted backup
playnite backup restore 5 --password "my_password"
```

## Selective Restore

Restore only specific categories to avoid overwriting unaffected data:

```bash
# Restore only the database
playnite backup restore 5 --categories database

# Restore database and configuration
playnite backup restore 5 --categories database --categories config

# Restore themes and plugins only
playnite backup restore 5 --categories themes --categories plugins
```

Available categories: `database`, `config`, `themes`, `plugins`,
`achievements`, `controller_mappings`

---

## Incremental Restore

When restoring an incremental backup, the system automatically restores the
parent backup chain first, then applies the incremental changes on top.
No special flags are required:

```bash
playnite backup restore 12   # automatically restores parent chain
```

---

## Disaster Recovery Mode

Use when the database is corrupted/missing and standard restore cannot
locate backup records.

```bash
# Restore directly from an archive file (bypasses the database)
playnite disaster-recovery /path/to/playnite_full_20240315.pnb

# Encrypted backup
playnite disaster-recovery /path/to/playnite_full_20240315.pnbe

# Specify target directory
playnite disaster-recovery /path/to/backup.pnb --destination /tmp/recovery
```

After disaster recovery:

```bash
# Re-initialise the database schema
playnite init-db

# Re-import achievement data if the database was not recoverable
playnite backup import ~/exports/library.json
```

---

## Verifying Before Restore

Always verify a backup before restoring to confirm integrity:

```bash
playnite backup verify 5
# Expected output:
#   Verification result: PASSED
#   ✓ file_exists: /path/to/backup.pnb
#   ✓ checksum: OK
#   ✓ zip_valid: OK
#   ✓ manifest: OK
#   ✓ file_checksums: All files OK
```

If verification fails, try an older backup or use the disaster recovery mode.

---

## Post-Restore Steps

1. **Restart the application** to reload the database.
2. **Re-run achievement sync** to fetch any achievements unlocked since the
   backup was created:
   ```bash
   playnite achievements sync
   ```
3. **Verify data integrity** by checking game counts and achievement counts.

---

## Migration to a New System

Export the library for cross-platform migration:

```bash
# On the source system
playnite backup export ~/playnite_library.json

# On the new system
playnite backup import ~/playnite_library.json
```

Or use a full backup:

```bash
# On source
playnite backup create --destination ~/

# On new system – disaster recovery mode works without a DB
playnite disaster-recovery ~/playnite_full_20240315.pnb --destination ~/.config/playnite
playnite init-db
```

---

## Automated Restore Testing

Test your backup strategy by periodically performing a restore to a temp
directory:

```bash
#!/bin/bash
# restore_test.sh – run weekly via cron

BACKUP_ID=$(playnite backup list --json | python3 -c \
  "import sys,json; data=json.load(sys.stdin); print(data[0]['id'])")

RESTORE_DIR=$(mktemp -d)
playnite backup restore "$BACKUP_ID" --destination "$RESTORE_DIR" --json && \
  echo "Restore test PASSED" || echo "Restore test FAILED"

rm -rf "$RESTORE_DIR"
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Backup file not found" | Check `destination` path; use `playnite backup list` |
| "Decryption failed" | Confirm password is correct; try `playnite backup verify` |
| "Invalid ZIP archive" | Archive is corrupt; restore from a different backup |
| "Parent backup not found" | Parent backup was deleted; restore from a full backup |
| Restore succeeded but app shows no games | Run `playnite init-db` and re-import |
