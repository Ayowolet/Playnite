# playnite_py

Python game library manager with an intelligent recommendation engine and media capture system. Works alongside [Playnite](https://playnite.link/) or standalone.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
  - [Global Flags](#global-flags)
  - [library](#library-commands)
  - [recommend](#recommend-commands)
  - [capture](#capture-commands)
  - [status](#status-command)
- [Configuration](#configuration)
- [Further Reading](#further-reading)

---

## Installation

```bash
# Install the package in editable mode (development)
pip install -e .

# Optional dependencies unlock additional features
pip install mss          # Faster screenshot capture (recommended)
pip install Pillow       # Image editing, annotations, cropping
pip install numpy scikit-learn  # Recommendation engine
pip install pynput       # Global hotkey support
# ffmpeg must be installed separately for video recording/editing
```

Check which components are available:

```bash
playnite status
```

---

## Quick Start

```bash
# Import your game library from a JSON export
playnite library import games.json

# Analyse your library and build a preference profile
playnite recommend analyse

# Get 10 personalised game recommendations
playnite recommend generate

# Capture a screenshot of the current screen
playnite capture screenshot --game "Hollow Knight"

# Start a 60-second instant replay buffer
playnite capture start-buffer --duration 60
# ... play some games ...
playnite capture save-replay --game "Hollow Knight"
```

---

## CLI Reference

### Global Flags

These flags apply to every command:

| Flag | Description |
|------|-------------|
| `--data-dir PATH` | Override the data directory (default: platform-specific, see [Configuration](#configuration)) |
| `--format table\|json\|plain` | Output format (default: `table`) |
| `--profile ID` | Use a specific user profile ID |
| `--verbose` | Enable verbose/debug logging |

---

### library commands

Manage your game library.

```bash
playnite library stats
```
Show total game count, playtime, completion stats.

```bash
playnite library list [--genre GENRE] [--platform PLATFORM] [--limit N]
```
List all games in your library.

```bash
playnite library import FILE
```
Import games from a JSON file. Existing games are updated by ID.

```bash
playnite library export [--output FILE]
```
Export the full library to JSON.

```bash
playnite library search QUERY [--genre GENRE] [--platform PLATFORM]
```
Full-text search across game names, genres, and tags.

---

### recommend commands

Intelligent game recommendations powered by a hybrid content + collaborative filter. See [docs/recommendations.md](docs/recommendations.md) for algorithm details.

```bash
playnite recommend analyse
```
Analyse your library and build/update your preference profile. Run this after importing new games.

```bash
playnite recommend generate [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--mood MOOD` | Filter by mood (relaxed, excited, casual, …) |
| `-n, --count N` | Number of recommendations (default: 10) |
| `--genre GENRE` | Restrict to a specific genre |
| `--platform PLATFORM` | Restrict to a specific platform |
| `--session quick\|deep` | Session length: `quick` (< 1 h) or `deep` (3+ h) |
| `--max-hours HOURS` | Maximum main-story completion time |
| `--min-hours HOURS` | Minimum main-story completion time |
| `--difficulty easy\|medium\|hard\|very hard` | Filter by difficulty |
| `--multiplayer` / `--no-multiplayer` | Require or exclude multiplayer games |
| `--vr` | Only VR-compatible games |
| `--include-unowned` | Include games not in your library |
| `--no-save` | Do not save this batch to history |

```bash
playnite recommend what-next [-n N]
```
Quick "what to play next" suggestion based on recent activity.

```bash
playnite recommend mood [MOOD|clear] [--list]
```
Set a persistent mood filter on your profile. Use `clear` or `--list` to see all moods.

```bash
playnite recommend clear-filters
```
Clear the persistent mood filter. Per-call filters (genre, platform, etc.) are cleared by simply omitting the flag.

```bash
playnite recommend feedback GAME_NAME ACTION [--notes TEXT]
```
Record feedback to improve future recommendations. `ACTION` is one of: `played`, `liked`, `disliked`, `dismissed`, `added_to_wishlist`, `ignored`.

```bash
playnite recommend stats
```
Show recommendation accuracy: acceptance rate, play conversion rate.

```bash
playnite recommend history [--limit N]
```
View past recommendation batches.

```bash
playnite recommend feed [-n N] [--mood MOOD]
```
Multi-shelf discovery feed: Top Picks, Because You Played X, From Your Backlog, Discover Something New, Seasonal Picks.

```bash
playnite recommend export [-o FILE]
```
Export full recommendation history and reasoning to JSON.

---

### capture commands

Screenshot and video capture. See [docs/capture.md](docs/capture.md) for setup and backend details.

#### Screenshots

```bash
playnite capture screenshot [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--game NAME` | Game name for organisation |
| `--game-id ID` | Library game ID |
| `--monitor N` | Monitor index, 1-based (default: 1) |
| `--format png\|jpeg\|webp` | Image format (default: png) |
| `--quality N` | JPEG quality 1–100 (default: 95) |
| `--output PATH` | Override output directory |
| `--backend mss\|pil\|mock` | Force a specific capture backend |
| `--timestamp-overlay` | Burn timestamp into the image |
| `--no-auto-organise` | Skip automatic directory organisation |

#### Video Recording

```bash
# Start recording
playnite capture start-recording [--game NAME] [--codec libx264] [--crf 23] [--fps 30] [--duration SECS]

# Stop recording
playnite capture stop-recording

# Check status
playnite capture recording-status
```

#### Instant Replay Buffer

```bash
# Start buffering (keeps last N seconds in memory)
playnite capture start-buffer [--duration 60]

# Save the buffer to a clip
playnite capture save-replay [--game NAME] [--last-seconds N] [--output PATH]

# Check buffer status
playnite capture buffer-status
```

#### Hotkeys

Start the hotkey listener to capture with keyboard shortcuts:

```bash
playnite capture start-hotkeys
```

Default hotkeys (configurable in `config.json`):

| Action | Default Key |
|--------|-------------|
| Screenshot | F12 |
| Start/stop recording | F9 |
| Save instant replay | F10 |

#### Managing Captures

```bash
# List captures with optional filters
playnite capture list [--game NAME] [--type screenshot|video|replay] \
                      [--tag TAG] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit N]

# View full sidecar metadata for a file
playnite capture view-metadata PATH/TO/screenshot.png

# Add or remove tags
playnite capture tag PATH/TO/screenshot.png --add boss --add epic --remove draft

# Show storage usage
playnite capture storage

# Clean up old captures
playnite capture cleanup [--max-age-days 90] [--max-gb 50] [--dry-run]
```

#### Editing

```bash
# Trim a video clip (times in seconds)
playnite capture trim input.mp4 output.mp4 10.0 30.5

# Crop a screenshot to a region
playnite capture crop input.png output.png --left 0 --top 0 --right 1280 --bottom 720

# Add a text annotation to an image
playnite capture annotate input.png output.png --text "Boss kill!" --x 10 --y 10

# Create a montage from multiple screenshots
playnite capture montage output.png shot1.png shot2.png shot3.png [--columns 3]

# Generate a highlights clip
playnite capture highlights input.mp4 output.mp4 [--count 3]

# Convert video format or resolution
playnite capture convert input.mp4 output.mp4 [--resolution 1920x1080] [--codec libx264] [--crf 23]
```

#### Game Detection

```bash
# Detect currently running games
playnite capture detect

# Simulate a running game (for testing)
playnite capture detect --simulate "Hollow Knight"
```

#### Cloud Upload

```bash
playnite capture upload PATH/TO/file [--backend local_copy] [--destination PATH]
```

---

### status command

Check which subsystems are available:

```bash
playnite status
```

Reports the status of: database, ffmpeg, ffprobe, PIL/Pillow, numpy, scikit-learn, mss, pynput, video recorder, replay buffer, hotkeys, screen overlay.

---

## Configuration

The configuration file is loaded automatically from:

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\PlaynitePy\config.json` |
| macOS | `~/Library/Application Support/PlaynitePy/config.json` |
| Linux | `~/.local/share/PlaynitePy/config.json` |

Override the data directory for a single command:

```bash
playnite --data-dir /my/custom/dir recommend generate
```

Key settings (all have sensible defaults):

```json
{
  "capture": {
    "screenshot_format": "png",
    "screenshot_hotkey": "f12",
    "record_hotkey": "f9",
    "save_replay_hotkey": "f10",
    "video_codec": "libx264",
    "video_crf": 23,
    "video_fps": 30,
    "buffer_duration_seconds": 60,
    "max_storage_gb": 50.0,
    "auto_cleanup_days": 90
  },
  "recommendations": {
    "content_weight": 0.60,
    "collaborative_weight": 0.25,
    "temporal_weight": 0.10,
    "popularity_weight": 0.05
  }
}
```

---

## Further Reading

- [docs/recommendations.md](docs/recommendations.md) — How the recommendation algorithm works and how to improve its accuracy
- [docs/capture.md](docs/capture.md) — Capture system setup, backends, hotkeys, editing tools, and cloud integration
- [docs/troubleshooting.md](docs/troubleshooting.md) — Common errors and how to fix them
