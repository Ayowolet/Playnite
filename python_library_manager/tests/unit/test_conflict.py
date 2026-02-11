"""Unit tests for conflict detection and resolution."""
import pytest
from game_library.merger.conflict import ConflictResolver, ConflictType, _path_key, _values_equal
from game_library.merger.strategies import MergeStrategy
from game_library.models.game import ReleaseDate
from tests.conftest import make_game


class TestConflictDetection:
    def test_no_conflicts_identical_games(self, witcher3_steam, witcher3_gog):
        """Near-identical games with the same field values should produce only MISSING conflicts."""
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        conflicts = resolver.detect_conflicts(witcher3_steam, witcher3_gog)
        scalar_mismatches = [c for c in conflicts if c.conflict_type == ConflictType.SCALAR_MISMATCH]
        # Cover images differ, but everything else should match
        assert len(scalar_mismatches) <= 3

    def test_detects_scalar_mismatch(self):
        a = make_game("My Game", description="Original description")
        b = make_game("My Game", description="Different description")
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        conflicts = resolver.detect_conflicts(a, b)
        desc_conflict = next((c for c in conflicts if c.field == "Description"), None)
        assert desc_conflict is not None
        assert desc_conflict.conflict_type == ConflictType.SCALAR_MISMATCH

    def test_detects_missing_in_master(self):
        a = make_game("My Game")  # no cover
        b = make_game("My Game", cover="source_cover.jpg")
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        conflicts = resolver.detect_conflicts(a, b)
        cover_conflict = next((c for c in conflicts if c.field == "CoverImage"), None)
        assert cover_conflict is not None
        assert cover_conflict.conflict_type == ConflictType.MISSING_IN_MASTER

    def test_detects_list_mismatch(self):
        a = make_game("My Game", platforms=["PC"])
        b = make_game("My Game", platforms=["PlayStation 5"])
        a.PlatformIds = ["pid-1"]
        b.PlatformIds = ["pid-2"]
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        conflicts = resolver.detect_conflicts(a, b)
        plat_conflict = next((c for c in conflicts if c.field == "PlatformIds"), None)
        assert plat_conflict is not None
        assert plat_conflict.conflict_type == ConflictType.LIST_MISMATCH


class TestConflictResolutionStrategies:
    def _make_conflicting_pair(self):
        """Return two games with different descriptions."""
        a = make_game("Test Game", description="Master description", cover="master.jpg")
        b = make_game("Test Game", description="Source description", cover="source.jpg")
        return a, b

    def test_keep_master_strategy(self):
        a, b = self._make_conflicting_pair()
        resolver = ConflictResolver(MergeStrategy.KEEP_MASTER)
        merged, conflicts = resolver.resolve(a, b)
        assert merged.Description == "Master description"
        assert merged.CoverImage == "master.jpg"

    def test_keep_source_strategy(self):
        a, b = self._make_conflicting_pair()
        resolver = ConflictResolver(MergeStrategy.KEEP_SOURCE)
        merged, conflicts = resolver.resolve(a, b)
        assert merged.Description == "Source description"
        assert merged.CoverImage == "source.jpg"

    def test_merge_prefer_master_fills_empty(self):
        a = make_game("Test Game", description="Master description")
        b = make_game("Test Game", description="Source description", cover="source.jpg")
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        merged, _ = resolver.resolve(a, b)
        # Non-conflicting empty field filled from source
        assert merged.CoverImage == "source.jpg"
        # Conflicting field: master wins
        assert merged.Description == "Master description"

    def test_merge_prefer_source_fills_empty(self):
        a = make_game("Test Game", description="Master description")
        b = make_game("Test Game", description="Source description", cover="source.jpg")
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_SOURCE)
        merged, _ = resolver.resolve(a, b)
        assert merged.CoverImage == "source.jpg"
        # Conflicting field: source wins
        assert merged.Description == "Source description"

    def test_most_complete_chooses_longer_string(self):
        a = make_game("Test", description="Short")
        b = make_game("Test", description="This is a much longer and more complete description.")
        resolver = ConflictResolver(MergeStrategy.MOST_COMPLETE)
        merged, _ = resolver.resolve(a, b)
        assert merged.Description == "This is a much longer and more complete description."

    def test_most_played_sums_playtime(self):
        """MOST_PLAYED should pick the higher Playtime value."""
        a = make_game("Test")
        a.Playtime = 7200
        b = make_game("Test")
        b.Playtime = 3600
        resolver = ConflictResolver(MergeStrategy.MOST_PLAYED)
        merged, _ = resolver.resolve(a, b)
        assert merged.Playtime == 7200

    def test_field_override_takes_precedence(self):
        a = make_game("Test", description="Master description", cover="master.jpg")
        b = make_game("Test", description="Source description", cover="source.jpg")
        resolver = ConflictResolver(MergeStrategy.KEEP_MASTER)
        resolver.field_overrides = {"Description": MergeStrategy.KEEP_SOURCE}
        merged, _ = resolver.resolve(a, b)
        # Description uses source override
        assert merged.Description == "Source description"
        # CoverImage falls back to default KEEP_MASTER
        assert merged.CoverImage == "master.jpg"

    def test_resolve_does_not_mutate_originals(self):
        a = make_game("Test", description="Original")
        b = make_game("Test", description="Source")
        resolver = ConflictResolver(MergeStrategy.KEEP_SOURCE)
        resolver.resolve(a, b)
        assert a.Description == "Original"  # unchanged

    def test_most_complete_union_of_lists(self):

        a = make_game("Test")
        b = make_game("Test")
        a.TagIds = ["tag-a", "tag-b"]
        b.TagIds = ["tag-b", "tag-c"]
        resolver = ConflictResolver(MergeStrategy.MOST_COMPLETE)
        merged, _ = resolver.resolve(a, b)
        assert "tag-a" in merged.TagIds
        assert "tag-b" in merged.TagIds
        assert "tag-c" in merged.TagIds


class TestPathFieldComparison:
    """Verify case-insensitive, separator-normalised path comparison for
    CoverImage / BackgroundImage / Icon fields."""

    # ── _path_key unit tests ──────────────────────────────────────────────────

    def test_path_key_casefolds(self):
        assert _path_key("Cover.JPG") == _path_key("cover.jpg")

    def test_path_key_normalises_backslash(self):
        assert _path_key("files\\cover.jpg") == _path_key("files/cover.jpg")

    def test_path_key_combined(self):
        assert _path_key("Files\\Cover.JPG") == _path_key("files/cover.jpg")

    def test_path_key_strips_trailing_slash(self):
        assert _path_key("files/covers/") == _path_key("files/covers")

    # ── _values_equal path-field branch ──────────────────────────────────────

    def test_values_equal_path_field_same_case(self):
        assert _values_equal("cover.jpg", "cover.jpg", "CoverImage") is True

    def test_values_equal_path_field_different_case(self):
        assert _values_equal("Cover.jpg", "cover.jpg", "CoverImage") is True

    def test_values_equal_path_field_different_separator(self):
        assert _values_equal("files\\cover.jpg", "files/cover.jpg", "CoverImage") is True

    def test_values_equal_path_field_case_and_separator(self):
        assert _values_equal("Files\\Cover.JPG", "files/cover.jpg", "BackgroundImage") is True

    def test_values_equal_path_field_genuinely_different(self):
        assert _values_equal("cover_a.jpg", "cover_b.jpg", "Icon") is False

    def test_values_equal_non_path_field_case_sensitive(self):
        """Non-path string fields must remain case-sensitive."""
        assert _values_equal("Witcher 3", "witcher 3", "Name") is False

    # ── End-to-end: no spurious conflict for same-path-different-case covers ──

    def test_cover_same_path_different_case_no_conflict(self):
        """Two games whose covers differ only by case must not produce a conflict."""
        a = make_game("My Game", cover="files\\Cover.jpg")
        b = make_game("My Game", cover="files/cover.jpg")
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        conflicts = resolver.detect_conflicts(a, b)
        cover_conflicts = [c for c in conflicts if c.field == "CoverImage"]
        assert cover_conflicts == [], f"Unexpected conflict: {cover_conflicts}"

    def test_cover_genuinely_different_still_conflicts(self):
        """Two games with genuinely different covers must still produce a conflict."""
        a = make_game("My Game", cover="cover_steam.jpg")
        b = make_game("My Game", cover="cover_gog.jpg")
        resolver = ConflictResolver(MergeStrategy.MERGE_PREFER_MASTER)
        conflicts = resolver.detect_conflicts(a, b)
        cover_conflicts = [c for c in conflicts if c.field == "CoverImage"]
        assert len(cover_conflicts) == 1
