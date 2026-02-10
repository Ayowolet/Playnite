# Capture System Setup Guide

Complete guide to setting up and configuring the screenshot and video capture system for Playnite Python.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Backend Selection](#backend-selection)
- [Hotkey Configuration](#hotkey-configuration)
- [Advanced Configuration](#advanced-configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Performance Tuning](#performance-tuning)

---

## Overview

The capture system provides:
- **Screenshot Capture**: Press a hotkey to capture moments
- **Video Recording**: Record gameplay sessions
- **Instant Replay**: Save the last 30-60 seconds of gameplay
- **Automatic Organization**: Files organized by game
- **Metadata Tagging**: Track when, where, and what you captured

### System Requirements

**Minimum**:
- CPU: Dual-core processor
- RAM: 4GB
- Disk: 10GB free space
- OS: Windows 10, macOS 10.15+, or Linux

**Recommended**:
- CPU: Quad-core processor (for video recording)
- RAM: 8GB+
- Disk: 50GB+ free space (SSD preferred)
- GPU: Dedicated graphics card with hardware encoding

---

## Prerequisites

### 1. Install Python Service

```bash
cd playnite-python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

### 2. Install FFmpeg (Required for Video)

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**macOS**:
```bash
brew install ffmpeg
```

**Windows**:
1. Download from https://ffmpeg.org/download.html
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to PATH

**Verify Installation**:
```bash
ffmpeg -version
ffprobe -version
```

### 3. Install Optional Dependencies

**For OBS Backend**:
```bash
# Install OBS Studio
# Ubuntu: sudo apt-get install obs-studio
# macOS: brew install obs
# Windows: Download from obsproject.com

# Install obs-websocket plugin
pip install obs-websocket-py
```

**For Hardware Acceleration** (NVIDIA):
```bash
# Check if NVENC is available
ffmpeg -encoders | grep nvenc

# Should show: h264_nvenc, hevc_nvenc
```

---

## Quick Start

### 1. Start the Service

```bash
python -m playnite_python serve
```

The service will start on `http://localhost:5555`.

### 2. Test Screenshot Capture

```bash
# Start capture session
python -m playnite_python capture start \
    --game-id test-game \
    --game-name "Test Game" \
    --backend direct

# Press F8 to capture screenshot
# Screenshots saved to: ~/Playnite/Captures/test-game/screenshots/
```

### 3. Test Video Recording

```bash
# Start session (if not already started)
python -m playnite_python capture start \
    --game-id test-game \
    --game-name "Test Game"

# Press F9 to start/stop recording
# Videos saved to: ~/Playnite/Captures/test-game/videos/
```

### 4. Verify Captures

```bash
# List captures for game
python -m playnite_python capture list test-game

# View statistics
python -m playnite_python capture stats
```

---

## Backend Selection

The capture system supports multiple backends. Choose based on your needs:

### Direct Capture (Default)

**How it works**: Captures entire primary monitor using `mss` (screenshots) and `opencv` (video).

**Pros**:
- ✅ No additional software needed
- ✅ Fast screenshot capture (<100ms)
- ✅ Works with all games
- ✅ Simple setup

**Cons**:
- ❌ Captures entire screen (not just game window)
- ❌ Higher CPU usage for video
- ❌ No game-specific overlays

**Best for**: Single-monitor setups, casual capturing

**Setup**:
```bash
# No setup needed - works out of the box
python -m playnite_python capture start \
    --backend direct
```

**Configuration**:
```python
# In settings
{
    "backend": "direct",
    "video_quality": "high",  # low, medium, high
    "screenshot_format": "png"  # png, jpg
}
```

---

### OBS Studio Backend

**How it works**: Uses OBS Studio via obs-websocket for professional-quality captures.

**Pros**:
- ✅ Best video quality
- ✅ Hardware encoding support
- ✅ Game capture (specific window)
- ✅ Customizable scenes and sources
- ✅ Streaming integration

**Cons**:
- ❌ Requires OBS installation
- ❌ More complex setup
- ❌ Higher resource usage

**Best for**: Content creators, high-quality captures, streaming

**Setup**:

1. **Install OBS Studio**:
   - Download from https://obsproject.com
   - Install for your operating system

2. **Install obs-websocket**:
   - OBS 28+ includes it by default
   - For older versions: Download from https://github.com/obsproject/obs-websocket

3. **Configure OBS**:
   ```
   OBS → Tools → WebSocket Server Settings
   - Enable WebSocket Server: ✓
   - Server Port: 4455
   - Server Password: (set a password)
   ```

4. **Configure Python Service**:
   ```bash
   # Set environment variables
   export OBS_WEBSOCKET_HOST=localhost
   export OBS_WEBSOCKET_PORT=4455
   export OBS_WEBSOCKET_PASSWORD=your-password

   # Or in .env file
   OBS_WEBSOCKET_HOST=localhost
   OBS_WEBSOCKET_PORT=4455
   OBS_WEBSOCKET_PASSWORD=your-password
   ```

5. **Create OBS Scene**:
   ```
   OBS → Scenes → + (Add)
   Name: "Playnite Capture"

   Add Source:
   - Game Capture (for specific game)
   OR
   - Display Capture (for full screen)
   ```

6. **Start Capture with OBS**:
   ```bash
   python -m playnite_python capture start \
       --backend obs \
       --game-id game-123 \
       --game-name "Dark Souls"
   ```

**Advanced OBS Configuration**:
```json
{
    "backend": "obs",
    "obs_scene": "Playnite Capture",
    "obs_source": "Game Capture",
    "video_quality": "high",
    "hardware_encoder": "nvenc",  # nvenc, qsv, amf
    "bitrate": 8000,  # kbps
    "framerate": 60
}
```

---

### Windows Game Bar Backend

**How it works**: Uses Windows 10/11 Game Bar API for captures.

**Pros**:
- ✅ Built into Windows
- ✅ Game-specific capture
- ✅ Low overhead
- ✅ Hardware encoding

**Cons**:
- ❌ Windows only
- ❌ Limited configuration
- ❌ May require Game Bar enabled

**Best for**: Windows users who want simple game-specific capture

**Setup**:

1. **Enable Game Bar**:
   ```
   Windows Settings → Gaming → Game Bar
   - Record game clips... : On
   - Game Mode: On
   ```

2. **Grant Permissions**:
   ```
   Windows Settings → Privacy → App permissions
   - Camera: Allow
   - Microphone: Allow (optional)
   ```

3. **Start Capture**:
   ```bash
   python -m playnite_python capture start \
       --backend gamebar \
       --game-id game-123 \
       --game-name "Dark Souls"
   ```

**Configuration**:
```json
{
    "backend": "gamebar",
    "video_quality": "high",
    "audio_capture": true,
    "microphone_capture": false
}
```

---

## Hotkey Configuration

### Default Hotkeys

| Action | Default Key | Description |
|--------|-------------|-------------|
| Screenshot | F8 | Capture a single screenshot |
| Video Toggle | F9 | Start/stop video recording |
| Instant Replay | F10 | Save last 30 seconds |

### Changing Hotkeys

**Via API**:
```bash
curl -X POST http://localhost:5555/api/v1/capture/start \
  -H "Content-Type: application/json" \
  -d '{
    "game_id": "game-123",
    "game_name": "Dark Souls",
    "process_id": 12345,
    "settings": {
      "screenshot_hotkey": "f12",
      "video_hotkey": "ctrl+f12",
      "instant_replay_hotkey": "alt+f12"
    }
  }'
```

**Via Configuration File** (`.env`):
```bash
CAPTURE_SCREENSHOT_HOTKEY=f12
CAPTURE_VIDEO_HOTKEY=ctrl+f12
CAPTURE_REPLAY_HOTKEY=alt+f12
```

**Via CLI**:
```bash
python -m playnite_python capture start \
    --game-id game-123 \
    --game-name "Dark Souls" \
    --screenshot-key f12 \
    --video-key "ctrl+f12" \
    --replay-key "alt+f12"
```

### Valid Hotkey Formats

**Single Keys**:
- Function keys: `f1` through `f12`
- Letters: `a` through `z`
- Numbers: `0` through `9`
- Special: `space`, `enter`, `esc`, `tab`

**Modifier Keys**:
- `ctrl+key` - Control + key
- `alt+key` - Alt + key
- `shift+key` - Shift + key
- `ctrl+alt+key` - Multiple modifiers
- `ctrl+shift+key` - Multiple modifiers

**Examples**:
```
Valid:
- f8
- f12
- ctrl+f8
- alt+s
- ctrl+shift+f12

Invalid:
- F8 (use lowercase)
- Ctrl+F8 (use lowercase)
- ctrl + f8 (no spaces)
```

### Hotkey Conflicts

**Check for Conflicts**:
```bash
# List all active hotkeys
python -m playnite_python capture hotkeys

# Output:
# Session: sess-game-123
#   Screenshot: F8
#   Video: F9
#   Replay: F10
```

**Resolve Conflicts**:
1. Use different function keys (F11, F12)
2. Add modifiers (Ctrl+F8, Alt+F8)
3. Check for OS-level hotkeys
4. Disable conflicting application hotkeys

**Common Conflicts**:
- F8: Often used by Windows Narrator
- F9: Sometimes used by game overlay (Steam, Discord)
- F10: Menu key in some applications

---

## Advanced Configuration

### Capture Directory

**Default Location**:
```
Windows: C:\Users\<username>\Playnite\Captures
macOS: /Users/<username>/Playnite/Captures
Linux: /home/<username>/Playnite/Captures
```

**Change Location**:
```bash
# In .env file
CAPTURE_BASE_PATH=/path/to/captures

# Or via API
curl -X POST http://localhost:5555/api/v1/capture/configure \
  -d '{"base_path": "/path/to/captures"}'
```

**Directory Structure**:
```
Captures/
├── {game-id-1}/
│   ├── screenshots/
│   │   ├── screenshot_20260210_143022_001.png
│   │   └── screenshot_20260210_143045_002.png
│   ├── videos/
│   │   └── video_20260210_143000.mp4
│   └── replays/
│       └── replay_20260210_150000.mp4
├── {game-id-2}/
│   └── screenshots/
│       └── screenshot_20260210_150000_001.png
```

### Video Quality Settings

**Presets**:
```python
VIDEO_QUALITY = {
    "low": {
        "resolution": "720p",
        "fps": 30,
        "bitrate": "2M",
        "cpu_usage": "low"
    },
    "medium": {
        "resolution": "1080p",
        "fps": 30,
        "bitrate": "4M",
        "cpu_usage": "medium"
    },
    "high": {
        "resolution": "1080p",
        "fps": 60,
        "bitrate": "8M",
        "cpu_usage": "high"
    },
    "ultra": {
        "resolution": "1440p",
        "fps": 60,
        "bitrate": "16M",
        "cpu_usage": "very_high"
    }
}
```

**Custom Settings**:
```bash
curl -X POST http://localhost:5555/api/v1/capture/start \
  -d '{
    "settings": {
      "video_quality": "custom",
      "video_resolution": "1920x1080",
      "video_fps": 60,
      "video_bitrate": 10000,
      "video_codec": "h264",
      "hardware_encoder": "nvenc"
    }
  }'
```

### Instant Replay Configuration

**Buffer Settings**:
```bash
# In .env
INSTANT_REPLAY_ENABLED=true
INSTANT_REPLAY_DURATION=30  # seconds
INSTANT_REPLAY_QUALITY=medium
INSTANT_REPLAY_FPS=30
```

**Memory Usage**:
- 30 seconds @ 1080p30: ~300MB RAM
- 60 seconds @ 1080p60: ~1.2GB RAM
- 120 seconds @ 1080p60: ~2.4GB RAM

**Adjust for Performance**:
```python
# Lower quality for less memory
{
    "instant_replay_duration": 30,
    "instant_replay_quality": "medium",  # lower than video quality
    "instant_replay_fps": 30  # lower FPS
}
```

### Achievement Detection

**Enable Achievement Capture**:
```bash
curl -X POST http://localhost:5555/api/v1/capture/start \
  -d '{
    "settings": {
      "achievement_detection_enabled": true,
      "achievement_check_interval": 0.5,
      "achievement_cooldown": 5.0
    }
  }'
```

**How It Works**:
- Checks screen for achievement popups every 0.5 seconds
- Automatically captures screenshot when detected
- Waits 5 seconds before next detection (cooldown)

**Supported Platforms**:
- Steam achievements
- Xbox achievements
- PlayStation trophies
- Epic Games achievements

---

## Testing

### Test Screenshot Capture

```bash
# Start test session
python -m playnite_python capture start \
    --game-id test \
    --game-name "Test" \
    --backend direct

# API test
curl -X POST http://localhost:5555/api/v1/capture/screenshot/sess-test-*

# Check output
ls ~/Playnite/Captures/test/screenshots/
```

### Test Video Recording

```bash
# Start recording
curl -X POST http://localhost:5555/api/v1/capture/video/start/sess-test-*

# Wait 10 seconds

# Stop recording
curl -X POST http://localhost:5555/api/v1/capture/video/stop/sess-test-*

# Check output
ls ~/Playnite/Captures/test/videos/
```

### Test Instant Replay

```bash
# Make sure instant replay is enabled
curl -X POST http://localhost:5555/api/v1/capture/start \
  -d '{
    "game_id": "test",
    "game_name": "Test",
    "process_id": 1234,
    "settings": {
      "instant_replay_enabled": true,
      "instant_replay_duration": 30
    }
  }'

# Wait 30+ seconds for buffer to fill

# Save replay
curl -X POST http://localhost:5555/api/v1/capture/replay/save/sess-test-*

# Check output
ls ~/Playnite/Captures/test/replays/
```

### Verify Metadata

```bash
# Get metadata for recent capture
curl http://localhost:5555/api/v1/capture/metadata/1

# Should show:
# - game_name
# - timestamp
# - file_size
# - resolution (for images)
# - duration (for videos)
```

---

## Troubleshooting

### Hotkeys Not Working

**Problem**: Pressing hotkey does nothing

**Checklist**:
1. ✓ Capture session active
   ```bash
   curl http://localhost:5555/api/v1/capture/sessions
   ```
2. ✓ Hotkey listener running (check logs)
3. ✓ No keyboard permission issues
4. ✓ No conflicting hotkeys

**Solutions**:
```bash
# Run with elevated permissions
sudo python -m playnite_python serve  # Linux/Mac
# Run as Administrator on Windows

# Try different hotkey
python -m playnite_python capture start \
    --screenshot-key f12

# Check logs
tail -f logs/playnite.log | grep hotkey
```

### Screenshots Are Black

**Problem**: Captured screenshots are entirely black

**Causes**:
1. Game using exclusive fullscreen
2. DRM/anti-cheat blocking capture
3. Multi-monitor setup issues

**Solutions**:
1. **Change game to borderless windowed**:
   - In game settings: Fullscreen → Borderless Window

2. **Try OBS backend**:
   ```bash
   python -m playnite_python capture start \
       --backend obs
   ```

3. **Specify correct monitor**:
   ```bash
   # In .env
   CAPTURE_MONITOR=2  # Use second monitor
   ```

### Video Recording Lags Game

**Problem**: Game stutters during recording

**Causes**:
1. High CPU usage
2. Insufficient RAM
3. Slow disk writes

**Solutions**:

1. **Lower quality**:
   ```bash
   --video-quality medium
   ```

2. **Enable hardware encoding**:
   ```bash
   --hardware-encoder nvenc  # NVIDIA
   --hardware-encoder qsv     # Intel
   --hardware-encoder amf     # AMD
   ```

3. **Use OBS backend** (more efficient):
   ```bash
   --backend obs
   ```

4. **Write to SSD** (not HDD):
   ```bash
   CAPTURE_BASE_PATH=/path/to/ssd/captures
   ```

### Instant Replay Not Saving

**Problem**: Replay hotkey pressed but no file saved

**Checklist**:
1. ✓ Instant replay enabled
2. ✓ Buffer filled (wait 30+ seconds)
3. ✓ Disk space available
4. ✓ Write permissions

**Debug**:
```bash
# Check replay buffer status
curl http://localhost:5555/api/v1/capture/replay/info/sess-*

# Should show:
# {
#   "enabled": true,
#   "buffer_duration": 30,
#   "buffer_filled": true,
#   "buffer_size_mb": 300
# }
```

### FFmpeg Not Found

**Error**: `FFmpeg not found in PATH`

**Solution**:
```bash
# Check if installed
which ffmpeg  # Linux/Mac
where ffmpeg  # Windows

# If not found, install:
# Ubuntu: sudo apt-get install ffmpeg
# macOS: brew install ffmpeg
# Windows: Download and add to PATH
```

### High Disk Usage

**Problem**: Captures using too much disk space

**Solutions**:

1. **Check usage**:
   ```bash
   curl http://localhost:5555/api/v1/storage/usage
   ```

2. **Lower quality**:
   ```bash
   # In .env
   CAPTURE_VIDEO_QUALITY=medium
   ```

3. **Enable auto-cleanup**:
   ```bash
   # In .env
   CAPTURE_AUTO_CLEANUP_ENABLED=true
   CAPTURE_RETENTION_DAYS=30
   ```

4. **Manual cleanup**:
   ```bash
   # Delete old captures
   python -m playnite_python capture cleanup \
       --older-than 30d
   ```

---

## Performance Tuning

### Optimize for Low-End Systems

```bash
# .env configuration
CAPTURE_VIDEO_QUALITY=low
CAPTURE_VIDEO_FPS=30
CAPTURE_VIDEO_RESOLUTION=720p
INSTANT_REPLAY_ENABLED=false
ACHIEVEMENT_DETECTION_ENABLED=false
```

### Optimize for High-End Systems

```bash
# .env configuration
CAPTURE_VIDEO_QUALITY=ultra
CAPTURE_VIDEO_FPS=60
CAPTURE_VIDEO_RESOLUTION=1440p
CAPTURE_HARDWARE_ENCODER=nvenc
INSTANT_REPLAY_ENABLED=true
INSTANT_REPLAY_DURATION=60
ACHIEVEMENT_DETECTION_ENABLED=true
```

### Benchmarking

Test capture performance:

```bash
# Run benchmark
python -m playnite_python capture benchmark

# Output:
# Screenshot capture: 45ms avg
# Video encoding: 8000 kbps sustained
# CPU usage: 15% during recording
# Memory usage: 450MB with replay buffer
# Disk write speed: 120 MB/s
```

---

## See Also

- [Video Editing Guide](VIDEO_EDITING.md) - Edit captured videos
- [Metadata Tagging](../METADATA_TAGGING_IMPLEMENTATION.md) - Organize captures
- [API Documentation](API.md) - Complete API reference
- [Troubleshooting](TROUBLESHOOTING.md) - General troubleshooting
