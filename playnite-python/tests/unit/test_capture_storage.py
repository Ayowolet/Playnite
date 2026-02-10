"""Unit tests for capture storage."""
import pytest
from pathlib import Path
import tempfile
import shutil
from playnite_python.capture.storage import CaptureStorage


@pytest.fixture
def temp_storage():
    """Create temporary storage for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    storage = CaptureStorage(base_path=temp_dir)

    yield storage

    # Cleanup
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def test_storage_initialization(temp_storage):
    """Test storage initializes correctly."""
    assert temp_storage.base_path.exists()
    assert temp_storage.base_path.is_dir()


def test_get_game_directory(temp_storage):
    """Test game directory creation."""
    game_dir = temp_storage.get_game_directory("test-game-1")

    assert game_dir.exists()
    assert game_dir.is_dir()
    assert game_dir.name == "test-game-1"


def test_get_screenshot_path(temp_storage):
    """Test screenshot path generation."""
    import time

    path1 = temp_storage.get_screenshot_path("test-game-1")
    time.sleep(0.01)  # Ensure different counter/timestamp
    path2 = temp_storage.get_screenshot_path("test-game-1")

    # Both should be in screenshots directory
    assert path1.parent.name == "screenshots"
    assert path2.parent.name == "screenshots"

    # Should be PNG files
    assert path1.suffix == ".png"
    assert path2.suffix == ".png"

    # Path should be valid
    assert "screenshot_" in path1.name


def test_get_video_path(temp_storage):
    """Test video path generation."""
    path = temp_storage.get_video_path("test-game-1")

    # Should be in videos directory
    assert path.parent.name == "videos"

    # Should be MP4 file
    assert path.suffix == ".mp4"


def test_list_captures_empty(temp_storage):
    """Test listing captures for game with no captures."""
    captures = temp_storage.list_captures("test-game-1")

    assert "screenshots" in captures
    assert "videos" in captures
    assert len(captures["screenshots"]) == 0
    assert len(captures["videos"]) == 0


def test_list_captures_with_files(temp_storage):
    """Test listing captures with actual files."""
    game_id = "test-game-1"

    # Create some test files
    screenshot_path = temp_storage.get_screenshot_path(game_id)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_text("test screenshot")

    video_path = temp_storage.get_video_path(game_id)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_text("test video")

    # List captures
    captures = temp_storage.list_captures(game_id)

    assert len(captures["screenshots"]) == 1
    assert len(captures["videos"]) == 1
    assert captures["screenshots"][0] == screenshot_path
    assert captures["videos"][0] == video_path


def test_get_storage_usage_single_game(temp_storage):
    """Test storage usage calculation for single game."""
    game_id = "test-game-1"

    # Create test file
    screenshot_path = temp_storage.get_screenshot_path(game_id)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_text("test" * 1000)  # ~4KB

    usage = temp_storage.get_storage_usage(game_id)

    assert usage["game_id"] == game_id
    assert usage["size_bytes"] > 0  # Should have some size from the file


def test_get_storage_usage_total(temp_storage):
    """Test total storage usage across all games."""
    # Create captures for multiple games
    for i in range(3):
        game_id = f"test-game-{i}"
        screenshot_path = temp_storage.get_screenshot_path(game_id)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_text("test" * 1000)

    usage = temp_storage.get_storage_usage()

    assert usage["total_size_bytes"] > 0
    assert usage["game_count"] == 3
    assert usage["total_screenshots"] == 3
    assert usage["total_videos"] == 0


def test_delete_game_captures(temp_storage):
    """Test deleting all captures for a game."""
    game_id = "test-game-1"

    # Create captures
    screenshot_path = temp_storage.get_screenshot_path(game_id)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_text("test")

    game_dir = temp_storage.get_game_directory(game_id)
    assert game_dir.exists()

    # Delete
    success = temp_storage.delete_game_captures(game_id)

    assert success
    assert not game_dir.exists()


def test_delete_nonexistent_game(temp_storage):
    """Test deleting captures for non-existent game."""
    success = temp_storage.delete_game_captures("nonexistent-game")

    # Should return True (idempotent - already doesn't exist)
    assert success
