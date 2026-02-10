# Troubleshooting

## Table of Contents

- [Checking System Status](#checking-system-status)
- [Installation Issues](#installation-issues)
- [Screenshot and Capture Errors](#screenshot-and-capture-errors)
- [Video Recording Errors](#video-recording-errors)
- [Hotkey Issues](#hotkey-issues)
- [Recommendation Engine Issues](#recommendation-engine-issues)
- [Database Issues](#database-issues)
- [Configuration Issues](#configuration-issues)
- [Log Files](#log-files)

---

## Checking System Status

Always start here. `playnite status` reports whether each subsystem is available:

```bash
playnite status
```

Sample output:

```
Component        Status
database         OK
ffmpeg           OK
ffprobe          OK
PIL              OK
numpy            OK
sklearn          OK
mss              OK
pynput           MISSING
recorder         OK
buffer           OK
hotkeys          MISSING  ← pynput not installed
overlay          OK
```

A `MISSING` status means the feature is unavailable but the rest of the tool still works. An `ERROR` status indicates a configuration or runtime problem.

---

## Installation Issues

### `ModuleNotFoundError: No module named 'mss'`

`mss` is optional but recommended for faster screenshots.

```bash
pip install mss
```

### `ModuleNotFoundError: No module named 'PIL'`

Pillow is required for image editing (crop, annotate, montage) and the `pil` screenshot backend.

```bash
pip install Pillow
```

### `ModuleNotFoundError: No module named 'sklearn'`

scikit-learn powers the collaborative filter in the recommendation engine. Without it, recommendations fall back to the content-only filter.

```bash
pip install scikit-learn
```

### `ModuleNotFoundError: No module named 'pynput'`

pynput is required for global hotkeys.

```bash
pip install pynput
```

### Installing all optional dependencies at once

```bash
pip install mss Pillow numpy scikit-learn pynput
```

---

## Screenshot and Capture Errors

### Screenshots produce a grey 400×225 placeholder

The mock backend is being used. This means neither `mss` nor Pillow is installed, or a non-existent backend was explicitly requested.

1. Run `playnite status` to check which backends are available.
2. Install `mss` (`pip install mss`) or Pillow (`pip install Pillow`).
3. If a backend was forced, check your command: `--backend mss` requires `mss` to be installed.

### `RuntimeError: Pillow is required for image cropping`

Pillow is not installed. Install it:

```bash
pip install Pillow
```

### Screenshot file exists but has size 0

The capture backend succeeded but could not write the image. Check:
- Disk space (`df -h` on Linux/macOS, `Get-PSDrive` on Windows)
- Write permission on the output directory
- Run with `--verbose` to see the full error trace:
  ```bash
  playnite --verbose capture screenshot
  ```

### `mss.ScreenShotError` on Linux

`mss` requires a running X11 or Wayland display server. It will not work in a headless SSH session without X forwarding. Use the `pil` backend or set up a virtual display:

```bash
playnite capture screenshot --backend pil
```

---

## Video Recording Errors

### `ffmpeg: command not found`

ffmpeg is not installed or not on your `PATH`.

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin/` folder to your `PATH`.

Verify the installation:
```bash
ffmpeg -version
```

### Recording starts but produces a 0-byte file

This usually means ffmpeg exited immediately due to an invalid codec or resolution argument.

1. Check the codec is available on your system: `ffmpeg -encoders | grep libx264`
2. If `libx264` is not listed, install it or switch to a codec that is available:
   ```bash
   playnite capture start-recording --codec mpeg4
   ```
3. Run with `--verbose` to capture the full ffmpeg stderr output.

### Recording hangs and never finishes

Use `capture stop-recording` to stop it manually. If that does not work, kill the process and check whether a partial video file was written to the output directory.

### `Smart App Control` crash on Windows

If you see an error about Smart App Control blocking the process, it is likely preventing unsigned executables (including ffmpeg) from running.

To resolve this, either:
- Disable Smart App Control in **Windows Security → App & browser control → Smart App Control**
- Or add ffmpeg to the allowed applications list

---

## Hotkey Issues

### Hotkeys do nothing

1. Check that the listener is running: `playnite capture recording-status`
2. Start it if needed: `playnite capture start-hotkeys`
3. Run `playnite status` and check that `pynput` and `hotkeys` are both `OK`.

### `pynput.keyboard._xorg.XorgError` on Linux

The hotkey listener requires an X11 display. It will not work in a pure terminal session. If you need headless operation, skip the hotkey listener and use the CLI commands directly.

### Hotkeys work but trigger on wrong keys

Check your configured key names in `config.json`. Key names follow the `pynput` convention (lowercase, e.g., `f12`, `f9`, `f10`). Invalid key names are silently ignored — the listener starts but those bindings are never triggered.

### macOS: hotkeys require Accessibility permission

`pynput` requires the terminal (or the app running `playnite`) to have Accessibility permission on macOS.

1. Go to **System Settings → Privacy & Security → Accessibility**.
2. Add your terminal application (Terminal, iTerm2, VS Code, etc.).
3. Restart the terminal and re-run `playnite capture start-hotkeys`.

---

## Recommendation Engine Issues

### "No recommendations found"

Possible causes:

1. **Library is empty.** Import games first: `playnite library import games.json`
2. **Filters are too strict.** Try removing some filters (e.g., `--vr`, `--difficulty`, `--max-hours`).
3. **Profile has not been analysed.** Run `playnite recommend analyse` first.
4. **All games score below `min_score_threshold`.** Lower the threshold in `config.json`:
   ```json
   { "recommendations": { "min_score_threshold": 0.01 } }
   ```

### Recommendations are always the same games

This usually means:
- The content filter is dominating. Try adding feedback: `playnite recommend feedback "GameName" played`.
- Your library is very small (< 10 games). The collaborative filter needs history to work.
- You have a persistent mood set. Clear it: `playnite recommend clear-filters`.

### `sklearn` or `numpy` errors during `recommend generate`

```
ImportError: cannot import name 'TruncatedSVD' from 'sklearn.decomposition'
```

Your scikit-learn version may be incompatible. Try upgrading:

```bash
pip install --upgrade scikit-learn numpy
```

### Recommendations do not improve after giving feedback

- Check the feedback was recorded: `playnite recommend stats` should show a non-zero feedback count.
- The `feedback_learning_rate` controls how quickly weights shift. If it is very low (e.g. 0.01), many feedback events are needed to see a change. Increase it temporarily:
  ```json
  { "recommendations": { "feedback_learning_rate": 0.3 } }
  ```
- Re-run `playnite recommend analyse` after a batch of feedback to rebuild weights from scratch.

---

## Database Issues

### `sqlite3.OperationalError: database is locked`

Another `playnite` process is running and holds the database lock.

1. Check for other running processes: `ps aux | grep playnite` (Linux/macOS) or Task Manager (Windows).
2. Wait for the other process to finish, or kill it.
3. If the lock persists after all processes have exited, the lock file may be stale. Look for a `{data_dir}/*.db-wal` or `*.db-shm` file and delete it (only when no processes are running).

### `sqlite3.DatabaseError: database disk image is malformed`

The database file is corrupted (e.g., due to a crash or power loss during a write).

1. Back up the existing file: `cp playnite.db playnite.db.bak`
2. Attempt recovery:
   ```bash
   sqlite3 playnite.db ".recover" | sqlite3 playnite_recovered.db
   ```
3. If recovery fails, delete the database and re-import your library from a JSON export.

### How to reset the database completely

```bash
# Find the data directory
playnite --verbose status 2>&1 | grep "data_dir"

# Delete the database (back it up first!)
rm ~/.local/share/PlaynitePy/playnite.db   # Linux
rm ~/Library/Application\ Support/PlaynitePy/playnite.db  # macOS
```

After deleting, re-import your library and re-run `recommend analyse`.

---

## Configuration Issues

### Where is `config.json`?

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\PlaynitePy\config.json` |
| macOS | `~/Library/Application Support/PlaynitePy/config.json` |
| Linux | `~/.local/share/PlaynitePy/config.json` |

The file is created automatically with defaults on first run. You can override the directory:

```bash
playnite --data-dir /custom/path status
```

### Config changes are not taking effect

`config.json` is read at startup. After editing the file, re-run the command. There is no hot-reload.

### Resetting configuration to defaults

Delete `config.json` and it will be recreated with default values on the next run:

```bash
rm ~/.local/share/PlaynitePy/config.json   # Linux
```

---

## Log Files

By default `playnite_py` logs warnings and errors to stderr. To enable verbose logging:

```bash
playnite --verbose <command>
```

To redirect logs to a file for later inspection:

```bash
playnite --verbose capture screenshot 2> capture.log
```

Key log messages to look for:

| Message | Meaning |
|---------|---------|
| `Failed to parse sidecar` | A metadata JSON file is malformed |
| `Could not remove empty dir` | Directory cleanup failed (permission issue) |
| `No module named ...` | Optional dependency missing |
| `ffmpeg exited with code` | ffmpeg error — run with `--verbose` to see ffmpeg stderr |
