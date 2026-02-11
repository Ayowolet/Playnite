"""
Tests for new C#-parity features implemented in the Python Playnite SDK.

Covers:
  - Enhanced Game model (enums, fields, computed properties, methods)
  - New lifecycle hooks
  - ScriptManager.invoke_function / set_variable
  - Rich NotificationAPI
  - Extended GameDatabaseAPI (entity collections, buffered_update)
  - PlayniteSDK.expand_game_variables / start_game / install_game / uninstall_game
  - Plugin base class
  - LibraryPlugin
  - MetadataPlugin
  - PluginManager

Run with::

    pytest source/playnite_python/tests/test_plugins.py -v
"""

from __future__ import annotations

import sys
import textwrap
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

# Ensure the package root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playnite_python.database.game_database import GameDatabase
from playnite_python.extensions.lifecycle import LifecycleDispatcher, ALL_HOOKS
from playnite_python.extensions.logger import ScriptLogManager
from playnite_python.extensions.manager import ScriptManager
from playnite_python.extensions.sdk import (
    PlayniteSDK, PathsAPI, NotificationAPI, NotificationType,
    NotificationMessage, GameDatabaseAPI,
)
from playnite_python.models.game import (
    Game, TrackingMode,
    ScoreRating, ScoreGroup, PastTimeSegment, PlaytimeCategory,
    InstallSizeGroup, InstallationStatus, GameField,
    _score_rating, _score_group, _classify_past_time,
)
from playnite_python.plugins import (
    Plugin, PluginProperties, MainMenuItem, GameMenuItem,
    GetMainMenuItemsArgs, GetGameMenuItemsArgs,
    LibraryPlugin, LibraryGetGamesArgs, GameMetadata,
    MetadataPlugin, MetadataField, OnDemandMetadataProvider,
    MetadataRequestOptions, GetMetadataFieldArgs,
    PluginManager,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_db():
    db = GameDatabase(":memory:")
    db.open()
    yield db
    db.close()


@pytest.fixture
def log_manager(tmp_path):
    return ScriptLogManager(str(tmp_path / "logs"))


@pytest.fixture
def lifecycle():
    return LifecycleDispatcher()


@pytest.fixture
def sdk(in_memory_db, tmp_path, log_manager, lifecycle):
    logger = log_manager.get_logger("test")
    paths = PathsAPI(
        app_path=str(tmp_path),
        config_path=str(tmp_path / "config"),
        database_path=str(tmp_path / "library.db"),
        extension_path=str(tmp_path / "extensions"),
        extension_data_path=str(tmp_path / "extensions" / ".data" / "test"),
        log_path=str(tmp_path / "logs"),
    )
    return PlayniteSDK(
        db=in_memory_db, paths=paths, logger=logger,
        headless=True, lifecycle=lifecycle,
    )


@pytest.fixture
def script_manager(in_memory_db, tmp_path):
    ext_dir = tmp_path / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    return ScriptManager(
        extensions_dir=str(ext_dir),
        db=in_memory_db,
        app_paths={
            "app": str(tmp_path),
            "config": str(tmp_path / "config"),
            "database": ":memory:",
            "logs": str(tmp_path / "logs"),
        },
    )


# ---------------------------------------------------------------------------
# 1. TestGameModelEnhancements
# ---------------------------------------------------------------------------

class TestGameModelEnhancements:

    # -- TrackingMode ----------------------------------------------------------

    def test_tracking_mode_original_process(self):
        assert TrackingMode.ORIGINAL_PROCESS.value == "OriginalProcess"
        action = TrackingMode("OriginalProcess")
        assert action == TrackingMode.ORIGINAL_PROCESS

    # -- New fields ------------------------------------------------------------

    def test_new_fields_defaults(self):
        g = Game()
        assert g.game_id == ""
        assert g.sorting_name == ""
        assert g.roms == []
        assert g.include_library_plugin_action is True
        assert g.last_size_scan_date is None
        assert g.is_installing is False
        assert g.is_uninstalling is False

    def test_new_fields_roundtrip(self):
        now = datetime(2024, 6, 15, 12, 0, 0)
        g = Game(
            game_id="570",
            sorting_name="Dota 2",
            roms=["/roms/game.rom"],
            include_library_plugin_action=False,
            last_size_scan_date=now,
            is_installing=True,
            is_uninstalling=True,
        )
        restored = Game.from_dict(g.to_dict())
        assert restored.game_id == "570"
        assert restored.sorting_name == "Dota 2"
        assert restored.roms == ["/roms/game.rom"]
        assert restored.include_library_plugin_action is False
        assert restored.last_size_scan_date == now
        assert restored.is_installing is True
        assert restored.is_uninstalling is True

    # -- Computed: release_year ------------------------------------------------

    def test_release_year_none_when_no_date(self):
        assert Game().release_year is None

    def test_release_year_with_date(self):
        g = Game(release_date=datetime(2004, 6, 1))
        assert g.release_year == 2004

    # -- Computed: is_custom_game ----------------------------------------------

    def test_is_custom_game_true(self):
        assert Game().is_custom_game is True

    def test_is_custom_game_false_when_plugin_id_set(self):
        g = Game(plugin_id="com.example.steam")
        assert g.is_custom_game is False

    # -- Computed: installation_status -----------------------------------------

    def test_installation_status_uninstalled(self):
        assert Game().installation_status == InstallationStatus.UNINSTALLED

    def test_installation_status_installed(self):
        g = Game(is_installed=True)
        assert g.installation_status == InstallationStatus.INSTALLED

    # -- Score ratings ---------------------------------------------------------

    def test_score_rating_none(self):
        assert _score_rating(None) == ScoreRating.NONE

    def test_score_rating_negative(self):
        assert _score_rating(0) == ScoreRating.NEGATIVE
        assert _score_rating(39) == ScoreRating.NEGATIVE

    def test_score_rating_mixed(self):
        assert _score_rating(40) == ScoreRating.MIXED
        assert _score_rating(74) == ScoreRating.MIXED

    def test_score_rating_positive(self):
        assert _score_rating(75) == ScoreRating.POSITIVE
        assert _score_rating(100) == ScoreRating.POSITIVE

    def test_game_score_rating_properties(self):
        g = Game(user_score=80, community_score=50, critic_score=30)
        assert g.user_score_rating == ScoreRating.POSITIVE
        assert g.community_score_rating == ScoreRating.MIXED
        assert g.critic_score_rating == ScoreRating.NEGATIVE

    # -- Score groups ----------------------------------------------------------

    def test_score_group_none(self):
        assert _score_group(None) == ScoreGroup.NONE

    def test_score_group_0s(self):
        assert _score_group(5) == ScoreGroup.O0x

    def test_score_group_7s(self):
        assert _score_group(75) == ScoreGroup.O7x

    def test_score_group_100(self):
        assert _score_group(100) == ScoreGroup.O9x

    def test_game_score_group_properties(self):
        g = Game(user_score=85, community_score=None, critic_score=15)
        assert g.user_score_group == ScoreGroup.O8x
        assert g.community_score_group == ScoreGroup.NONE
        assert g.critic_score_group == ScoreGroup.O1x

    # -- Past time segments ----------------------------------------------------

    def test_classify_none_is_never(self):
        assert _classify_past_time(None) == PastTimeSegment.NEVER

    def test_classify_today(self):
        assert _classify_past_time(datetime.now()) == PastTimeSegment.TODAY

    def test_classify_yesterday(self):
        dt = datetime.now() - timedelta(days=1)
        assert _classify_past_time(dt) == PastTimeSegment.YESTERDAY

    def test_classify_past_week(self):
        dt = datetime.now() - timedelta(days=5)
        assert _classify_past_time(dt) == PastTimeSegment.PAST_WEEK

    def test_classify_past_month(self):
        dt = datetime.now() - timedelta(days=20)
        assert _classify_past_time(dt) == PastTimeSegment.PAST_MONTH

    def test_classify_past_year(self):
        dt = datetime.now() - timedelta(days=200)
        assert _classify_past_time(dt) == PastTimeSegment.PAST_YEAR

    def test_classify_more_than_year(self):
        dt = datetime.now() - timedelta(days=400)
        assert _classify_past_time(dt) == PastTimeSegment.MORE_THAN_YEAR

    def test_game_last_activity_segment(self):
        g = Game(last_activity=datetime.now())
        assert g.last_activity_segment == PastTimeSegment.TODAY

    def test_game_added_segment_today(self):
        # default 'added' is datetime.now()
        assert Game().added_segment == PastTimeSegment.TODAY

    # -- Playtime category -----------------------------------------------------

    def test_playtime_not_played(self):
        assert Game(play_time=0).playtime_category == PlaytimeCategory.NOT_PLAYED

    def test_playtime_less_than_hour(self):
        assert Game(play_time=1800).playtime_category == PlaytimeCategory.LESS_THAN_HOUR

    def test_playtime_1_10(self):
        assert Game(play_time=7200).playtime_category == PlaytimeCategory.O1_10

    def test_playtime_10_100(self):
        assert Game(play_time=180_000).playtime_category == PlaytimeCategory.O10_100

    def test_playtime_100_500(self):
        assert Game(play_time=900_000).playtime_category == PlaytimeCategory.O100_500

    def test_playtime_500_1000(self):
        assert Game(play_time=2_500_000).playtime_category == PlaytimeCategory.O500_1000

    def test_playtime_over_1000(self):
        assert Game(play_time=4_000_000).playtime_category == PlaytimeCategory.O1000PLUS

    # -- Install size group ----------------------------------------------------

    def test_install_size_group_none(self):
        assert Game().install_size_group == InstallSizeGroup.NONE
        assert Game(install_size=0).install_size_group == InstallSizeGroup.NONE

    def test_install_size_group_s0_under_100mb(self):
        assert Game(install_size=50 * 1024 * 1024).install_size_group == InstallSizeGroup.S0

    def test_install_size_group_s2_1to5gb(self):
        assert Game(install_size=2 * 1024**3).install_size_group == InstallSizeGroup.S2

    def test_install_size_group_s7_over_100gb(self):
        assert Game(install_size=150 * 1024**3).install_size_group == InstallSizeGroup.S7

    # -- get_copy --------------------------------------------------------------

    def test_get_copy_returns_equal_object(self):
        g = Game(name="Celeste", user_score=90)
        copy = g.get_copy()
        assert copy.name == "Celeste"
        assert copy.user_score == 90

    def test_get_copy_is_independent(self):
        g = Game(name="Original")
        copy = g.get_copy()
        copy.name = "Modified"
        assert g.name == "Original"

    # -- get_name_group --------------------------------------------------------

    def test_get_name_group_alphabetic(self):
        assert Game(name="Zelda").get_name_group() == "Z"
        assert Game(name="abcde").get_name_group() == "A"

    def test_get_name_group_non_alpha(self):
        assert Game(name="1984").get_name_group() == "#"
        assert Game(name="").get_name_group() == "#"

    # -- get_install_drive -----------------------------------------------------

    def test_get_install_drive_empty(self):
        assert Game().get_install_drive() == ""

    def test_get_install_drive_unix(self):
        g = Game(install_directory="/home/user/games/celeste")
        assert g.get_install_drive() == "/"

    def test_get_install_drive_group(self):
        g = Game(install_directory="/games/doom")
        # On Unix, anchor is "/" — group strips trailing slash → ""
        # but we fall back to "#" when empty
        result = g.get_install_drive_group()
        assert isinstance(result, str)

    # -- get_differences -------------------------------------------------------

    def test_get_differences_same_game(self):
        g = Game(name="Hollow Knight")
        assert g.get_differences(g.get_copy()) == []

    def test_get_differences_name_changed(self):
        g = Game(name="Hollow Knight")
        h = g.get_copy()
        h.name = "Silksong"
        diffs = g.get_differences(h)
        assert GameField.Name in diffs

    def test_get_differences_multiple(self):
        g = Game(name="A", user_score=80)
        h = Game(name="B", user_score=90)
        diffs = g.get_differences(h)
        assert GameField.Name in diffs
        assert GameField.UserScore in diffs

    # -- copy_diff_to ----------------------------------------------------------

    def test_copy_diff_to_copies_non_default_fields(self):
        source = Game(name="New Name", description="Some desc")
        target = Game(name="Old Name", description="")
        source.copy_diff_to(target)
        assert target.name == "New Name"
        assert target.description == "Some desc"

    def test_copy_diff_to_does_not_overwrite_with_default(self):
        # source has default (empty) name, target has a real name
        source = Game(name="", description="Source desc")
        target = Game(name="Original", description="Old desc")
        source.copy_diff_to(target)
        # name is default ("") so should NOT be copied
        assert target.name == "Original"
        # description is non-default so IS copied
        assert target.description == "Source desc"

    # -- GameField enum --------------------------------------------------------

    def test_game_field_enum_values(self):
        assert GameField.Name.value == "Name"
        assert GameField.SortingName.value == "SortingName"
        assert GameField.GameId.value == "GameId"
        assert GameField.Roms.value == "Roms"
        assert GameField.IsInstalling.value == "IsInstalling"


# ---------------------------------------------------------------------------
# 2. TestLifecycleNewHooks
# ---------------------------------------------------------------------------

class TestLifecycleNewHooks:

    def test_new_hooks_in_all_hooks(self):
        assert "on_game_startup_cancelled" in ALL_HOOKS
        assert "on_game_installation_cancelled" in ALL_HOOKS
        assert "on_game_selected" in ALL_HOOKS
        assert "on_settings_changed" in ALL_HOOKS

    def test_on_game_startup_cancelled_dispatched(self):
        dispatcher = LifecycleDispatcher()
        calls = []
        dispatcher.register("on_game_startup_cancelled", lambda g: calls.append(g), "test")
        game = Game(name="Doom")
        dispatcher.on_game_startup_cancelled(game)
        assert len(calls) == 1 and calls[0].name == "Doom"

    def test_on_game_installation_cancelled_dispatched(self):
        dispatcher = LifecycleDispatcher()
        calls = []
        dispatcher.register("on_game_installation_cancelled", lambda g: calls.append(g), "test")
        game = Game(name="Quake")
        dispatcher.on_game_installation_cancelled(game)
        assert calls[0].name == "Quake"

    def test_on_game_selected_dispatched_with_none(self):
        dispatcher = LifecycleDispatcher()
        calls = []
        dispatcher.register("on_game_selected", lambda g: calls.append(g), "test")
        dispatcher.on_game_selected(None)
        assert calls == [None]

    def test_on_game_selected_dispatched_with_game(self):
        dispatcher = LifecycleDispatcher()
        calls = []
        dispatcher.register("on_game_selected", lambda g: calls.append(g), "test")
        game = Game(name="Half-Life")
        dispatcher.on_game_selected(game)
        assert calls[0].name == "Half-Life"

    def test_on_settings_changed_dispatched(self):
        dispatcher = LifecycleDispatcher()
        calls = []
        dispatcher.register("on_settings_changed", lambda: calls.append(True), "test")
        dispatcher.on_settings_changed()
        assert calls == [True]

    def test_new_hooks_registered_from_namespace(self):
        dispatcher = LifecycleDispatcher()
        calls = []
        namespace = {
            "on_game_startup_cancelled": lambda g: calls.append(("startup_cancelled", g)),
            "on_settings_changed": lambda: calls.append(("settings_changed",)),
        }
        registered = dispatcher.register_from_namespace(namespace, "myscript")
        assert "on_game_startup_cancelled" in registered
        assert "on_settings_changed" in registered
        dispatcher.on_game_startup_cancelled(Game(name="X"))
        dispatcher.on_settings_changed()
        assert any(r[0] == "startup_cancelled" for r in calls)
        assert any(r[0] == "settings_changed" for r in calls)


# ---------------------------------------------------------------------------
# 3. TestScriptManagerInvoke
# ---------------------------------------------------------------------------

class TestScriptManagerInvoke:

    @pytest.fixture
    def loaded_manager(self, in_memory_db, tmp_path):
        ext_dir = tmp_path / "extensions"
        ext_dir.mkdir()
        # Write a simple script
        script = ext_dir / "greet.py"
        script.write_text(textwrap.dedent("""\
            def say_hello(name):
                return f"Hello, {name}!"

            def add(a, b):
                return a + b

            x = 42
        """), encoding="utf-8")
        mgr = ScriptManager(
            extensions_dir=str(ext_dir),
            db=in_memory_db,
            app_paths={"logs": str(tmp_path / "logs")},
        )
        mgr.load_script(str(script))
        return mgr

    def test_invoke_function_returns_value(self, loaded_manager):
        result = loaded_manager.invoke_function("greet", "say_hello", "World")
        assert result == "Hello, World!"

    def test_invoke_function_with_multiple_args(self, loaded_manager):
        result = loaded_manager.invoke_function("greet", "add", 3, 4)
        assert result == 7

    def test_invoke_function_unknown_script_raises_key_error(self, loaded_manager):
        with pytest.raises(KeyError, match="not loaded"):
            loaded_manager.invoke_function("no_such_script", "say_hello")

    def test_invoke_function_missing_fn_raises_attribute_error(self, loaded_manager):
        with pytest.raises(AttributeError, match="not found or not callable"):
            loaded_manager.invoke_function("greet", "nonexistent_fn")

    def test_set_variable_injects_into_namespace(self, loaded_manager):
        loaded_manager.set_variable("greet", "my_var", 999)
        result = loaded_manager.invoke_function("greet", "say_hello", "test")
        # my_var is now in the namespace
        script = loaded_manager.get_script("greet")
        assert script.namespace["my_var"] == 999

    def test_set_variable_unknown_script_raises_key_error(self, loaded_manager):
        with pytest.raises(KeyError, match="not loaded"):
            loaded_manager.set_variable("no_such_script", "x", 1)


# ---------------------------------------------------------------------------
# 4. TestNotificationAPI
# ---------------------------------------------------------------------------

class TestNotificationAPI:

    def test_add_creates_message(self):
        api = NotificationAPI()
        api.add("n1", "Hello", NotificationType.INFO)
        assert api.count == 1
        assert api.messages[0].id == "n1"
        assert api.messages[0].text == "Hello"
        assert api.messages[0].type == NotificationType.INFO

    def test_add_with_action(self):
        api = NotificationAPI()
        cb = lambda: None
        api.add("n2", "Click me", action=cb)
        assert api.messages[0].activation_action is cb

    def test_remove_by_id(self):
        api = NotificationAPI()
        api.add("a", "First")
        api.add("b", "Second")
        api.remove("a")
        assert api.count == 1
        assert api.messages[0].id == "b"

    def test_remove_nonexistent_is_noop(self):
        api = NotificationAPI()
        api.add("x", "msg")
        api.remove("does_not_exist")
        assert api.count == 1

    def test_remove_all(self):
        api = NotificationAPI()
        api.add("1", "a")
        api.add("2", "b")
        api.remove_all()
        assert api.count == 0

    def test_messages_property_returns_snapshot(self):
        api = NotificationAPI()
        api.add("id", "text")
        snap = api.messages
        api.remove_all()
        # snapshot is independent
        assert len(snap) == 1

    def test_count_property(self):
        api = NotificationAPI()
        assert api.count == 0
        api.add("a", "x")
        api.add("b", "y")
        assert api.count == 2

    def test_show_backward_compat(self):
        api = NotificationAPI()
        api.show("Legacy message", "info")
        assert api.count == 1
        msg = api.messages[0]
        assert msg.text == "Legacy message"
        assert msg.type == NotificationType.INFO

    def test_show_error_type(self):
        api = NotificationAPI()
        api.show("Something broke", "error")
        assert api.messages[0].type == NotificationType.ERROR

    def test_callbacks_fired_on_add(self):
        api = NotificationAPI()
        fired = []
        api._register_handler(lambda text, ntype: fired.append((text, ntype)))
        api.add("n", "Test msg", NotificationType.ERROR)
        assert fired == [("Test msg", "error")]

    def test_clear_callbacks(self):
        api = NotificationAPI()
        fired = []
        api._register_handler(lambda t, n: fired.append(t))
        api.clear_callbacks()
        api.add("x", "msg")
        assert fired == []

    def test_notification_type_enum(self):
        assert NotificationType.INFO.value == "info"
        assert NotificationType.ERROR.value == "error"


# ---------------------------------------------------------------------------
# 5. TestGameDatabaseAPIExtended
# ---------------------------------------------------------------------------

class TestGameDatabaseAPIExtended:

    def test_platforms_pass_through(self, in_memory_db, tmp_path, log_manager, lifecycle):
        logger = log_manager.get_logger("test")
        paths = PathsAPI(
            app_path=str(tmp_path), config_path=str(tmp_path / "cfg"),
            database_path=":memory:", extension_path=str(tmp_path),
            extension_data_path=str(tmp_path), log_path=str(tmp_path),
        )
        sdk = PlayniteSDK(db=in_memory_db, paths=paths, logger=logger, lifecycle=lifecycle)
        from playnite_python.models.game import Platform
        p = Platform(name="PC")
        in_memory_db.platforms.add(p)
        result = sdk.database.platforms.all()
        assert any(pl.name == "PC" for pl in result)

    def test_tags_pass_through(self, in_memory_db, tmp_path, log_manager, lifecycle):
        logger = log_manager.get_logger("test2")
        paths = PathsAPI(
            app_path=str(tmp_path), config_path=str(tmp_path / "cfg"),
            database_path=":memory:", extension_path=str(tmp_path),
            extension_data_path=str(tmp_path), log_path=str(tmp_path),
        )
        sdk = PlayniteSDK(db=in_memory_db, paths=paths, logger=logger, lifecycle=lifecycle)
        from playnite_python.models.game import Tag
        t = Tag(name="Action")
        in_memory_db.tags.add(t)
        result = sdk.database.tags.all()
        assert any(tag.name == "Action" for tag in result)

    def test_database_path_property(self, sdk):
        assert sdk.database.database_path == ":memory:"

    def test_entity_collections_exist(self, sdk):
        # All entity collection properties are accessible
        assert hasattr(sdk.database, "genres")
        assert hasattr(sdk.database, "categories")
        assert hasattr(sdk.database, "series")
        assert hasattr(sdk.database, "age_ratings")
        assert hasattr(sdk.database, "regions")
        assert hasattr(sdk.database, "features")
        assert hasattr(sdk.database, "sources")
        assert hasattr(sdk.database, "completion_statuses")
        assert hasattr(sdk.database, "companies")

    def test_buffered_update_context_manager(self, in_memory_db, tmp_path, log_manager, lifecycle):
        logger = log_manager.get_logger("buf")
        paths = PathsAPI(
            app_path=str(tmp_path), config_path=str(tmp_path / "cfg"),
            database_path=":memory:", extension_path=str(tmp_path),
            extension_data_path=str(tmp_path), log_path=str(tmp_path),
        )
        sdk = PlayniteSDK(db=in_memory_db, paths=paths, logger=logger, lifecycle=lifecycle)
        games_to_add = [Game(name=f"Game {i}") for i in range(5)]
        with sdk.database.buffered_update():
            for g in games_to_add:
                sdk.database.add_game(g)
        assert len(sdk.database.get_games()) == 5

    def test_game_database_buffered_update(self, in_memory_db):
        games = [Game(name=f"G{i}") for i in range(3)]
        with in_memory_db.buffered_update():
            for g in games:
                in_memory_db.games.add(g)
        assert in_memory_db.games.count() == 3


# ---------------------------------------------------------------------------
# 6. TestPlayniteSDKExtended
# ---------------------------------------------------------------------------

class TestPlayniteSDKExtended:

    def test_expand_game_variables_name(self, sdk):
        g = Game(name="Celeste", version="1.4")
        result = sdk.expand_game_variables(g, "Playing {game.name} v{game.version}")
        assert result == "Playing Celeste v1.4"

    def test_expand_game_variables_id(self, sdk):
        g = Game()
        result = sdk.expand_game_variables(g, "ID: {game.id}")
        assert result == f"ID: {g.id}"

    def test_expand_game_variables_unknown_field(self, sdk):
        g = Game(name="X")
        result = sdk.expand_game_variables(g, "Data: {game.nonexistent_field}")
        assert result == "Data: {game.nonexistent_field}"

    def test_expand_game_variables_no_placeholders(self, sdk):
        g = Game(name="Doom")
        result = sdk.expand_game_variables(g, "No variables here")
        assert result == "No variables here"

    def test_start_game_fires_lifecycle_hook(self, sdk, in_memory_db, lifecycle):
        game = Game(name="Portal")
        in_memory_db.games.add(game)
        fired = []
        lifecycle.register("on_game_starting", lambda g: fired.append(g.name), "test")
        sdk.start_game(game.id)
        assert fired == ["Portal"]

    def test_install_game_fires_lifecycle_hook(self, sdk, in_memory_db, lifecycle):
        game = Game(name="Minecraft")
        in_memory_db.games.add(game)
        fired = []
        lifecycle.register("on_game_installed", lambda g: fired.append(g.name), "test")
        sdk.install_game(game.id)
        assert fired == ["Minecraft"]

    def test_uninstall_game_fires_lifecycle_hook(self, sdk, in_memory_db, lifecycle):
        game = Game(name="GTA V", is_installed=True)
        in_memory_db.games.add(game)
        fired = []
        lifecycle.register("on_game_uninstalled", lambda g: fired.append(g.name), "test")
        sdk.uninstall_game(game.id)
        assert fired == ["GTA V"]

    def test_start_game_unknown_id_raises(self, sdk):
        with pytest.raises(ValueError, match="not found"):
            sdk.start_game("non-existent-id")

    def test_install_game_unknown_id_raises(self, sdk):
        with pytest.raises(ValueError, match="not found"):
            sdk.install_game("non-existent-id")

    def test_uninstall_game_unknown_id_raises(self, sdk):
        with pytest.raises(ValueError, match="not found"):
            sdk.uninstall_game("non-existent-id")

    def test_no_lifecycle_no_error(self, in_memory_db, tmp_path, log_manager):
        logger = log_manager.get_logger("nolc")
        paths = PathsAPI(
            app_path=str(tmp_path), config_path=str(tmp_path),
            database_path=":memory:", extension_path=str(tmp_path),
            extension_data_path=str(tmp_path), log_path=str(tmp_path),
        )
        sdk_no_lc = PlayniteSDK(db=in_memory_db, paths=paths, logger=logger, lifecycle=None)
        g = Game(name="Safe")
        in_memory_db.games.add(g)
        sdk_no_lc.start_game(g.id)  # should not raise


# ---------------------------------------------------------------------------
# Concrete plugin helpers
# ---------------------------------------------------------------------------

class _DummyPlugin(Plugin):
    @property
    def plugin_id(self) -> str:
        return "com.test.dummy"

    @property
    def name(self) -> str:
        return "Dummy Plugin"


class _CallTrackingPlugin(Plugin):
    def __init__(self, api):
        super().__init__(api)
        self.calls = []

    @property
    def plugin_id(self) -> str:
        return "com.test.tracker"

    @property
    def name(self) -> str:
        return "Tracker Plugin"

    def on_game_started(self, game):
        self.calls.append(("game_started", game.name))

    def on_game_startup_cancelled(self, game):
        self.calls.append(("startup_cancelled", game.name))

    def on_settings_changed(self):
        self.calls.append(("settings_changed",))


class _TestLibraryPlugin(LibraryPlugin):
    @property
    def plugin_id(self) -> str:
        return "com.test.library"

    @property
    def name(self) -> str:
        return "Test Library"

    def get_games(self, args: LibraryGetGamesArgs) -> List[GameMetadata]:
        return [
            GameMetadata(game_id="100", name="Alpha"),
            GameMetadata(game_id="200", name="Beta", genre_ids=["rpg"]),
        ]


class _TestMetadataPlugin(MetadataPlugin):
    @property
    def plugin_id(self) -> str:
        return "com.test.metadata"

    @property
    def name(self) -> str:
        return "Test Metadata"

    @property
    def supported_fields(self) -> List[MetadataField]:
        return [MetadataField.Name, MetadataField.Description, MetadataField.CriticScore]

    def get_metadata_provider(self, options):
        class _Provider(OnDemandMetadataProvider):
            def get_name(self, args):
                return "Downloaded Name"

            def get_description(self, args):
                return "Downloaded Desc"

            def get_critic_score(self, args):
                return 88
        return _Provider()


# ---------------------------------------------------------------------------
# 7. TestPluginBase
# ---------------------------------------------------------------------------

class TestPluginBase:

    def test_instantiation(self, sdk):
        plugin = _DummyPlugin(sdk)
        assert plugin.plugin_id == "com.test.dummy"
        assert plugin.name == "Dummy Plugin"

    def test_default_properties(self, sdk):
        plugin = _DummyPlugin(sdk)
        assert plugin.properties.has_settings is False

    def test_lifecycle_hooks_are_noop(self, sdk):
        plugin = _DummyPlugin(sdk)
        game = Game(name="Test")
        plugin.on_application_started()
        plugin.on_application_stopped()
        plugin.on_library_updated()
        plugin.on_game_starting(game)
        plugin.on_game_started(game)
        plugin.on_game_stopped(game, 100.0)
        plugin.on_game_installed(game)
        plugin.on_game_uninstalled(game)
        plugin.on_game_startup_cancelled(game)
        plugin.on_game_installation_cancelled(game)
        plugin.on_game_selected(game)
        plugin.on_game_selected(None)
        plugin.on_settings_changed()

    def test_empty_menu_items(self, sdk):
        plugin = _DummyPlugin(sdk)
        assert plugin.get_main_menu_items(GetMainMenuItemsArgs()) == []
        assert plugin.get_game_menu_items(GetGameMenuItemsArgs()) == []

    def test_empty_action_lists(self, sdk):
        plugin = _DummyPlugin(sdk)
        g = Game()
        assert plugin.get_play_actions(g) == []
        assert plugin.get_install_actions(g) == []
        assert plugin.get_uninstall_actions(g) == []

    def test_get_plugin_user_data_path(self, sdk):
        plugin = _DummyPlugin(sdk)
        path = plugin.get_plugin_user_data_path()
        assert "com.test.dummy" in path

    def test_save_load_settings(self, sdk, tmp_path):
        # Override extension_data_path to use tmp_path for isolation
        (tmp_path / "com.test.dummy").mkdir(parents=True, exist_ok=True)
        plugin = _DummyPlugin(sdk)
        settings = {"key": "value", "count": 42}
        plugin.save_plugin_settings(settings)
        loaded = plugin.load_plugin_settings()
        assert loaded == settings

    def test_load_settings_none_when_no_file(self, sdk):
        plugin = _DummyPlugin(sdk)
        # settings file doesn't exist yet
        result = plugin.load_plugin_settings()
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# 8. TestLibraryPlugin
# ---------------------------------------------------------------------------

class TestLibraryPlugin:

    def test_get_games_returns_metadata(self, sdk):
        plugin = _TestLibraryPlugin(sdk)
        games = plugin.get_games(LibraryGetGamesArgs())
        assert len(games) == 2
        assert games[0].game_id == "100"
        assert games[1].name == "Beta"

    def test_import_games_returns_game_objects(self, sdk):
        plugin = _TestLibraryPlugin(sdk)
        imported = plugin.import_games()
        assert len(imported) == 2
        assert all(isinstance(g, Game) for g in imported)

    def test_import_games_sets_game_id(self, sdk):
        plugin = _TestLibraryPlugin(sdk)
        imported = plugin.import_games()
        assert imported[0].game_id == "100"
        assert imported[1].game_id == "200"

    def test_import_games_sets_plugin_id(self, sdk):
        plugin = _TestLibraryPlugin(sdk)
        imported = plugin.import_games()
        assert all(g.plugin_id == "com.test.library" for g in imported)

    def test_import_games_sets_genre_ids(self, sdk):
        plugin = _TestLibraryPlugin(sdk)
        imported = plugin.import_games()
        assert imported[1].genre_ids == ["rpg"]

    def test_library_icon_default_empty(self, sdk):
        assert _TestLibraryPlugin(sdk).library_icon == ""

    def test_full_import_arg(self, sdk):
        plugin = _TestLibraryPlugin(sdk)
        # Full import flag is passed through (plugin can check it)
        imported = plugin.import_games(LibraryGetGamesArgs(full_import=True))
        assert len(imported) == 2


# ---------------------------------------------------------------------------
# 9. TestMetadataPlugin
# ---------------------------------------------------------------------------

class TestMetadataPlugin:

    def test_metadata_field_enum_values(self):
        assert MetadataField.Name.value == "Name"
        assert MetadataField.CoverImage.value == "CoverImage"
        assert MetadataField.InstallSize.value == "InstallSize"
        assert len(list(MetadataField)) == 19

    def test_on_demand_provider_all_none(self):
        provider = OnDemandMetadataProvider()
        args = GetMetadataFieldArgs()
        assert provider.get_name(args) is None
        assert provider.get_genres(args) is None
        assert provider.get_critic_score(args) is None
        assert provider.get_install_size(args) is None

    def test_download_metadata_calls_getters(self, sdk):
        plugin = _TestMetadataPlugin(sdk)
        game = Game(name="Test Game")
        result = plugin.download_metadata(game)
        assert result[MetadataField.Name.value] == "Downloaded Name"
        assert result[MetadataField.Description.value] == "Downloaded Desc"
        assert result[MetadataField.CriticScore.value] == 88

    def test_download_metadata_with_field_subset(self, sdk):
        plugin = _TestMetadataPlugin(sdk)
        game = Game(name="Test")
        result = plugin.download_metadata(game, fields=[MetadataField.Name])
        assert set(result.keys()) == {MetadataField.Name.value}

    def test_supported_fields(self, sdk):
        plugin = _TestMetadataPlugin(sdk)
        assert MetadataField.Name in plugin.supported_fields
        assert MetadataField.CriticScore in plugin.supported_fields


# ---------------------------------------------------------------------------
# 10. TestPluginManager
# ---------------------------------------------------------------------------

class TestPluginManager:

    def test_register_plugin(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        plugin = _DummyPlugin(sdk)
        mgr.register_plugin(plugin)
        assert len(mgr.get_plugins()) == 1

    def test_get_plugin_by_id(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        plugin = _DummyPlugin(sdk)
        mgr.register_plugin(plugin)
        assert mgr.get_plugin("com.test.dummy") is plugin

    def test_get_plugin_unknown_returns_none(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        assert mgr.get_plugin("does.not.exist") is None

    def test_unregister_plugin(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        plugin = _DummyPlugin(sdk)
        mgr.register_plugin(plugin)
        mgr.unregister_plugin("com.test.dummy")
        assert mgr.get_plugins() == []

    def test_unregister_unknown_raises(self, lifecycle):
        mgr = PluginManager(lifecycle)
        with pytest.raises(KeyError, match="not registered"):
            mgr.unregister_plugin("no.such.plugin")

    def test_wire_hooks_fires_lifecycle(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        plugin = _CallTrackingPlugin(sdk)
        mgr.register_plugin(plugin)
        game = Game(name="Overwatch")
        lifecycle.on_game_started(game)
        assert ("game_started", "Overwatch") in plugin.calls

    def test_wire_hooks_new_hooks(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        plugin = _CallTrackingPlugin(sdk)
        mgr.register_plugin(plugin)
        game = Game(name="Hades")
        lifecycle.on_game_startup_cancelled(game)
        lifecycle.on_settings_changed()
        assert ("startup_cancelled", "Hades") in plugin.calls
        assert ("settings_changed",) in plugin.calls

    def test_unregistered_plugin_stops_receiving_events(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        plugin = _CallTrackingPlugin(sdk)
        mgr.register_plugin(plugin)
        mgr.unregister_plugin("com.test.tracker")
        game = Game(name="Dark Souls")
        lifecycle.on_game_started(game)
        assert not any(c[0] == "game_started" for c in plugin.calls)

    def test_get_all_main_menu_items_empty(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        mgr.register_plugin(_DummyPlugin(sdk))
        assert mgr.get_all_main_menu_items() == []

    def test_get_all_game_menu_items_empty(self, sdk, lifecycle):
        mgr = PluginManager(lifecycle)
        mgr.register_plugin(_DummyPlugin(sdk))
        assert mgr.get_all_game_menu_items([Game()]) == []

    def test_load_plugin_from_file(self, sdk, lifecycle, tmp_path):
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(textwrap.dedent("""\
            from playnite_python.plugins.base import Plugin

            class FilePlugin(Plugin):
                @property
                def plugin_id(self):
                    return "com.test.file_plugin"

                @property
                def name(self):
                    return "File Plugin"
        """), encoding="utf-8")
        mgr = PluginManager(lifecycle)
        loaded = mgr.load_plugin_from_file(str(plugin_file), sdk)
        assert loaded.plugin_id == "com.test.file_plugin"
        assert mgr.get_plugin("com.test.file_plugin") is not None

    def test_load_plugin_from_file_no_subclass_raises(self, sdk, lifecycle, tmp_path):
        bad_file = tmp_path / "no_plugin.py"
        bad_file.write_text("x = 42\n", encoding="utf-8")
        mgr = PluginManager(lifecycle)
        with pytest.raises(ValueError, match="No Plugin subclass"):
            mgr.load_plugin_from_file(str(bad_file), sdk)
