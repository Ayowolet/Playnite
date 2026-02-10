# Playnite Python Service - API Documentation

## Base URL

```
http://localhost:5555/api/v1
```

## Interactive Documentation

Once the service is running, visit:
- **Swagger UI**: http://localhost:5555/docs
- **ReDoc**: http://localhost:5555/redoc

## Authentication

Currently: None (localhost only, trusted environment)

Future: API key authentication via `X-API-Key` header

## Endpoints

### Health Check

#### GET `/health`

Check if the service is running and healthy.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600.45,
  "timestamp": "2026-02-10T12:00:00+00:00"
}
```

**Status Codes:**
- `200 OK`: Service is healthy
- `503 Service Unavailable`: Service is starting or unhealthy

---

### Recommendations

#### POST `/recommendations/generate`

Generate personalized game recommendations.

**Request Body:**
```json
{
  "user_id": "default-user",
  "library": [
    {
      "game_id": "1",
      "name": "Dark Souls",
      "genres": ["RPG", "Action"],
      "developers": ["FromSoftware"],
      "publishers": ["Bandai Namco"],
      "platforms": ["PC"],
      "tags": ["Souls-like", "Difficult"],
      "features": ["Single Player"],
      "playtime_seconds": 72000,
      "play_count": 15,
      "last_activity": "2026-01-15T00:00:00Z",
      "user_score": 90,
      "community_score": 89,
      "critic_score": null,
      "completion_status": "Completed",
      "is_installed": true,
      "favorite": true,
      "hidden": false
    }
  ],
  "context": {
    "mood": "challenging",
    "time_of_day": "evening",
    "session_length": "long"
  },
  "limit": 10
}
```

**Request Fields:**
- `user_id` (string, required): User identifier
- `library` (array, required): Complete game library
- `context` (object, optional): Context for recommendations
  - `mood`: "relaxing", "challenging", "story", "social", "creative", "competitive", "quick", "immersive"
  - `time_of_day`: "morning", "afternoon", "evening", "night"
  - `session_length`: "short", "medium", "long"
- `limit` (integer, optional): Number of recommendations (1-50, default: 10)

**Response:**
```json
{
  "recommendations": [
    {
      "game_id": "2",
      "game_name": "Elden Ring",
      "score": 0.87,
      "reason": "Similar to Dark Souls (Perfect for challenging mood)",
      "factors": {
        "content_similarity": 0.92,
        "max_similarity": 0.95,
        "similar_to": "Dark Souls",
        "mood_boost": 1.3
      },
      "sources": ["content", "collaborative"]
    }
  ],
  "count": 10,
  "generated_at": "2026-02-10T12:00:00+00:00",
  "model_version": "1.0.0"
}
```

**Status Codes:**
- `200 OK`: Recommendations generated successfully
- `400 Bad Request`: Invalid request data
- `500 Internal Server Error`: Recommendation generation failed

---

#### GET `/recommendations/test`

Test endpoint with sample data.

**Response:**
```json
{
  "message": "Test recommendations generated successfully",
  "recommendations": [...]
}
```

---

### Capture - Session Management

#### POST `/capture/start`

Start a new capture session for a game.

**Request Body:**
```json
{
  "game_id": "game-guid",
  "game_name": "Dark Souls",
  "process_id": 12345,
  "settings": {
    "screenshot_hotkey": "f8",
    "video_hotkey": "f9",
    "backend": "direct",
    "video_quality": "high"
  }
}
```

**Request Fields:**
- `game_id` (string, required): Game identifier
- `game_name` (string, required): Game name
- `process_id` (integer, required): Game process ID
- `settings` (object, optional): Capture settings
  - `screenshot_hotkey` (string): Hotkey for screenshots (default: "f8")
  - `video_hotkey` (string): Hotkey for video toggle (default: "f9")
  - `backend` (string): Capture backend - "direct", "obs", "gamebar" (default: "direct")
  - `video_quality` (string): Video quality - "low", "medium", "high" (default: "high")

**Response:**
```json
{
  "session_id": "sess-game-guid-1707566400",
  "status": "active",
  "game_name": "Dark Souls",
  "backend": "direct",
  "screenshot_count": 0,
  "video_count": 0
}
```

**Status Codes:**
- `200 OK`: Session started successfully
- `500 Internal Server Error`: Failed to start session

---

#### POST `/capture/screenshot/{session_id}`

Capture a screenshot in an active session.

**Path Parameters:**
- `session_id` (string): Capture session identifier

**Response:**
```json
{
  "session_id": "sess-game-guid-1707566400",
  "file_path": "/home/user/Playnite/Captures/game-guid/screenshots/screenshot_20260210_120000_001.png",
  "timestamp": "2026-02-10T12:00:00+00:00",
  "size_bytes": 2048576
}
```

**Status Codes:**
- `200 OK`: Screenshot captured successfully
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Capture failed

---

#### POST `/capture/video/start/{session_id}`

Start video recording for a session.

**Path Parameters:**
- `session_id` (string): Capture session identifier

**Query Parameters:**
- `quality` (string, optional): Video quality - "low", "medium", "high" (default: "high")

**Response:**
```json
{
  "session_id": "sess-game-guid-1707566400",
  "recording": true,
  "file_path": null
}
```

**Status Codes:**
- `200 OK`: Recording started
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Failed to start recording

---

#### POST `/capture/video/stop/{session_id}`

Stop video recording for a session.

**Path Parameters:**
- `session_id` (string): Capture session identifier

**Response:**
```json
{
  "session_id": "sess-game-guid-1707566400",
  "recording": false,
  "file_path": "/home/user/Playnite/Captures/game-guid/videos/video_20260210_120000.mp4"
}
```

**Status Codes:**
- `200 OK`: Recording stopped
- `500 Internal Server Error`: Failed to stop recording

---

#### POST `/capture/stop/{session_id}`

Stop a capture session and cleanup resources.

**Path Parameters:**
- `session_id` (string): Capture session identifier

**Response:**
```json
{
  "session_id": "sess-game-guid-1707566400",
  "game_name": "Dark Souls",
  "status": "stopped",
  "duration_seconds": 3600,
  "screenshot_count": 15,
  "video_count": 2
}
```

**Status Codes:**
- `200 OK`: Session stopped successfully
- `404 Not Found`: Session not found

---

#### GET `/capture/sessions`

List all active capture sessions.

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "sess-game-guid-1707566400",
      "game_id": "game-guid",
      "game_name": "Dark Souls",
      "backend": "direct",
      "screenshot_count": 15,
      "video_count": 2,
      "duration_seconds": 3600
    }
  ]
}
```

---

### Storage Management

#### GET `/storage/usage`

Get overall storage usage statistics.

**Response:**
```json
{
  "total_size_bytes": 10485760000,
  "total_size_mb": 10000.0,
  "total_size_gb": 9.77,
  "game_count": 25,
  "total_screenshots": 450,
  "total_videos": 30
}
```

---

#### GET `/storage/game/{game_id}`

Get storage usage for a specific game.

**Path Parameters:**
- `game_id` (string): Game identifier

**Response:**
```json
{
  "game_id": "game-guid",
  "size_bytes": 524288000,
  "size_mb": 500.0,
  "screenshot_count": 25,
  "video_count": 3
}
```

---

#### GET `/captures/{game_id}`

List all captures for a game.

**Path Parameters:**
- `game_id` (string): Game identifier

**Response:**
```json
{
  "game_id": "game-guid",
  "screenshots": [
    "/path/to/screenshot_001.png",
    "/path/to/screenshot_002.png"
  ],
  "videos": [
    "/path/to/video_001.mp4"
  ]
}
```

---

#### DELETE `/captures/{game_id}`

Delete all captures for a game.

**Path Parameters:**
- `game_id` (string): Game identifier

**Response:**
```json
{
  "message": "Deleted all captures for game game-guid"
}
```

**Status Codes:**
- `200 OK`: Captures deleted successfully
- `404 Not Found`: Game not found or deletion failed

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common Status Codes:**
- `400 Bad Request`: Invalid input data
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server-side error

---

## Rate Limiting

Currently: None

Future: Rate limiting will be implemented to prevent abuse.

---

## Examples

### Using cURL

**Health Check:**
```bash
curl http://localhost:5555/api/v1/health
```

**Generate Recommendations:**
```bash
curl -X POST http://localhost:5555/api/v1/recommendations/generate \
  -H "Content-Type: application/json" \
  -d @library.json
```

**Start Capture Session:**
```bash
curl -X POST http://localhost:5555/api/v1/capture/start \
  -H "Content-Type: application/json" \
  -d '{
    "game_id": "test-game",
    "game_name": "Test Game",
    "process_id": 12345,
    "settings": {
      "screenshot_hotkey": "f8"
    }
  }'
```

### Using Python (httpx)

```python
import httpx

# Health check
response = httpx.get("http://localhost:5555/api/v1/health")
print(response.json())

# Generate recommendations
library_data = {...}
response = httpx.post(
    "http://localhost:5555/api/v1/recommendations/generate",
    json={
        "user_id": "test-user",
        "library": library_data,
        "limit": 5
    }
)
recommendations = response.json()
```

### Using C# (HttpClient)

```csharp
using System.Net.Http;
using Newtonsoft.Json;

var client = new HttpClient();
client.BaseAddress = new Uri("http://localhost:5555");

// Health check
var response = await client.GetAsync("/api/v1/health");
var content = await response.Content.ReadAsStringAsync();

// Generate recommendations
var request = new {
    user_id = "test-user",
    library = libraryData,
    limit = 10
};
var json = JsonConvert.SerializeObject(request);
var httpContent = new StringContent(json, Encoding.UTF8, "application/json");
response = await client.PostAsync("/api/v1/recommendations/generate", httpContent);
```

---

## Versioning

Current API version: `v1`

API versioning is done via URL path (`/api/v1/`). Future versions will use `/api/v2/`, etc.

Breaking changes will result in a new API version. Non-breaking changes will be added to the current version.

---

## Support

- GitHub Issues: https://github.com/yourusername/playnite-python/issues
- Documentation: https://github.com/yourusername/playnite-python/wiki
