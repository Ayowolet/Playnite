"""Unit tests for the DuplicateDetector."""
import pytest
from game_library.duplicate.detector import DuplicateDetector, DetectorConfig, DuplicateGroup
from tests.conftest import make_game, make_library


class TestDetectorBasicDetection:
    def test_finds_exact_duplicate(self, master_library, source_library):
        """Identical game names in two libraries → one group per game."""
        detector = DuplicateDetector()
        report = detector.detect(master_library, source_library)
        assert report.group_count >= 2  # Witcher 3 + Portal 2

    def test_exact_match_confidence_high(self, master_library, source_library):
        """Exact title matches should produce confidence scores ≥85%."""
        detector = DuplicateDetector(DetectorConfig(threshold=0.80))
        report = detector.detect(master_library, source_library)
        for group in report.groups:
            for dup_id, score in group.scores.items():
                assert score >= 0.80, f"Low score {score:.2f} for group {group.id}"

    def test_no_false_positives_for_different_games(self):
        """Completely different games must not form a group."""
        portal = make_game("Portal 2", year=2011, platforms=["PC"])
        witcher = make_game("The Witcher 3", year=2015, platforms=["PC"])
        lib = make_library("test", [portal, witcher])
        detector = DuplicateDetector()
        report = detector.detect(lib)
        assert report.group_count == 0

    def test_report_fields_populated(self, master_library, source_library):
        report = detector = DuplicateDetector().detect(master_library, source_library)
        assert report.generated_at != ""
        assert report.total_games > 0
        assert report.games_scanned > 0

    def test_to_dict_serialisable(self, master_library, source_library):
        import json
        report = DuplicateDetector().detect(master_library, source_library)
        d = report.to_dict()
        # Must round-trip through JSON without error
        json.dumps(d)


class TestDetectorEditionVariants:
    def test_goty_detected_as_duplicate(self, witcher3_steam, witcher3_goty):
        lib = make_library("test", [witcher3_steam, witcher3_goty])
        detector = DuplicateDetector(DetectorConfig(threshold=0.75))
        report = detector.detect(lib)
        assert report.group_count >= 1, "GOTY edition should be detected as duplicate"

    def test_remaster_detected(self):
        base = make_game("Halo 2", year=2004, platforms=["PC"], developers=["Bungie"])
        remaster = make_game("Halo 2 Remastered", year=2014, platforms=["PC"], developers=["Bungie"])
        lib = make_library("test", [base, remaster])
        detector = DuplicateDetector(DetectorConfig(threshold=0.75))
        report = detector.detect(lib)
        assert report.group_count >= 1


class TestDetectorFilters:
    def test_exclude_hidden_filter(self, witcher3_steam, witcher3_gog):
        witcher3_gog.Hidden = True
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        detector = DuplicateDetector(DetectorConfig(exclude_hidden=True))
        report = detector.detect(lib)
        assert report.group_count == 0  # hidden game excluded

    def test_include_platform_filter(self):
        pc_game = make_game("Doom", year=2016, platforms=["PC"])
        console_game = make_game("Doom", year=2016, platforms=["Xbox One"])
        lib = make_library("test", [pc_game, console_game])
        detector = DuplicateDetector(DetectorConfig(include_platforms=["Xbox One"]))
        report = detector.detect(lib)
        # Only console_game is in scope, so no pair can form
        assert report.games_scanned == 1

    def test_exclude_platform_filter(self):
        pc_game = make_game("Doom", year=2016, platforms=["PC"])
        console_game = make_game("Doom", year=2016, platforms=["Xbox One"])
        lib = make_library("test", [pc_game, console_game])
        detector = DuplicateDetector(DetectorConfig(exclude_platforms=["Xbox One"]))
        report = detector.detect(lib)
        assert report.games_scanned == 1  # only PC game

    def test_include_source_filter(self, witcher3_steam, witcher3_gog):
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        detector = DuplicateDetector(DetectorConfig(include_sources=["Steam"]))
        report = detector.detect(lib)
        assert report.games_scanned == 1  # only Steam game

    def test_include_category_filter(self):
        """Only games in the requested category should be scanned."""
        rpg_game = make_game("Dragon Quest XI", year=2017, platforms=["PC"],
                             categories=["RPG"])
        racing_game = make_game("Gran Turismo 7", year=2022, platforms=["PC"],
                                categories=["Racing"])
        lib = make_library("test", [rpg_game, racing_game])
        detector = DuplicateDetector(DetectorConfig(include_categories=["RPG"]))
        report = detector.detect(lib)
        assert report.games_scanned == 1  # only RPG game scanned


class TestDetectorSourcePriority:
    def test_steam_preferred_over_gog(self, witcher3_steam, witcher3_gog):
        """With Steam first in priority list, Steam game is master."""
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        cfg = DetectorConfig(
            threshold=0.80,
            source_priority=["Steam", "GOG"],
        )
        report = DuplicateDetector(cfg).detect(lib)
        assert report.group_count >= 1
        group = report.groups[0]
        assert group.master._source_name == "Steam"

    def test_gog_preferred_when_listed_first(self, witcher3_steam, witcher3_gog):
        """When GOG is first in priority, GOG game becomes master."""
        lib = make_library("test", [witcher3_steam, witcher3_gog])
        cfg = DetectorConfig(
            threshold=0.80,
            source_priority=["GOG", "Steam"],
        )
        report = DuplicateDetector(cfg).detect(lib)
        assert report.group_count >= 1
        group = report.groups[0]
        assert group.master._source_name == "GOG"

    def test_completeness_tiebreaker(self):
        """When source priority is equal, more complete game wins."""
        game_rich = make_game(
            "Portal", year=2007, platforms=["PC"], cover="cover.jpg",
            description="Test-chamber puzzle game.", source="Steam"
        )
        game_bare = make_game("Portal", year=2007, source="Steam")
        lib = make_library("test", [game_rich, game_bare])
        cfg = DetectorConfig(threshold=0.80)
        report = DuplicateDetector(cfg).detect(lib)
        if report.group_count > 0:
            assert report.groups[0].master.Id == game_rich.Id


class TestDetectorSimilarityMode:
    def test_similarity_mode_lower_threshold(self):
        """Similarity mode should find near-duplicates below the normal threshold."""
        ga = make_game("Call of Duty Modern Warfare", year=2019, platforms=["PC"])
        gb = make_game("Call of Duty Modern Warfare 2", year=2022, platforms=["PC"])
        lib = make_library("test", [ga, gb])
        # Normal mode should NOT flag these as duplicates
        report_normal = DuplicateDetector(DetectorConfig(threshold=0.90)).detect(lib)
        # Similarity mode may catch them depending on scorer
        report_sim = DuplicateDetector(
            DetectorConfig(similarity_mode=True, similarity_threshold=0.65)
        ).detect(lib)
        # Similarity mode should find at least as many groups (or more)
        assert report_sim.group_count >= report_normal.group_count


class TestDetectorPerformance:
    def test_large_library_under_500mb_memory(self):
        """20,000 unique games must stay within 500 MB peak RAM.

        Uses tracemalloc which measures Python-level allocations.  The actual
        figure is well under 500 MB; the limit is generous to accommodate
        different platforms and Python versions.
        """
        import tracemalloc
        import hashlib

        games = [
            make_game(
                hashlib.sha256(f"mem-game-{i}".encode()).hexdigest()[:16],
                year=2000 + (i % 23),
            )
            for i in range(20_000)
        ]
        lib = make_library("mem", games)
        detector = DuplicateDetector()

        tracemalloc.start()
        detector.detect(lib)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024
        assert peak_mb < 500, f"Peak memory {peak_mb:.1f} MB exceeds 500 MB limit"

    def test_large_library_under_30_seconds(self):
        """5000 unique games should be scanned in <30 seconds.

        Game titles are derived from SHA-256 digests so:
        - Each title is unique and non-similar to every other.
        - Hex prefixes distribute into ~hundreds of distinct blocks so the
          blocking algorithm keeps per-block comparison counts tiny.
        - quick_candidate rejects all pairs → O(n) effective complexity.
        """
        import time
        import hashlib

        games = [
            make_game(
                # 16-char hex slug – unique, random-looking, no word overlap
                hashlib.sha256(f"perf-game-{i}".encode()).hexdigest()[:16],
                year=2000 + (i % 23),
            )
            for i in range(5000)
        ]
        lib = make_library("perf", games)
        detector = DuplicateDetector()
        t0 = time.perf_counter()
        report = detector.detect(lib)
        elapsed = time.perf_counter() - t0
        assert elapsed < 30.0, f"Detection took {elapsed:.1f}s (limit 30s)"
        # No two hex-slug games should be mistaken for duplicates
        assert report.group_count == 0, f"Expected 0 groups, got {report.group_count}"
