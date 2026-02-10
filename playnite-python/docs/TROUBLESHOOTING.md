# Comprehensive Troubleshooting Guide

Complete guide to diagnosing and fixing common issues with Playnite Python integration.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Installation Issues](#installation-issues)
- [Service Issues](#service-issues)
- [Recommendation Issues](#recommendation-issues)
- [Capture Issues](#capture-issues)
- [API Issues](#api-issues)
- [Database Issues](#database-issues)
- [Performance Issues](#performance-issues)
- [Integration Issues](#integration-issues)
- [Getting Help](#getting-help)

---

## Quick Diagnostics

Run these commands first to identify common problems:

```bash
# Check service status
curl http://localhost:5555/api/v1/health

# Check Python version
python --version  # Should be 3.8+

# Check dependencies
pip list | grep -E "fastapi|scikit-learn|opencv"

# Check FFmpeg
ffmpeg -version
ffprobe -version

# Check logs
tail -50 logs/playnite.log

# Check disk space
df -h  # Linux/Mac
dir  # Windows

# Check database
sqlite3 playnite_captures.db "PRAGMA integrity_check;"
```

---

## Installation Issues

### Error: "Python not found" or "python: command not found"

**Symptoms**:
```bash
$ python --version
bash: python: command not found
```

**Cause**: Python not installed or not in PATH

**Solutions**:

**Check if Python is installed**:
```bash
# Try different commands
python3 --version
py --version  # Windows
which python  # Linux/Mac
where python  # Windows
```

**Install Python 3.8+**:

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv
```

**macOS**:
```bash
# Install Homebrew first (if needed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.11
```

**Windows**:
1. Download from https://www.python.org/downloads/
2. Run installer
3. ✓ Check "Add Python to PATH"
4. Restart terminal

**Add to PATH**:

**Linux/Mac** (add to `~/.bashrc` or `~/.zshrc`):
```bash
export PATH="/usr/local/bin/python3:$PATH"
```

**Windows**:
```
Control Panel → System → Advanced → Environment Variables
Add Python install directory to PATH
```

---

### Error: "pip install" fails with compilation errors

**Symptoms**:
```
error: command 'gcc' failed with exit status 1
error: Microsoft Visual C++ 14.0 is required
```

**Cause**: Missing compiler or system libraries

**Solutions**:

**Ubuntu/Debian**:
```bash
sudo apt-get install build-essential python3-dev
```

**macOS**:
```bash
xcode-select --install
```

**Windows**:
1. Install Visual Studio Build Tools
2. Download from https://visualstudio.microsoft.com/downloads/
3. Select "Desktop development with C++"
4. Restart and retry `pip install`

---

### Error: "No module named 'sklearn'" or similar

**Symptoms**:
```python
ModuleNotFoundError: No module named 'sklearn'
```

**Cause**: Dependencies not installed or wrong Python environment

**Solutions**:

**1. Verify virtual environment active**:
```bash
# Should show (venv) prefix
which python  # Should point to venv/bin/python
```

**2. Activate virtual environment**:
```bash
# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Install dependencies**:
```bash
pip install -e .
# OR
pip install -r requirements.txt
```

**4. Verify installation**:
```bash
pip list | grep scikit-learn
```

---

### Error: "Permission denied" during installation

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied: '/usr/local/lib/python3.9/site-packages'
```

**Cause**: Installing to system Python without permissions

**Solutions**:

**1. Use virtual environment (RECOMMENDED)**:
```bash
python -m venv venv
source venv/bin/activate
pip install -e .
```

**2. Use --user flag**:
```bash
pip install --user -e .
```

**3. Use sudo (NOT RECOMMENDED)**:
```bash
sudo pip install -e .
```

---

## Service Issues

### Error: "Address already in use" or "Port 5555 already in use"

**Symptoms**:
```
OSError: [Errno 48] Address already in use
ERROR: Could not bind to port 5555
```

**Cause**: Another process using port 5555

**Solutions**:

**1. Find process using port**:

**Linux/Mac**:
```bash
lsof -i :5555
# Output shows PID and process name
```

**Windows**:
```cmd
netstat -ano | findstr :5555
# Note the PID in last column
```

**2. Kill the process**:

**Linux/Mac**:
```bash
kill -9 <PID>
```

**Windows**:
```cmd
taskkill /PID <PID> /F
```

**3. Use different port**:
```bash
python -m playnite_python serve --port 5556
```

**4. Configure in .env**:
```bash
PORT=5556
```

---

### Service crashes immediately on startup

**Symptoms**:
```
Service started...
[Crash with stack trace]
```

**Diagnosis**:

**1. Check logs**:
```bash
cat logs/playnite.log
```

**2. Run in debug mode**:
```bash
export LOG_LEVEL=DEBUG
python -m playnite_python serve
```

**Common Causes**:

**Database corrupted**:
```bash
# Backup and recreate
mv playnite_captures.db playnite_captures.db.bak
python -m playnite_python serve
```

**Missing configuration**:
```bash
# Create .env from example
cp .env.example .env
# Edit .env with your settings
```

**Disk full**:
```bash
df -h  # Check disk space
# Clean up logs and old captures
```

---

### Service runs but API returns 500 errors

**Symptoms**:
```bash
$ curl http://localhost:5555/api/v1/health
{"detail":"Internal Server Error"}
```

**Diagnosis**:

**1. Check service logs**:
```bash
tail -f logs/playnite.log
```

**2. Test database connection**:
```bash
python -c "from src.playnite_python.database.connection import get_session; get_session()"
```

**3. Verify database initialized**:
```bash
ls -lh playnite_captures.db
sqlite3 playnite_captures.db ".tables"
```

**Solutions**:

**Initialize database**:
```bash
python -c "from src.playnite_python.database.models import Base; from sqlalchemy import create_engine; engine = create_engine('sqlite:///playnite_captures.db'); Base.metadata.create_all(engine)"
```

**Check permissions**:
```bash
ls -l playnite_captures.db
# Should be writable by current user
chmod 644 playnite_captures.db
```

---

## Recommendation Issues

### No recommendations returned

**Symptoms**:
```json
{
  "recommendations": [],
  "count": 0
}
```

**Common Causes**:

**1. All games already played**:
- Recommendations only suggest unplayed games
- Check playtime_seconds in library data

**Solution**:
```bash
# Mark game as unplayed for testing
# Set playtime_seconds to 0 in library JSON
```

**2. Library too small**:
- Need at least 5-10 games
- Need variety in genres/types

**Solution**:
```bash
# Add more games to library
# Or reduce minimum similarity threshold
```

**3. Filters too restrictive**:
- Check if explicit filters excluding all games
- Check if context filters too narrow

**Solution**:
```bash
# Remove filters temporarily
curl -X POST http://localhost:5555/api/v1/recommendations/generate \
  -d '{"user_id": "test", "library": [...], "filters": {}, "limit": 10}'
```

---

### Recommendations not relevant

**Symptoms**: Suggested games don't match user preferences

**Diagnosis**:

**1. Check algorithm weights**:
```bash
curl http://localhost:5555/api/v1/feedback/weights
```

**2. Check accuracy metrics**:
```bash
curl http://localhost:5555/api/v1/feedback/accuracy?time_window_days=30
```

**Solutions**:

**1. Submit feedback on recommendations**:
```bash
# Like good recommendations
curl -X POST http://localhost:5555/api/v1/feedback/submit \
  -d '{"recommendation_id": 123, "game_id": "game-xyz", "feedback_type": "liked"}'

# Dismiss bad recommendations
curl -X POST http://localhost:5555/api/v1/feedback/submit \
  -d '{"recommendation_id": 456, "game_id": "game-abc", "feedback_type": "dismissed"}'
```

**2. Auto-tune weights**:
```bash
curl -X POST http://localhost:5555/api/v1/feedback/tune-weights?time_window_days=30
```

**3. Reset to defaults**:
```bash
curl -X POST http://localhost:5555/api/v1/feedback/reset-weights
```

**4. Check library data quality**:
- Verify genres are accurate
- Check tags and features
- Ensure playtime data is correct

---

### Error: "KeyError" or "AttributeError" in recommendations

**Symptoms**:
```
KeyError: 'genres'
AttributeError: 'NoneType' object has no attribute 'get'
```

**Cause**: Missing required fields in library data

**Required Fields**:
- `game_id` (string)
- `name` (string)
- `genres` (array, can be empty)
- `playtime_seconds` (integer)

**Solution**:

**Validate library data**:
```python
# Check library structure
import json

with open('library.json') as f:
    library = json.load(f)

for game in library:
    assert 'game_id' in game
    assert 'name' in game
    assert 'genres' in game
    assert isinstance(game['genres'], list)
    assert 'playtime_seconds' in game
```

**Add missing fields**:
```python
# Fix library data
for game in library:
    game.setdefault('genres', [])
    game.setdefault('playtime_seconds', 0)
    game.setdefault('features', [])
```

---

## Capture Issues

### Hotkeys not responding

**Symptoms**: Pressing F8/F9 does nothing

**Diagnosis**:

**1. Check session active**:
```bash
curl http://localhost:5555/api/v1/capture/sessions
# Should show active session
```

**2. Check logs for hotkey events**:
```bash
tail -f logs/playnite.log | grep -i hotkey
```

**3. Test hotkey listener**:
```python
from pynput import keyboard

def on_press(key):
    print(f'Key pressed: {key}')

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
# Press keys to verify detection
```

**Common Causes**:

**1. Permission issues**:
```bash
# Linux: Need input group membership
sudo usermod -a -G input $USER
# Logout and login

# macOS: Need accessibility permissions
System Preferences → Security & Privacy → Accessibility
# Add Terminal or Python
```

**2. Conflicting hotkeys**:
- Check OS hotkeys (Windows key combos, Mac system shortcuts)
- Check other running applications (Steam overlay, Discord)

**Solution**:
```bash
# Use different hotkeys
python -m playnite_python capture start \
    --screenshot-key f12 \
    --video-key ctrl+f12
```

**3. Session not started**:
```bash
# Verify session exists
curl http://localhost:5555/api/v1/capture/sessions

# If empty, start session
curl -X POST http://localhost:5555/api/v1/capture/start \
  -d '{"game_id": "test", "game_name": "Test", "process_id": 12345}'
```

---

### Screenshots are completely black

**Symptoms**: Captured images are solid black

**Causes**:
1. Game using exclusive fullscreen
2. DRM/anti-cheat blocking screen capture
3. Wrong monitor selected
4. Graphics API incompatibility

**Solutions**:

**1. Change game to borderless windowed**:
```
In-game settings:
Fullscreen → Borderless Window
OR
Windowed Fullscreen
```

**2. Try OBS backend**:
```bash
python -m playnite_python capture start \
    --backend obs \
    --game-id game-123
```

**3. Specify correct monitor**:
```bash
# .env configuration
CAPTURE_MONITOR=1  # Try 0, 1, 2...
```

**4. Use Game Capture (OBS)**:
- Create OBS scene with "Game Capture" source
- Captures game directly, bypasses restrictions

**5. Check for DRM**:
- Some games (Denuvo, etc.) block capture
- Try windowed mode or OBS workarounds

---

### Video recording causes game lag

**Symptoms**: Game stutters or drops FPS during recording

**Diagnosis**:

**1. Check CPU usage**:
```bash
# While recording
top  # Linux/Mac
taskmgr  # Windows
```

**2. Check disk write speed**:
```bash
# Test write speed
dd if=/dev/zero of=testfile bs=1M count=1024  # Linux/Mac
# Should be >50 MB/s for smooth recording
```

**Solutions**:

**1. Lower video quality**:
```bash
# In settings
"video_quality": "medium"  # instead of "high"
"video_fps": 30            # instead of 60
"video_resolution": "720p"  # instead of "1080p"
```

**2. Enable hardware encoding**:
```bash
# NVIDIA
"hardware_encoder": "nvenc"

# Intel
"hardware_encoder": "qsv"

# AMD
"hardware_encoder": "amf"
```

**Verify hardware encoder available**:
```bash
ffmpeg -encoders | grep nvenc  # NVIDIA
ffmpeg -encoders | grep qsv    # Intel
ffmpeg -encoders | grep amf    # AMD
```

**3. Write to SSD instead of HDD**:
```bash
CAPTURE_BASE_PATH=/path/to/ssd/captures
```

**4. Use OBS backend** (more efficient):
```bash
python -m playnite_python capture start --backend obs
```

**5. Close other applications**:
- Close browsers, Discord, etc.
- Disable unnecessary background processes

---

### Instant replay not saving

**Symptoms**: Press F10 but no replay file created

**Diagnosis**:

**1. Check if instant replay enabled**:
```bash
curl http://localhost:5555/api/v1/capture/sessions
# Check "instant_replay_enabled": true
```

**2. Check buffer status**:
```bash
curl http://localhost:5555/api/v1/capture/replay/info/sess-*
```

**3. Check logs**:
```bash
tail -f logs/playnite.log | grep -i replay
```

**Common Causes**:

**1. Instant replay not enabled**:
```bash
# Enable in session start
curl -X POST http://localhost:5555/api/v1/capture/start \
  -d '{
    "game_id": "test",
    "game_name": "Test",
    "process_id": 12345,
    "settings": {
      "instant_replay_enabled": true,
      "instant_replay_duration": 30
    }
  }'
```

**2. Buffer not filled yet**:
- Wait for buffer duration (e.g., 30 seconds)
- Check buffer_filled status

**3. Out of memory**:
- Replay buffer uses significant RAM
- Check system memory: `free -h` (Linux) or Task Manager (Windows)

**Solution**:
```bash
# Reduce buffer duration
"instant_replay_duration": 15  # instead of 30 or 60
```

**4. Disk full**:
```bash
df -h  # Check disk space
```

---

### FFmpeg errors during video processing

**Symptoms**:
```
[ERROR] FFmpeg error: ...
av_interleaved_write_frame(): Broken pipe
```

**Solutions**:

**1. Check FFmpeg installed**:
```bash
ffmpeg -version
```

**2. Reinstall FFmpeg**:
```bash
# Ubuntu
sudo apt-get install --reinstall ffmpeg

# macOS
brew reinstall ffmpeg

# Windows
# Download fresh install from ffmpeg.org
```

**3. Check codec support**:
```bash
ffmpeg -codecs | grep h264
```

**4. Try different codec**:
```bash
# In settings
"video_codec": "h264"  # Try: h264, hevc, vp9
```

**5. Check disk space**:
```bash
df -h
# Need sufficient space for video file
```

---

## API Issues

### Error: "Connection refused" when calling API

**Symptoms**:
```bash
$ curl http://localhost:5555/api/v1/health
curl: (7) Failed to connect to localhost port 5555: Connection refused
```

**Diagnosis**:

**1. Check if service running**:
```bash
ps aux | grep playnite  # Linux/Mac
tasklist | findstr python  # Windows
```

**2. Check correct port**:
```bash
netstat -tuln | grep 5555  # Linux
netstat -an | findstr 5555  # Windows
```

**Solutions**:

**1. Start service**:
```bash
python -m playnite_python serve
```

**2. Verify correct URL**:
```bash
# Correct
curl http://localhost:5555/api/v1/health

# Wrong (missing /api/v1/)
curl http://localhost:5555/health
```

**3. Check firewall**:
```bash
# Linux
sudo ufw status
sudo ufw allow 5555/tcp

# Windows
# Check Windows Firewall settings
```

---

### Error: 404 Not Found for valid endpoint

**Symptoms**:
```json
{"detail":"Not Found"}
```

**Common Mistakes**:

**1. Missing API version**:
```bash
# Wrong
curl http://localhost:5555/health

# Correct
curl http://localhost:5555/api/v1/health
```

**2. Wrong HTTP method**:
```bash
# Wrong (endpoint expects POST)
curl http://localhost:5555/api/v1/recommendations/generate

# Correct
curl -X POST http://localhost:5555/api/v1/recommendations/generate \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**3. Check available endpoints**:
```bash
# View interactive docs
open http://localhost:5555/docs
```

---

### Error: 422 Validation Error

**Symptoms**:
```json
{
  "detail": [
    {
      "loc": ["body", "user_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**Cause**: Missing or invalid request parameters

**Solution**: Check request format against API documentation

```bash
# View docs for correct format
curl http://localhost:5555/docs

# Example correct request
curl -X POST http://localhost:5555/api/v1/recommendations/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "library": [...],
    "limit": 10
  }'
```

---

## Database Issues

### Error: "Database is locked"

**Symptoms**:
```
sqlite3.OperationalError: database is locked
```

**Cause**: Multiple processes accessing database simultaneously

**Solutions**:

**1. Close other instances**:
```bash
# Find processes
ps aux | grep playnite
# Kill duplicate processes
kill <PID>
```

**2. Check for zombie processes**:
```bash
ps aux | grep -E "python.*playnite" | grep -v grep
```

**3. Restart service**:
```bash
# Stop all instances
pkill -f "python.*playnite"
# Start fresh
python -m playnite_python serve
```

**4. Use connection pooling** (in code):
```python
# Configure SQLAlchemy
engine = create_engine(
    'sqlite:///playnite_captures.db',
    connect_args={'check_same_thread': False},
    pool_pre_ping=True
)
```

---

### Error: "Database disk image is malformed" or corruption

**Symptoms**:
```
sqlite3.DatabaseError: database disk image is malformed
```

**Cause**: Database corrupted (crash during write, disk issues)

**Solutions**:

**1. Check integrity**:
```bash
sqlite3 playnite_captures.db "PRAGMA integrity_check;"
```

**2. Try to recover**:
```bash
# Backup first
cp playnite_captures.db playnite_captures.db.corrupted

# Dump and recreate
sqlite3 playnite_captures.db .dump > dump.sql
sqlite3 playnite_captures_new.db < dump.sql
mv playnite_captures_new.db playnite_captures.db
```

**3. Restore from backup**:
```bash
cp playnite_captures.db.backup playnite_captures.db
```

**4. Rebuild from scratch** (LAST RESORT - loses data):
```bash
rm playnite_captures.db
python -m playnite_python serve
# Database will be recreated
```

---

## Performance Issues

### Slow recommendation generation (>5 seconds)

**Symptoms**: Recommendations take very long

**Diagnosis**:

**1. Check library size**:
```python
import json
with open('library.json') as f:
    library = json.load(f)
print(f"Library size: {len(library)} games")
# >1000 games may be slow
```

**2. Profile execution**:
```python
import time
start = time.time()
# Generate recommendations
elapsed = time.time() - start
print(f"Took {elapsed:.2f} seconds")
```

**Solutions**:

**1. Enable caching** (in .env):
```bash
ENABLE_RECOMMENDATION_CACHE=true
CACHE_TTL_SECONDS=3600
```

**2. Limit library size**:
```python
# Filter to installed games only
library_filtered = [g for g in library if g.get('is_installed')]
```

**3. Reduce limit**:
```bash
# Ask for fewer recommendations
"limit": 5  # instead of 10 or 20
```

**4. Optimize database**:
```bash
sqlite3 playnite_captures.db "VACUUM;"
sqlite3 playnite_captures.db "ANALYZE;"
```

---

### High memory usage (>1GB)

**Symptoms**: Service using excessive RAM

**Diagnosis**:
```bash
# Check memory usage
ps aux | grep playnite  # Linux/Mac
# Check Python process memory
```

**Common Causes**:

**1. Large instant replay buffer**:
```bash
# 60 seconds @ 1080p60 = ~1.2GB RAM
# Reduce duration
"instant_replay_duration": 30  # Use 30 instead of 60
```

**2. Memory leak**:
- Check if memory grows over time
- Restart service periodically

**3. Large library data cached**:
```bash
# Clear cache
curl -X POST http://localhost:5555/api/v1/cache/clear
```

**Solutions**:

**1. Reduce instant replay buffer**:
```bash
INSTANT_REPLAY_DURATION=15
INSTANT_REPLAY_QUALITY=medium
```

**2. Restart service periodically**:
```bash
# Cron job to restart daily
0 3 * * * systemctl restart playnite-python
```

**3. Monitor for leaks**:
```python
import tracemalloc
tracemalloc.start()
# Run operations
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

---

### Slow disk writes during capture

**Symptoms**: Capture lags, stutters, or fails

**Diagnosis**:

**1. Test disk speed**:
```bash
# Write test
dd if=/dev/zero of=testfile bs=1M count=1024 conv=fdatasync
# Should be >50 MB/s
```

**2. Check disk space**:
```bash
df -h
# Need sufficient free space
```

**Solutions**:

**1. Use SSD instead of HDD**:
```bash
CAPTURE_BASE_PATH=/path/to/ssd/captures
```

**2. Lower video quality**:
```bash
"video_quality": "medium"
"video_bitrate": 4000  # Lower bitrate
```

**3. Close other disk-intensive apps**:
- Stop torrents, downloads
- Close video editors
- Disable disk indexing temporarily

---

## Integration Issues

### C# Plugin can't connect to Python service

**Symptoms**: Plugin shows connection errors in Playnite logs

**Diagnosis**:

**1. Check service running**:
```bash
curl http://localhost:5555/api/v1/health
```

**2. Check Playnite logs**:
```
%APPDATA%\Playnite\playnite.log  # Windows
```

**3. Check network connectivity**:
```bash
netstat -an | grep 5555
```

**Solutions**:

**1. Start Python service first**:
```bash
python -m playnite_python serve &
```

**2. Configure correct URL in plugin**:
```csharp
// In plugin config
serviceClient = new PythonServiceClient("http://localhost:5555");
```

**3. Check firewall** (Windows):
```
Windows Firewall → Allow an app
Add Python to allowed apps
```

---

### Game events not triggering captures

**Symptoms**: Starting game doesn't start capture session

**Diagnosis**:

**1. Check plugin enabled** in Playnite:
```
Playnite → Settings → Plugins
PythonBridge should be enabled
```

**2. Check Python service logs**:
```bash
tail -f logs/playnite.log | grep -i game
```

**3. Test manual start**:
```bash
curl -X POST http://localhost:5555/api/v1/capture/start \
  -d '{"game_id": "test", "game_name": "Test", "process_id": 12345}'
```

**Solutions**:

**1. Verify plugin installed correctly**:
- Check Playnite extensions directory
- Verify DLL present
- Check manifest (extension.yaml)

**2. Check plugin permissions**:
- Plugin needs network access
- May need elevation for hotkeys

**3. Enable debug logging** in plugin:
```csharp
// In plugin code
LogLevel = LogLevel.Debug;
```

---

## Getting Help

### Enable Debug Logging

**1. Set log level**:
```bash
# In .env file
LOG_LEVEL=DEBUG

# Or environment variable
export LOG_LEVEL=DEBUG
python -m playnite_python serve
```

**2. View logs**:
```bash
# Real-time monitoring
tail -f logs/playnite.log

# Search for errors
grep ERROR logs/playnite.log

# Last 100 lines
tail -100 logs/playnite.log
```

**3. Filter by component**:
```bash
grep "recommendation" logs/playnite.log
grep "capture" logs/playnite.log
grep "database" logs/playnite.log
```

---

### Collect Diagnostic Information

Before reporting issues, collect:

**1. System information**:
```bash
# Python version
python --version

# OS information
uname -a  # Linux/Mac
systeminfo  # Windows

# Installed packages
pip list

# FFmpeg version
ffmpeg -version
```

**2. Service information**:
```bash
# Health check
curl http://localhost:5555/api/v1/health

# Active sessions
curl http://localhost:5555/api/v1/capture/sessions

# Storage usage
curl http://localhost:5555/api/v1/storage/usage
```

**3. Logs**:
```bash
# Last 100 lines
tail -100 logs/playnite.log > diagnostic_log.txt

# Error lines
grep ERROR logs/playnite.log > errors.txt
```

**4. Configuration**:
```bash
# Sanitize sensitive info first!
cat .env | grep -v PASSWORD > config.txt
```

---

### Report Issues

**1. Search existing issues**:
- https://github.com/yourusername/playnite-python/issues

**2. Create new issue** with template:

```markdown
## Description
Brief description of the problem

## Environment
- OS: Windows 11 / macOS 13 / Ubuntu 22.04
- Python version: 3.11.5
- Service version: 1.0.0
- FFmpeg version: 6.0

## Steps to Reproduce
1. Start service
2. Run command X
3. Observe error Y

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Logs
```
[Paste relevant log entries]
```

## Screenshots
[If applicable]

## Additional Context
Any other information
```

**3. Include diagnostic info**:
- System information
- Logs (last 100 lines)
- Configuration (sanitized)
- Steps to reproduce

---

### Community Support

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **Discord** (if available): Real-time chat support
- **Wiki**: Additional documentation and guides

---

## See Also

- [Capture Setup Guide](CAPTURE_SETUP.md) - Initial setup
- [Video Editing Guide](VIDEO_EDITING.md) - Edit captures
- [API Documentation](API.md) - Complete API reference
- [Architecture](ARCHITECTURE.md) - System design
