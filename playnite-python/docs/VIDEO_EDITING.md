# Video Editing and Processing

The Playnite Python capture system includes comprehensive video editing and processing tools for post-processing captured gameplay footage. These tools allow you to trim clips, merge videos, detect highlights, and create montages.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [CLI Usage](#cli-usage)
- [Highlight Detection](#highlight-detection)
- [Montage Generation](#montage-generation)
- [Advanced Features](#advanced-features)
- [Configuration](#configuration)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## Overview

### Features

**Basic Editing:**
- ✂️ Trim videos to specific time ranges
- 🔗 Concatenate multiple clips
- 🎨 Apply transitions between clips
- 📊 Extract metadata (duration, resolution, framerate)

**Intelligent Processing:**
- 🌟 Automatic highlight detection
- 🎬 Montage generation from multiple clips
- 🎯 Scene detection and analysis
- 🔊 Audio level analysis

**Output Options:**
- Multiple quality presets (low, medium, high, ultra)
- Configurable codec and format
- Hardware acceleration support (NVIDIA, AMD)
- Batch processing support

---

## Quick Start

### 1. Trim a Video

Extract a 30-second clip from a longer video:

```bash
# CLI
python -m playnite_python edit trim \
    --input gameplay.mp4 \
    --start 120 \
    --end 150 \
    --output clip.mp4

# API
curl -X POST http://localhost:5555/api/v1/editor/trim \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/captures/game-123/video_001.mp4",
    "start_seconds": 120.0,
    "end_seconds": 150.0,
    "output_path": "/captures/game-123/clip.mp4"
  }'
```

### 2. Merge Multiple Clips

Concatenate clips into a single video:

```bash
# CLI
python -m playnite_python edit concat \
    --inputs clip1.mp4 clip2.mp4 clip3.mp4 \
    --output compilation.mp4

# API
curl -X POST http://localhost:5555/api/v1/editor/concatenate \
  -H "Content-Type: application/json" \
  -d '{
    "input_files": [
      "/captures/game-123/clip1.mp4",
      "/captures/game-123/clip2.mp4",
      "/captures/game-123/clip3.mp4"
    ],
    "output_path": "/captures/game-123/compilation.mp4"
  }'
```

### 3. Detect Highlights

Find exciting moments automatically:

```bash
# CLI
python -m playnite_python edit highlights \
    --input gameplay.mp4 \
    --sensitivity high \
    --min-duration 5 \
    --max-count 10

# API
curl -X POST http://localhost:5555/api/v1/editor/detect-highlights \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "/captures/game-123/gameplay.mp4",
    "sensitivity": "high",
    "min_duration_seconds": 5,
    "max_highlights": 10
  }'
```

---

## API Reference

### POST /api/v1/editor/trim

Trim a video to a specific time range.

**Request Body:**
```json
{
  "file_path": "/path/to/video.mp4",
  "start_seconds": 120.5,
  "end_seconds": 180.2,
  "output_path": "/path/to/output.mp4",
  "quality": "high"
}
```

**Parameters:**
- `file_path` (string, required): Path to input video
- `start_seconds` (float, required): Start time in seconds
- `end_seconds` (float, required): End time in seconds
- `output_path` (string, required): Path for output video
- `quality` (string, optional): Quality preset - "low", "medium", "high", "ultra" (default: "high")

**Response:**
```json
{
  "status": "success",
  "output_file": "/path/to/output.mp4",
  "duration_seconds": 59.7,
  "file_size_bytes": 12582912,
  "processing_time_seconds": 3.45
}
```

**Status Codes:**
- `200 OK`: Video trimmed successfully
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Input file not found
- `500 Internal Server Error`: Processing failed

---

### POST /api/v1/editor/concatenate

Merge multiple video clips into one.

**Request Body:**
```json
{
  "input_files": [
    "/path/to/clip1.mp4",
    "/path/to/clip2.mp4",
    "/path/to/clip3.mp4"
  ],
  "output_path": "/path/to/merged.mp4",
  "quality": "high",
  "add_transitions": true,
  "transition_duration": 0.5
}
```

**Parameters:**
- `input_files` (array, required): List of video paths to concatenate
- `output_path` (string, required): Path for output video
- `quality` (string, optional): Quality preset (default: "high")
- `add_transitions` (boolean, optional): Add fade transitions between clips (default: false)
- `transition_duration` (float, optional): Transition duration in seconds (default: 0.5)

**Response:**
```json
{
  "status": "success",
  "output_file": "/path/to/merged.mp4",
  "total_duration_seconds": 180.5,
  "clip_count": 3,
  "file_size_bytes": 45678912,
  "processing_time_seconds": 12.3
}
```

---

### POST /api/v1/editor/detect-highlights

Automatically detect exciting moments in gameplay footage.

**Request Body:**
```json
{
  "video_path": "/path/to/gameplay.mp4",
  "sensitivity": "high",
  "min_duration_seconds": 5,
  "max_highlights": 10,
  "output_format": "clips"
}
```

**Parameters:**
- `video_path` (string, required): Path to gameplay video
- `sensitivity` (string, optional): Detection sensitivity - "low", "medium", "high" (default: "medium")
- `min_duration_seconds` (float, optional): Minimum highlight duration (default: 3.0)
- `max_highlights` (integer, optional): Maximum number of highlights to return (default: 10)
- `output_format` (string, optional): "clips" (save individual files) or "timestamps" (return time ranges) (default: "timestamps")

**Response:**
```json
{
  "status": "success",
  "highlights": [
    {
      "start_seconds": 45.2,
      "end_seconds": 52.8,
      "duration_seconds": 7.6,
      "score": 0.92,
      "reason": "High action detected",
      "output_file": "/path/to/highlight_001.mp4"
    },
    {
      "start_seconds": 123.5,
      "end_seconds": 135.1,
      "duration_seconds": 11.6,
      "score": 0.87,
      "reason": "Achievement unlocked",
      "output_file": "/path/to/highlight_002.mp4"
    }
  ],
  "total_highlights": 2,
  "processing_time_seconds": 45.2
}
```

**Detection Algorithms:**
- **Audio Spikes**: Loud sounds (explosions, achievements)
- **Motion Intensity**: Rapid camera movement or action
- **Scene Changes**: Dramatic transitions
- **Achievement Detection**: On-screen achievement popups
- **Score Changes**: HUD score increases

---

### POST /api/v1/editor/montage

Create a montage from captured clips.

**Request Body:**
```json
{
  "game_id": "game-123",
  "duration_seconds": 60,
  "style": "fast-paced",
  "music_path": "/path/to/music.mp3",
  "output_path": "/path/to/montage.mp4",
  "include_intro": true,
  "intro_text": "Best Moments"
}
```

**Parameters:**
- `game_id` (string, required): Game identifier to source clips from
- `duration_seconds` (float, optional): Target montage duration (default: 60)
- `style` (string, optional): Montage style - "fast-paced", "cinematic", "highlights" (default: "highlights")
- `music_path` (string, optional): Background music file path
- `output_path` (string, required): Path for output montage
- `include_intro` (boolean, optional): Add intro title screen (default: false)
- `intro_text` (string, optional): Text for intro screen

**Response:**
```json
{
  "status": "success",
  "output_file": "/path/to/montage.mp4",
  "clips_used": 8,
  "total_duration_seconds": 62.3,
  "style": "fast-paced",
  "file_size_bytes": 25678912,
  "processing_time_seconds": 34.5
}
```

---

### GET /api/v1/editor/info

Get metadata about a video file.

**Query Parameters:**
- `file_path` (string, required): Path to video file

**Response:**
```json
{
  "file_path": "/path/to/video.mp4",
  "duration_seconds": 125.8,
  "resolution": {
    "width": 1920,
    "height": 1080
  },
  "framerate": 60.0,
  "codec": "h264",
  "bitrate_kbps": 5000,
  "file_size_bytes": 78643200,
  "file_size_mb": 75.0,
  "format": "mp4",
  "has_audio": true,
  "audio_codec": "aac"
}
```

---

## CLI Usage

### Installation

The video editing tools are included with the main installation:

```bash
pip install -e .
```

### Available Commands

View all editing commands:

```bash
python -m playnite_python edit --help
```

### Trim Video

```bash
python -m playnite_python edit trim \
    --input gameplay.mp4 \
    --start 120 \
    --end 180 \
    --output clip.mp4 \
    --quality high
```

**Options:**
- `--input` / `-i`: Input video file (required)
- `--start` / `-s`: Start time in seconds (required)
- `--end` / `-e`: End time in seconds (required)
- `--output` / `-o`: Output video file (required)
- `--quality` / `-q`: Quality preset: low, medium, high, ultra (default: high)

### Concatenate Videos

```bash
python -m playnite_python edit concat \
    --inputs clip1.mp4 clip2.mp4 clip3.mp4 \
    --output merged.mp4 \
    --transitions \
    --transition-duration 0.5
```

**Options:**
- `--inputs` / `-i`: Input video files (required, multiple)
- `--output` / `-o`: Output video file (required)
- `--quality` / `-q`: Quality preset (default: high)
- `--transitions` / `-t`: Add fade transitions (flag)
- `--transition-duration`: Transition length in seconds (default: 0.5)

### Detect Highlights

```bash
python -m playnite_python edit highlights \
    --input gameplay.mp4 \
    --sensitivity high \
    --min-duration 5 \
    --max-count 10 \
    --output-clips
```

**Options:**
- `--input` / `-i`: Input video file (required)
- `--sensitivity` / `-s`: Detection sensitivity: low, medium, high (default: medium)
- `--min-duration`: Minimum highlight duration in seconds (default: 3)
- `--max-count`: Maximum number of highlights (default: 10)
- `--output-clips`: Save individual clip files (flag)
- `--output-dir`: Directory for output clips (default: same as input)

### Create Montage

```bash
python -m playnite_python edit montage \
    --game-id game-123 \
    --duration 60 \
    --style fast-paced \
    --music background.mp3 \
    --output montage.mp4 \
    --intro "Best Moments"
```

**Options:**
- `--game-id` / `-g`: Game identifier (required)
- `--duration` / `-d`: Target duration in seconds (default: 60)
- `--style` / `-s`: Montage style: fast-paced, cinematic, highlights (default: highlights)
- `--music` / `-m`: Background music file
- `--output` / `-o`: Output video file (required)
- `--intro`: Intro text for title screen
- `--quality` / `-q`: Quality preset (default: high)

### Get Video Info

```bash
python -m playnite_python edit info gameplay.mp4
```

Output:
```
File: gameplay.mp4
Duration: 125.8 seconds (2m 5.8s)
Resolution: 1920x1080
Framerate: 60.0 fps
Codec: h264
Bitrate: 5000 kbps
File Size: 75.0 MB
Audio: aac
```

---

## Highlight Detection

### How It Works

The highlight detection system analyzes multiple signals to identify exciting moments:

**1. Audio Analysis**
- Detects volume spikes (explosions, gunfire)
- Identifies achievement sound effects
- Analyzes music intensity

**2. Visual Analysis**
- Tracks motion intensity (action sequences)
- Detects scene changes (cuts, transitions)
- Identifies HUD changes (score increases)

**3. Achievement Detection**
- Recognizes achievement popup patterns
- Detects Xbox/PlayStation/Steam achievement UI
- Custom achievement templates supported

**4. Scoring System**
Each moment gets a score (0-1) based on:
- Audio spike magnitude
- Motion intensity
- Scene change significance
- Achievement presence

### Sensitivity Levels

**Low Sensitivity**:
- Only major events (boss kills, achievements)
- Minimum score: 0.7
- Conservative, fewer false positives

**Medium Sensitivity** (Default):
- Notable moments (kills, objectives)
- Minimum score: 0.5
- Balanced detection

**High Sensitivity**:
- All interesting moments
- Minimum score: 0.3
- More highlights, may include minor events

### Custom Detection

Configure custom detection rules:

```python
from playnite_python.capture.processors.highlight_detector import HighlightDetector

detector = HighlightDetector()

# Add custom rule
detector.add_rule(
    name="boss_kill",
    audio_threshold=0.8,  # Loud sound
    motion_threshold=0.6,  # High action
    duration_range=(5, 15),  # 5-15 second clips
    priority=1.0  # High priority
)

# Detect with custom rules
highlights = detector.detect(video_path="gameplay.mp4")
```

---

## Montage Generation

### Styles

**Fast-Paced**:
- Short clips (2-5 seconds each)
- Rapid cuts and transitions
- High-energy moments only
- Sync to music beats (if provided)
- Best for: Action games, competitive gameplay

**Cinematic**:
- Longer clips (5-10 seconds each)
- Smooth transitions (fades, dissolves)
- Mix of action and scenic moments
- Slower pacing
- Best for: Story-driven games, exploration

**Highlights**:
- Medium clips (3-7 seconds each)
- Balanced pacing
- Focus on achievements and big moments
- Simple transitions
- Best for: General gameplay, mixed content

### Music Synchronization

When music is provided, the montage syncs to beats:

```bash
python -m playnite_python edit montage \
    --game-id game-123 \
    --music epic-music.mp3 \
    --style fast-paced \
    --sync-to-beats
```

**Beat Detection**:
- Analyzes music tempo and beats
- Places cuts on strong beats
- Adjusts clip duration to match rhythm
- Creates more dynamic montages

### Example Workflow

Create a 60-second highlight reel:

```bash
# Step 1: Detect highlights from all gameplay videos
python -m playnite_python edit highlights \
    --input ~/Playnite/Captures/dark-souls/videos/*.mp4 \
    --sensitivity high \
    --min-duration 3 \
    --output-clips \
    --output-dir highlights/

# Step 2: Create montage from highlights
python -m playnite_python edit montage \
    --game-id dark-souls \
    --duration 60 \
    --style fast-paced \
    --music epic-soundtrack.mp3 \
    --intro "Dark Souls - Best Moments" \
    --output dark-souls-montage.mp4
```

---

## Advanced Features

### Batch Processing

Process multiple videos at once:

```bash
# Trim multiple videos
python -m playnite_python edit batch-trim \
    --inputs *.mp4 \
    --start 0 \
    --end 30 \
    --output-dir trimmed/ \
    --quality high
```

### Hardware Acceleration

Enable GPU acceleration for faster processing:

```bash
# NVIDIA GPU
python -m playnite_python edit trim \
    --input gameplay.mp4 \
    --start 0 \
    --end 60 \
    --output clip.mp4 \
    --hwaccel nvidia

# AMD GPU
python -m playnite_python edit trim \
    --input gameplay.mp4 \
    --start 0 \
    --end 60 \
    --output clip.mp4 \
    --hwaccel amd
```

### Custom Transitions

Add custom transitions between clips:

```python
# Via API
{
  "input_files": ["clip1.mp4", "clip2.mp4"],
  "output_path": "merged.mp4",
  "transitions": [
    {"type": "fade", "duration": 0.5},
    {"type": "wipe", "duration": 0.3, "direction": "left"}
  ]
}
```

Available transitions:
- `fade`: Crossfade
- `wipe`: Directional wipe (left, right, up, down)
- `dissolve`: Dissolve
- `slide`: Slide (left, right, up, down)

---

## Configuration

### Video Quality Presets

Configured in `config.py`:

```python
VIDEO_QUALITY_PRESETS = {
    "low": {
        "crf": 28,
        "preset": "fast",
        "resolution": None,  # Keep original
        "bitrate": "2M"
    },
    "medium": {
        "crf": 23,
        "preset": "medium",
        "resolution": None,
        "bitrate": "4M"
    },
    "high": {
        "crf": 18,
        "preset": "slow",
        "resolution": None,
        "bitrate": "8M"
    },
    "ultra": {
        "crf": 15,
        "preset": "slower",
        "resolution": None,
        "bitrate": "16M"
    }
}
```

### Highlight Detection Settings

```python
HIGHLIGHT_DETECTION = {
    "audio_threshold": 0.6,  # Volume spike threshold
    "motion_threshold": 0.5,  # Motion intensity threshold
    "min_duration": 3.0,  # Minimum highlight duration
    "max_duration": 15.0,  # Maximum highlight duration
    "merge_gap": 2.0,  # Merge highlights within 2 seconds
    "achievement_templates": [
        "templates/xbox_achievement.png",
        "templates/steam_achievement.png"
    ]
}
```

---

## Examples

### Example 1: Create Highlight Reel

Extract top 5 moments from a long gameplay session:

```bash
# Detect highlights
python -m playnite_python edit highlights \
    --input 2hr-gameplay.mp4 \
    --sensitivity high \
    --max-count 5 \
    --output-clips

# Result: highlight_001.mp4 through highlight_005.mp4
```

### Example 2: Merge Best Moments

Combine highlights into compilation:

```bash
python -m playnite_python edit concat \
    --inputs highlight_*.mp4 \
    --output compilation.mp4 \
    --transitions \
    --quality ultra
```

### Example 3: Auto-Generated Montage

Create 60-second montage with music:

```bash
python -m playnite_python edit montage \
    --game-id elden-ring \
    --duration 60 \
    --style fast-paced \
    --music soundtrack.mp3 \
    --intro "Elden Ring - Epic Moments" \
    --output elden-ring-montage.mp4
```

### Example 4: Python Script

Complete workflow in Python:

```python
import httpx

base_url = "http://localhost:5555/api/v1/editor"

# Step 1: Detect highlights
response = httpx.post(
    f"{base_url}/detect-highlights",
    json={
        "video_path": "/captures/gameplay.mp4",
        "sensitivity": "high",
        "max_highlights": 10,
        "output_format": "clips"
    }
)
highlights = response.json()["highlights"]

# Step 2: Concatenate top 5 highlights
clip_paths = [h["output_file"] for h in highlights[:5]]
response = httpx.post(
    f"{base_url}/concatenate",
    json={
        "input_files": clip_paths,
        "output_path": "/captures/best-moments.mp4",
        "add_transitions": True
    }
)

print(f"Compilation created: {response.json()['output_file']}")
```

---

## Troubleshooting

### FFmpeg Not Found

**Error**: `FFmpeg not found in PATH`

**Solution**:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
# Add to PATH
```

### Processing Too Slow

**Problem**: Video editing takes too long

**Solutions**:
1. Use lower quality preset: `--quality medium`
2. Enable hardware acceleration: `--hwaccel nvidia`
3. Reduce resolution: `--scale 720p`
4. Use faster preset in config

### Highlight Detection Not Working

**Problem**: No highlights detected

**Possible Causes**:
1. Sensitivity too low → Try `--sensitivity high`
2. Video too short → Need at least 30 seconds
3. Low action gameplay → Adjust thresholds
4. Audio missing → Check video has audio track

### Concatenation Fails

**Error**: `Unable to concatenate videos`

**Common Issues**:
1. Different resolutions → Use `--scale` to normalize
2. Different framerates → Use `--normalize-fps`
3. Different codecs → Re-encode with same preset
4. Corrupted video → Check with `edit info`

### Out of Memory

**Error**: `MemoryError during processing`

**Solutions**:
1. Process in smaller batches
2. Reduce quality preset
3. Close other applications
4. Increase system swap space

---

## Performance Tips

1. **Use Hardware Acceleration** - 5-10x faster with GPU
2. **Lower Quality for Previews** - Use `low` preset for testing
3. **Batch Processing** - Process multiple files together
4. **Disable Transitions** - Skip transitions for speed
5. **Cache Detection Results** - Save highlight timestamps

---

## See Also

- [Capture System Setup](CAPTURE_SETUP.md) - Configure video capture
- [API Documentation](API.md) - Complete API reference
- [Metadata Tagging](../METADATA_TAGGING_IMPLEMENTATION.md) - Organize captures
- [Storage Management](../README.md#storage-management) - Manage disk space
