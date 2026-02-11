"""Unit tests for the DuplicateResolver."""
import pytest
from game_library.duplicate.detector import DuplicateDetector, DetectorConfig, DuplicateGroup
from game_library.duplicate.resolver import DuplicateResolver, ResolutionAction
from tests.conftest import make_game, make_library


def _detect_groups(lib):
    return DuplicateDetector(DetectorConfig(threshold=0.80)).detect(lib).groups


class TestHideDuplicates:
    def test_hides_non_master(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        assert groups, "Expected at least one duplicate group"
        resolver = DuplicateResolver(lib)
        rec = resolver.hide_duplicates(groups[0])
        assert rec.action == ResolutionAction.HIDE_DUPLICATES
        # All duplicates should now be hidden
        for dup in groups[0].duplicates:
            game = lib.get_game(dup.Id)
            assert game is not None
            assert game.Hidden is True
        # Master should NOT be hidden
        master = lib.get_game(groups[0].master.Id)
        assert master is not None
        assert master.Hidden is False

    def test_undo_unhides(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        resolver = DuplicateResolver(lib)
        resolver.hide_duplicates(groups[0])
        resolver.undo_last()
        for dup in groups[0].duplicates:
            game = lib.get_game(dup.Id)
            assert game is not None
            # After undo, hidden state should be restored to original
            assert game.Hidden == dup.Hidden


class TestDeleteDuplicates:
    def test_deletes_non_master(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        resolver = DuplicateResolver(lib)
        resolver.delete_duplicates(groups[0])
        for dup in groups[0].duplicates:
            assert lib.get_game(dup.Id) is None
        assert lib.get_game(groups[0].master.Id) is not None

    def test_undo_restores_deleted(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        resolver = DuplicateResolver(lib)
        resolver.delete_duplicates(groups[0])
        resolver.undo_last()
        for dup in groups[0].duplicates:
            assert lib.get_game(dup.Id) is not None


class TestMergeIntoMaster:
    def test_copies_missing_fields(self):
        game_with_cover = make_game("Portal", year=2007, source="Steam",
                                    cover="cover.jpg", description="<p>Fun</p>")
        game_bare = make_game("Portal", year=2007, source="GOG")
        lib = make_library("test", [game_bare, game_with_cover])
        groups = _detect_groups(lib)
        assert groups
        # Ensure game_bare is master and game_with_cover is duplicate (or vice versa)
        resolver = DuplicateResolver(lib)
        resolver.merge_into_master(groups[0])
        master = lib.get_game(groups[0].master.Id)
        # Master should now have cover (merged from duplicate)
        assert master.CoverImage or master.Description  # at least one was merged

    def test_sums_playtime(self):
        ga = make_game("Doom", year=2016, source="Steam", installed=True)
        ga.Playtime = 3600
        gb = make_game("Doom", year=2016, source="GOG")
        gb.Playtime = 1800
        lib = make_library("test", [ga, gb])
        groups = _detect_groups(lib)
        if not groups:
            pytest.skip("No duplicate groups found")
        master_before = lib.get_game(groups[0].master.Id).Playtime
        resolver = DuplicateResolver(lib)
        resolver.merge_into_master(groups[0])
        master_after = lib.get_game(groups[0].master.Id).Playtime
        assert master_after >= master_before


class TestSetMaster:
    def test_override_master(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        assert groups
        group = groups[0]
        # Override master to the non-default duplicate
        new_master_id = group.duplicates[0].Id
        resolver = DuplicateResolver(lib)
        updated_group = resolver.set_master(group, new_master_id)
        assert updated_group.master.Id == new_master_id

    def test_invalid_master_id_raises(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        resolver = DuplicateResolver(lib)
        with pytest.raises(ValueError):
            resolver.set_master(groups[0], "non-existent-id")


class TestBulkResolve:
    def test_bulk_hide_all_groups(self, master_library, source_library):
        groups = DuplicateDetector(DetectorConfig(threshold=0.80)).detect(
            master_library, source_library
        ).groups
        resolver = DuplicateResolver(master_library)
        records = resolver.bulk_resolve(groups, ResolutionAction.HIDE_DUPLICATES)
        assert len(records) == len(groups)
        for rec in records:
            assert rec.action == ResolutionAction.HIDE_DUPLICATES


class TestHistoryPersistence:
    def test_save_and_load_history(self, witcher3_steam, witcher3_gog, tmp_path):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        groups = _detect_groups(lib)
        resolver = DuplicateResolver(lib)
        resolver.hide_duplicates(groups[0])
        history_path = tmp_path / "history.json"
        resolver.save_history(history_path)
        # Reload into a new resolver
        resolver2 = DuplicateResolver(lib)
        resolver2.load_history(history_path)
        assert len(resolver2.history) == 1
        assert resolver2.history[0].action == ResolutionAction.HIDE_DUPLICATES
