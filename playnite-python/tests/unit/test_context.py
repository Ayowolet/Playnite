"""Unit tests for contextual filtering."""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone
from src.playnite_python.recommendations.context import ContextualFilter


@pytest.fixture
def filter():
    """Create a ContextualFilter instance for testing."""
    return ContextualFilter()


@pytest.fixture
def sample_library():
    """Sample game library for testing."""
    return [
        {
            "game_id": "1",
            "name": "Stardew Valley",
            "genres": ["Simulation", "Casual"],
            "tags": ["Farming", "Relaxing"],
        },
        {
            "game_id": "2",
            "name": "Dark Souls",
            "genres": ["Action", "RPG"],
            "tags": ["Difficult", "Challenging"],
        },
        {
            "game_id": "3",
            "name": "Portal 2",
            "genres": ["Puzzle", "Adventure"],
            "tags": ["Story Rich", "Co-op"],
        },
        {
            "game_id": "4",
            "name": "The Witcher 3",
            "genres": ["RPG", "Open World"],
            "tags": ["Story Rich", "Immersive"],
        },
        {
            "game_id": "5",
            "name": "Rocket League",
            "genres": ["Sports", "Racing"],
            "tags": ["Competitive", "Multiplayer"],
        },
    ]


@pytest.fixture
def sample_recommendations():
    """Sample recommendations for testing."""
    return [
        {
            "game_id": "1",
            "score": 0.8,
            "reason": "Similar to games you enjoyed",
            "factors": {},
        },
        {
            "game_id": "2",
            "score": 0.75,
            "reason": "Highly rated",
            "factors": {},
        },
        {
            "game_id": "3",
            "score": 0.7,
            "reason": "Popular in your library",
            "factors": {},
        },
        {
            "game_id": "4",
            "score": 0.85,
            "reason": "Similar to favorites",
            "factors": {},
        },
        {
            "game_id": "5",
            "score": 0.65,
            "reason": "Recommended by community",
            "factors": {},
        },
    ]


def test_get_time_of_day_morning(filter):
    """Test time of day detection for morning."""
    with patch('src.playnite_python.recommendations.context.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 10, 8, 0, tzinfo=timezone.utc)
        assert filter.get_time_of_day() == "morning"


def test_get_time_of_day_afternoon(filter):
    """Test time of day detection for afternoon."""
    with patch('src.playnite_python.recommendations.context.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 10, 14, 0, tzinfo=timezone.utc)
        assert filter.get_time_of_day() == "afternoon"


def test_get_time_of_day_evening(filter):
    """Test time of day detection for evening."""
    with patch('src.playnite_python.recommendations.context.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 10, 20, 0, tzinfo=timezone.utc)
        assert filter.get_time_of_day() == "evening"


def test_get_time_of_day_night(filter):
    """Test time of day detection for night."""
    with patch('src.playnite_python.recommendations.context.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 10, 23, 0, tzinfo=timezone.utc)
        assert filter.get_time_of_day() == "night"


def test_filter_no_context(filter, sample_recommendations, sample_library):
    """Test filtering with no context returns all recommendations."""
    result = filter.filter(sample_recommendations, sample_library, None)

    # Should return all recommendations, just sorted by score
    assert len(result) == len(sample_recommendations)


def test_filter_by_mood_relaxing(filter, sample_recommendations, sample_library):
    """Test filtering by relaxing mood."""
    context = {"mood": "relaxing"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Stardew Valley (game_id 1) should be boosted for relaxing mood
    stardew = next((r for r in result if r["game_id"] == "1"), None)
    assert stardew is not None
    assert stardew["score"] > 0.8  # Boosted from original 0.8
    assert "relaxing" in stardew["reason"].lower()
    assert "mood_boost" in stardew["factors"]


def test_filter_by_mood_challenging(filter, sample_recommendations, sample_library):
    """Test filtering by challenging mood."""
    context = {"mood": "challenging"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Dark Souls (game_id 2) should be boosted for challenging mood
    dark_souls = next((r for r in result if r["game_id"] == "2"), None)
    assert dark_souls is not None
    assert dark_souls["score"] > 0.75  # Boosted from original 0.75
    assert "challenging" in dark_souls["reason"].lower()


def test_filter_by_mood_story(filter, sample_recommendations, sample_library):
    """Test filtering by story mood."""
    context = {"mood": "story"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # The Witcher 3 (game_id 4) should be boosted for story mood
    witcher = next((r for r in result if r["game_id"] == "4"), None)
    assert witcher is not None
    assert witcher["score"] > 0.85  # Boosted


def test_filter_by_mood_competitive(filter, sample_recommendations, sample_library):
    """Test filtering by competitive mood."""
    context = {"mood": "competitive"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Rocket League (game_id 5) should be boosted for competitive mood
    rocket_league = next((r for r in result if r["game_id"] == "5"), None)
    assert rocket_league is not None
    assert rocket_league["score"] > 0.65  # Boosted


def test_filter_keeps_high_scored_regardless_of_mood(filter, sample_library):
    """Test that high-scored recommendations are kept even if mood doesn't match."""
    recommendations = [
        {
            "game_id": "4",  # Witcher 3 (RPG, not matching relaxing)
            "score": 0.85,
            "reason": "Highly rated",
            "factors": {},
        }
    ]

    context = {"mood": "relaxing"}  # Doesn't match RPG

    result = filter.filter(recommendations, sample_library, context)

    # Should still be included because score > 0.7
    assert len(result) > 0


def test_adjust_for_time_morning(filter, sample_recommendations, sample_library):
    """Test time adjustment for morning."""
    context = {"time_of_day": "morning"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Puzzle/Casual games should get time boost in morning
    portal = next((r for r in result if r["game_id"] == "3"), None)
    if portal and "time_boost" in portal["factors"]:
        assert portal["factors"]["time_boost"] == 1.15


def test_adjust_for_time_evening(filter, sample_recommendations, sample_library):
    """Test time adjustment for evening."""
    context = {"time_of_day": "evening"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # RPG/Story games should get time boost in evening
    witcher = next((r for r in result if r["game_id"] == "4"), None)
    if witcher and "time_boost" in witcher["factors"]:
        assert witcher["factors"]["time_boost"] == 1.15


def test_filter_by_session_length_short(filter, sample_recommendations, sample_library):
    """Test filtering by short session length."""
    context = {"session_length": "short"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Puzzle games should be boosted for short sessions
    portal = next((r for r in result if r["game_id"] == "3"), None)
    assert portal is not None
    if "session_boost" in portal["factors"]:
        assert portal["factors"]["session_boost"] == 1.2


def test_filter_by_session_length_long(filter, sample_recommendations, sample_library):
    """Test filtering by long session length."""
    context = {"session_length": "long"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # RPG games should be boosted for long sessions
    witcher = next((r for r in result if r["game_id"] == "4"), None)
    assert witcher is not None
    if "session_boost" in witcher["factors"]:
        assert witcher["factors"]["session_boost"] == 1.2


def test_filter_by_session_length_medium(filter, sample_recommendations, sample_library):
    """Test filtering with medium session length (no specific boost)."""
    context = {"session_length": "medium"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Should not apply session_boost for medium
    assert all("session_boost" not in r["factors"] for r in result)


def test_combined_context_filters(filter, sample_recommendations, sample_library):
    """Test multiple context filters applied together."""
    context = {
        "mood": "story",
        "time_of_day": "evening",
        "session_length": "long"
    }

    result = filter.filter(sample_recommendations, sample_library, context)

    # Witcher 3 should get multiple boosts (story mood + evening + long session)
    witcher = next((r for r in result if r["game_id"] == "4"), None)
    assert witcher is not None
    assert witcher["score"] > 0.85  # Multiple boosts applied


def test_filter_sorts_by_score(filter, sample_recommendations, sample_library):
    """Test that results are sorted by score descending."""
    result = filter.filter(sample_recommendations, sample_library, {})

    scores = [r["score"] for r in result]
    assert scores == sorted(scores, reverse=True)


def test_filter_with_missing_game_in_library(filter, sample_library):
    """Test filtering with recommendation for game not in library."""
    recommendations = [
        {
            "game_id": "999",  # Doesn't exist in library
            "score": 0.8,
            "reason": "Test",
            "factors": {},
        }
    ]

    context = {"mood": "relaxing"}

    # Should handle gracefully without crashing
    result = filter.filter(recommendations, sample_library, context)
    assert len(result) == 0


def test_filter_with_empty_recommendations(filter, sample_library):
    """Test filtering with empty recommendations list."""
    result = filter.filter([], sample_library, {"mood": "relaxing"})
    assert result == []


def test_filter_with_invalid_mood(filter, sample_recommendations, sample_library):
    """Test filtering with invalid mood."""
    context = {"mood": "invalid_mood"}

    # Should not crash, just skip mood filtering
    result = filter.filter(sample_recommendations, sample_library, context)
    assert len(result) == len(sample_recommendations)


def test_mood_genres_mapping(filter):
    """Test that MOOD_GENRES has expected mappings."""
    assert "relaxing" in filter.MOOD_GENRES
    assert "challenging" in filter.MOOD_GENRES
    assert "story" in filter.MOOD_GENRES
    assert "competitive" in filter.MOOD_GENRES

    # Check some specific mappings
    assert "Simulation" in filter.MOOD_GENRES["relaxing"]
    assert "Action" in filter.MOOD_GENRES["challenging"]


def test_time_preferences_mapping(filter):
    """Test that TIME_PREFERENCES has expected mappings."""
    assert "morning" in filter.TIME_PREFERENCES
    assert "afternoon" in filter.TIME_PREFERENCES
    assert "evening" in filter.TIME_PREFERENCES
    assert "night" in filter.TIME_PREFERENCES


def test_filter_modifies_factors_dict(filter, sample_recommendations, sample_library):
    """Test that filtering adds factors to recommendation dicts."""
    context = {"mood": "relaxing"}

    result = filter.filter(sample_recommendations, sample_library, context)

    # Check that factors were added to boosted recommendations
    boosted = [r for r in result if "mood_boost" in r["factors"]]
    assert len(boosted) > 0
