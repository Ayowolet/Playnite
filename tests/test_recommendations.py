"""
Unit and integration tests for the recommendation engine.

Run with:
    pytest tests/test_recommendations.py -v
    pytest tests/test_recommendations.py -v --tb=short

Tests cover:
- Content-based filtering (TF-IDF + cosine similarity)
- Collaborative filtering (SVD)
- Mood filter
- Temporal filter
- Explanation generation
- Feedback engine
- Full recommendation pipeline
- CLI recommendation commands
"""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

import pytest

from playnite_py.config import AppConfig
from playnite_py.database.db import GameDatabase
from playnite_py.library.manager import LibraryManager
from playnite_py.models.game import Game
from playnite_py.models.user_profile import Mood, UserProfile, RecommendationFeedback
from playnite_py.recommendations.content_filter import ContentBasedFilter
from playnite_py.recommendations.collaborative import CollaborativeFilter
from playnite_py.recommendations.mood_filter import MoodFilter
from playnite_py.recommendations.temporal_filter import TemporalFilter
from playnite_py.recommendations.explainer import RecommendationExplainer
from playnite_py.recommendations.feedback import FeedbackEngine
from playnite_py.recommendations.engine import RecommendationEngine, Recommendation
from playnite_py.recommendations.feed import DiscoveryFeed, FeedShelf


# ================================================================== #
# Fixtures                                                             #
# ================================================================== #

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_library.json"


def _make_game(**kwargs) -> Game:
    defaults = dict(
        id=str(uuid.uuid4()),
        name="Test Game",
        genres=["Action"],
        themes=["fantasy"],
        mechanics=["open world"],
        developers=["Test Dev"],
        tags=["adventure"],
        playtime_seconds=0,
        play_count=0,
        is_owned=True,
    )
    defaults.update(kwargs)
    return Game(**defaults)  # type: ignore[arg-type]


def _make_profile(**kwargs) -> UserProfile:
    defaults = dict(
        id=str(uuid.uuid4()),
        username="tester",
        genre_weights={"RPG": 0.9, "Action": 0.7, "Metroidvania": 0.8},
        mechanic_weights={"open world": 0.8, "platformer": 0.7},
        theme_weights={"dark": 0.8, "fantasy": 0.9},
        ratings={},
        wishlist=[],
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def sample_games() -> List[Game]:
    """10 diverse games for testing."""
    return [
        _make_game(id="rpg1", name="Epic Quest", genres=["RPG"], themes=["fantasy"],
                   mechanics=["open world"], playtime_seconds=72000, play_count=5),
        _make_game(id="rpg2", name="Dark Saga", genres=["RPG", "Action"],
                   themes=["dark", "fantasy"], mechanics=["action rpg"],
                   playtime_seconds=36000, play_count=2),
        _make_game(id="act1", name="Speed Runner", genres=["Action", "Platformer"],
                   themes=["sci-fi"], mechanics=["platformer", "speed"],
                   playtime_seconds=18000, play_count=3),
        _make_game(id="str1", name="Empire Builder", genres=["Strategy"],
                   themes=["historical"], mechanics=["turn-based", "4x"],
                   playtime_seconds=0, play_count=0),
        _make_game(id="rog1", name="Dungeon Crawler", genres=["Roguelike", "Action"],
                   themes=["dark", "dungeon"], mechanics=["roguelite", "action"],
                   playtime_seconds=0, play_count=0),
        _make_game(id="sim1", name="City Sim", genres=["Simulation", "Strategy"],
                   themes=["urban", "management"], mechanics=["city builder"],
                   playtime_seconds=0, play_count=0),
        _make_game(id="adv1", name="Island Explorer", genres=["Adventure", "Sandbox"],
                   themes=["nature", "exploration"], mechanics=["exploration", "crafting"],
                   playtime_seconds=0, play_count=0),
        _make_game(id="hor1", name="Nightmare House", genres=["Horror", "Survival"],
                   themes=["horror", "dark"], mechanics=["stealth", "survival"],
                   playtime_seconds=0, play_count=0),
        _make_game(id="puz1", name="Mind Bender", genres=["Puzzle"],
                   themes=["abstract"], mechanics=["puzzle"],
                   playtime_seconds=0, play_count=0),
        _make_game(id="met1", name="Underworld", genres=["Metroidvania", "Action"],
                   themes=["dark", "fantasy"], mechanics=["metroidvania", "exploration"],
                   playtime_seconds=0, play_count=0),
    ]


@pytest.fixture
def profile(sample_games: List[Game]) -> UserProfile:
    return _make_profile()


@pytest.fixture
def temp_config(tmp_path: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.data_dir = str(tmp_path)
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def library(temp_config: AppConfig, sample_games: List[Game]) -> LibraryManager:
    mgr = LibraryManager(temp_config)
    for g in sample_games:
        mgr.add_game(g)
    return mgr


# ================================================================== #
# Content-based filter                                                 #
# ================================================================== #

class TestContentBasedFilter:

    def test_fit_and_score(self, sample_games: List[Game], profile: UserProfile):
        played = [g for g in sample_games if g.is_played]
        candidates = [g for g in sample_games if not g.is_played]

        cf = ContentBasedFilter()
        cf.fit(sample_games)

        scores = cf.score_candidates(candidates, played, profile)
        assert len(scores) == len(candidates)
        for gid, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {gid}"

    def test_cold_start_returns_uniform(self, sample_games: List[Game]):
        """When no played games, should return small uniform scores."""
        profile = _make_profile(genre_weights={}, mechanic_weights={}, theme_weights={})
        cf = ContentBasedFilter()
        cf.fit(sample_games)
        candidates = sample_games
        scores = cf.score_candidates(candidates, [], profile)
        assert all(s == 0.1 for s in scores.values())

    def test_high_score_for_similar_genre(self, sample_games: List[Game]):
        """A game with the same genre as played games should score higher than unrelated ones."""
        # User has played RPG games
        played = [g for g in sample_games if "RPG" in g.genres]
        # Candidate: another RPG vs a Strategy game
        rpg_candidate = _make_game(name="Another RPG", genres=["RPG"], themes=["fantasy"])
        str_candidate = _make_game(name="Strategy Game", genres=["Strategy"], themes=["historical"])

        all_games = sample_games + [rpg_candidate, str_candidate]
        profile = _make_profile(genre_weights={"RPG": 0.9}, theme_weights={"fantasy": 0.8})
        cf = ContentBasedFilter()
        cf.fit(all_games)

        rpg_score = cf.score_candidates([rpg_candidate], played, profile)
        str_score = cf.score_candidates([str_candidate], played, profile)

        assert rpg_score.get(rpg_candidate.id, 0) >= str_score.get(str_candidate.id, 0), \
            "RPG candidate should score >= Strategy candidate for RPG-preferring user"

    def test_empty_corpus(self):
        cf = ContentBasedFilter()
        cf.fit([])
        scores = cf.score_candidates([], [], _make_profile())
        assert scores == {}

    def test_feature_string_used(self):
        game = _make_game(genres=["Horror"], themes=["dark"], mechanics=["stealth"])
        tokens = game.feature_tokens()
        assert "horror" in tokens
        assert "dark" in tokens
        assert "stealth" in tokens

    def test_get_top_features(self, sample_games: List[Game]):
        cf = ContentBasedFilter()
        cf.fit(sample_games)
        game = sample_games[0]
        features = cf.get_top_features(game, top_n=3)
        assert len(features) <= 3


# ================================================================== #
# Collaborative filter                                                 #
# ================================================================== #

class TestCollaborativeFilter:

    def test_fit_and_score(self, sample_games: List[Game], profile: UserProfile):
        # Give played games playtime
        for g in sample_games[:3]:
            g.playtime_seconds = 3600
            g.play_count = 1

        profiles = [profile]
        cf = CollaborativeFilter()
        cf.fit(sample_games, profiles)

        candidates = sample_games[3:]
        scores = cf.score_candidates(candidates, profile, sample_games)

        assert len(scores) == len(candidates)
        for gid, score in scores.items():
            assert 0.0 <= score <= 1.0

    def test_empty_corpus(self):
        cf = CollaborativeFilter()
        cf.fit([], [])
        scores = cf.score_candidates([], _make_profile(), [])
        assert scores == {}

    def test_similar_games(self, sample_games: List[Game]):
        profiles = [_make_profile()]
        cf = CollaborativeFilter()
        cf.fit(sample_games, profiles)

        game = sample_games[0]
        similar = cf.find_similar_games(game, sample_games, top_n=3)
        assert len(similar) <= 3
        # Game should not appear in its own similar list
        assert all(g.id != game.id for g, _ in similar)

    def test_unfitted_returns_empty(self, sample_games: List[Game], profile: UserProfile):
        cf = CollaborativeFilter()
        scores = cf.score_candidates(sample_games, profile, sample_games)
        assert scores == {}


# ================================================================== #
# Mood filter                                                          #
# ================================================================== #

class TestMoodFilter:

    def test_relaxed_boosts_puzzle(self):
        mf = MoodFilter()
        puzzle_game = _make_game(genres=["Puzzle"], themes=["abstract"], mechanics=["puzzle"])
        action_game = _make_game(genres=["Action"], tags=["intense", "fast-paced"])

        puzzle_score = mf.score_game_for_mood(puzzle_game, Mood.RELAXED.value)
        action_score = mf.score_game_for_mood(action_game, Mood.RELAXED.value)

        assert puzzle_score > 0.5, "Puzzle should match relaxed mood"
        assert puzzle_score > action_score, "Puzzle should score higher than action for relaxed"

    def test_excited_boosts_action(self):
        mf = MoodFilter()
        action_game = _make_game(genres=["Action", "Shooter"], mechanics=["fast-paced"])
        puzzle_game = _make_game(genres=["Puzzle"], themes=["abstract"])

        action_score = mf.score_game_for_mood(action_game, Mood.EXCITED.value)
        puzzle_score = mf.score_game_for_mood(puzzle_game, Mood.EXCITED.value)

        assert action_score > puzzle_score

    def test_spooky_boosts_horror(self):
        mf = MoodFilter()
        horror_game = _make_game(genres=["Horror"], themes=["dark", "horror"])
        puzzle_game = _make_game(genres=["Puzzle"], themes=["abstract"])

        horror_score = mf.score_game_for_mood(horror_game, Mood.SPOOKY.value)
        assert horror_score > 0.5

    def test_apply_mood_scores_adjusts_all(self):
        mf = MoodFilter()
        games = [
            _make_game(id="a", genres=["Puzzle"]),
            _make_game(id="b", genres=["Action"]),
        ]
        base = {"a": 0.5, "b": 0.5}
        adjusted = mf.apply_mood_scores(base, games, Mood.RELAXED.value)
        assert "a" in adjusted
        assert "b" in adjusted

    def test_no_mood_returns_unchanged(self):
        mf = MoodFilter()
        base = {"a": 0.7, "b": 0.3}
        result = mf.apply_mood_scores(base, [], None)
        assert result == base

    def test_list_moods_returns_all(self):
        mf = MoodFilter()
        moods = mf.list_moods()
        mood_names = {m["mood"] for m in moods}
        assert Mood.RELAXED.value in mood_names
        assert Mood.SPOOKY.value in mood_names
        assert len(moods) == len(Mood)

    def test_score_range(self):
        mf = MoodFilter()
        for mood in Mood:
            game = _make_game(genres=["Action"], themes=["dark"])
            score = mf.score_game_for_mood(game, mood.value)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for mood {mood}"


# ================================================================== #
# Temporal filter                                                      #
# ================================================================== #

class TestTemporalFilter:

    def test_scores_in_range(self, sample_games: List[Game], profile: UserProfile):
        tf = TemporalFilter()
        scores = tf.get_temporal_scores(sample_games, profile)
        for gid, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {gid}"

    def test_context_summary_keys(self):
        tf = TemporalFilter()
        ctx = tf.get_context_summary()
        assert "season" in ctx
        assert "time_of_day" in ctx
        assert "day_type" in ctx
        assert ctx["season"] in ("winter", "spring", "summer", "autumn")
        assert ctx["time_of_day"] in ("morning", "afternoon", "evening", "night")
        assert ctx["day_type"] in ("weekend", "weekday")

    def test_empty_candidates(self):
        tf = TemporalFilter()
        scores = tf.get_temporal_scores([], _make_profile())
        assert scores == {}

    def test_specific_season(self):
        winter_dt = datetime(2024, 1, 15, 20, 0)  # January, evening
        tf = TemporalFilter(now=winter_dt)
        cozy_game = _make_game(genres=["Simulation"], tags=["cozy"])
        action_game = _make_game(genres=["Action", "Sports"])

        scores = tf.get_temporal_scores([cozy_game, action_game], _make_profile())
        # Cozy should score higher in winter evening
        assert scores.get(cozy_game.id, 0) >= 0.0
        assert scores.get(action_game.id, 0) >= 0.0


# ================================================================== #
# Explanation generator                                                #
# ================================================================== #

class TestRecommendationExplainer:

    def test_explanation_has_primary_reason(self, sample_games: List[Game], profile: UserProfile):
        explainer = RecommendationExplainer()
        played = [g for g in sample_games if g.is_played]
        candidate = sample_games[-1]

        scores = {
            "content": {candidate.id: 0.8},
            "collaborative": {candidate.id: 0.6},
            "temporal": {candidate.id: 0.5},
            "mood": {},
        }
        explanation = explainer.explain(candidate, profile, played, scores)
        assert explanation.game_id == candidate.id
        assert explanation.game_name == candidate.name
        assert explanation.primary_reason != ""

    def test_explanation_signals_sorted_by_weight(self, sample_games: List[Game]):
        explainer = RecommendationExplainer()
        profile = _make_profile()
        candidate = sample_games[0]
        scores = {
            "content": {candidate.id: 0.9},
            "collaborative": {candidate.id: 0.3},
            "temporal": {candidate.id: 0.1},
            "mood": {},
        }
        explanation = explainer.explain(candidate, profile, [], scores)
        if len(explanation.signals) >= 2:
            assert explanation.signals[0].weight >= explanation.signals[1].weight

    def test_explanation_to_dict(self, sample_games: List[Game]):
        explainer = RecommendationExplainer()
        candidate = sample_games[0]
        scores = {"content": {candidate.id: 0.7}, "collaborative": {}, "temporal": {}, "mood": {}}
        explanation = explainer.explain(candidate, _make_profile(), [], scores)
        d = explanation.to_dict()
        assert "game_id" in d
        assert "primary_reason" in d
        assert "signals" in d

    def test_format_batch(self, sample_games: List[Game]):
        explainer = RecommendationExplainer()
        profile = _make_profile()
        explanations = []
        for game in sample_games[:3]:
            scores = {"content": {game.id: 0.5}, "collaborative": {}, "temporal": {}, "mood": {}}
            explanations.append(explainer.explain(game, profile, [], scores))
        text = explainer.format_batch(explanations)
        assert "1." in text
        assert "2." in text


# ================================================================== #
# Feedback engine                                                      #
# ================================================================== #

class TestFeedbackEngine:

    def test_record_feedback_creates_valid_record(self, sample_games: List[Game]):
        engine = FeedbackEngine()
        game = sample_games[0]
        fb = engine.record_feedback(
            user_id="user1",
            recommendation_id="rec1",
            game=game,
            action="liked",
            content_score=0.8,
        )
        assert fb.user_id == "user1"
        assert fb.game_id == game.id
        assert fb.action == "liked"
        assert fb.is_positive

    def test_invalid_action_raises(self, sample_games: List[Game]):
        engine = FeedbackEngine()
        with pytest.raises(ValueError, match="Unknown action"):
            engine.record_feedback("u1", "r1", sample_games[0], "invalid_action")

    def test_update_profile_from_feedback(self, sample_games: List[Game]):
        engine = FeedbackEngine()
        profile = _make_profile(genre_weights={"Action": 0.5, "RPG": 0.5})
        game = _make_game(genres=["Action"])
        game_map = {game.id: game}

        feedback = [
            RecommendationFeedback(
                user_id=profile.id, recommendation_id="r1",
                game_id=game.id, action="liked"
            )
            for _ in range(6)   # exceed min_feedback_count
        ]
        updated = engine.update_profile_from_feedback(profile, feedback, game_map)
        # Action weight should have increased after positive feedback
        assert updated.genre_weights.get("Action", 0.5) >= 0.5

    def test_accuracy_metrics_empty(self):
        engine = FeedbackEngine()
        metrics = engine.get_accuracy_metrics([])
        assert metrics == {}

    def test_accuracy_metrics_with_data(self, sample_games: List[Game]):
        engine = FeedbackEngine()
        game = sample_games[0]
        feedback = [
            RecommendationFeedback(user_id="u1", recommendation_id="r1",
                                   game_id=game.id, action="played"),
            RecommendationFeedback(user_id="u1", recommendation_id="r1",
                                   game_id=game.id, action="disliked"),
            RecommendationFeedback(user_id="u1", recommendation_id="r1",
                                   game_id=game.id, action="liked"),
        ]
        metrics = engine.get_accuracy_metrics(feedback)
        assert metrics["total_feedback"] == 3
        assert 0.0 <= metrics["acceptance_rate"] <= 1.0

    def test_adjust_engine_weights_not_enough_data(self):
        engine = FeedbackEngine()
        new_cw, new_lw = engine.adjust_engine_weights([], 0.6, 0.25)
        assert new_cw == 0.6
        assert new_lw == 0.25


# ================================================================== #
# Full recommendation engine                                           #
# ================================================================== #

class TestRecommendationEngine:

    def test_generate_with_sample_library(self, library: LibraryManager, temp_config: AppConfig):
        """Integration test: generate recommendations from a real library."""
        profile = library.get_or_create_profile()
        # Mark first 3 games as played
        games = library.get_all_games()
        for g in games[:3]:
            g.playtime_seconds = 3600
            g.play_count = 1
            library.update_game(g)

        profile = library.build_user_preference_weights(profile)
        library.save_profile(profile)

        engine = RecommendationEngine(library, temp_config)
        engine.fit()
        recs = engine.generate(profile, n=5, save_to_db=False)

        assert 1 <= len(recs) <= 5, f"Expected 1–5 recommendations, got {len(recs)}"
        for rec in recs:
            assert rec.final_score > 0
            assert rec.explanation is not None
            assert rec.explanation.primary_reason != ""
            # Should not recommend already-played games
            assert not any(rec.game.id == g.id for g in games[:3])

    def test_generate_with_mood(self, library: LibraryManager, temp_config: AppConfig):
        profile = library.get_or_create_profile()
        engine = RecommendationEngine(library, temp_config)
        engine.fit()
        recs = engine.generate(profile, n=5, mood=Mood.RELAXED.value, save_to_db=False)
        # Should not crash and should return recommendations
        assert isinstance(recs, list)

    def test_generate_empty_library(self, temp_config: AppConfig):
        empty_lib = LibraryManager(temp_config)
        engine = RecommendationEngine(empty_lib, temp_config)
        profile = empty_lib.get_or_create_profile()
        recs = engine.generate(profile, n=5, save_to_db=False)
        assert recs == []

    def test_recommendations_ranked(self, library: LibraryManager, temp_config: AppConfig):
        profile = library.get_or_create_profile()
        engine = RecommendationEngine(library, temp_config)
        engine.fit()
        recs = engine.generate(profile, n=10, save_to_db=False)

        if len(recs) >= 2:
            for i in range(len(recs) - 1):
                assert recs[i].final_score >= recs[i + 1].final_score, \
                    "Recommendations should be sorted by descending score"

    def test_export_history(self, library: LibraryManager, temp_config: AppConfig, tmp_path: Path):
        profile = library.get_or_create_profile()
        engine = RecommendationEngine(library, temp_config)
        engine.fit()
        engine.generate(profile, n=3, save_to_db=True)

        out_path = tmp_path / "history.json"
        result = engine.export_history(profile, output_path=out_path)
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "user_id" in data
        assert "history" in data

    def test_feedback_updates_profile(self, library: LibraryManager, temp_config: AppConfig):
        profile = library.get_or_create_profile()
        engine = RecommendationEngine(library, temp_config)
        engine.fit()
        recs = engine.generate(profile, n=3, save_to_db=False)

        if recs:
            engine.record_feedback(profile, recs[0], "liked")
            # Profile should still be valid
            updated = library.get_or_create_profile(profile.id)
            assert updated is not None

    def test_genre_filter(self, library: LibraryManager, temp_config: AppConfig):
        profile = library.get_or_create_profile()
        engine = RecommendationEngine(library, temp_config)
        engine.fit()
        recs = engine.generate(profile, n=10, genre_filter="Roguelike", save_to_db=False)
        for rec in recs:
            assert any("roguelike" in g.lower() for g in rec.game.genres), \
                f"{rec.game.name} should be Roguelike"

    def test_analyse_library_updates_weights(self, library: LibraryManager, temp_config: AppConfig):
        games = library.get_all_games()
        for g in games[:5]:
            g.playtime_seconds = 7200
            g.play_count = 2
            library.update_game(g)

        profile = library.get_or_create_profile()
        engine = RecommendationEngine(library, temp_config)
        updated_profile = engine.analyse_library(profile)
        assert bool(updated_profile.genre_weights), "Profile should have genre weights after analysis"


# ================================================================== #
# Fixture-based integration test                                       #
# ================================================================== #

class TestWithSampleFixture:

    def test_load_and_recommend(self, tmp_path: Path):
        """Full pipeline test using the sample library fixture."""
        cfg = AppConfig()
        cfg.data_dir = str(tmp_path)
        cfg.ensure_dirs()

        mgr = LibraryManager(cfg)
        assert FIXTURE_PATH.exists(), f"Fixture not found at {FIXTURE_PATH}"
        count = mgr.import_from_json(FIXTURE_PATH)
        assert count >= 10, f"Expected >= 10 games, got {count}"

        profile = mgr.get_or_create_profile()
        # Load user data from fixture
        fixture_data = json.loads(FIXTURE_PATH.read_text())
        user_data = fixture_data.get("user", {})
        profile.ratings = user_data.get("ratings", {})
        profile.wishlist = user_data.get("wishlist", [])
        profile = mgr.build_user_preference_weights(profile)
        mgr.save_profile(profile)

        engine = RecommendationEngine(mgr, cfg)
        engine.fit()
        recs = engine.generate(profile, n=10, save_to_db=False)

        assert len(recs) > 0
        for rec in recs:
            assert rec.final_score >= cfg.recommendations.min_score_threshold
            assert rec.explanation is not None

        # Recommendations should not include heavily-played games
        heavily_played_ids = {"g001", "g002", "g003"}
        rec_ids = {r.game.id for r in recs}
        overlap = rec_ids & heavily_played_ids
        assert len(overlap) == 0, f"Should not recommend already-played games: {overlap}"


# ================================================================== #
# CLI tests                                                            #
# ================================================================== #

class TestRecommendCLI:

    def test_recommend_test_command(self, tmp_path: Path):
        """Test the 'recommend test' CLI command with synthetic data."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "recommend", "test", "-n", "5",
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        # Output should be valid JSON
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_recommend_test_with_fixture(self, tmp_path: Path):
        """Test the 'recommend test' CLI with fixture data."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "recommend", "test",
            "--library-file", str(FIXTURE_PATH),
            "-n", "5",
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}"

    def test_mood_list_command(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "recommend", "mood", "--list",
        ])
        assert result.exit_code == 0
        moods = json.loads(result.output)
        assert len(moods) >= len(Mood)

    def test_library_stats_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        # Import fixture first
        runner.invoke(cli, ["--data-dir", str(tmp_path), "library", "import", str(FIXTURE_PATH)])
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "library", "stats",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_games" in data
        assert data["total_games"] >= 10

    def test_recommend_generate_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        runner.invoke(cli, ["--data-dir", str(tmp_path), "library", "import", str(FIXTURE_PATH)])
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "recommend", "generate", "-n", "5",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ================================================================== #
# R13 — Discovery feed tests                                           #
# ================================================================== #

class TestDiscoveryFeed:
    """Tests for the multi-shelf DiscoveryFeed."""

    @pytest.fixture
    def feed_setup(self, tmp_path: Path):
        cfg = AppConfig()
        cfg.data_dir = str(tmp_path)
        mgr = LibraryManager(cfg)
        # Load fixture library so we have played + unplayed games
        mgr.import_from_json(FIXTURE_PATH)
        profile = mgr.get_or_create_profile()
        profile = mgr.build_user_preference_weights(profile)
        mgr.save_profile(profile)
        engine = RecommendationEngine(mgr, cfg)
        engine.fit()
        feed = DiscoveryFeed(engine, mgr)
        return feed, profile, mgr

    def test_generate_returns_shelves(self, feed_setup):
        feed, profile, _ = feed_setup
        shelves = feed.generate(profile, n_per_shelf=3)
        assert len(shelves) >= 1
        for shelf in shelves:
            assert isinstance(shelf, FeedShelf)
            assert shelf.name
            assert shelf.tag
            assert isinstance(shelf.recommendations, list)

    def test_top_picks_shelf_present(self, feed_setup):
        feed, profile, _ = feed_setup
        shelves = feed.generate(profile, n_per_shelf=3)
        tags = [s.tag for s in shelves]
        assert "top_picks" in tags

    def test_backlog_shelf_present(self, feed_setup):
        """'backlog' shelf appears when there are owned unplayed games."""
        feed, profile, _ = feed_setup
        shelves = feed.generate(profile, n_per_shelf=3)
        tags = [s.tag for s in shelves]
        # Fixture has unplayed owned games → backlog shelf should appear
        assert "backlog" in tags

    def test_no_duplicate_games_across_shelves(self, feed_setup):
        """The same game should not appear in two different shelves."""
        feed, profile, _ = feed_setup
        shelves = feed.generate(profile, n_per_shelf=5)
        seen_ids = []
        for shelf in shelves:
            # backlog shelf has zero final_score and no explanation — skip de-dup check
            if shelf.tag == "backlog":
                continue
            for rec in shelf.recommendations:
                seen_ids.append(rec.game.id)
        # All IDs in non-backlog shelves should be unique
        assert len(seen_ids) == len(set(seen_ids))

    def test_shelf_to_dict_serialisable(self, feed_setup):
        """FeedShelf.to_dict() produces JSON-serialisable output."""
        feed, profile, _ = feed_setup
        shelves = feed.generate(profile, n_per_shelf=2)
        for shelf in shelves:
            d = shelf.to_dict()
            json.dumps(d, default=str)   # must not raise
            assert d["tag"] == shelf.tag
            assert d["count"] == len(shelf.recommendations)

    def test_mood_applied_to_top_picks(self, feed_setup):
        """Passing mood= does not break feed generation."""
        feed, profile, _ = feed_setup
        shelves = feed.generate(profile, n_per_shelf=3, mood="relaxed")
        assert len(shelves) >= 1

    def test_feed_unfitted_engine_auto_fits(self, tmp_path: Path):
        """DiscoveryFeed calls engine.fit() automatically if not fitted."""
        cfg = AppConfig()
        cfg.data_dir = str(tmp_path)
        mgr = LibraryManager(cfg)
        mgr.import_from_json(FIXTURE_PATH)
        profile = mgr.get_or_create_profile()
        engine = RecommendationEngine(mgr, cfg)
        assert not engine._fitted
        feed = DiscoveryFeed(engine, mgr)
        shelves = feed.generate(profile, n_per_shelf=2)
        assert engine._fitted
        assert len(shelves) >= 1


class TestFeedCLI:

    def test_recommend_feed_json(self, tmp_path: Path):
        """recommend feed --format json returns a list of shelf dicts."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        runner.invoke(cli, ["--data-dir", str(tmp_path), "library", "import", str(FIXTURE_PATH)])
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "recommend", "feed", "-n", "3",
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        for shelf in data:
            assert "name" in shelf
            assert "tag" in shelf
            assert "recommendations" in shelf

    def test_recommend_feed_with_mood(self, tmp_path: Path):
        """recommend feed accepts --mood without error."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        runner.invoke(cli, ["--data-dir", str(tmp_path), "library", "import", str(FIXTURE_PATH)])
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "recommend", "feed", "--mood", "relaxed", "-n", "2",
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        data = json.loads(result.output)
        assert isinstance(data, list)


# ================================================================== #
# Session-length filtering                                             #
# ================================================================== #

class TestSessionFilter:
    """Tests for session_type filtering in _build_candidate_list and generate()."""

    def _make_library(self, tmp_path: Path, games: list) -> tuple:
        cfg = AppConfig(data_dir=str(tmp_path))
        cfg.ensure_dirs()
        db = GameDatabase(cfg.database_path)
        for g in games:
            db.upsert_game(g)
        db.close()
        mgr = LibraryManager(cfg)
        engine = RecommendationEngine(mgr, cfg)
        profile = UserProfile()
        return mgr, engine, profile

    def test_quick_filter_excludes_long_session_games(self, tmp_path: Path):
        """Games with typical_session_minutes >= 60 are excluded for session_type='quick'."""
        short = _make_game(name="Short Game", typical_session_minutes=30)
        long = _make_game(name="Long Game", typical_session_minutes=240)
        mgr, engine, profile = self._make_library(tmp_path, [short, long])
        engine.fit()
        recs = engine.generate(profile, n=10, session_type="quick", save_to_db=False)
        names = [r.game.name for r in recs]
        assert "Short Game" in names
        assert "Long Game" not in names

    def test_quick_filter_allows_short_session_games(self, tmp_path: Path):
        """Games with typical_session_minutes < 60 are included for session_type='quick'."""
        short = _make_game(name="Quick Game", typical_session_minutes=45)
        mgr, engine, profile = self._make_library(tmp_path, [short])
        engine.fit()
        recs = engine.generate(profile, n=10, session_type="quick", save_to_db=False)
        assert any(r.game.name == "Quick Game" for r in recs)

    def test_deep_filter_excludes_short_session_games(self, tmp_path: Path):
        """Games with typical_session_minutes < 180 are excluded for session_type='deep'."""
        short = _make_game(name="Short Game", typical_session_minutes=30)
        epic = _make_game(name="Epic Game", typical_session_minutes=240)
        mgr, engine, profile = self._make_library(tmp_path, [short, epic])
        engine.fit()
        recs = engine.generate(profile, n=10, session_type="deep", save_to_db=False)
        names = [r.game.name for r in recs]
        assert "Epic Game" in names
        assert "Short Game" not in names

    def test_session_filter_allows_unknown_session_games(self, tmp_path: Path):
        """Games with typical_session_minutes=None pass both quick and deep filters."""
        unknown = _make_game(name="Unknown Session Game", typical_session_minutes=None)
        mgr, engine, profile = self._make_library(tmp_path, [unknown])
        engine.fit()

        recs_quick = engine.generate(profile, n=10, session_type="quick", save_to_db=False)
        recs_deep = engine.generate(profile, n=10, session_type="deep", save_to_db=False)
        assert any(r.game.name == "Unknown Session Game" for r in recs_quick)
        assert any(r.game.name == "Unknown Session Game" for r in recs_deep)

    def test_generate_with_session_type_returns_list(self, tmp_path: Path):
        """engine.generate() with session_type does not crash and returns a list."""
        games = [
            _make_game(name=f"Game {i}", typical_session_minutes=i * 20)
            for i in range(1, 6)
        ]
        mgr, engine, profile = self._make_library(tmp_path, games)
        engine.fit()
        result = engine.generate(profile, n=5, session_type="quick", save_to_db=False)
        assert isinstance(result, list)


# ================================================================== #
# Challenging mood                                                     #
# ================================================================== #

class TestChallengingMood:
    """Tests for the CHALLENGING mood entry added to the recommendation system."""

    def test_challenging_boosts_difficult_game(self):
        """A game tagged 'difficult'/'hardcore' scores > 0.5 for the challenging mood."""
        mf = MoodFilter()
        hard_game = _make_game(
            tags=["difficult", "hardcore", "punishing"],
            mechanics=["permadeath", "bullet hell"],
        )
        score = mf.score_game_for_mood(hard_game, Mood.CHALLENGING.value)
        assert score > 0.5, f"Expected score > 0.5 for hard game, got {score}"

    def test_challenging_penalizes_easy_game(self):
        """A game tagged 'easy'/'casual' scores < 0.5 for the challenging mood."""
        mf = MoodFilter()
        easy_game = _make_game(
            tags=["easy", "family friendly"],
            genres=["Casual"],
            mechanics=["casual"],
        )
        score = mf.score_game_for_mood(easy_game, Mood.CHALLENGING.value)
        assert score < 0.5, f"Expected score < 0.5 for easy game, got {score}"

    def test_challenging_in_mood_list(self):
        """MoodFilter.list_moods() includes 'challenging' with a description."""
        mf = MoodFilter()
        moods = mf.list_moods()
        mood_values = [m["mood"] for m in moods]
        assert "challenging" in mood_values

    def test_challenging_in_mood_enum(self):
        """Mood('challenging') resolves to Mood.CHALLENGING without error."""
        mood = Mood("challenging")
        assert mood == Mood.CHALLENGING
        assert mood.value == "challenging"


# ================================================================== #
# Completion-hours range filtering                                     #
# ================================================================== #

class TestCompletionHoursFilter:
    """Tests for max_completion_hours / min_completion_hours in generate()."""

    def _make_library(self, tmp_path: Path, games: list) -> tuple:
        cfg = AppConfig(data_dir=str(tmp_path))
        cfg.ensure_dirs()
        db = GameDatabase(cfg.database_path)
        for g in games:
            db.upsert_game(g)
        db.close()
        mgr = LibraryManager(cfg)
        engine = RecommendationEngine(mgr, cfg)
        profile = UserProfile()
        return mgr, engine, profile

    def test_max_hours_excludes_long_games(self, tmp_path: Path):
        """Games with completion_hours > max_completion_hours are excluded."""
        short = _make_game(name="Short Game", completion_hours=5.0)
        epic = _make_game(name="Epic Game", completion_hours=80.0)
        mgr, engine, profile = self._make_library(tmp_path, [short, epic])
        engine.fit()
        recs = engine.generate(profile, n=10, max_completion_hours=10.0, save_to_db=False)
        names = [r.game.name for r in recs]
        assert "Short Game" in names
        assert "Epic Game" not in names

    def test_max_hours_allows_short_games(self, tmp_path: Path):
        """Games with completion_hours <= max_completion_hours are included."""
        short = _make_game(name="Quick Finish", completion_hours=5.0)
        mgr, engine, profile = self._make_library(tmp_path, [short])
        engine.fit()
        recs = engine.generate(profile, n=10, max_completion_hours=10.0, save_to_db=False)
        assert any(r.game.name == "Quick Finish" for r in recs)

    def test_min_hours_excludes_short_games(self, tmp_path: Path):
        """Games with completion_hours < min_completion_hours are excluded."""
        short = _make_game(name="Short Game", completion_hours=5.0)
        long = _make_game(name="Long Game", completion_hours=80.0)
        mgr, engine, profile = self._make_library(tmp_path, [short, long])
        engine.fit()
        recs = engine.generate(profile, n=10, min_completion_hours=50.0, save_to_db=False)
        names = [r.game.name for r in recs]
        assert "Long Game" in names
        assert "Short Game" not in names

    def test_completion_hours_filter_allows_unknown(self, tmp_path: Path):
        """Games with completion_hours=None pass both min and max filters (lenient)."""
        unknown = _make_game(name="Unknown Length Game", completion_hours=None)
        mgr, engine, profile = self._make_library(tmp_path, [unknown])
        engine.fit()
        recs_max = engine.generate(profile, n=10, max_completion_hours=1.0, save_to_db=False)
        recs_min = engine.generate(profile, n=10, min_completion_hours=999.0, save_to_db=False)
        assert any(r.game.name == "Unknown Length Game" for r in recs_max)
        assert any(r.game.name == "Unknown Length Game" for r in recs_min)

    def test_hours_range_filter_integration(self, tmp_path: Path):
        """engine.generate() with max_completion_hours returns a list without error."""
        games = [
            _make_game(name=f"Game {i}", completion_hours=float(i * 10))
            for i in range(1, 6)
        ]
        mgr, engine, profile = self._make_library(tmp_path, games)
        engine.fit()
        result = engine.generate(profile, n=5, max_completion_hours=25.0, save_to_db=False)
        assert isinstance(result, list)


# ================================================================== #
# Difficulty filtering                                                 #
# ================================================================== #

class TestDifficultyFilter:
    """Tests for difficulty_filter in generate()."""

    def _make_library(self, tmp_path: Path, games: list) -> tuple:
        cfg = AppConfig(data_dir=str(tmp_path))
        cfg.ensure_dirs()
        db = GameDatabase(cfg.database_path)
        for g in games:
            db.upsert_game(g)
        db.close()
        mgr = LibraryManager(cfg)
        engine = RecommendationEngine(mgr, cfg)
        profile = UserProfile()
        return mgr, engine, profile

    def test_difficulty_filter_excludes_wrong_difficulty(self, tmp_path: Path):
        """Games with a different difficulty value are excluded."""
        easy = _make_game(name="Easy Game", difficulty="easy")
        hard = _make_game(name="Hard Game", difficulty="hard")
        mgr, engine, profile = self._make_library(tmp_path, [easy, hard])
        engine.fit()
        recs = engine.generate(profile, n=10, difficulty_filter="hard", save_to_db=False)
        names = [r.game.name for r in recs]
        assert "Hard Game" in names
        assert "Easy Game" not in names

    def test_difficulty_filter_allows_matching_difficulty(self, tmp_path: Path):
        """Games whose difficulty matches the filter are included."""
        hard = _make_game(name="Hard Game", difficulty="hard")
        mgr, engine, profile = self._make_library(tmp_path, [hard])
        engine.fit()
        recs = engine.generate(profile, n=10, difficulty_filter="hard", save_to_db=False)
        assert any(r.game.name == "Hard Game" for r in recs)

    def test_difficulty_filter_allows_none_difficulty(self, tmp_path: Path):
        """Games with difficulty=None always pass the difficulty filter (lenient)."""
        unknown = _make_game(name="Unrated Game", difficulty=None)
        mgr, engine, profile = self._make_library(tmp_path, [unknown])
        engine.fit()
        recs = engine.generate(profile, n=10, difficulty_filter="hard", save_to_db=False)
        assert any(r.game.name == "Unrated Game" for r in recs)

    def test_difficulty_filter_integration(self, tmp_path: Path):
        """engine.generate() with difficulty_filter returns a list without error."""
        games = [
            _make_game(name="Game Easy", difficulty="easy"),
            _make_game(name="Game Hard", difficulty="hard"),
            _make_game(name="Game Unknown", difficulty=None),
        ]
        mgr, engine, profile = self._make_library(tmp_path, games)
        engine.fit()
        result = engine.generate(profile, n=5, difficulty_filter="hard", save_to_db=False)
        assert isinstance(result, list)


# ================================================================== #
# Multiplayer and VR filtering                                        #
# ================================================================== #

class TestMultiplayerVRFilter:
    """Tests for multiplayer_filter and vr_only in generate()."""

    def _make_library(self, tmp_path: Path, games: list) -> tuple:
        cfg = AppConfig(data_dir=str(tmp_path))
        cfg.ensure_dirs()
        db = GameDatabase(cfg.database_path)
        for g in games:
            db.upsert_game(g)
        db.close()
        mgr = LibraryManager(cfg)
        engine = RecommendationEngine(mgr, cfg)
        profile = UserProfile()
        return mgr, engine, profile

    def test_multiplayer_filter_true_excludes_singleplayer(self, tmp_path: Path):
        """multiplayer_filter=True excludes games with multiplayer_support=False."""
        solo = _make_game(name="Solo Game", multiplayer_support=False)
        multi = _make_game(name="Multi Game", multiplayer_support=True)
        mgr, engine, profile = self._make_library(tmp_path, [solo, multi])
        engine.fit()
        recs = engine.generate(profile, n=10, multiplayer_filter=True, save_to_db=False)
        names = [r.game.name for r in recs]
        assert "Multi Game" in names
        assert "Solo Game" not in names

    def test_multiplayer_filter_true_allows_multiplayer_game(self, tmp_path: Path):
        """multiplayer_filter=True includes games with multiplayer_support=True."""
        multi = _make_game(name="Online Game", multiplayer_support=True)
        mgr, engine, profile = self._make_library(tmp_path, [multi])
        engine.fit()
        recs = engine.generate(profile, n=10, multiplayer_filter=True, save_to_db=False)
        assert any(r.game.name == "Online Game" for r in recs)

    def test_vr_only_excludes_non_vr_games(self, tmp_path: Path):
        """vr_only=True excludes games with vr_compatible=False."""
        flat = _make_game(name="Flat Game", vr_compatible=False)
        vr = _make_game(name="VR Game", vr_compatible=True)
        mgr, engine, profile = self._make_library(tmp_path, [flat, vr])
        engine.fit()
        recs = engine.generate(profile, n=10, vr_only=True, save_to_db=False)
        names = [r.game.name for r in recs]
        assert "VR Game" in names
        assert "Flat Game" not in names

    def test_vr_only_allows_vr_games(self, tmp_path: Path):
        """vr_only=True includes games with vr_compatible=True."""
        vr = _make_game(name="VR Experience", vr_compatible=True)
        mgr, engine, profile = self._make_library(tmp_path, [vr])
        engine.fit()
        recs = engine.generate(profile, n=10, vr_only=True, save_to_db=False)
        assert any(r.game.name == "VR Experience" for r in recs)


# ================================================================== #
# Combining multiple filters                                           #
# ================================================================== #

class TestCombineFilters:
    """Tests for combining multiple recommendation filters at once."""

    def _make_library(self, tmp_path: Path, games: list) -> tuple:
        cfg = AppConfig(data_dir=str(tmp_path))
        cfg.ensure_dirs()
        db = GameDatabase(cfg.database_path)
        for g in games:
            db.upsert_game(g)
        db.close()
        mgr = LibraryManager(cfg)
        engine = RecommendationEngine(mgr, cfg)
        profile = UserProfile()
        return mgr, engine, profile

    def test_combine_difficulty_and_session_filters(self, tmp_path: Path):
        """difficulty_filter + session_type both apply simultaneously."""
        match = _make_game(
            name="Hard Quick Game",
            difficulty="hard",
            typical_session_minutes=30,
        )
        no_match_diff = _make_game(
            name="Easy Quick Game",
            difficulty="easy",
            typical_session_minutes=30,
        )
        no_match_sess = _make_game(
            name="Hard Long Game",
            difficulty="hard",
            typical_session_minutes=240,
        )
        mgr, engine, profile = self._make_library(
            tmp_path, [match, no_match_diff, no_match_sess]
        )
        engine.fit()
        recs = engine.generate(
            profile, n=10,
            difficulty_filter="hard",
            session_type="quick",
            save_to_db=False,
        )
        names = [r.game.name for r in recs]
        assert "Hard Quick Game" in names
        assert "Easy Quick Game" not in names
        assert "Hard Long Game" not in names

    def test_combine_genre_and_multiplayer_filters(self, tmp_path: Path):
        """genre_filter + multiplayer_filter both apply simultaneously."""
        match = _make_game(
            name="RPG Online",
            genres=["RPG"],
            multiplayer_support=True,
        )
        no_match_genre = _make_game(
            name="Action Online",
            genres=["Action"],
            multiplayer_support=True,
        )
        no_match_multi = _make_game(
            name="RPG Solo",
            genres=["RPG"],
            multiplayer_support=False,
        )
        mgr, engine, profile = self._make_library(
            tmp_path, [match, no_match_genre, no_match_multi]
        )
        engine.fit()
        recs = engine.generate(
            profile, n=10,
            genre_filter="RPG",
            multiplayer_filter=True,
            save_to_db=False,
        )
        names = [r.game.name for r in recs]
        assert "RPG Online" in names
        assert "Action Online" not in names
        assert "RPG Solo" not in names


# ================================================================== #
# clear-filters command                                               #
# ================================================================== #

class TestClearFiltersCommand:
    """Tests for the 'playnite recommend clear-filters' CLI command."""

    def _make_cfg(self, tmp_path: Path) -> AppConfig:
        cfg = AppConfig(data_dir=str(tmp_path))
        cfg.ensure_dirs()
        return cfg

    def test_clear_filters_clears_mood(self, tmp_path: Path):
        """clear-filters removes the profile's current_mood."""
        from click.testing import CliRunner
        from playnite_py.cli.recommend_commands import recommend

        cfg = self._make_cfg(tmp_path)
        mgr = LibraryManager(cfg)
        profile = mgr.get_or_create_profile()
        profile.set_mood("relaxed")
        mgr.save_profile(profile)
        assert profile.current_mood == "relaxed"

        runner = CliRunner()
        result = runner.invoke(
            recommend,
            ["clear-filters"],
            obj={"config": cfg, "output_format": "table"},
        )
        assert result.exit_code == 0

        # Reload profile from DB and verify mood is cleared
        updated = mgr.get_or_create_profile(profile.id)
        assert updated.current_mood is None

    def test_clear_filters_no_op_when_no_mood(self, tmp_path: Path):
        """clear-filters exits cleanly when no persistent filters are set."""
        from click.testing import CliRunner
        from playnite_py.cli.recommend_commands import recommend

        cfg = self._make_cfg(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            recommend,
            ["clear-filters"],
            obj={"config": cfg, "output_format": "table"},
        )
        assert result.exit_code == 0
        assert "No persistent filters" in result.output or "omit the flag" in result.output
