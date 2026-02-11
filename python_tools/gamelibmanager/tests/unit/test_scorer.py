"""Tests for DuplicateScorer."""

import uuid
from datetime import datetime

import pytest
from gamelibmanager.duplicates.scorer import DuplicateScorer, MatchScore, ScoringWeights
from gamelibmanager.duplicates.config import ScoringWeights
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate

STEAM_PLUGIN = uuid.UUID("10000000-0000-0000-0000-000000000001")
GOG_PLUGIN = uuid.UUID("10000000-0000-0000-0000-000000000002")
PC_PLATFORM = uuid.UUID("20000000-0000-0000-0000-000000000001")


class TestDuplicateScorer:
    def setup_method(self):
        self.scorer = DuplicateScorer()

    def test_exact_title_match(self):
        a = Game(name="DOOM")
        b = Game(name="DOOM")
        score = self.scorer.score_pair(a, b)
        assert score.title_score == 1.0
        assert score.composite_score > 0.9

    def test_near_title_match(self):
        a = Game(name="The Witcher 3: Wild Hunt")
        b = Game(name="The Witcher 3 Wild Hunt")
        score = self.scorer.score_pair(a, b)
        assert score.title_score > 0.9

    def test_different_games(self):
        a = Game(name="DOOM Eternal")
        b = Game(name="Minecraft")
        score = self.scorer.score_pair(a, b)
        assert score.composite_score < 0.5

    def test_year_exact_match(self):
        a = Game(name="Game", release_date=ReleaseDate(2020))
        b = Game(name="Game", release_date=ReleaseDate(2020))
        score = self.scorer.score_pair(a, b)
        assert score.year_score == 1.0

    def test_year_off_by_one(self):
        a = Game(name="Game", release_date=ReleaseDate(2020))
        b = Game(name="Game", release_date=ReleaseDate(2021))
        score = self.scorer.score_pair(a, b)
        assert score.year_score == 0.5

    def test_year_mismatch(self):
        a = Game(name="Game", release_date=ReleaseDate(2015))
        b = Game(name="Game", release_date=ReleaseDate(2020))
        score = self.scorer.score_pair(a, b)
        assert score.year_score == 0.0

    def test_year_missing(self):
        a = Game(name="Game")
        b = Game(name="Game", release_date=ReleaseDate(2020))
        score = self.scorer.score_pair(a, b)
        assert score.year_score is None

    def test_platform_overlap_identical(self):
        pid = [PC_PLATFORM]
        a = Game(name="Game", platform_ids=pid)
        b = Game(name="Game", platform_ids=pid)
        score = self.scorer.score_pair(a, b)
        assert score.platform_score == 1.0

    def test_platform_overlap_none(self):
        a = Game(name="Game", platform_ids=[uuid.uuid4()])
        b = Game(name="Game", platform_ids=[uuid.uuid4()])
        score = self.scorer.score_pair(a, b)
        assert score.platform_score == 0.0

    def test_exact_provider_match(self):
        a = Game(name="Game", plugin_id=STEAM_PLUGIN, game_id="12345")
        b = Game(name="Game", plugin_id=STEAM_PLUGIN, game_id="12345")
        score = self.scorer.score_pair(a, b)
        assert score.is_exact_provider_match is True
        assert score.composite_score == 1.0

    def test_different_provider(self):
        a = Game(name="Game", plugin_id=STEAM_PLUGIN, game_id="12345")
        b = Game(name="Game", plugin_id=GOG_PLUGIN, game_id="67890")
        score = self.scorer.score_pair(a, b)
        assert score.is_exact_provider_match is False
        assert score.gameid_score == 0.0

    def test_custom_weights(self):
        weights = ScoringWeights(title=1.0, year=0.0, developer=0.0,
                                 publisher=0.0, platform=0.0, gameid=0.0)
        scorer = DuplicateScorer(weights=weights)
        a = Game(name="DOOM")
        b = Game(name="DOOM")
        score = scorer.score_pair(a, b)
        assert score.composite_score == 1.0

    def test_weight_redistribution(self):
        """When year/dev/pub/platform/gameid are all N/A, all weight goes to title."""
        a = Game(name="Test Game")
        b = Game(name="Test Game")
        score = self.scorer.score_pair(a, b)
        # Title is the only signal, should get full weight
        assert score.composite_score == pytest.approx(1.0, abs=0.01)

    def test_edition_variants_match(self):
        a = Game(name="Skyrim")
        b = Game(name="Skyrim Special Edition")
        score = self.scorer.score_pair(a, b)
        # After normalization, "skyrim" vs "skyrim" should be 1.0
        assert score.title_score == 1.0
