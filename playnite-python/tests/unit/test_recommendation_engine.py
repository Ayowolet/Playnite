"""Unit tests for main recommendation engine."""
import pytest
from playnite_python.recommendations.engine import RecommendationEngine


@pytest.fixture
def sample_library():
    """Sample game library for testing."""
    return [
        {
            "game_id": "1",
            "name": "Dark Souls",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "playtime_seconds": 72000,
            "user_score": 90,
            "community_score": 89,
            "favorite": True,
            "hidden": False,
        },
        {
            "game_id": "2",
            "name": "Elden Ring",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "playtime_seconds": 0,
            "community_score": 95,
            "hidden": False,
        },
        {
            "game_id": "3",
            "name": "Stardew Valley",
            "genres": ["Simulation", "Indie"],
            "developers": ["ConcernedApe"],
            "playtime_seconds": 0,
            "community_score": 92,
            "hidden": False,
        },
        {
            "game_id": "4",
            "name": "Portal 2",
            "genres": ["Puzzle", "Platformer"],
            "developers": ["Valve"],
            "playtime_seconds": 18000,
            "user_score": 95,
            "community_score": 95,
            "favorite": True,
            "hidden": False,
        },
        {
            "game_id": "5",
            "name": "Half-Life 3",
            "genres": ["FPS", "Action"],
            "developers": ["Valve"],
            "playtime_seconds": 0,
            "community_score": 50,
            "hidden": False,
        },
    ]


def test_engine_initialization():
    """Test engine initializes correctly."""
    engine = RecommendationEngine()

    assert engine.content_filter is not None
    assert engine.collaborative_filter is not None
    assert engine.context_filter is not None


def test_generate_basic(sample_library):
    """Test basic recommendation generation."""
    engine = RecommendationEngine()

    recommendations = engine.generate(
        user_id="test-user",
        library=sample_library,
        play_histories=[],
        limit=5
    )

    assert len(recommendations) > 0
    assert len(recommendations) <= 5


def test_generate_with_context(sample_library):
    """Test recommendation generation with context."""
    engine = RecommendationEngine()

    context = {
        "mood": "challenging",
        "time_of_day": "evening"
    }

    recommendations = engine.generate(
        user_id="test-user",
        library=sample_library,
        play_histories=[],
        context=context,
        limit=5
    )

    assert len(recommendations) > 0


def test_recommendation_structure(sample_library):
    """Test that recommendations have correct structure."""
    engine = RecommendationEngine()

    recommendations = engine.generate(
        user_id="test-user",
        library=sample_library,
        play_histories=[],
        limit=5
    )

    if recommendations:
        rec = recommendations[0]

        # Required fields
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "factors" in rec
        assert "sources" in rec
        assert "game_name" in rec

        # Score validation
        assert isinstance(rec["score"], (int, float))
        assert rec["score"] >= 0

        # Sources should be a list
        assert isinstance(rec["sources"], list)


def test_generate_empty_library():
    """Test generation with empty library."""
    engine = RecommendationEngine()

    recommendations = engine.generate(
        user_id="test-user",
        library=[],
        play_histories=[],
        limit=5
    )

    assert len(recommendations) == 0


def test_generate_respects_limit(sample_library):
    """Test that limit parameter is respected."""
    engine = RecommendationEngine()

    for limit in [1, 3, 10]:
        recommendations = engine.generate(
            user_id="test-user",
            library=sample_library,
            play_histories=[],
            limit=limit
        )

        assert len(recommendations) <= limit


def test_recommendations_sorted_by_score(sample_library):
    """Test that recommendations are sorted by score (descending)."""
    engine = RecommendationEngine()

    recommendations = engine.generate(
        user_id="test-user",
        library=sample_library,
        play_histories=[],
        limit=10
    )

    if len(recommendations) > 1:
        scores = [r["score"] for r in recommendations]
        assert scores == sorted(scores, reverse=True)


def test_no_duplicate_recommendations(sample_library):
    """Test that each game is recommended at most once."""
    engine = RecommendationEngine()

    recommendations = engine.generate(
        user_id="test-user",
        library=sample_library,
        play_histories=[],
        limit=10
    )

    game_ids = [r["game_id"] for r in recommendations]
    assert len(game_ids) == len(set(game_ids))
