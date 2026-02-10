"""Unit tests for collaborative filtering."""
import pytest
from src.playnite_python.recommendations.collaborative import CollaborativeFilter


@pytest.fixture
def filter():
    """Create a CollaborativeFilter instance for testing."""
    return CollaborativeFilter()


@pytest.fixture
def sample_library():
    """Sample game library for testing."""
    return [
        {
            "game_id": "1",
            "name": "The Witcher 3",
            "community_score": 95,
            "critic_score": 92,
            "hidden": False,
        },
        {
            "game_id": "2",
            "name": "Cyberpunk 2077",
            "community_score": 70,
            "critic_score": 75,
            "hidden": False,
        },
        {
            "game_id": "3",
            "name": "Portal 2",
            "community_score": 98,
            "critic_score": 95,
            "hidden": False,
        },
        {
            "game_id": "4",
            "name": "Unpopular Game",
            "community_score": 40,
            "critic_score": 35,
            "hidden": False,
        },
        {
            "game_id": "5",
            "name": "Hidden Game",
            "community_score": 90,
            "critic_score": 88,
            "hidden": True,
        },
    ]


@pytest.fixture
def play_histories():
    """Sample play history data."""
    return [
        {"user_id": "user1", "game_id": "1"},  # User1 played The Witcher 3
        {"user_id": "user2", "game_id": "2"},  # User2 played Cyberpunk
    ]


def test_collaborative_filter_initialization(filter):
    """Test collaborative filter initializes correctly."""
    assert filter.user_game_matrix is None


def test_recommend_basic(filter, sample_library, play_histories):
    """Test basic collaborative recommendations."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=5)

    # Should return recommendations
    assert len(recommendations) > 0
    assert len(recommendations) <= 5

    # Should not recommend already played game (The Witcher 3)
    game_ids = [r["game_id"] for r in recommendations]
    assert "1" not in game_ids


def test_recommend_only_highly_rated(filter, sample_library, play_histories):
    """Test that only highly rated games are recommended."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=10)

    # Should not recommend "Unpopular Game" (scores too low)
    game_ids = [r["game_id"] for r in recommendations]
    assert "4" not in game_ids

    # All recommendations should have popularity > 0.6
    for rec in recommendations:
        assert rec["score"] > 0.6


def test_recommend_skips_hidden_games(filter, sample_library, play_histories):
    """Test that hidden games are not recommended."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=10)

    game_ids = [r["game_id"] for r in recommendations]
    assert "5" not in game_ids  # Hidden Game


def test_recommend_uses_community_score(filter, play_histories):
    """Test that community score is used when available."""
    library = [
        {
            "game_id": "99",  # Different ID to avoid play history conflict
            "name": "Community Favorite",
            "community_score": 90,  # 0.9 score, above 0.6 threshold
            "critic_score": 0,  # No critic score
            "hidden": False,
        }
    ]

    recommendations = filter.recommend("user1", library, play_histories, limit=5)

    assert len(recommendations) == 1
    # Score should be community_score / 100 = 0.9
    assert recommendations[0]["score"] == pytest.approx(0.9)


def test_recommend_uses_critic_score(filter, play_histories):
    """Test that critic score is used when community score unavailable."""
    library = [
        {
            "game_id": "98",  # Different ID to avoid play history conflict
            "name": "Critics Choice",
            "community_score": 0,  # No community score
            "critic_score": 85,  # 0.85 score, above 0.6 threshold
            "hidden": False,
        }
    ]

    recommendations = filter.recommend("user1", library, play_histories, limit=5)

    assert len(recommendations) == 1
    # Score should be critic_score / 100 = 0.85
    assert recommendations[0]["score"] == pytest.approx(0.85)


def test_recommend_weighted_average(filter, play_histories):
    """Test that weighted average is used when both scores available."""
    library = [
        {
            "game_id": "97",  # Different ID to avoid play history conflict
            "name": "Well Rated",
            "community_score": 90,
            "critic_score": 80,
            "hidden": False,
        }
    ]

    recommendations = filter.recommend("user1", library, play_histories, limit=5)

    assert len(recommendations) == 1
    # Weighted average: (90 * 0.7 + 80 * 0.3) / 100 = 0.87
    expected_score = (90 * 0.7 + 80 * 0.3) / 100.0
    assert recommendations[0]["score"] == pytest.approx(expected_score)


def test_recommend_no_scores(filter, play_histories):
    """Test that games without scores are not recommended."""
    library = [
        {
            "game_id": "1",
            "name": "Unrated Game",
            "community_score": 0,
            "critic_score": 0,
            "hidden": False,
        }
    ]

    recommendations = filter.recommend("user1", library, play_histories, limit=5)

    # Should not recommend game with no scores
    assert len(recommendations) == 0


def test_recommend_respects_limit(filter, sample_library, play_histories):
    """Test that recommendations respect the limit parameter."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=2)

    assert len(recommendations) <= 2


def test_recommend_sorted_by_score(filter, sample_library, play_histories):
    """Test that recommendations are sorted by score (descending)."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=10)

    # Check that scores are in descending order
    scores = [r["score"] for r in recommendations]
    assert scores == sorted(scores, reverse=True)


def test_recommend_empty_library(filter):
    """Test recommendations with empty library."""
    recommendations = filter.recommend("user1", [], [], limit=5)

    assert len(recommendations) == 0


def test_recommend_no_play_history(filter, sample_library):
    """Test recommendations with no play history."""
    recommendations = filter.recommend("user1", sample_library, [], limit=5)

    # Should still recommend popular games
    assert len(recommendations) > 0


def test_recommend_structure(filter, sample_library, play_histories):
    """Test that recommendations have correct structure."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=5)

    if recommendations:
        rec = recommendations[0]

        # Should have required fields
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "factors" in rec

        # Score should be valid
        assert 0 <= rec["score"] <= 1

        # Factors should include popularity
        assert "popularity" in rec["factors"]
        assert "community_score" in rec["factors"]
        assert "critic_score" in rec["factors"]


def test_recommend_reason_text(filter, sample_library, play_histories):
    """Test that reason text is appropriate."""
    recommendations = filter.recommend("user1", sample_library, play_histories, limit=5)

    if recommendations:
        rec = recommendations[0]
        assert rec["reason"] == "Highly rated by the community"


def test_recommend_filters_played_games_for_specific_user(filter, sample_library, play_histories):
    """Test that only the specific user's played games are filtered."""
    # user1 played game 1, user2 played game 2

    # Recommendations for user1 should not include game 1
    user1_recs = filter.recommend("user1", sample_library, play_histories, limit=10)
    user1_game_ids = [r["game_id"] for r in user1_recs]
    assert "1" not in user1_game_ids

    # Recommendations for user2 should not include game 2
    user2_recs = filter.recommend("user2", sample_library, play_histories, limit=10)
    user2_game_ids = [r["game_id"] for r in user2_recs]
    assert "2" not in user2_game_ids

    # Recommendations for user3 (no history) should include all eligible games
    user3_recs = filter.recommend("user3", sample_library, play_histories, limit=10)
    user3_game_ids = [r["game_id"] for r in user3_recs]
    assert "1" in user3_game_ids
    assert "3" in user3_game_ids


def test_recommend_threshold_filtering(filter, play_histories):
    """Test that popularity threshold is enforced."""
    library = [
        {
            "game_id": "91",  # Different IDs to avoid conflicts
            "name": "Highly Rated",
            "community_score": 90,
            "critic_score": 0,
            "hidden": False,
        },
        {
            "game_id": "92",
            "name": "Medium Rated",
            "community_score": 65,  # 0.65 score
            "critic_score": 0,
            "hidden": False,
        },
        {
            "game_id": "93",
            "name": "Low Rated",
            "community_score": 50,  # 0.50 score (below 0.6 threshold)
            "critic_score": 0,
            "hidden": False,
        },
    ]

    recommendations = filter.recommend("user1", library, play_histories, limit=10)

    # Should only recommend games with score > 0.6
    game_ids = [r["game_id"] for r in recommendations]
    assert "91" in game_ids  # 0.9 score
    assert "92" in game_ids  # 0.65 score
    assert "93" not in game_ids  # 0.5 score (below threshold)
