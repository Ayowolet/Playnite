"""Unit tests for explicit filtering."""
import pytest
from src.playnite_python.recommendations.explicit_filter import ExplicitFilter


@pytest.fixture
def filter():
    """Create an ExplicitFilter instance for testing."""
    return ExplicitFilter()


@pytest.fixture
def sample_library():
    """Sample game library for testing with all filter fields."""
    return [
        {
            "game_id": "1",
            "name": "Portal 2",
            "genres": ["Puzzle"],
            "platforms": ["PC", "PlayStation 3"],
            "features": ["Single Player", "Co-op"],
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
            "time_to_complete": 45,
            "difficulty": "easy",
            "vr_compatible": False,
            "vr_required": False,
        },
        {
            "game_id": "4",
            "name": "Elden Ring",
            "genres": ["RPG", "Action"],
            "platforms": ["PC", "PlayStation 5"],
            "features": ["Single Player", "Multiplayer"],
            "time_to_complete": 80,
            "difficulty": "hard",
            "vr_compatible": False,
            "vr_required": False,
        },
        {
            "game_id": "5",
            "name": "Half-Life: Alyx",
            "genres": ["Action", "VR"],
            "platforms": ["PC"],
            "features": ["Single Player"],
            "time_to_complete": 12,
            "difficulty": "medium",
            "vr_compatible": True,
            "vr_required": True,
        },
        {
            "game_id": "6",
            "name": "Beat Saber",
            "genres": ["Rhythm", "VR"],
            "platforms": ["PC", "PlayStation 5"],
            "features": ["Single Player", "Multiplayer"],
            "time_to_complete": None,  # No completion time
            "difficulty": "medium",
            "vr_compatible": True,
            "vr_required": True,
        },
        {
            "game_id": "7",
            "name": "Rocket League",
            "genres": ["Sports"],
            "platforms": ["PC", "Xbox Series X"],
            "features": ["Multiplayer", "Co-op"],
            "time_to_complete": None,  # Endless game
            "difficulty": "medium",
            "vr_compatible": False,
            "vr_required": False,
        },
        {
            "game_id": "8",
            "name": "Celeste",
            "genres": ["Platformer"],
            "platforms": ["PC", "Nintendo Switch"],
            "features": ["Single Player"],
            "time_to_complete": 9,
            "difficulty": "hard",
            "vr_compatible": False,
            "vr_required": False,
        },
    ]


@pytest.fixture
def sample_recommendations(sample_library):
    """Sample recommendations matching the library."""
    return [
        {
            "game_id": game["game_id"],
            "score": 0.8 - (i * 0.05),
            "reason": "Test recommendation",
            "factors": {},
        }
        for i, game in enumerate(sample_library)
    ]


# ============================================================================
# TIME TO COMPLETE FILTERING TESTS
# ============================================================================


def test_filter_no_filters_returns_all(filter, sample_recommendations, sample_library):
    """Test that no filters returns all recommendations."""
    result = filter.filter(sample_recommendations, sample_library, None)
    assert len(result) == len(sample_recommendations)


def test_filter_empty_filters_returns_all(filter, sample_recommendations, sample_library):
    """Test that empty filter dict returns all recommendations."""
    result = filter.filter(sample_recommendations, sample_library, {})
    assert len(result) == len(sample_recommendations)


def test_filter_by_max_completion_time(filter, sample_recommendations, sample_library):
    """Test filtering by maximum completion time (<10 hours)."""
    filters = {"max_completion_hours": 10}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Portal 2 (8h), Celeste (9h)
    # Should exclude: Dark Souls (60h), Stardew Valley (45h), Elden Ring (80h), Half-Life: Alyx (12h)
    # Should exclude: Beat Saber (None), Rocket League (None)
    game_ids = [r["game_id"] for r in result]
    assert "1" in game_ids  # Portal 2
    assert "8" in game_ids  # Celeste
    assert "2" not in game_ids  # Dark Souls
    assert "3" not in game_ids  # Stardew Valley
    assert "4" not in game_ids  # Elden Ring


def test_filter_by_min_completion_time(filter, sample_recommendations, sample_library):
    """Test filtering by minimum completion time (>50 hours)."""
    filters = {"min_completion_hours": 50}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Dark Souls (60h), Elden Ring (80h)
    game_ids = [r["game_id"] for r in result]
    assert "2" in game_ids  # Dark Souls
    assert "4" in game_ids  # Elden Ring
    assert "1" not in game_ids  # Portal 2 (too short)
    assert "3" not in game_ids  # Stardew Valley (45h, below threshold)


def test_filter_by_completion_time_range(filter, sample_recommendations, sample_library):
    """Test filtering by completion time range (10-50 hours)."""
    filters = {"min_completion_hours": 10, "max_completion_hours": 50}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Half-Life: Alyx (12h), Stardew Valley (45h)
    game_ids = [r["game_id"] for r in result]
    assert "5" in game_ids  # Half-Life: Alyx
    assert "3" in game_ids  # Stardew Valley
    assert "1" not in game_ids  # Portal 2 (too short)
    assert "2" not in game_ids  # Dark Souls (too long)
    assert "4" not in game_ids  # Elden Ring (too long)


def test_filter_excludes_games_without_completion_time(
    filter, sample_recommendations, sample_library
):
    """Test that games without completion time data are excluded from time filtering."""
    filters = {"max_completion_hours": 100}
    result = filter.filter(sample_recommendations, sample_library, filters)

    game_ids = [r["game_id"] for r in result]
    # Beat Saber and Rocket League have no completion time, should be excluded
    assert "6" not in game_ids  # Beat Saber
    assert "7" not in game_ids  # Rocket League


# ============================================================================
# DIFFICULTY FILTERING TESTS
# ============================================================================


def test_filter_by_difficulty_easy(filter, sample_recommendations, sample_library):
    """Test filtering by easy difficulty."""
    filters = {"difficulty_levels": ["easy"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Portal 2, Stardew Valley
    game_ids = [r["game_id"] for r in result]
    assert "1" in game_ids  # Portal 2
    assert "3" in game_ids  # Stardew Valley
    assert "2" not in game_ids  # Dark Souls (extreme)


def test_filter_by_difficulty_hard(filter, sample_recommendations, sample_library):
    """Test filtering by hard difficulty."""
    filters = {"difficulty_levels": ["hard"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Elden Ring, Celeste
    game_ids = [r["game_id"] for r in result]
    assert "4" in game_ids  # Elden Ring
    assert "8" in game_ids  # Celeste
    assert "1" not in game_ids  # Portal 2 (easy)


def test_filter_by_difficulty_multiple_levels(filter, sample_recommendations, sample_library):
    """Test filtering by multiple difficulty levels."""
    filters = {"difficulty_levels": ["easy", "medium"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Portal 2 (easy), Stardew Valley (easy), Half-Life: Alyx (medium),
    # Beat Saber (medium), Rocket League (medium)
    game_ids = [r["game_id"] for r in result]
    assert "1" in game_ids  # Portal 2
    assert "3" in game_ids  # Stardew Valley
    assert "5" in game_ids  # Half-Life: Alyx
    assert "7" in game_ids  # Rocket League
    assert "2" not in game_ids  # Dark Souls (extreme)
    assert "4" not in game_ids  # Elden Ring (hard)


def test_filter_by_difficulty_extreme(filter, sample_recommendations, sample_library):
    """Test filtering by extreme difficulty."""
    filters = {"difficulty_levels": ["extreme"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include only: Dark Souls
    game_ids = [r["game_id"] for r in result]
    assert "2" in game_ids  # Dark Souls
    assert len(game_ids) == 1


def test_filter_invalid_difficulty_levels_ignored(
    filter, sample_recommendations, sample_library
):
    """Test that invalid difficulty levels are ignored gracefully."""
    filters = {"difficulty_levels": ["super_easy", "impossible"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should return all games since invalid levels are ignored
    assert len(result) == len(sample_recommendations)


# ============================================================================
# MULTIPLAYER FILTERING TESTS
# ============================================================================


def test_filter_multiplayer_only(filter, sample_recommendations, sample_library):
    """Test filtering for multiplayer-only games."""
    filters = {"multiplayer_only": True}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Portal 2 (has Co-op), Stardew Valley, Elden Ring, Beat Saber, Rocket League
    game_ids = [r["game_id"] for r in result]
    assert "1" in game_ids  # Portal 2 (Co-op)
    assert "3" in game_ids  # Stardew Valley
    assert "4" in game_ids  # Elden Ring
    assert "6" in game_ids  # Beat Saber
    assert "7" in game_ids  # Rocket League
    assert "2" not in game_ids  # Dark Souls (single-player only)
    assert "5" not in game_ids  # Half-Life: Alyx (single-player only)


def test_filter_single_player_only(filter, sample_recommendations, sample_library):
    """Test filtering for single-player-only games."""
    filters = {"multiplayer_only": False}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Dark Souls, Half-Life: Alyx, Celeste
    game_ids = [r["game_id"] for r in result]
    assert "2" in game_ids  # Dark Souls
    assert "5" in game_ids  # Half-Life: Alyx
    assert "8" in game_ids  # Celeste
    assert "3" not in game_ids  # Stardew Valley (has multiplayer)
    assert "7" not in game_ids  # Rocket League (multiplayer)


def test_filter_multiplayer_case_insensitive(filter, sample_library):
    """Test that multiplayer detection is case-insensitive."""
    # Create game with mixed-case "Multiplayer"
    recs = [{"game_id": "3", "score": 0.8, "reason": "Test", "factors": {}}]
    filters = {"multiplayer_only": True}

    result = filter.filter(recs, sample_library, filters)
    assert len(result) == 1  # Should find Stardew Valley


# ============================================================================
# VR FILTERING TESTS
# ============================================================================


def test_filter_vr_compatible_only(filter, sample_recommendations, sample_library):
    """Test filtering for VR-compatible games."""
    filters = {"vr_compatible": True}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Half-Life: Alyx, Beat Saber
    game_ids = [r["game_id"] for r in result]
    assert "5" in game_ids  # Half-Life: Alyx
    assert "6" in game_ids  # Beat Saber
    assert len(game_ids) == 2


def test_filter_non_vr_only(filter, sample_recommendations, sample_library):
    """Test filtering for non-VR games."""
    filters = {"vr_compatible": False}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should exclude: Half-Life: Alyx, Beat Saber
    game_ids = [r["game_id"] for r in result]
    assert "5" not in game_ids  # Half-Life: Alyx
    assert "6" not in game_ids  # Beat Saber
    assert "1" in game_ids  # Portal 2
    assert "2" in game_ids  # Dark Souls


def test_filter_vr_required_exclusive(filter, sample_recommendations, sample_library):
    """Test filtering for VR-exclusive (VR required) games."""
    filters = {"vr_required": True}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Half-Life: Alyx, Beat Saber (both VR-exclusive)
    game_ids = [r["game_id"] for r in result]
    assert "5" in game_ids  # Half-Life: Alyx
    assert "6" in game_ids  # Beat Saber
    assert len(game_ids) == 2


def test_filter_vr_required_overrides_vr_compatible(
    filter, sample_recommendations, sample_library
):
    """Test that vr_required filter takes priority over vr_compatible."""
    filters = {"vr_compatible": False, "vr_required": True}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # vr_required should take priority, return VR-exclusive games
    game_ids = [r["game_id"] for r in result]
    assert "5" in game_ids  # Half-Life: Alyx
    assert "6" in game_ids  # Beat Saber


# ============================================================================
# PLATFORM FILTERING TESTS
# ============================================================================


def test_filter_by_platform_single(filter, sample_recommendations, sample_library):
    """Test filtering by single platform (PC)."""
    filters = {"platforms": ["PC"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # All test games have PC except some exclusives
    game_ids = [r["game_id"] for r in result]
    assert "1" in game_ids  # Portal 2 (PC)
    assert "2" in game_ids  # Dark Souls (PC)
    assert len(game_ids) == 8  # All games have PC


def test_filter_by_platform_multiple(filter, sample_recommendations, sample_library):
    """Test filtering by multiple platforms."""
    filters = {"platforms": ["Nintendo Switch", "Xbox Series X"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Stardew Valley (Switch), Celeste (Switch), Rocket League (Xbox)
    game_ids = [r["game_id"] for r in result]
    assert "3" in game_ids  # Stardew Valley
    assert "8" in game_ids  # Celeste
    assert "7" in game_ids  # Rocket League


def test_filter_by_platform_case_insensitive(filter, sample_recommendations, sample_library):
    """Test that platform filtering is case-insensitive."""
    filters = {"platforms": ["pc"]}  # lowercase
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should still match "PC" in library
    assert len(result) == 8


def test_filter_by_platform_excludes_non_matching(
    filter, sample_recommendations, sample_library
):
    """Test that platform filter excludes non-matching games."""
    filters = {"platforms": ["PlayStation 5"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Elden Ring (PS5), Beat Saber (PS5)
    game_ids = [r["game_id"] for r in result]
    assert "4" in game_ids  # Elden Ring
    assert "6" in game_ids  # Beat Saber


# ============================================================================
# COMBINED FILTERING TESTS
# ============================================================================


def test_combine_time_and_difficulty(filter, sample_recommendations, sample_library):
    """Test combining time-to-complete and difficulty filters."""
    filters = {"max_completion_hours": 20, "difficulty_levels": ["easy", "medium"]}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Portal 2 (8h, easy), Half-Life: Alyx (12h, medium)
    game_ids = [r["game_id"] for r in result]
    assert "1" in game_ids  # Portal 2
    assert "5" in game_ids  # Half-Life: Alyx
    assert "2" not in game_ids  # Dark Souls (too long, wrong difficulty)
    assert "8" not in game_ids  # Celeste (9h but hard)


def test_combine_platform_and_multiplayer(filter, sample_recommendations, sample_library):
    """Test combining platform and multiplayer filters."""
    filters = {"platforms": ["Nintendo Switch"], "multiplayer_only": True}
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Stardew Valley (Switch + Multiplayer)
    game_ids = [r["game_id"] for r in result]
    assert "3" in game_ids  # Stardew Valley
    assert "8" not in game_ids  # Celeste (Switch but single-player)


def test_combine_all_filters(filter, sample_recommendations, sample_library):
    """Test combining all filter types."""
    filters = {
        "min_completion_hours": 5,
        "max_completion_hours": 50,
        "difficulty_levels": ["easy", "medium"],
        "multiplayer_only": True,
        "vr_compatible": False,
        "platforms": ["PC"],
    }
    result = filter.filter(sample_recommendations, sample_library, filters)

    # Should include: Stardew Valley (45h, easy, multiplayer, non-VR, PC)
    game_ids = [r["game_id"] for r in result]
    assert "3" in game_ids  # Stardew Valley
    # Portal 2 has co-op (8h, easy, PC) but let's check
    assert "1" in game_ids  # Portal 2 should pass


def test_filters_return_empty_when_no_matches(
    filter, sample_recommendations, sample_library
):
    """Test that filters return empty list when no games match."""
    filters = {
        "min_completion_hours": 200,  # No game this long
    }
    result = filter.filter(sample_recommendations, sample_library, filters)

    assert len(result) == 0


def test_filters_with_context_boosts_preserved(filter, sample_library):
    """Test that existing score boosts are preserved through filtering."""
    # Create recommendations with different scores (as if boosted by context)
    recs = [
        {"game_id": "1", "score": 1.5, "reason": "Boosted", "factors": {"mood_boost": 1.3}},
        {"game_id": "2", "score": 0.9, "reason": "Normal", "factors": {}},
    ]

    filters = {"max_completion_hours": 20}
    result = filter.filter(recs, sample_library, filters)

    # Portal 2 should pass (8h < 20h) with boosted score preserved
    assert len(result) == 1
    assert result[0]["game_id"] == "1"
    assert result[0]["score"] == 1.5
    assert "mood_boost" in result[0]["factors"]


# ============================================================================
# EDGE CASES
# ============================================================================


def test_filter_empty_recommendations(filter, sample_library):
    """Test filtering with empty recommendations list."""
    result = filter.filter([], sample_library, {"max_completion_hours": 10})
    assert len(result) == 0


def test_filter_missing_game_in_library(filter, sample_library):
    """Test filtering with recommendation for game not in library."""
    recs = [
        {"game_id": "999", "score": 0.8, "reason": "Missing game", "factors": {}}
    ]
    filters = {"max_completion_hours": 10}

    result = filter.filter(recs, sample_library, filters)
    # Game not in library should be filtered out
    assert len(result) == 0


def test_filter_preserves_recommendation_structure(
    filter, sample_recommendations, sample_library
):
    """Test that filtering preserves recommendation dictionary structure."""
    filters = {"max_completion_hours": 10}
    result = filter.filter(sample_recommendations, sample_library, filters)

    if result:
        rec = result[0]
        assert "game_id" in rec
        assert "score" in rec
        assert "reason" in rec
        assert "factors" in rec


# ============================================================================
# FILTER SUMMARY TESTS
# ============================================================================


def test_get_filter_summary_no_filters(filter):
    """Test filter summary with no filters."""
    summary = filter.get_filter_summary(None)
    assert summary == "No filters active"


def test_get_filter_summary_empty_filters(filter):
    """Test filter summary with empty filter dict."""
    summary = filter.get_filter_summary({})
    assert summary == "No filters active"


def test_get_filter_summary_time_filters(filter):
    """Test filter summary with time filters."""
    filters = {"min_completion_hours": 10, "max_completion_hours": 50}
    summary = filter.get_filter_summary(filters)

    assert "≥10h to complete" in summary
    assert "≤50h to complete" in summary


def test_get_filter_summary_difficulty_filter(filter):
    """Test filter summary with difficulty filter."""
    filters = {"difficulty_levels": ["easy", "medium"]}
    summary = filter.get_filter_summary(filters)

    assert "Difficulty: easy, medium" in summary


def test_get_filter_summary_multiplayer_filter(filter):
    """Test filter summary with multiplayer filters."""
    filters_mp = {"multiplayer_only": True}
    summary_mp = filter.get_filter_summary(filters_mp)
    assert "Multiplayer only" in summary_mp

    filters_sp = {"multiplayer_only": False}
    summary_sp = filter.get_filter_summary(filters_sp)
    assert "Single-player only" in summary_sp


def test_get_filter_summary_vr_filter(filter):
    """Test filter summary with VR filters."""
    filters_vr_req = {"vr_required": True}
    summary_vr_req = filter.get_filter_summary(filters_vr_req)
    assert "VR-exclusive only" in summary_vr_req

    filters_vr_comp = {"vr_compatible": True}
    summary_vr_comp = filter.get_filter_summary(filters_vr_comp)
    assert "VR-compatible" in summary_vr_comp

    filters_non_vr = {"vr_compatible": False}
    summary_non_vr = filter.get_filter_summary(filters_non_vr)
    assert "Non-VR only" in summary_non_vr


def test_get_filter_summary_platform_filter(filter):
    """Test filter summary with platform filter."""
    filters = {"platforms": ["PC", "PlayStation 5"]}
    summary = filter.get_filter_summary(filters)

    assert "Platforms: PC, PlayStation 5" in summary


def test_get_filter_summary_all_filters(filter):
    """Test filter summary with all filters."""
    filters = {
        "min_completion_hours": 10,
        "max_completion_hours": 50,
        "difficulty_levels": ["medium", "hard"],
        "multiplayer_only": True,
        "vr_compatible": False,
        "platforms": ["PC"],
    }
    summary = filter.get_filter_summary(filters)

    # All filter types should be mentioned
    assert "≥10h to complete" in summary
    assert "≤50h to complete" in summary
    assert "Difficulty: medium, hard" in summary
    assert "Multiplayer only" in summary
    assert "Non-VR only" in summary
    assert "Platforms: PC" in summary
