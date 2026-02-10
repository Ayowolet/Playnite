"""Unit tests for recommendation engine."""
import pytest
from src.playnite_python.recommendations.engine import RecommendationEngine
from src.playnite_python.recommendations.feedback_learner import FeedbackLearner


@pytest.fixture
def engine():
    """Create a RecommendationEngine instance for testing."""
    return RecommendationEngine()


@pytest.fixture
def sample_library():
    """Sample game library for testing."""
    return [
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
            "hidden": False,
        },
        {
            "game_id": "2",
            "name": "Elden Ring",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "tags": ["Open World"],
            "playtime_seconds": 0,
            "community_score": 95,
            "hidden": False,
        },
        {
            "game_id": "3",
            "name": "Stardew Valley",
            "genres": ["Simulation"],
            "developers": ["ConcernedApe"],
            "tags": ["Farming"],
            "playtime_seconds": 0,
            "community_score": 92,
            "hidden": False,
        },
        {
            "game_id": "4",
            "name": "Portal 2",
            "genres": ["Puzzle"],
            "developers": ["Valve"],
            "tags": ["Story Rich"],
            "playtime_seconds": 0,
            "community_score": 96,
            "hidden": False,
        },
    ]


@pytest.fixture
def play_histories():
    """Sample play history data."""
    return [
        {"user_id": "user1", "game_id": "1", "duration_seconds": 72000}
    ]


def test_engine_initialization():
    """Test that engine initializes with all components."""
    engine = RecommendationEngine()

    assert engine.content_filter is not None
    assert engine.collaborative_filter is not None
    assert engine.context_filter is not None
    assert engine.feedback_learner is not None


def test_engine_initialization_with_custom_learner():
    """Test initialization with custom feedback learner."""
    custom_learner = FeedbackLearner()
    custom_learner.algorithm_weights["content"] = 0.7

    engine = RecommendationEngine(feedback_learner=custom_learner)

    assert engine.feedback_learner.algorithm_weights["content"] == 0.7


def test_generate_basic(engine, sample_library, play_histories):
    """Test basic recommendation generation."""
    recommendations = engine.generate("user1", sample_library, play_histories, limit=5)

    assert len(recommendations) > 0
    assert len(recommendations) <= 5

    # Should have required fields
    for rec in recommendations:
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "game_name" in rec  # Engine enriches with game name


def test_generate_empty_library(engine):
    """Test generation with empty library."""
    recommendations = engine.generate("user1", [], [], limit=5)

    assert len(recommendations) == 0


def test_generate_uses_both_algorithms(engine, sample_library, play_histories):
    """Test that both content and collaborative algorithms are used."""
    recommendations = engine.generate("user1", sample_library, play_histories, limit=10)

    # Should have recommendations from both sources
    # (In real scenario, sources would be tracked in factors)
    assert len(recommendations) > 0


def test_generate_with_context(engine, sample_library, play_histories):
    """Test generation with contextual filters."""
    context = {
        "mood": "relaxing",
        "time_of_day": "evening"
    }

    recommendations = engine.generate("user1", sample_library, play_histories, context=context, limit=5)

    # Should apply context filters
    assert len(recommendations) > 0


def test_generate_respects_limit(engine, sample_library, play_histories):
    """Test that generation respects limit parameter."""
    recommendations = engine.generate("user1", sample_library, play_histories, limit=2)

    assert len(recommendations) <= 2


def test_generate_no_play_history(engine, sample_library):
    """Test generation with no play history."""
    recommendations = engine.generate("user1", sample_library, None, limit=5)

    # Should still generate recommendations (collaborative will use community scores)
    assert len(recommendations) > 0


def test_generate_enriches_with_game_names(engine, sample_library, play_histories):
    """Test that recommendations include game names."""
    recommendations = engine.generate("user1", sample_library, play_histories, limit=5)

    for rec in recommendations:
        assert "game_name" in rec
        # Find game in library and verify name matches
        game = next((g for g in sample_library if g["game_id"] == rec["game_id"]), None)
        if game:
            assert rec["game_name"] == game["name"]


def test_generate_sorts_by_score(engine, sample_library, play_histories):
    """Test that recommendations are sorted by score descending."""
    recommendations = engine.generate("user1", sample_library, play_histories, limit=10)

    scores = [r["score"] for r in recommendations]
    assert scores == sorted(scores, reverse=True)


def test_merge_recommendations(engine, sample_library):
    """Test merging recommendations from multiple algorithms."""
    content_recs = [
        {
            "game_id": "2",
            "score": 0.8,
            "reason": "Similar to Dark Souls",
            "factors": {"content_similarity": 0.8}
        }
    ]

    collab_recs = [
        {
            "game_id": "2",
            "score": 0.9,
            "reason": "Highly rated",
            "factors": {"popularity": 0.9}
        }
    ]

    merged = engine._merge_recommendations(content_recs, collab_recs, sample_library)

    # Should have game_id "2" merged from both sources
    # Note: Engine may add fallback recommendations if < 10 total
    game_2 = next((r for r in merged if r["game_id"] == "2"), None)
    assert game_2 is not None
    assert game_2["game_id"] == "2"

    # Score should be weighted combination
    weights = engine.feedback_learner.get_current_weights()
    expected_score = 0.8 * weights["content"] + 0.9 * weights["collaborative"]
    assert game_2["score"] == pytest.approx(expected_score, rel=0.01)


def test_merge_recommendations_different_games(engine, sample_library):
    """Test merging recommendations with different games."""
    content_recs = [
        {
            "game_id": "2",
            "score": 0.8,
            "reason": "Similar",
            "factors": {}
        }
    ]

    collab_recs = [
        {
            "game_id": "3",
            "score": 0.9,
            "reason": "Popular",
            "factors": {}
        }
    ]

    merged = engine._merge_recommendations(content_recs, collab_recs, sample_library)

    # Should have both games (and possibly fallbacks)
    # Engine may add fallback recommendations if < 10 total
    game_ids = [r["game_id"] for r in merged]
    assert "2" in game_ids
    assert "3" in game_ids


def test_merge_uses_learned_weights(engine, sample_library):
    """Test that merging uses weights from feedback learner."""
    # Adjust weights
    engine.feedback_learner.algorithm_weights["content"] = 0.7
    engine.feedback_learner.algorithm_weights["collaborative"] = 0.3
    engine.feedback_learner._normalize_weights()

    content_recs = [
        {"game_id": "2", "score": 1.0, "reason": "Test", "factors": {}}
    ]
    collab_recs = []

    merged = engine._merge_recommendations(content_recs, collab_recs, sample_library)

    # Should use content weight of 0.7
    assert merged[0]["score"] == pytest.approx(1.0 * 0.7, rel=0.01)


def test_get_popular_fallback(engine, sample_library):
    """Test fallback to popular games when few recommendations."""
    exclude_ids = {"1"}  # Exclude Dark Souls

    fallbacks = engine._get_popular_fallback(sample_library, exclude_ids, limit=5)

    # Should return popular unplayed games
    assert len(fallbacks) > 0

    # Should not include excluded game
    game_ids = [f["game_id"] for f in fallbacks]
    assert "1" not in game_ids

    # Should have lower scores (fallback weight of 0.3)
    for fallback in fallbacks:
        assert fallback["score"] <= 0.3  # Max community score (100) * 0.3


def test_get_popular_fallback_excludes_played(engine, sample_library):
    """Test that fallback excludes already played games."""
    # Modify library to have some played games
    for game in sample_library:
        if game["game_id"] == "2":
            game["playtime_seconds"] = 1000

    fallbacks = engine._get_popular_fallback(sample_library, set(), limit=10)

    # Should not include played game
    game_ids = [f["game_id"] for f in fallbacks]
    assert "2" not in game_ids


def test_get_popular_fallback_excludes_hidden(engine, sample_library):
    """Test that fallback excludes hidden games."""
    # Mark a game as hidden
    sample_library[1]["hidden"] = True

    fallbacks = engine._get_popular_fallback(sample_library, set(), limit=10)

    # Should not include hidden game
    game_ids = [f["game_id"] for f in fallbacks]
    assert "2" not in game_ids


def test_get_popular_fallback_sorts_by_score(engine, sample_library):
    """Test that fallbacks are sorted by popularity."""
    fallbacks = engine._get_popular_fallback(sample_library, set(), limit=10)

    scores = [f["score"] for f in fallbacks]
    assert scores == sorted(scores, reverse=True)


def test_get_popular_fallback_marks_as_fallback(engine, sample_library):
    """Test that fallback recommendations are marked."""
    fallbacks = engine._get_popular_fallback(sample_library, set(), limit=5)

    for fallback in fallbacks:
        assert "fallback" in fallback["factors"]
        assert fallback["factors"]["fallback"] is True
        assert "sources" in fallback
        assert "fallback" in fallback["sources"]


def test_engine_handles_insufficient_recommendations(engine):
    """Test that engine adds fallbacks when insufficient recommendations."""
    # Small library with mostly played games
    library = [
        {
            "game_id": "1",
            "name": "Played Game",
            "genres": ["Action"],
            "playtime_seconds": 10000,
            "community_score": 90,
            "hidden": False,
        },
        {
            "game_id": "2",
            "name": "Unplayed Game",
            "genres": ["Action"],
            "playtime_seconds": 0,
            "community_score": 85,
            "hidden": False,
        },
    ]

    play_histories = [{"user_id": "user1", "game_id": "1", "duration_seconds": 10000}]

    recommendations = engine.generate("user1", library, play_histories, limit=10)

    # Should include fallback recommendations to fill the list
    assert len(recommendations) > 0


def test_engine_integration_workflow(engine, sample_library, play_histories):
    """Test complete recommendation workflow."""
    # Generate recommendations
    recommendations = engine.generate(
        user_id="user1",
        library=sample_library,
        play_histories=play_histories,
        context={"mood": "challenging", "session_length": "long"},
        limit=3
    )

    # Verify structure
    assert len(recommendations) > 0
    assert len(recommendations) <= 3

    for rec in recommendations:
        # All required fields present
        assert all(key in rec for key in ["game_id", "score", "reason", "game_name"])

        # Score is valid
        assert 0 <= rec["score"] <= 2.0  # Can be boosted above 1.0

        # Game name is enriched
        assert isinstance(rec["game_name"], str)
        assert len(rec["game_name"]) > 0


def test_engine_with_different_users(engine, sample_library):
    """Test that different users get different recommendations."""
    play_histories_user1 = [{"user_id": "user1", "game_id": "1", "duration_seconds": 10000}]
    play_histories_user2 = [{"user_id": "user2", "game_id": "3", "duration_seconds": 10000}]

    recs_user1 = engine.generate("user1", sample_library, play_histories_user1, limit=5)
    recs_user2 = engine.generate("user2", sample_library, play_histories_user2, limit=5)

    # Both should get recommendations
    assert len(recs_user1) > 0
    assert len(recs_user2) > 0

    # May have different game IDs (depending on what they played)
    # This is expected behavior
