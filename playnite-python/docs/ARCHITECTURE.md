# Playnite Python Integration - Architecture

## Overview

The Playnite Python integration provides intelligent game recommendations and media capture capabilities through a hybrid architecture combining a C# bridge plugin with an external Python service.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PLAYNITE (C#/.NET 4.6.2)                      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │         PythonBridge Plugin (C# GenericPlugin)             │ │
│  │                                                             │ │
│  │  • Event Handlers (OnGameStarted, OnGameStopped)          │ │
│  │  • Menu Items (Recommendations, Export, Captures)         │ │
│  │  • Service Client (HTTP REST communication)               │ │
│  │  • Service Manager (Lifecycle management)                 │ │
│  │  • Game Data Exporter (LiteDB → JSON)                     │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              │ IPlayniteAPI                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Playnite Core                                            │ │
│  │  • Database (LiteDB)                                      │ │
│  │  • Game Library                                           │ │
│  │  • Event System                                           │ │
│  │  • Notifications                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP REST API
                              │ (localhost:5555)
                              │ JSON Payloads
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              PYTHON SERVICE (Python 3.8+)                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │          FastAPI REST Server (Uvicorn)                     │ │
│  │                                                             │ │
│  │  Endpoints:                                                │ │
│  │  • GET  /api/v1/health                                     │ │
│  │  • POST /api/v1/recommendations/generate                   │ │
│  │  • POST /api/v1/capture/start                              │ │
│  │  • POST /api/v1/capture/screenshot/{session_id}            │ │
│  │  • POST /api/v1/capture/video/start/{session_id}           │ │
│  │  • POST /api/v1/capture/stop/{session_id}                  │ │
│  │  • GET  /api/v1/storage/usage                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│  ┌─────────────────────┬────────────────┬─────────────────────┐ │
│  │  Recommendation     │    Capture     │    Core             │ │
│  │  Engine             │    System      │    Components       │ │
│  │                     │                │                     │ │
│  │  ContentBasedFilter │  CaptureManager│  Configuration      │ │
│  │  CollaborativeFilter│  DirectCapture │  Logging            │ │
│  │  ContextualFilter   │  CaptureStorage│  Database           │ │
│  │  RecommendationDB   │  HotkeyListener│  CLI Commands       │ │
│  └─────────────────────┴────────────────┴─────────────────────┘ │
│                                                                  │
│  Storage:                                                        │
│  • SQLite Database (recommendations, sessions, history)         │
│  • File System (captured media organized by game)               │
└─────────────────────────────────────────────────────────────────┘
```

## Design Decisions

### Why External Python Service?

**Options Considered:**
1. **IronPython Plugin** - Rejected: Only supports Python 2.7, incompatible with modern ML libraries
2. **Python.NET Embedding** - Rejected: Complex, memory management issues, difficult to test independently
3. **External Service (Chosen)** - Pros: Full Python 3.8+ ecosystem, independent testing, clean separation

**Trade-offs:**
- ✅ Access to full Python ecosystem (scikit-learn, OpenCV, pandas, etc.)
- ✅ Service can run even when Playnite is closed
- ✅ Easy to test and develop independently
- ✅ Clean separation of concerns
- ⚠️ Requires managing separate process
- ⚠️ Network overhead (minimal for localhost)

### Communication Protocol: HTTP REST

**Why REST over alternatives?**
- **Named Pipes**: Platform-specific, more complex
- **gRPC**: Overkill for this use case, adds complexity
- **Message Queue**: Too heavy, requires additional infrastructure
- **REST (Chosen)**: Simple, well-understood, easy to debug, built-in with FastAPI

### Data Flow Patterns

#### 1. Event-Driven Game Tracking
```
Game Starts → Playnite Event → C# Plugin → HTTP POST → Python Service
                                                        → Start Capture Session
                                                        → Track Play History

Game Stops  → Playnite Event → C# Plugin → HTTP POST → Python Service
                                                        → Stop Capture
                                                        → Update Statistics
```

#### 2. Request-Response for Recommendations
```
User Action → Menu Click → C# Plugin → Export Library → HTTP POST Request
                                        ↓
                                      Python Service
                                        ↓
                                      ML Processing
                                        ↓
                                      HTTP Response ← Display Results
```

#### 3. Background Capture Management
```
Capture Session Active → Hotkey Pressed → Python (pynput) → Screenshot/Video
                                          ↓
                                        Save to File System
                                          ↓
                                        Organize by Game ID
```

## Component Details

### C# Bridge Plugin

**Responsibilities:**
- Monitor Playnite events (game start/stop, app lifecycle)
- Export game library data from LiteDB
- Communicate with Python service via HTTP
- Manage Python service lifecycle (start/stop/health check)
- Display results in Playnite UI

**Key Classes:**
- `PythonBridgePlugin`: Main plugin, event handlers, menu items
- `PythonServiceClient`: HTTP REST client for API calls
- `PythonServiceManager`: Process management for Python service
- `GameDataExporter`: Convert Playnite Game objects to JSON DTOs

### Python Service

**Responsibilities:**
- Generate game recommendations using ML algorithms
- Capture screenshots and videos during gameplay
- Organize captured media by game
- Track play history and user preferences
- Expose REST API for C# plugin

**Module Structure:**
```
playnite_python/
├── api/              # FastAPI routes and models
├── recommendations/  # ML recommendation engine
├── capture/          # Media capture system
├── database/         # SQLAlchemy models and storage
├── core/             # Configuration, logging, utilities
└── cli/              # Command-line interface
```

## Recommendation Algorithm

### Hybrid Approach

The recommendation engine combines three techniques:

**1. Content-Based Filtering (60% weight)**
- Uses TF-IDF vectorization on game attributes
- Calculates cosine similarity between games
- Identifies user's enjoyed games (high playtime, ratings, favorites)
- Recommends similar unplayed games

**2. Collaborative Filtering (40% weight)**
- Currently uses popularity-based approach (single-user)
- Future: Matrix factorization for multi-user recommendations
- Uses community and critic scores as proxy for user ratings

**3. Contextual Filtering**
- Mood-based filtering (relaxing, challenging, story, etc.)
- Time-of-day adjustments
- Session length preferences

### Scoring Formula

```python
final_score = (content_similarity * 0.6) + (collaborative_score * 0.4)

# Apply contextual boosts
if mood_match:
    final_score *= 1.3
if time_appropriate:
    final_score *= 1.15
```

### Explanation Generation

Each recommendation includes:
- **Score**: 0-1 float indicating confidence
- **Reason**: Human-readable explanation
- **Factors**: Dictionary of detailed scoring components
- **Sources**: List of algorithms that contributed

## Capture System

### Backend Architecture

**Interface-Based Design:**
- `CaptureBackend` abstract base class
- Multiple implementations: DirectCapture, OBS, WindowsGameBar
- Strategy pattern for backend selection

**Current Implementation: DirectCapture**
- Uses `mss` for fast screenshots
- Uses `cv2` (OpenCV) for video recording
- Captures entire primary monitor
- Background async loop for video frames

**Future Backends:**
- OBS Studio integration via obs-websocket
- Windows Game Bar integration
- NVIDIA ShadowPlay integration

### Media Organization

```
~/Playnite/Captures/
├── {game-guid-1}/
│   ├── screenshots/
│   │   ├── screenshot_20260210_143022_001.png
│   │   └── screenshot_20260210_143045_002.png
│   └── videos/
│       └── video_20260210_143000.mp4
├── {game-guid-2}/
│   └── screenshots/
│       └── screenshot_20260210_150000_001.png
```

### Hotkey Management

- Uses `pynput` for keyboard monitoring
- Asynchronous hotkey callbacks
- Multiple hotkeys per session (screenshot, video, instant replay)
- Graceful cleanup on session end

## Database Schema

### SQLite Database (Python)

```sql
-- User preferences and statistics
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    preferences JSON
);

-- Cached game data from Playnite
CREATE TABLE game_data (
    game_id TEXT PRIMARY KEY,
    name TEXT,
    genres JSON,
    developers JSON,
    last_synced TIMESTAMP
);

-- Play session history
CREATE TABLE play_history (
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    game_id TEXT,
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    duration_seconds INTEGER
);

-- Generated recommendations
CREATE TABLE recommendations (
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    game_id TEXT,
    score REAL,
    reason TEXT,
    factors JSON,
    generated_at TIMESTAMP,
    user_feedback TEXT  -- 'liked', 'dismissed', 'played'
);

-- Capture sessions
CREATE TABLE capture_sessions (
    id INTEGER PRIMARY KEY,
    session_id TEXT UNIQUE,
    game_id TEXT,
    game_name TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    screenshot_count INTEGER,
    video_count INTEGER,
    backend_used TEXT
);
```

### LiteDB (Playnite C#)

Playnite's existing database is read-only for the plugin:
- Game library with full metadata
- Play history and statistics
- User ratings and completion status

## Performance Considerations

### Recommendation Generation
- **Target**: < 500ms for 1000 games
- **Optimization**: Pre-compute similarity matrices, cache user profiles
- **Scaling**: Async processing, background updates

### Screenshot Capture
- **Target**: < 100ms per screenshot
- **Optimization**: mss library (fast), minimal processing
- **Trade-off**: Captures entire screen vs. game window only

### Video Recording
- **Target**: Minimal performance impact during gameplay
- **Optimization**: Async frame capture, configurable quality/FPS
- **Trade-off**: Quality vs. file size vs. performance

### Storage Management
- **Automatic cleanup**: Configurable retention policies
- **Compression**: PNG for screenshots, MP4 for videos
- **Organization**: By game for easy management

## Security Considerations

### Current (Development)
- Service binds to `127.0.0.1` (localhost only)
- No authentication (single-user, local machine)
- No external network access

### Future Enhancements
- API key authentication for remote access
- HTTPS support for network deployment
- User-based access control
- Rate limiting

## Testing Strategy

### Unit Tests (Python)
- Recommendation algorithms (content-based, collaborative, contextual)
- Capture storage management
- Database operations
- Pytest framework with >80% coverage goal

### Integration Tests (Python)
- FastAPI endpoint testing with httpx
- End-to-end recommendation flow
- Capture session lifecycle

### Manual Testing (C#)
- Plugin loads in Playnite without errors
- Menu items functional
- Service communication working
- Capture triggers correctly

### CLI Testing
- Standalone recommendation generation
- Storage management commands
- Service health checks

## Deployment Model

### User Installation
1. Install Python 3.8+ (if not present)
2. Run PowerShell installation script
3. Install C# plugin in Playnite
4. Plugin auto-starts Python service

### Developer Setup
1. Clone repository
2. Run `scripts/install.ps1 -Dev`
3. Build C# plugin in Visual Studio
4. Copy plugin DLL to Playnite extensions directory

## Future Enhancements

### Recommendations
- Deep learning models (game embeddings)
- Multi-user collaborative filtering
- Integration with IGDB/Steam for external recommendations
- Achievement-based suggestions

### Capture
- Intelligent highlight detection (kills, achievements)
- Automatic montage generation
- Cloud upload (YouTube, Twitch, Discord)
- AI-powered editing

### General
- Web dashboard for statistics
- Mobile companion app
- Plugin marketplace integration
- Telemetry and analytics (opt-in)
