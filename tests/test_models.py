"""Tests for game data models and database."""

import json
import os
import tempfile

import pytest

from playnite_py.models.game import (
    Game, Platform, Genre, Developer, Publisher, Tag,
    Category, Feature, Series, AgeRating, Region, Link,
    CompletionStatus,
)
from playnite_py.models.action import (
    GameAction, ActionType, ActionPhase, ActionPriority,
    ActionCondition, ActionResult, ActionChainResult,
)
from playnite_py.models.database import GameDatabase


# ======================================================================
# Game model tests
# ======================================================================

class TestGame:
    def test_create_default(self):
        game = Game()
        assert game.id
        assert game.name == ""
        assert game.completion_status == CompletionStatus.NOT_PLAYED
        assert game.playtime == 0
        assert game.is_installed is False

    def test_create_with_fields(self):
        game = Game(name="Test Game", source="Steam", is_installed=True)
        assert game.name == "Test Game"
        assert game.source == "Steam"
        assert game.is_installed is True

    def test_to_dict(self):
        game = Game(name="Test", source="GOG")
        d = game.to_dict()
        assert d["name"] == "Test"
        assert d["source"] == "GOG"
        assert d["completion_status"] == "not_played"
        assert isinstance(d["links"], list)

    def test_from_dict(self):
        data = {
            "id": "test-id",
            "name": "From Dict",
            "source": "Epic",
            "completion_status": "completed",
            "playtime": 3600,
            "links": [{"name": "Website", "url": "https://example.com"}],
        }
        game = Game.from_dict(data)
        assert game.id == "test-id"
        assert game.name == "From Dict"
        assert game.completion_status == CompletionStatus.COMPLETED
        assert game.playtime == 3600
        assert len(game.links) == 1
        assert game.links[0].url == "https://example.com"

    def test_round_trip(self):
        game = Game(
            name="Round Trip",
            platform_ids=["p1", "p2"],
            genre_ids=["g1"],
            links=[Link(name="Steam", url="https://store.steampowered.com")],
            completion_status=CompletionStatus.BEATEN,
            playtime=7200,
            favorite=True,
        )
        data = game.to_dict()
        restored = Game.from_dict(data)
        assert restored.name == game.name
        assert restored.platform_ids == game.platform_ids
        assert restored.completion_status == game.completion_status
        assert restored.playtime == 7200
        assert restored.favorite is True

    def test_clone(self):
        game = Game(name="Original", tag_ids=["t1"])
        cloned = game.clone()
        cloned.name = "Clone"
        cloned.tag_ids.append("t2")
        assert game.name == "Original"
        assert "t2" not in game.tag_ids


class TestMetadataEntities:
    def test_platform(self):
        p = Platform(name="PC")
        d = p.to_dict()
        assert d["name"] == "PC"
        restored = Platform.from_dict(d)
        assert restored.name == "PC"

    def test_genre(self):
        g = Genre(name="RPG")
        assert Genre.from_dict(g.to_dict()).name == "RPG"

    def test_tag(self):
        t = Tag(name="Favorite")
        assert Tag.from_dict(t.to_dict()).name == "Favorite"

    def test_link(self):
        link = Link(name="Homepage", url="https://example.com")
        d = link.to_dict()
        assert d["name"] == "Homepage"
        assert Link.from_dict(d).url == "https://example.com"


# ======================================================================
# Action model tests
# ======================================================================

class TestGameAction:
    def test_create_default(self):
        action = GameAction()
        assert action.id
        assert action.action_type == ActionType.CUSTOM
        assert action.phase == ActionPhase.PRE_LAUNCH
        assert action.priority == ActionPriority.NORMAL.value
        assert action.enabled is True

    def test_to_dict_from_dict(self):
        action = GameAction(
            name="Test Action",
            script="print('hello')",
            action_type=ActionType.PLAY,
            phase=ActionPhase.POST_EXIT,
            priority=75,
            conditions=[ActionCondition(field="env.os", operator="equals", value="linux")],
            game_id="game-123",
        )
        d = action.to_dict()
        assert d["action_type"] == "play"
        assert d["phase"] == "post_exit"

        restored = GameAction.from_dict(d)
        assert restored.name == "Test Action"
        assert restored.action_type == ActionType.PLAY
        assert restored.phase == ActionPhase.POST_EXIT
        assert len(restored.conditions) == 1
        assert restored.conditions[0].field == "env.os"


class TestActionResult:
    def test_chain_result_all_succeeded(self):
        chain = ActionChainResult(
            game_id="g1",
            phase=ActionPhase.PRE_LAUNCH,
            results=[
                ActionResult(action_id="a1", success=True),
                ActionResult(action_id="a2", success=True),
            ],
        )
        assert chain.all_succeeded is True

    def test_chain_result_failure(self):
        chain = ActionChainResult(
            results=[
                ActionResult(success=True),
                ActionResult(success=False, error="timeout"),
            ],
        )
        assert chain.all_succeeded is False

    def test_chain_result_round_trip(self):
        chain = ActionChainResult(
            game_id="g1",
            phase=ActionPhase.POST_EXIT,
            results=[ActionResult(action_id="a1", success=True, duration=0.5)],
            total_duration=0.5,
        )
        d = chain.to_dict()
        assert d["all_succeeded"] is True
        restored = ActionChainResult.from_dict(d)
        assert restored.phase == ActionPhase.POST_EXIT
        assert len(restored.results) == 1


# ======================================================================
# Database tests
# ======================================================================

class TestGameDatabase:
    def test_add_and_get_game(self):
        db = GameDatabase()
        game = Game(name="Test Game")
        db.add_game(game)
        assert db.get_game(game.id) is game
        assert len(db.get_all_games()) == 1

    def test_update_game(self):
        db = GameDatabase()
        game = Game(name="Original")
        db.add_game(game)
        game.name = "Updated"
        db.update_game(game)
        assert db.get_game(game.id).name == "Updated"

    def test_remove_game(self):
        db = GameDatabase()
        game = Game(name="To Remove")
        db.add_game(game)
        assert db.remove_game(game.id) is True
        assert db.get_game(game.id) is None
        assert db.remove_game("nonexistent") is False

    def test_query_games(self):
        db = GameDatabase()
        db.add_game(Game(name="Installed Game", is_installed=True, source="Steam"))
        db.add_game(Game(name="Not Installed", is_installed=False, source="GOG"))
        db.add_game(Game(name="Another Steam", is_installed=True, source="Steam"))

        assert len(db.query_games(is_installed=True)) == 2
        assert len(db.query_games(source="Steam")) == 2
        assert len(db.query_games(source="GOG")) == 1
        assert len(db.query_games(name="Another")) == 1

    def test_actions_crud(self):
        db = GameDatabase()
        game = Game(name="Test")
        db.add_game(game)

        action = GameAction(name="Pre-launch", game_id=game.id, phase=ActionPhase.PRE_LAUNCH)
        db.add_action(action)
        assert action.id in game.action_ids
        assert db.get_action(action.id) is action

        actions = db.get_actions_for_game(game.id, "pre_launch")
        assert len(actions) == 1

        db.remove_action(action.id)
        assert db.get_action(action.id) is None
        assert action.id not in game.action_ids

    def test_metadata_crud(self):
        db = GameDatabase()
        p = db.add_platform(Platform(name="PC"))
        g = db.add_genre(Genre(name="RPG"))
        t = db.add_tag(Tag(name="Favorite"))

        assert len(db.get_platforms()) == 1
        assert len(db.get_genres()) == 1
        assert len(db.get_tags()) == 1

        db.remove_tag(t.id)
        assert len(db.get_tags()) == 0

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            # Write
            db = GameDatabase(path=path)
            db.add_game(Game(name="Persistent Game", source="Steam"))
            db.add_platform(Platform(name="PC"))
            db.add_action(GameAction(name="Test Action"))
            db.save()

            # Read back
            db2 = GameDatabase(path=path)
            games = db2.get_all_games()
            assert len(games) == 1
            assert games[0].name == "Persistent Game"
            assert len(db2.get_platforms()) == 1
            assert len(db2.get_all_actions()) == 1
        finally:
            os.unlink(path)

    def test_event_callbacks(self):
        db = GameDatabase()
        added_games = []
        removed_games = []
        db.on_game_added.append(lambda g: added_games.append(g))
        db.on_game_removed.append(lambda g: removed_games.append(g))

        game = Game(name="Event Test")
        db.add_game(game)
        assert len(added_games) == 1

        db.remove_game(game.id)
        assert len(removed_games) == 1

    def test_stats(self):
        db = GameDatabase()
        db.add_game(Game(name="G1", playtime=100, is_installed=True))
        db.add_game(Game(name="G2", playtime=200, is_installed=False,
                         completion_status=CompletionStatus.COMPLETED))
        stats = db.get_stats()
        assert stats["total_games"] == 2
        assert stats["installed_games"] == 1
        assert stats["total_playtime_seconds"] == 300
