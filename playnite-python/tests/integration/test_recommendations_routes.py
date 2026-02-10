"""Integration tests for recommendations API endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.playnite_python.api.app import app


@pytest.fixture
def client():
    """Create test client for API."""
    return TestClient(app)


@pytest.fixture
def sample_request_data():
    """Sample request data for recommendations."""
    return {
        "user_id": "test_user",
        "library": [
            {
                "game_id": "1",
                "name": "Dark Souls",
                "genres": ["RPG", "Action"],
                "developers": ["FromSoftware"],
                "tags": ["Difficult"],
                "playtime_seconds": 72000,
                "user_score": 90,
                "community_score": 89,
                "favorite": True,
                "hidden": False
            },
            {
                "game_id": "2",
                "name": "Elden Ring",
                "genres": ["RPG", "Action"],
                "developers": ["FromSoftware"],
                "tags": ["Open World"],
                "playtime_seconds": 0,
                "community_score": 95,
                "hidden": False
            },
            {
                "game_id": "3",
                "name": "Stardew Valley",
                "genres": ["Simulation"],
                "developers": ["ConcernedApe"],
                "playtime_seconds": 0,
                "community_score": 92,
                "hidden": False
            }
        ],
        "limit": 5
    }


def test_generate_recommendations_success(client, sample_request_data):
    """Test successful recommendation generation."""
    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0
    assert len(data) <= 5

    # Check recommendation structure
    for rec in data:
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "factors" in rec


def test_generate_recommendations_empty_library(client):
    """Test recommendations with empty library."""
    request_data = {
        "user_id": "test_user",
        "library": [],
        "limit": 5
    }

    response = client.post("/api/v1/recommendations/generate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_generate_recommendations_with_context(client, sample_request_data):
    """Test recommendations with context."""
    sample_request_data["context"] = {
        "mood": "relaxing",
        "time_of_day": "evening"
    }

    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_generate_recommendations_respects_limit(client, sample_request_data):
    """Test that limit parameter is respected."""
    sample_request_data["limit"] = 2

    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 2


def test_generate_recommendations_missing_user_id(client):
    """Test recommendations without user_id."""
    request_data = {
        "library": [
            {
                "game_id": "1",
                "name": "Test Game",
                "genres": ["Action"]
            }
        ],
        "limit": 5
    }

    response = client.post("/api/v1/recommendations/generate", json=request_data)

    # Should return 422 for validation error
    assert response.status_code == 422


def test_generate_recommendations_invalid_limit(client, sample_request_data):
    """Test recommendations with invalid limit."""
    sample_request_data["limit"] = -1

    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    # Should handle gracefully or return validation error
    assert response.status_code in [200, 422]


def test_generate_recommendations_large_library(client):
    """Test recommendations with large library."""
    # Create library with 100 games
    library = []
    for i in range(100):
        library.append({
            "game_id": str(i),
            "name": f"Game {i}",
            "genres": ["Action"],
            "playtime_seconds": 0 if i > 10 else 1000,
            "community_score": 80 + (i % 20),
            "hidden": False
        })

    request_data = {
        "user_id": "test_user",
        "library": library,
        "limit": 10
    }

    response = client.post("/api/v1/recommendations/generate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 10


def test_generate_recommendations_returns_sorted(client, sample_request_data):
    """Test that recommendations are sorted by score."""
    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response.status_code == 200
    data = response.json()

    if len(data) > 1:
        scores = [rec["score"] for rec in data]
        assert scores == sorted(scores, reverse=True)


def test_generate_recommendations_includes_game_names(client, sample_request_data):
    """Test that recommendations include game names."""
    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response.status_code == 200
    data = response.json()

    for rec in data:
        assert "game_name" in rec
        # Verify game name matches library
        game = next((g for g in sample_request_data["library"] if g["game_id"] == rec["game_id"]), None)
        if game:
            assert rec["game_name"] == game["name"]


def test_generate_recommendations_content_type(client, sample_request_data):
    """Test that response has correct content type."""
    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


def test_generate_recommendations_performance(client, sample_request_data):
    """Test that recommendations are generated quickly."""
    import time

    start = time.time()
    response = client.post("/api/v1/recommendations/generate", json=sample_request_data)
    duration = time.time() - start

    assert response.status_code == 200
    # Should complete in under 1 second for small library
    assert duration < 1.0


def test_generate_recommendations_idempotent(client, sample_request_data):
    """Test that same request generates consistent recommendations."""
    response1 = client.post("/api/v1/recommendations/generate", json=sample_request_data)
    response2 = client.post("/api/v1/recommendations/generate", json=sample_request_data)

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    # Should return same games (order may vary slightly due to scoring)
    game_ids1 = {rec["game_id"] for rec in data1}
    game_ids2 = {rec["game_id"] for rec in data2}

    # At least 80% overlap expected
    overlap = len(game_ids1 & game_ids2)
    total = len(game_ids1 | game_ids2)
    assert overlap / total >= 0.8 if total > 0 else True
