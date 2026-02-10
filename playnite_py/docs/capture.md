# Capture System

`playnite_py` can capture screenshots, record video, and maintain an instant replay buffer. This document covers setup, capture backends, hotkey configuration, editing tools, and upload/cloud integration.

## Table of Contents

- [Dependencies](#dependencies)
- [Capture Backends](#capture-backends)
- [Screenshot Capture](#screenshot-capture)
- [Video Recording](#video-recording)
- [Instant Replay Buffer](#instant-replay-buffer)
- [Hotkeys](#hotkeys)
- [Managing Captures](#managing-captures)
- [Editing Tools](#editing-tools)
- [Cloud and Upload Integration](#cloud-and-upload-integration)
- [Storage Management](#storage-management)

---

## Dependencies

| Feature | Required package | Install |
|---------|-----------------|---------|
| Fast screenshot capture | `mss` | `pip install mss` |
| Image editing, annotations, cropping | `Pillow` | `pip install Pillow` |
| Video recording and editing | `ffmpeg` | System package manager |
| Global hotkeys | `pynput` | `pip install pynput` |

Check which are detected:

```bash
playnite status
```

None of these are strictly required — the system degrades gracefully: without `mss` it falls back to Pillow, without Pillow it produces a minimal placeholder image. Video commands require `ffmpeg` to be on your `PATH`.

---

## Capture Backends

The screenshot system supports three backends, selected in order of preference:

### mss (recommended)

`mss` is the fastest option and works on Windows, macOS, and Linux without a display server dependency.

```bash
pip install mss
```

### pil (Pillow fallback)

`PIL.ImageGrab` is used when `mss` is not available. It has good support on macOS and Windows. On Linux it requires an X11 display.

```bash
pip install Pillow
```

### mock (testing only)

When neither `mss` nor Pillow is installed, the mock backend generates a 400×225 grey placeholder image. This is useful for CI/CD pipelines and automated tests. It produces a real PNG file on disk so all file-handling code works normally.

### Backend comparison

| Backend | Speed | Platforms | Notes |
|---------|-------|-----------|-------|
| `mss` | Fastest | Windows, macOS, Linux | No display server dependency |
| `pil` | Medium | Windows, macOS, Linux (X11) | Requires Pillow |
| `mock` | Fast | All | Placeholder image only; for testing |

### Forcing a backend

```bash
playnite capture screenshot --backend pil
```

Or set the default in `config.json` (see [Configuration](../README.md#configuration)).

---

## Screenshot Capture

```bash
playnite capture screenshot [OPTIONS]
```

### Basic usage

```bash
# Capture the primary monitor
playnite capture screenshot

# Capture with game metadata attached
playnite capture screenshot --game "Hollow Knight" --game-id abc123

# Capture a specific monitor
playnite capture screenshot --monitor 2

# Save as JPEG at 80% quality
playnite capture screenshot --format jpeg --quality 80

# Add a timestamp burned into the corner
playnite capture screenshot --timestamp-overlay

# Skip automatic directory organisation
playnite capture screenshot --no-auto-organise
```

### Output organisation

By default screenshots are organised into a game-specific subdirectory:

```
{captures_dir}/
  {GameName}/
    screenshots/
      YYYY-MM-DD/
        HHMMSS_{uuid}.png
        HHMMSS_{uuid}.json    ← sidecar metadata
```

The sidecar JSON contains: `id`, `capture_type`, `game_name`, `game_id`, `captured_at`, `resolution`, `format`, `backend`, `tags`, and optionally `session_id`.

---

## Video Recording

Video recording requires `ffmpeg` on your `PATH`.

```bash
# Start recording
playnite capture start-recording --game "Elden Ring" --fps 60 --crf 20

# Check status
playnite capture recording-status

# Stop and save
playnite capture stop-recording
```

### Recording options

| Option | Default | Description |
|--------|---------|-------------|
| `--codec` | `libx264` | Video codec |
| `--crf` | `23` | Quality: 0 (lossless) – 51 (worst); lower = larger file |
| `--fps` | `30` | Frame rate |
| `--resolution` | auto | e.g. `1920x1080` |
| `--duration N` | none | Auto-stop after N seconds |
| `--simulate` | off | Simulate recording without ffmpeg (for testing) |

Videos are saved to `{captures_dir}/{GameName}/videos/YYYY-MM-DD/`.

---

## Instant Replay Buffer

The replay buffer continuously records the last N seconds in a circular buffer in memory. When something noteworthy happens, save the last chunk as a clip without having had to start recording in advance.

```bash
# Start buffering (keeps last 60 seconds)
playnite capture start-buffer --duration 60

# Save the full buffer
playnite capture save-replay --game "Hollow Knight"

# Save only the last 15 seconds
playnite capture save-replay --game "Hollow Knight" --last-seconds 15

# Check buffer status
playnite capture buffer-status

# Stop and discard the buffer
playnite capture stop-buffer
```

The default buffer duration is 60 seconds. This is configurable:

```json
{
  "capture": {
    "buffer_duration_seconds": 60
  }
}
```

Replays are saved to `{captures_dir}/{GameName}/replays/YYYY-MM-DD/`.

---

## Hotkeys

The hotkey listener captures screenshots and saves replays from anywhere on your desktop without switching to the terminal.

```bash
# Start the hotkey listener (runs in the foreground; Ctrl-C to stop)
playnite capture start-hotkeys

# Stop the listener
playnite capture stop-hotkeys
```

### Default hotkeys

| Action | Default key |
|--------|-------------|
| Screenshot | F12 |
| Start/stop video recording | F9 |
| Save instant replay | F10 |

### Changing hotkeys

Edit `config.json` in your data directory:

```json
{
  "capture": {
    "screenshot_hotkey": "f12",
    "record_hotkey": "f9",
    "save_replay_hotkey": "f10"
  }
}
```

Key names follow the `pynput` convention: `f1`–`f12`, letter keys (`a`–`z`), modifier keys (`ctrl`, `shift`, `alt`), etc.

Hotkeys require the `pynput` package:

```bash
pip install pynput
```

On macOS you may need to grant Accessibility permissions to the terminal application running `playnite`.

---

## Managing Captures

### Listing captures

```bash
# All captures
playnite capture list

# Filter by game
playnite capture list --game "Hollow Knight"

# Filter by type
playnite capture list --type screenshot

# Filter by tag
playnite capture list --tag boss

# Filter by date range
playnite capture list --since 2024-01-01 --until 2024-06-30

# Combine filters
playnite capture list --game "Celeste" --type screenshot --tag "golden strawberry" --since 2024-01-01

# Limit results
playnite capture list --limit 50

# JSON output
playnite --format json capture list
```

### Viewing metadata

```bash
playnite capture view-metadata path/to/screenshot.png
```

Displays all sidecar fields (game name, timestamp, resolution, format, backend, tags, session ID) in a table. Use `--format json` for machine-readable output.

### Tagging captures

Tags let you organise captures by milestone, quality, or any custom label.

```bash
# Add tags
playnite capture tag screenshot.png --add boss --add epic

# Remove a tag
playnite capture tag screenshot.png --remove draft

# Add and remove in one command
playnite capture tag screenshot.png --add highlight --remove draft
```

Tags are stored in the sidecar JSON and are searchable via `capture list --tag`.

---

## Editing Tools

All editing commands require Pillow (for images) or ffmpeg (for video). Check availability with `playnite status`.

### Trim a video

Cut a clip to a specific time range (seconds):

```bash
playnite capture trim input.mp4 output.mp4 10.0 30.5
```

Keeps only the segment from 10.0 s to 30.5 s.

### Crop a screenshot

```bash
playnite capture crop input.png output.png --left 100 --top 50 --right 1820 --bottom 1030
```

Coordinates are in pixels (left, top, right, bottom).

### Annotate a screenshot

Add a text label to an image:

```bash
playnite capture annotate input.png output.png --text "Final boss!" --x 10 --y 10
```

Default text colour is white. The position is the top-left corner of the text.

### Create a montage

Combine multiple screenshots into a grid:

```bash
playnite capture montage output.png shot1.png shot2.png shot3.png shot4.png --columns 2
```

Default column count is 3.

### Generate a highlights clip

Extract highlight segments from a longer recording:

```bash
playnite capture highlights long_recording.mp4 highlights.mp4 --count 3
```

Extracts the top 3 highlight segments and concatenates them.

### Convert format or resolution

Re-encode a video to a different format, codec, or resolution:

```bash
# Change codec
playnite capture convert input.mp4 output.mkv --codec libx265 --crf 28

# Downscale to 1080p
playnite capture convert input.mp4 output.mp4 --resolution 1920x1080
```

---

## Cloud and Upload Integration

```bash
playnite capture upload PATH/TO/file [--backend BACKEND] [--destination PATH]
```

### Available backends

| Backend | Description |
|---------|-------------|
| `local_copy` | Copy the file to another local directory |
| `simulated` | Simulate an upload without moving files (for testing) |

### Example: Copy to a network share

```bash
playnite capture upload screenshot.png --backend local_copy --destination /mnt/nas/captures/
```

### Adding real cloud backends

Real cloud upload (S3, Google Drive, etc.) is not included out of the box. The `MediaUploader` class in `playnite_py/capture/uploader.py` is designed for extension — add a new backend class that implements the `upload(source: Path, destination: str) -> str` interface, then register it in the uploader's backend registry.

---

## Storage Management

### Check current usage

```bash
playnite capture storage
```

Shows total storage used and a per-game breakdown.

### Automatic cleanup

```bash
# Delete captures older than 90 days
playnite capture cleanup --max-age-days 90

# Delete oldest captures until total is under 20 GB
playnite capture cleanup --max-gb 20

# Preview what would be deleted without deleting anything
playnite capture cleanup --max-age-days 30 --dry-run
```

Configure automatic cleanup defaults in `config.json`:

```json
{
  "capture": {
    "max_storage_gb": 50.0,
    "auto_cleanup_days": 90
  }
}
```

### Generate an HTML gallery

Create a static HTML gallery for a game's screenshots:

```bash
playnite capture gallery "Hollow Knight" [--output path/to/gallery.html]
```

The gallery is saved to `{captures_dir}/Hollow_Knight/gallery.html` by default and can be opened directly in a browser.
