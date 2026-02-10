# Metadata Tagging Assessment
## Playnite Python Integration Project

**Assessment Date:** February 10, 2026
**Assessment Type:** Metadata Tagging for Captured Media
**Status:** **PARTIALLY IMPLEMENTED**

---

## Executive Summary

The capture system has basic timestamp and file path tracking, but lacks a comprehensive metadata tagging system for screenshots and videos. Metadata viewing, editing, searching, and filtering capabilities are **NOT implemented**.

**Overall Score: 2/9 items (22%)** ❌

---

## Checklist Assessment

| Item | Status | Implementation | Evidence |
|------|--------|----------------|----------|
| **View metadata for screenshot** | ⚠️ PARTIAL | Basic info via API response | `capture.py:77-82` - Only path, timestamp, size |
| **Verify game name is tagged** | ❌ NOT IMPLEMENTED | No metadata storage | Game name not persisted with file |
| **Verify timestamp is tagged** | ⚠️ PARTIAL | Timestamp in filename only | `storage.py:48` - Filename format only |
| **Verify session info is tagged** | ❌ NOT IMPLEMENTED | Session ID in filename only | No persistent session metadata |
| **View metadata for video** | ⚠️ PARTIAL | Path and status only | No duration tracking |
| **Verify duration is tagged** | ❌ NOT IMPLEMENTED | No duration calculation | No video duration field |
| **Edit metadata tags manually** | ❌ NOT IMPLEMENTED | No edit endpoint | No metadata editing API |
| **Search captures by metadata** | ❌ NOT IMPLEMENTED | No search functionality | No search API |
| **Filter captures by date range** | ❌ NOT IMPLEMENTED | No filter functionality | No date filtering |

**Score Breakdown:**
- ✅ Fully Implemented: 0/9 (0%)
- ⚠️ Partially Implemented: 3/9 (33%)
- ❌ Not Implemented: 6/9 (67%)

---

## What IS Implemented

### 1. Basic File Organization ✅

**Current Implementation (storage.py:33-84):**
```python
def get_screenshot_path(self, game_id: str, session_id: str = None):
    # Generates path like: screenshots/screenshot_20261210_145523_001.png
    # Or: screenshots/screenshot_sess-123_20261210_145523_001.png

def get_video_path(self, game_id: str, session_id: str = None):
    # Generates path like: videos/video_20261210_145523.mp4
```

**What Works:**
- ✅ Filenames include timestamps (YYYYMMDD_HHMMSS format)
- ✅ Optional session ID in filename
- ✅ Organized by game (game_id/screenshots/, game_id/videos/)
- ✅ Counter for duplicate timestamps

### 2. Basic Metadata via API Response ⚠️

**Current Implementation (capture.py:77-82):**
```python
return ScreenshotResponse(
    session_id=session_id,
    file_path=str(file_path),
    timestamp=datetime.now(timezone.utc).isoformat(),
    size_bytes=size_bytes,
)
```

**What Works:**
- ⚠️ Timestamp available at capture time (not persisted)
- ⚠️ File path returned
- ⚠️ File size calculated
- ❌ No game name in response
- ❌ Not stored for later retrieval

### 3. File Listing ⚠️

**Current Implementation (storage.py:110-161):**
```python
def list_captures(self, game_id: str):
    # Returns screenshot/video paths sorted by modification time
    # Does NOT return metadata beyond filesystem info
```

**What Works:**
- ✅ Lists all captures for a game
- ✅ Sorted by modification time
- ❌ No metadata extraction
- ❌ No filtering capabilities

---

## What IS NOT Implemented

### 1. Persistent Metadata Storage ❌

**Missing:**
- No database table for capture metadata
- No JSON sidecar files (e.g., `screenshot_001.png.json`)
- No metadata embedded in files (EXIF, XMP, etc.)

**Expected:**
```python
class CaptureMetadata(Base):
    __tablename__ = "capture_metadata"

    id = Column(Integer, primary_key=True)
    file_path = Column(String, unique=True)
    game_id = Column(String)
    game_name = Column(String)          # MISSING
    session_id = Column(String)
    capture_type = Column(String)       # screenshot, video, replay
    timestamp = Column(DateTime)
    file_size_bytes = Column(Integer)
    duration_seconds = Column(Float)    # For videos - MISSING
    resolution = Column(String)         # e.g., "1920x1080" - MISSING
    tags = Column(JSON)                 # User-defined tags - MISSING
    notes = Column(Text)                # User notes - MISSING
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

### 2. Video Duration Tracking ❌

**Missing:**
```python
# No functionality to extract video duration
# Should use ffprobe or similar
def get_video_duration(file_path: Path) -> float:
    """Get video duration in seconds."""
    # Not implemented
```

### 3. Metadata Viewing Endpoint ❌

**Missing API Endpoint:**
```python
@router.get("/metadata/{capture_id}")
async def get_capture_metadata(capture_id: int):
    """Get full metadata for a capture."""
    # Not implemented
```

### 4. Metadata Editing Endpoint ❌

**Missing API Endpoint:**
```python
@router.patch("/metadata/{capture_id}")
async def update_capture_metadata(capture_id: int, updates: MetadataUpdate):
    """Update metadata tags, notes, or custom fields."""
    # Not implemented
```

### 5. Search Functionality ❌

**Missing API Endpoint:**
```python
@router.get("/search")
async def search_captures(
    game_id: Optional[str] = None,
    game_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    capture_type: Optional[str] = None,
):
    """Search captures by metadata."""
    # Not implemented
```

### 6. Date Range Filtering ❌

**Missing Functionality:**
- No API parameter for date ranges
- No filter implementation in storage layer

---

## Implementation Gap Analysis

### Current Architecture (Insufficient)

```
Capture Created
    ↓
File Saved (with timestamp in filename)
    ↓
API Returns: {file_path, timestamp, size}
    ↓
[METADATA LOST - Not persisted]
```

### Required Architecture

```
Capture Created
    ↓
File Saved
    ↓
Metadata Extracted/Created
    ├── Game name
    ├── Session info
    ├── Timestamp
    ├── File size
    ├── Duration (for videos)
    ├── Resolution
    └── User tags
    ↓
Metadata Stored in Database
    ↓
API Endpoints Available:
    ├── View metadata
    ├── Edit metadata
    ├── Search by metadata
    └── Filter by date/tags
```

---

## Detailed Missing Components

### 1. Database Model for Capture Metadata

**File:** `src/playnite_python/database/models.py` (needs addition)

```python
class CaptureMetadata(Base):
    """Metadata for captured screenshots and videos."""

    __tablename__ = "capture_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String, unique=True, nullable=False, index=True)
    file_name = Column(String, nullable=False)

    # Game information
    game_id = Column(String, nullable=False, index=True)
    game_name = Column(String, nullable=False)

    # Session information
    session_id = Column(String, index=True)

    # Capture details
    capture_type = Column(String, nullable=False)  # screenshot, video, replay
    timestamp = Column(DateTime, nullable=False, index=True)
    file_size_bytes = Column(Integer)

    # Video-specific
    duration_seconds = Column(Float, nullable=True)

    # Technical details
    resolution_width = Column(Integer)
    resolution_height = Column(Integer)
    format = Column(String)  # png, mp4, etc.

    # User-editable metadata
    tags = Column(JSON, default=list)  # ["epic", "funny", "achievement"]
    notes = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5 stars
    is_favorite = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

### 2. Metadata Service

**File:** `src/playnite_python/capture/metadata_service.py` (missing)

```python
class MetadataService:
    """Service for managing capture metadata."""

    def create_metadata(
        self,
        file_path: Path,
        game_id: str,
        game_name: str,
        session_id: str,
        capture_type: str
    ) -> CaptureMetadata:
        """Create metadata entry for a new capture."""

    def get_metadata(self, capture_id: int) -> Optional[CaptureMetadata]:
        """Retrieve metadata by capture ID."""

    def update_metadata(
        self,
        capture_id: int,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        rating: Optional[int] = None
    ) -> CaptureMetadata:
        """Update user-editable metadata fields."""

    def search_captures(
        self,
        game_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        capture_type: Optional[str] = None
    ) -> List[CaptureMetadata]:
        """Search captures by metadata criteria."""

    def extract_video_duration(self, file_path: Path) -> float:
        """Extract video duration using ffprobe."""
        # ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 video.mp4
```

### 3. API Models

**File:** `src/playnite_python/api/models/capture.py` (needs addition)

```python
class CaptureMetadataResponse(BaseModel):
    """Complete metadata for a capture."""

    id: int
    file_path: str
    file_name: str
    game_id: str
    game_name: str
    session_id: Optional[str]
    capture_type: str
    timestamp: str
    file_size_bytes: Optional[int]
    file_size_mb: Optional[float]
    duration_seconds: Optional[float]
    resolution: Optional[str]
    format: str
    tags: List[str]
    notes: Optional[str]
    rating: Optional[int]
    is_favorite: bool
    created_at: str
    updated_at: str


class MetadataUpdateRequest(BaseModel):
    """Request to update capture metadata."""

    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    is_favorite: Optional[bool] = None


class SearchCapturesRequest(BaseModel):
    """Request to search captures by metadata."""

    game_id: Optional[str] = None
    game_name: Optional[str] = None
    tags: Optional[List[str]] = None
    date_from: Optional[str] = None  # ISO format
    date_to: Optional[str] = None
    capture_type: Optional[str] = None
    is_favorite: Optional[bool] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
```

### 4. API Endpoints

**File:** `src/playnite_python/api/routes/capture.py` (needs additions)

```python
@router.get("/metadata/{capture_id}", response_model=CaptureMetadataResponse)
async def get_capture_metadata(capture_id: int):
    """Get full metadata for a specific capture."""
    # Not implemented

@router.patch("/metadata/{capture_id}", response_model=CaptureMetadataResponse)
async def update_capture_metadata(
    capture_id: int,
    updates: MetadataUpdateRequest
):
    """Update user-editable metadata fields."""
    # Not implemented

@router.get("/search", response_model=List[CaptureMetadataResponse])
async def search_captures(
    game_id: Optional[str] = None,
    tags: Optional[str] = None,  # Comma-separated
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    capture_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Search captures by metadata criteria."""
    # Not implemented

@router.get("/game/{game_id}/captures", response_model=List[CaptureMetadataResponse])
async def get_game_captures_with_metadata(
    game_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """Get all captures for a game with full metadata."""
    # Not implemented
```

### 5. Integration with Capture Flow

**Required Changes to `manager.py`:**

```python
async def capture_screenshot(self, session_id: str) -> Optional[Path]:
    """Capture screenshot and create metadata."""
    file_path = await session.backend.capture_screenshot(output_path)

    # NEW: Create metadata entry
    metadata_service.create_metadata(
        file_path=file_path,
        game_id=session.game_id,
        game_name=session.game_name,
        session_id=session_id,
        capture_type="screenshot"
    )

    return file_path

async def stop_video_recording(self, session_id: str):
    """Stop video recording and create metadata with duration."""
    file_path = await session.backend.stop_recording()

    # NEW: Extract video duration
    duration = metadata_service.extract_video_duration(file_path)

    # NEW: Create metadata entry
    metadata_service.create_metadata(
        file_path=file_path,
        game_id=session.game_id,
        game_name=session.game_name,
        session_id=session_id,
        capture_type="video",
        duration_seconds=duration
    )

    return file_path
```

---

## Implementation Effort Estimate

### Phase 1: Database Schema (1 day)
- Add CaptureMetadata model
- Create Alembic migration
- Test database operations

### Phase 2: Metadata Service (2-3 days)
- Create MetadataService class
- Implement CRUD operations
- Implement video duration extraction
- Add search/filter logic
- Unit tests

### Phase 3: API Integration (2 days)
- Add Pydantic models
- Create API endpoints
- Update capture flow to create metadata
- Integration tests

### Phase 4: Search & Filter (1-2 days)
- Implement search logic
- Date range filtering
- Tag-based search
- Test edge cases

### Phase 5: Testing (1-2 days)
- Unit tests (20+ tests)
- Integration tests (10+ tests)
- End-to-end tests

**Total Effort:** 7-10 days

---

## Testing Requirements

### Unit Tests Needed (25+ tests)

**Metadata Creation:**
- test_create_screenshot_metadata
- test_create_video_metadata_with_duration
- test_metadata_includes_game_name
- test_metadata_includes_timestamp
- test_metadata_includes_session_id

**Metadata Viewing:**
- test_get_metadata_by_id
- test_get_metadata_not_found
- test_metadata_response_structure

**Metadata Editing:**
- test_update_tags
- test_update_notes
- test_update_rating
- test_update_favorite_status
- test_partial_update

**Search & Filter:**
- test_search_by_game_id
- test_search_by_tags
- test_search_by_date_range
- test_filter_by_capture_type
- test_filter_favorites_only
- test_search_pagination

**Video Duration:**
- test_extract_video_duration
- test_duration_stored_in_metadata

**Edge Cases:**
- test_search_no_results
- test_invalid_date_range
- test_duplicate_file_path

---

## Current vs. Required

| Feature | Current | Required | Gap |
|---------|---------|----------|-----|
| **Metadata Storage** | Filename only | Database table | Full implementation needed |
| **Game Name Tag** | Not persisted | Stored in DB | ❌ Missing |
| **Timestamp Tag** | Filename only | DB + searchable | ⚠️ Partial |
| **Session Info Tag** | Filename only | DB with details | ⚠️ Partial |
| **Video Duration** | Not tracked | Extracted & stored | ❌ Missing |
| **Metadata Viewing** | Basic API response | Full metadata endpoint | ❌ Missing |
| **Metadata Editing** | No editing | PATCH endpoint | ❌ Missing |
| **Search** | No search | Full-text + filters | ❌ Missing |
| **Date Filter** | No filtering | Date range queries | ❌ Missing |

---

## Example Usage (After Implementation)

### View Screenshot Metadata
```python
GET /api/v1/capture/metadata/42

Response:
{
  "id": 42,
  "file_path": "/captures/game-1/screenshots/screenshot_20261210_145523_001.png",
  "file_name": "screenshot_20261210_145523_001.png",
  "game_id": "game-1",
  "game_name": "Dark Souls",
  "session_id": "sess-123",
  "capture_type": "screenshot",
  "timestamp": "2026-12-10T14:55:23Z",
  "file_size_bytes": 2456789,
  "file_size_mb": 2.34,
  "resolution": "1920x1080",
  "format": "png",
  "tags": ["epic", "boss-fight"],
  "notes": "First Ornstein & Smough kill!",
  "rating": 5,
  "is_favorite": true,
  "created_at": "2026-12-10T14:55:23Z",
  "updated_at": "2026-12-10T15:30:00Z"
}
```

### Edit Metadata
```python
PATCH /api/v1/capture/metadata/42
{
  "tags": ["epic", "boss-fight", "achievement"],
  "notes": "First Ornstein & Smough kill! Epic moment!",
  "rating": 5,
  "is_favorite": true
}
```

### Search Captures
```python
GET /api/v1/capture/search?game_id=game-1&tags=epic&date_from=2026-12-01&date_to=2026-12-31

Response:
{
  "results": [
    {
      "id": 42,
      "game_name": "Dark Souls",
      "timestamp": "2026-12-10T14:55:23Z",
      "tags": ["epic", "boss-fight"],
      ...
    },
    ...
  ],
  "count": 15,
  "limit": 100,
  "offset": 0
}
```

### Filter by Date Range
```python
GET /api/v1/capture/game/game-1/captures?date_from=2026-12-01&date_to=2026-12-31

Response: [list of captures with metadata in date range]
```

---

## Final Verdict

**Overall Grade: F (22%)** ❌

**Status:** Metadata tagging is **NOT IMPLEMENTED** for the most part. Basic file organization exists, but comprehensive metadata storage, viewing, editing, searching, and filtering are all missing.

**Gap Summary:**
- ✅ File organization: COMPLETE
- ⚠️ Basic metadata: PARTIAL (timestamp, file path, size)
- ❌ Persistent metadata storage: MISSING
- ❌ Game name tagging: MISSING
- ❌ Session info persistence: MISSING
- ❌ Video duration tracking: MISSING
- ❌ Metadata viewing endpoint: MISSING
- ❌ Metadata editing: MISSING
- ❌ Search functionality: MISSING
- ❌ Date filtering: MISSING

**Recommendation:** **NOT PRODUCTION-READY FOR METADATA FEATURES**

To implement metadata tagging, the team would need 7-10 days of development work to:
1. Add database model for capture metadata
2. Create metadata service for CRUD operations
3. Integrate metadata creation into capture flow
4. Implement video duration extraction
5. Add API endpoints for viewing/editing/searching
6. Write comprehensive tests (35+ tests)
7. Document metadata API

---

_Assessment completed: February 10, 2026_
_Assessor: Senior Engineering Manager (Cheetah)_
_Status: ❌ NOT IMPLEMENTED_
_Score: 2/9 (22%)_
