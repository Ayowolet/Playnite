"""Unit tests for the GameMatcher fuzzy matching engine."""
import pytest
from game_library.duplicate.matcher import GameMatcher, MatchWeights, MatchResult
from tests.conftest import make_game


class TestMatchWeights:
    def test_default_weights_sum_to_one(self):
        w = MatchWeights()
        assert abs(w.title + w.year + w.platform + w.developer + w.publisher - 1.0) < 1e-9

    def test_custom_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            MatchWeights(title=0.5, year=0.1, platform=0.1, developer=0.1, publisher=0.1)


class TestGameMatcherExactDuplicates:
    """Identical games should score very close to 1.0."""

    def test_identical_titles(self, witcher3_steam, witcher3_gog):
        m = GameMatcher()
        result = m.match(witcher3_steam, witcher3_gog)
        assert result.score >= 0.85, f"Expected ≥0.85, got {result.score:.3f}"
        assert result.title_score == 1.0

    def test_identical_portal_games(self, portal2, portal2_gog):
        m = GameMatcher()
        result = m.match(portal2, portal2_gog)
        assert result.score >= 0.85

    def test_confidence_pct(self, witcher3_steam, witcher3_gog):
        m = GameMatcher()
        result = m.match(witcher3_steam, witcher3_gog)
        assert result.confidence_pct == round(result.score * 100)
        assert result.confidence_pct >= 85

    def test_is_duplicate_true(self, witcher3_steam, witcher3_gog):
        m = GameMatcher()
        result = m.match(witcher3_steam, witcher3_gog)
        assert result.is_duplicate(0.85)


class TestGameMatcherEditionVariants:
    """Edition variants should match after title normalisation."""

    def test_goty_matches_base(self, witcher3_steam, witcher3_goty):
        m = GameMatcher()
        result = m.match(witcher3_steam, witcher3_goty)
        # GOTY edition title normalises to same base title → title_score should be 1.0
        assert result.title_score >= 0.95, f"title_score {result.title_score:.3f}"

    def test_remaster_detected(self):
        base = make_game("Halo 2", year=2004, platforms=["PC"], developers=["Bungie"])
        remaster = make_game("Halo 2 Remastered", year=2014, platforms=["PC"], developers=["Bungie"])
        m = GameMatcher()
        result = m.match(base, remaster)
        assert result.title_score >= 0.95


class TestGameMatcherNonDuplicates:
    """Clearly different games should score below threshold."""

    def test_different_games_low_score(self, witcher3_steam, unrelated_game):
        m = GameMatcher()
        result = m.match(witcher3_steam, unrelated_game)
        assert result.score < 0.85

    def test_quick_candidate_false_for_unrelated(self, witcher3_steam, unrelated_game):
        m = GameMatcher()
        # "The Witcher 3" vs "Cyberpunk 2077" – title filter should reject
        assert not m.quick_candidate(witcher3_steam, unrelated_game)

    def test_quick_candidate_true_for_near_match(self, witcher3_steam, witcher3_gog):
        m = GameMatcher()
        assert m.quick_candidate(witcher3_steam, witcher3_gog)


class TestGameMatcherComponents:
    """Validate individual component scores."""

    def test_year_exact_match_score_one(self):
        ga = make_game("Test Game", year=2015)
        gb = make_game("Test Game", year=2015)
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.year_score == 1.0

    def test_year_off_by_one_score_half(self):
        ga = make_game("Test Game", year=2015)
        gb = make_game("Test Game", year=2014)
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.year_score == 0.5

    def test_year_far_apart_score_zero(self):
        ga = make_game("Test Game", year=2000)
        gb = make_game("Test Game", year=2020)
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.year_score == 0.0

    def test_year_unknown_neutral(self):
        ga = make_game("Test Game")
        gb = make_game("Test Game", year=2015)
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.year_score == 0.5

    def test_platform_overlap_full(self):
        ga = make_game("Test", platforms=["PC", "Xbox"])
        gb = make_game("Test", platforms=["PC", "Xbox"])
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.platform_score == 1.0

    def test_platform_no_overlap(self):
        ga = make_game("Test", platforms=["PC"])
        gb = make_game("Test", platforms=["PlayStation 5"])
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.platform_score == 0.0

    def test_developer_normalisation(self):
        """Valve Inc. and Valve Corporation should both normalise to 'valve'."""
        ga = make_game("Portal 2", developers=["Valve, Inc."])
        gb = make_game("Portal 2", developers=["Valve Corporation"])
        m = GameMatcher()
        r = m.match(ga, gb)
        assert r.developer_score == 1.0


class TestMatchDetails:
    def test_details_populated(self, witcher3_steam, witcher3_gog):
        m = GameMatcher()
        r = m.match(witcher3_steam, witcher3_gog)
        assert "title_norm_a" in r.details
        assert "title_norm_b" in r.details
        assert r.details["title_norm_a"] == r.details["title_norm_b"]
