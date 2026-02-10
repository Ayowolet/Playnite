"""Unit tests for MetadataService."""
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PIL import Image

from src.playnite_python.capture.metadata import MetadataService


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def metadata_service(temp_dir):
    """Create MetadataService with temporary database."""
    db_path = temp_dir / "test_metadata.db"
    service = MetadataService(str(db_path))
    return service


@pytest.fixture
def sample_screenshot(temp_dir):
    """Create a sample screenshot file."""
    img_path = temp_dir / "screenshot_001.png"
    img = Image.new("RGB", (1920, 1080), color="blue")
    img.save(img_path)
    return img_path


@pytest.fixture
def sample_video(temp_dir):
    """Create a sample video file (empty for testing)."""
    video_path = temp_dir / "video_001.mp4"
    video_path.write_text("fake video content")
    return video_path


# ============================================================================
# Metadata Creation Tests
# ============================================================================


def test_create_screenshot_metadata(metadata_service, sample_screenshot):
    """Test creating metadata for a screenshot."""
    metadata_id = metadata_service.create_metadata(
        file_path=sample_screenshot,
        game_id="game-123",
        game_name="Portal 2",
        session_id="sess-123",
        capture_type="screenshot",
    )

    assert metadata_id is not None
    assert metadata_id > 0

    # Verify metadata was created
    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata is not None
    assert metadata["file_name"] == "screenshot_001.png"
    assert metadata["game_id"] == "game-123"
    assert metadata["game_name"] == "Portal 2"
    assert metadata["session_id"] == "sess-123"
    assert metadata["capture_type"] == "screenshot"
    assert metadata["file_size_bytes"] > 0
    assert metadata["resolution_width"] == 1920
    assert metadata["resolution_height"] == 1080
    assert metadata["format"] == "png"


def test_create_video_metadata(metadata_service, sample_video):
    """Test creating metadata for a video."""
    metadata_id = metadata_service.create_metadata(
        file_path=sample_video,
        game_id="game-456",
        game_name="Dark Souls",
        session_id="sess-456",
        capture_type="video",
    )

    assert metadata_id is not None

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["capture_type"] == "video"
    assert metadata["format"] == "mp4"


def test_create_replay_metadata(metadata_service, sample_video):
    """Test creating metadata for instant replay."""
    metadata_id = metadata_service.create_metadata(
        file_path=sample_video,
        game_id="game-789",
        game_name="Elden Ring",
        session_id="sess-789",
        capture_type="replay",
    )

    assert metadata_id is not None

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["capture_type"] == "replay"


def test_create_metadata_for_missing_file(metadata_service, temp_dir):
    """Test creating metadata for non-existent file."""
    fake_path = temp_dir / "missing.png"

    metadata_id = metadata_service.create_metadata(
        file_path=fake_path,
        game_id="game-000",
        game_name="Test Game",
        session_id="sess-000",
        capture_type="screenshot",
    )

    # Should return None for missing file
    assert metadata_id is None


def test_create_metadata_with_default_values(metadata_service, sample_screenshot):
    """Test that metadata has correct default values."""
    metadata_id = metadata_service.create_metadata(
        file_path=sample_screenshot,
        game_id="game-123",
        game_name="Test Game",
        session_id="sess-123",
        capture_type="screenshot",
    )

    metadata = metadata_service.get_metadata(metadata_id)

    # Check defaults
    assert metadata["tags"] == []
    assert metadata["notes"] is None
    assert metadata["rating"] is None
    assert metadata["is_favorite"] is False
    assert metadata["created_at"] is not None
    assert metadata["updated_at"] is not None


# ============================================================================
# Metadata Retrieval Tests
# ============================================================================


def test_get_metadata_by_id(metadata_service, sample_screenshot):
    """Test retrieving metadata by ID."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    metadata = metadata_service.get_metadata(metadata_id)

    assert metadata is not None
    assert metadata["id"] == metadata_id


def test_get_metadata_not_found(metadata_service):
    """Test retrieving non-existent metadata."""
    metadata = metadata_service.get_metadata(99999)
    assert metadata is None


def test_get_metadata_by_path(metadata_service, sample_screenshot):
    """Test retrieving metadata by file path."""
    metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    metadata = metadata_service.get_metadata_by_path(str(sample_screenshot))

    assert metadata is not None
    assert metadata["file_path"] == str(sample_screenshot)


def test_get_metadata_by_path_not_found(metadata_service):
    """Test retrieving metadata by non-existent path."""
    metadata = metadata_service.get_metadata_by_path("/fake/path.png")
    assert metadata is None


# ============================================================================
# Metadata Update Tests
# ============================================================================


def test_update_metadata_tags(metadata_service, sample_screenshot):
    """Test updating tags."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    success = metadata_service.update_metadata(
        metadata_id, tags=["epic", "boss-fight", "victory"]
    )

    assert success is True

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["tags"] == ["epic", "boss-fight", "victory"]


def test_update_metadata_notes(metadata_service, sample_screenshot):
    """Test updating notes."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    success = metadata_service.update_metadata(
        metadata_id, notes="This was an amazing moment!"
    )

    assert success is True

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["notes"] == "This was an amazing moment!"


def test_update_metadata_rating(metadata_service, sample_screenshot):
    """Test updating rating."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    success = metadata_service.update_metadata(metadata_id, rating=5)

    assert success is True

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["rating"] == 5


def test_update_metadata_invalid_rating(metadata_service, sample_screenshot):
    """Test updating with invalid rating (should be ignored)."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    # Try to set rating to 10 (invalid)
    metadata_service.update_metadata(metadata_id, rating=10)

    metadata = metadata_service.get_metadata(metadata_id)
    # Rating should remain None (not updated)
    assert metadata["rating"] is None


def test_update_metadata_favorite(metadata_service, sample_screenshot):
    """Test updating favorite status."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    success = metadata_service.update_metadata(metadata_id, is_favorite=True)

    assert success is True

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["is_favorite"] is True


def test_update_metadata_multiple_fields(metadata_service, sample_screenshot):
    """Test updating multiple fields at once."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    success = metadata_service.update_metadata(
        metadata_id,
        tags=["cool", "impressive"],
        notes="Great shot!",
        rating=4,
        is_favorite=True,
    )

    assert success is True

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["tags"] == ["cool", "impressive"]
    assert metadata["notes"] == "Great shot!"
    assert metadata["rating"] == 4
    assert metadata["is_favorite"] is True


def test_update_metadata_not_found(metadata_service):
    """Test updating non-existent metadata."""
    success = metadata_service.update_metadata(99999, tags=["test"])
    assert success is False


def test_update_metadata_partial(metadata_service, sample_screenshot):
    """Test updating only some fields leaves others unchanged."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    # Set initial values
    metadata_service.update_metadata(
        metadata_id, tags=["initial"], notes="Initial note", rating=3
    )

    # Update only tags
    metadata_service.update_metadata(metadata_id, tags=["updated"])

    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata["tags"] == ["updated"]  # Changed
    assert metadata["notes"] == "Initial note"  # Unchanged
    assert metadata["rating"] == 3  # Unchanged


# ============================================================================
# Search Tests
# ============================================================================


def test_search_by_game_id(metadata_service, sample_screenshot, sample_video):
    """Test searching by game ID."""
    # Create captures for different games
    metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )
    metadata_service.create_metadata(
        sample_video, "game-2", "Game 2", "sess-2", "video"
    )

    results = metadata_service.search_captures(game_id="game-1")

    assert len(results) == 1
    assert results[0]["game_id"] == "game-1"


def test_search_by_capture_type(metadata_service, sample_screenshot, sample_video):
    """Test searching by capture type."""
    metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )
    metadata_service.create_metadata(
        sample_video, "game-1", "Game 1", "sess-1", "video"
    )

    results = metadata_service.search_captures(capture_type="screenshot")

    assert len(results) == 1
    assert results[0]["capture_type"] == "screenshot"


def test_search_by_favorite(metadata_service, sample_screenshot, sample_video):
    """Test searching by favorite status."""
    id1 = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )
    id2 = metadata_service.create_metadata(
        sample_video, "game-1", "Game 1", "sess-1", "video"
    )

    # Mark one as favorite
    metadata_service.update_metadata(id1, is_favorite=True)

    results = metadata_service.search_captures(is_favorite=True)

    assert len(results) == 1
    assert results[0]["is_favorite"] is True


def test_search_by_min_rating(metadata_service, sample_screenshot, sample_video):
    """Test searching by minimum rating."""
    id1 = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )
    id2 = metadata_service.create_metadata(
        sample_video, "game-1", "Game 1", "sess-1", "video"
    )

    # Set different ratings
    metadata_service.update_metadata(id1, rating=5)
    metadata_service.update_metadata(id2, rating=2)

    results = metadata_service.search_captures(min_rating=4)

    assert len(results) == 1
    assert results[0]["rating"] == 5


def test_search_by_tags(metadata_service, sample_screenshot, sample_video):
    """Test searching by tags."""
    id1 = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )
    id2 = metadata_service.create_metadata(
        sample_video, "game-1", "Game 1", "sess-1", "video"
    )

    metadata_service.update_metadata(id1, tags=["epic", "boss-fight"])
    metadata_service.update_metadata(id2, tags=["funny", "glitch"])

    results = metadata_service.search_captures(tags=["epic"])

    assert len(results) == 1
    assert "epic" in results[0]["tags"]


def test_search_by_date_range(metadata_service, temp_dir):
    """Test searching by date range."""
    # Create files with different timestamps
    img1 = temp_dir / "old.png"
    img2 = temp_dir / "new.png"

    Image.new("RGB", (100, 100)).save(img1)
    Image.new("RGB", (100, 100)).save(img2)

    metadata_service.create_metadata(img1, "game-1", "Game 1", "sess-1", "screenshot")

    # Get current timestamp
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)

    # Search for today's captures
    results = metadata_service.search_captures(start_date=yesterday, end_date=tomorrow)

    assert len(results) >= 1


def test_search_with_pagination(metadata_service, temp_dir):
    """Test search pagination."""
    # Create multiple captures
    for i in range(15):
        img = temp_dir / f"screenshot_{i:03d}.png"
        Image.new("RGB", (100, 100)).save(img)
        metadata_service.create_metadata(
            img, "game-1", "Game 1", "sess-1", "screenshot"
        )

    # Get first page
    results_page1 = metadata_service.search_captures(limit=10, offset=0)
    assert len(results_page1) == 10

    # Get second page
    results_page2 = metadata_service.search_captures(limit=10, offset=10)
    assert len(results_page2) == 5


def test_search_combined_filters(metadata_service, temp_dir):
    """Test searching with multiple filters combined."""
    # Create captures with different attributes
    for i in range(5):
        img = temp_dir / f"screenshot_{i:03d}.png"
        Image.new("RGB", (100, 100)).save(img)
        metadata_id = metadata_service.create_metadata(
            img, "game-1", "Game 1", "sess-1", "screenshot"
        )

        if i < 2:
            metadata_service.update_metadata(metadata_id, rating=5, is_favorite=True)

    # Search for favorites with high rating
    results = metadata_service.search_captures(is_favorite=True, min_rating=4)

    assert len(results) == 2


# ============================================================================
# Game Captures Tests
# ============================================================================


def test_get_game_captures(metadata_service, temp_dir):
    """Test getting all captures for a game."""
    # Create different types of captures
    screenshot = temp_dir / "screenshot.png"
    video = temp_dir / "video.mp4"
    replay = temp_dir / "replay.mp4"

    Image.new("RGB", (100, 100)).save(screenshot)
    video.write_text("fake video")
    replay.write_text("fake replay")

    metadata_service.create_metadata(
        screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )
    metadata_service.create_metadata(video, "game-1", "Game 1", "sess-1", "video")
    metadata_service.create_metadata(replay, "game-1", "Game 1", "sess-1", "replay")

    captures = metadata_service.get_game_captures("game-1")

    assert len(captures["screenshots"]) == 1
    assert len(captures["videos"]) == 1
    assert len(captures["replays"]) == 1


def test_get_game_captures_empty(metadata_service):
    """Test getting captures for game with no captures."""
    captures = metadata_service.get_game_captures("nonexistent-game")

    assert captures["screenshots"] == []
    assert captures["videos"] == []
    assert captures["replays"] == []


# ============================================================================
# Delete Tests
# ============================================================================


def test_delete_metadata(metadata_service, sample_screenshot):
    """Test deleting metadata."""
    metadata_id = metadata_service.create_metadata(
        sample_screenshot, "game-1", "Game 1", "sess-1", "screenshot"
    )

    success = metadata_service.delete_metadata(metadata_id)
    assert success is True

    # Verify it's gone
    metadata = metadata_service.get_metadata(metadata_id)
    assert metadata is None


def test_delete_metadata_not_found(metadata_service):
    """Test deleting non-existent metadata."""
    success = metadata_service.delete_metadata(99999)
    assert success is False


# ============================================================================
# Statistics Tests
# ============================================================================


def test_get_statistics(metadata_service, temp_dir):
    """Test getting overall statistics."""
    # Create various captures
    for i in range(3):
        img = temp_dir / f"screenshot_{i}.png"
        Image.new("RGB", (100, 100)).save(img)
        metadata_id = metadata_service.create_metadata(
            img, f"game-{i % 2}", f"Game {i % 2}", "sess-1", "screenshot"
        )

        if i == 0:
            metadata_service.update_metadata(metadata_id, is_favorite=True)

    video = temp_dir / "video.mp4"
    video.write_text("fake video")
    metadata_service.create_metadata(video, "game-1", "Game 1", "sess-1", "video")

    stats = metadata_service.get_statistics()

    assert stats["total_captures"] == 4
    assert stats["total_screenshots"] == 3
    assert stats["total_videos"] == 1
    assert stats["total_replays"] == 0
    assert stats["favorites_count"] == 1
    assert stats["games_count"] == 2
    assert stats["total_size_bytes"] > 0
    assert stats["total_size_mb"] > 0


def test_get_statistics_empty(metadata_service):
    """Test statistics with no captures."""
    stats = metadata_service.get_statistics()

    assert stats["total_captures"] == 0
    assert stats["total_screenshots"] == 0
    assert stats["total_videos"] == 0
    assert stats["favorites_count"] == 0
    assert stats["total_size_bytes"] == 0
