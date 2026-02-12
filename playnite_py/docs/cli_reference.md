# CLI Reference

Complete reference for all Playnite-Py command-line interface commands.

## Global Options

```
playnite [OPTIONS] COMMAND [ARGS]...
```

| Option | Description |
|--------|-------------|
| `--data-dir PATH` | Data directory path (default: platform-specific) |
| `--json` | Output in JSON format for scripting |
| `-v, --verbose` | Enable verbose logging |
| `--version` | Show version information |
| `--help` | Show help message |

## Commands Overview

| Command | Description |
|---------|-------------|
| `status` | Show application status |
| `version` | Show version information |
| `profile` | Manage library profiles |
| `config` | Manage platform configurations |
| `game` | Manage games in the library |

---

## status

Show current status of the application.

```bash
playnite status
```

**Output includes:**
- Detected platform type
- Operating system information
- CPU and RAM details
- Active profile (if any)

**JSON output:**
```json
{
  "platform": "desktop",
  "os": "Linux 6.1.0",
  "cpu": "AMD Ryzen 9 5900X",
  "ram_gb": 32,
  "current_profile": "Gaming"
}
```

---

## version

Show version information.

```bash
playnite version
```

---

## profile

Manage library profiles.

### profile create

Create a new profile.

```bash
playnite profile create NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-d, --description TEXT` | Profile description |
| `-t, --template TEXT` | Template to use (default, kids, work, testing, family, streaming) |
| `-p, --parent TEXT` | Parent profile for inheritance |
| `--default` | Set as default startup profile |

**Examples:**
```bash
playnite profile create "Gaming"
playnite profile create "Kids" --template kids
playnite profile create "Laptop Gaming" --parent "Gaming"
```

### profile list

List all profiles.

```bash
playnite profile list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-a, --all` | Show all details |

### profile switch

Switch to a different profile.

```bash
playnite profile switch NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-p, --password TEXT` | Password for protected profiles |
| `-f, --force` | Force switch even if locked |

### profile delete

Delete a profile.

```bash
playnite profile delete NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--delete-data` | Also delete all profile data files |
| `-p, --password TEXT` | Password for protected profiles |
| `-y, --yes` | Skip confirmation prompt |

### profile info

Show detailed profile information.

```bash
playnite profile info NAME
```

### profile export

Export a profile for backup or migration.

```bash
playnite profile export NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Output file path (required) |
| `--no-games` | Exclude game library |
| `--no-media` | Exclude media files |
| `-p, --password TEXT` | Encrypt export with password |

### profile import

Import a profile from an export file.

```bash
playnite profile import PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-n, --name TEXT` | Override profile name |
| `-p, --password TEXT` | Decryption password |
| `--overwrite` | Overwrite existing profile |

### profile set-password

Set or change profile password.

```bash
playnite profile set-password NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--current-password TEXT` | Current password (if already protected) |

### profile templates

List available profile templates.

```bash
playnite profile templates
```

### profile set-default

Set a profile as the default startup profile.

```bash
playnite profile set-default NAME
```

---

## config

Manage platform configurations.

### config create

Create a new platform configuration for a game.

```bash
playnite config create [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-g, --game TEXT` | Game name or ID (required) |
| `-n, --name TEXT` | Configuration name (required) |
| `-d, --description TEXT` | Configuration description |
| `-p, --preset TEXT` | Use a preset template |
| `--platform TEXT` | Target platform (desktop, laptop, htpc, handheld, vm, remote) |
| `--default` | Set as default configuration |

**Presets:** performance, quality, balanced, battery-saver, streaming, handheld, debug

**Examples:**
```bash
playnite config create --game "Cyberpunk 2077" --name "Desktop" --preset quality
playnite config create -g "My Game" -n "Laptop" --platform laptop --preset battery-saver
```

### config list

List platform configurations.

```bash
playnite config list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-g, --game TEXT` | Filter by game name or ID |

### config info

Show detailed configuration information.

```bash
playnite config info [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-g, --game TEXT` | Game name or ID (required) |
| `-c, --config TEXT` | Configuration name (required) |

### config delete

Delete a configuration.

```bash
playnite config delete [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-g, --game TEXT` | Game name or ID (required) |
| `-c, --config TEXT` | Configuration name (required) |
| `-y, --yes` | Skip confirmation |

### config set-default

Set a configuration as the default for a game.

```bash
playnite config set-default [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-g, --game TEXT` | Game name or ID (required) |
| `-c, --config TEXT` | Configuration name (required) |

### config templates

List available configuration templates.

```bash
playnite config templates
```

### config validate

Validate a configuration.

```bash
playnite config validate [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-g, --game TEXT` | Game name or ID (required) |
| `-c, --config TEXT` | Configuration name (required) |

### config detect

Detect current platform and hardware.

```bash
playnite config detect
```

**JSON output:**
```json
{
  "platform": "desktop",
  "os": "Linux 6.1.0",
  "cpu": "AMD Ryzen 9 5900X",
  "cpu_cores": 12,
  "cpu_threads": 24,
  "ram_mb": 32768,
  "gpus": [{"name": "NVIDIA GeForce RTX 3080", "vendor": "nvidia"}],
  "displays": [{"name": "DP-1", "width": 2560, "height": 1440}],
  "power_source": "ac",
  "is_laptop": false,
  "is_steam_deck": false
}
```

---

## game

Manage games in the library.

### game list

List games in the current profile.

```bash
playnite game list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-s, --source TEXT` | Filter by source |
| `-f, --favorites` | Show only favorites |
| `-q, --search TEXT` | Search by name |

### game add

Add a game to the library.

```bash
playnite game add NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-p, --path PATH` | Path to game executable |
| `-s, --source TEXT` | Game source (default: manual) |
| `-d, --description TEXT` | Game description |
| `--install-dir PATH` | Game installation directory |

**Examples:**
```bash
playnite game add "My Game" --path "/games/mygame/game.exe"
playnite game add "Steam Game" --source steam
```

### game info

Show detailed game information.

```bash
playnite game info NAME
```

### game delete

Delete a game from the library.

```bash
playnite game delete NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-y, --yes` | Skip confirmation |

### game launch

Launch a game.

```bash
playnite game launch NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-c, --config TEXT` | Configuration to use |
| `-a, --action TEXT` | Action to execute |
| `--no-wait` | Don't wait for game to exit |

### game favorite

Add or remove a game from favorites.

```bash
playnite game favorite NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-r, --remove` | Remove from favorites |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (see error message) |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PLAYNITE_DATA_DIR` | Override data directory location |

## JSON Output

Add `--json` flag for machine-readable output:

```bash
playnite --json profile list
playnite --json game info "My Game"
playnite --json config detect
```

JSON output structure varies by command. Error responses include:
```json
{
  "success": false,
  "error": "Error message"
}
```
