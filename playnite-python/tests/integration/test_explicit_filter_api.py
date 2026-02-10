"""Integration tests for explicit filtering through the API."""
import pytest
from fastapi.testclient import TestClient
from src.playnite_python.api.app import app


@pytest.fixture
def client():
    """Create test client for API."""
    return TestClient(app)


@pytest.fixture
def sample_library_with_filters():
    """Sample game library with filter fields for API testing."""
    return [
    {
        "game_id": "1",
        "name": "Portal 2",
        "genres": ["Puzzle"],
        "platforms": ["PC"],
        "features": ["Single Player", "Co-op"],
        "playtime_seconds": 0,
        "time_to_complete": 8,
        "difficulty": "easy",
        "vr_compatible": False,
        "vr_required": False,
    },
    {
        "game_id": "2",
        "name": "Dark Souls",
        "genres": ["Action", "RPG"],
        "platforms": ["PC"],
        "features": ["Single Player"],
        "playtime_seconds": 72000,  # Played
        "time_to_complete": 60,
        "difficulty": "extreme",
        "vr_compatible": False,
        "vr_required": False,
    },
    {
        "game_id": "3",
        "name": "Stardew Valley",
        "genres": ["Simulation"],
        "platforms": ["PC", "Nintendo Switch"],
        "features": ["Single Player", "Multiplayer"],
        "playtime_seconds": 0,
        "time_to_complete": 45,
        "difficulty": "easy",
        "vr_compatible": False,
        "vr_required": False,
    },
    {
        "game_id": "4",
        "name": "Half-Life: Alyx",
        "genres": ["Action", "VR"],
        "platforms": ["PC"],
        "features": ["Single Player"],
        "playtime_seconds": 0,
        "time_to_complete": 12,
        "difficulty": "medium",
        "vr_compatible": True,
        "vr_required": True,
    },
    ]


def test_filter_by_completion_time_short_games(client, sample_library_with_filters):
    """Test API filtering for short games (<10 hours)."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"max_completion_hours": 10},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should only recommend Portal 2 (8h)
        # Dark Souls excluded (played), Stardew Valley (45h too long), Half-Life: Alyx (12h too long)
    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "1" in game_ids  # Portal 2
    assert "3" not in game_ids  # Stardew Valley (too long)
    assert "4" not in game_ids  # Half-Life: Alyx (too long)


def test_filter_by_completion_time_long_games(client, sample_library_with_filters):
    """Test API filtering for long games (>50 hours)."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"min_completion_hours": 50},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should not recommend any since Dark Souls is already played
        # If it weren't played, Dark Souls (60h) would be recommended
    assert data["count"] == 0


def test_filter_by_difficulty(client, sample_library_with_filters):
    """Test API filtering by difficulty."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"difficulty_levels": ["easy"]},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "1" in game_ids  # Portal 2 (easy)
    assert "3" in game_ids  # Stardew Valley (easy)
    assert "4" not in game_ids  # Half-Life: Alyx (medium)


def test_filter_by_multiplayer(client, sample_library_with_filters):
    """Test API filtering by multiplayer support."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"multiplayer_only": True},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "1" in game_ids  # Portal 2 (has Co-op)
    assert "3" in game_ids  # Stardew Valley (has Multiplayer)
    assert "4" not in game_ids  # Half-Life: Alyx (single-player only)


def test_filter_by_vr(client, sample_library_with_filters):
    """Test API filtering by VR compatibility."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"vr_compatible": True},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should only recommend Half-Life: Alyx
    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "4" in game_ids  # Half-Life: Alyx
    assert len(game_ids) == 1


def test_filter_by_platform(client, sample_library_with_filters):
    """Test API filtering by platform."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"platforms": ["Nintendo Switch"]},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should only recommend Stardew Valley (has Switch)
    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "3" in game_ids  # Stardew Valley
        # Others only have PC


def test_combine_multiple_filters(client, sample_library_with_filters):
    """Test API with multiple filters combined."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {
                "max_completion_hours": 50,
                "difficulty_levels": ["easy", "medium"],
                "platforms": ["PC"],
            },
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should include: Portal 2 (8h, easy, PC), Stardew Valley (45h, easy, PC),
        # Half-Life: Alyx (12h, medium, PC)
    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "1" in game_ids  # Portal 2
    assert "3" in game_ids  # Stardew Valley
    assert "4" in game_ids  # Half-Life: Alyx


def test_context_and_filters_together(client, sample_library_with_filters):
    """Test API with both context (mood) and explicit filters."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "context": {"mood": "relaxing", "session_length": "short"},
            "filters": {"max_completion_hours": 15, "difficulty_levels": ["easy"]},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should apply both context boosts AND explicit filters
        # Portal 2 (8h, easy) and possibly Stardew Valley if relaxing boost applies
    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert len(game_ids) > 0

        # Verify recommendations have required fields
    for rec in data["recommendations"]:
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "recommendation_id" in rec


def test_filters_with_no_matches_returns_empty(client, sample_library_with_filters):
    """Test API filters with no matching games returns empty."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {
                "min_completion_hours": 100,  # No game this long
            },
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert len(data["recommendations"]) == 0


def test_no_filters_returns_all_eligible(client, sample_library_with_filters):
    """Test API without filters returns all eligible games."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Should return recommendations for all unplayed games
        # Dark Souls excluded (already played)
    game_ids = [rec["game_id"] for rec in data["recommendations"]]
    assert "1" in game_ids  # Portal 2
    assert "3" in game_ids  # Stardew Valley
    assert "4" in game_ids  # Half-Life: Alyx


def test_clear_filters_via_null(client, sample_library_with_filters):
    """Test that filters can be 'cleared' by not providing them."""
    
        # First request with filters
    response1 = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"max_completion_hours": 10},
            "limit": 10,
        },
    )

    data1 = response1.json()
    filtered_count = data1["count"]

        # Second request without filters (cleared)
    response2 = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "limit": 10,
        },
    )

    data2 = response2.json()
    unfiltered_count = data2["count"]

        # Unfiltered should have more or equal recommendations
    assert unfiltered_count >= filtered_count


def test_response_structure_with_filters(client, sample_library_with_filters):
    """Test that API response structure is correct with filters."""
    
    response = client.post(
        "/api/v1/recommendations/generate",
        json={
            "user_id": "test-user",
            "library": sample_library_with_filters,
            "filters": {"difficulty_levels": ["easy"]},
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()

        # Verify response structure
    assert "recommendations" in data
    assert "count" in data
    assert "generated_at" in data
    assert "model_version" in data

        # Verify each recommendation has required fields
    for rec in data["recommendations"]:
        assert "recommendation_id" in rec
        assert "game_id" in rec
        assert "game_name" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "factors" in rec
