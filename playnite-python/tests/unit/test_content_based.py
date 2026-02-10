"""Unit tests for content-based filtering."""
import pytest
from playnite_python.recommendations.content_based import ContentBasedFilter


@pytest.fixture
def sample_library():
    """Sample game library for testing."""
    return [
        {
            "game_id": "1",
            "name": "Dark Souls",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "tags": ["Souls-like", "Difficult"],
            "playtime_seconds": 72000,
            "user_score": 90,
            "favorite": True,
            "hidden": False,
        },
        {
            "game_id": "2",
            "name": "Elden Ring",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "tags": ["Souls-like", "Open World"],
            "playtime_seconds": 0,
            "hidden": False,
        },
        {
            "game_id": "3",
            "name": "Stardew Valley",
            "genres": ["Simulation", "Indie"],
            "developers": ["ConcernedApe"],
            "tags": ["Farming", "Relaxing"],
            "playtime_seconds": 0,
            "hidden": False,
        },
        {
            "game_id": "4",
            "name": "The Witcher 3",
            "genres": ["RPG", "Action"],
            "developers": ["CD Projekt Red"],
            "tags": ["Open World", "Story Rich"],
            "playtime_seconds": 0,
            "hidden": False,
        },
        {
            "game_id": "5",
            "name": "Bloodborne",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "tags": ["Souls-like", "Gothic"],
            "playtime_seconds": 0,
            "hidden": False,
        },
    ]


def test_build_game_features(sample_library):
    """Test feature string generation."""
    filter = ContentBasedFilter()

    features = filter.build_game_features(sample_library[0])  # Dark Souls

    # Should include genres (weighted 3x)
    assert "rpg" in features.lower()
    assert "action" in features.lower()

    # Should include developers (weighted 2x)
    assert "fromsoftware" in features.lower()

    # Should include tags (weighted 2x)
    assert "souls-like" in features.lower()


def test_identify_enjoyed_games(sample_library):
    """Test identification of enjoyed games."""
    filter = ContentBasedFilter()

    enjoyed = filter.identify_enjoyed_games(sample_library, min_playtime=3600)

    # Dark Souls should be identified (favorite + high playtime + high score)
    assert any(g["game_id"] == "1" for g in enjoyed)

    # Others should not be included (no playtime/rating)
    assert len(enjoyed) == 1


def test_calculate_similarity(sample_library):
    """Test similarity matrix calculation."""
    filter = ContentBasedFilter()

    similarity_matrix = filter.calculate_similarity(sample_library)

    # Should be square matrix
    assert similarity_matrix.shape == (len(sample_library), len(sample_library))

    # Diagonal should be 1.0 (game is identical to itself)
    for i in range(len(sample_library)):
        assert abs(similarity_matrix[i][i] - 1.0) < 0.01

    # Dark Souls (0) and Elden Ring (1) should be very similar
    assert similarity_matrix[0][1] > 0.7

    # Dark Souls (0) and Stardew Valley (2) should be dissimilar
    assert similarity_matrix[0][2] < 0.3


def test_recommend_basic(sample_library):
    """Test basic recommendation generation."""
    filter = ContentBasedFilter()

    recommendations = filter.recommend({}, sample_library, limit=5)

    # Should return recommendations
    assert len(recommendations) > 0
    assert len(recommendations) <= 5

    # Should not recommend already-played game (Dark Souls)
    assert not any(r["game_id"] == "1" for r in recommendations)

    # Should recommend similar games (Elden Ring, Bloodborne)
    recommended_ids = [r["game_id"] for r in recommendations]
    assert "2" in recommended_ids or "5" in recommended_ids  # Elden Ring or Bloodborne


def test_recommend_with_similarity_threshold(sample_library):
    """Test recommendation with custom similarity threshold."""
    filter = ContentBasedFilter()

    # Very high threshold should return fewer results
    high_threshold = filter.recommend({}, sample_library, limit=10, similarity_threshold=0.8)

    # Lower threshold should return more results
    low_threshold = filter.recommend({}, sample_library, limit=10, similarity_threshold=0.3)

    assert len(low_threshold) >= len(high_threshold)


def test_recommend_empty_library():
    """Test recommendation with empty library."""
    filter = ContentBasedFilter()

    recommendations = filter.recommend({}, [], limit=5)

    assert len(recommendations) == 0


def test_recommend_single_game():
    """Test recommendation with single game library."""
    filter = ContentBasedFilter()

    single_game = [
        {
            "game_id": "1",
            "name": "Test Game",
            "genres": ["Action"],
            "playtime_seconds": 0,
            "hidden": False,
        }
    ]

    recommendations = filter.recommend({}, single_game, limit=5)

    # Can't recommend from single game
    assert len(recommendations) == 0


def test_skip_hidden_games(sample_library):
    """Test that hidden games are not recommended."""
    filter = ContentBasedFilter()

    # Mark Elden Ring as hidden
    sample_library[1]["hidden"] = True

    recommendations = filter.recommend({}, sample_library, limit=10)

    # Elden Ring should not be in recommendations
    assert not any(r["game_id"] == "2" for r in recommendations)


def test_recommendation_structure(sample_library):
    """Test that recommendations have correct structure."""
    filter = ContentBasedFilter()

    recommendations = filter.recommend({}, sample_library, limit=5)

    if recommendations:
        rec = recommendations[0]

        # Should have required fields
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "factors" in rec

        # Score should be valid
        assert 0 <= rec["score"] <= 1

        # Factors should include similarity
        assert "content_similarity" in rec["factors"]
