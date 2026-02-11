"""
False-positive regression tests for the duplicate detector.

Verifies that genuinely different games are NOT flagged as duplicates and
that every flagged duplicate carries enough detail to understand why it
was matched (identifiability).

Test categories
---------------
1. Sequential numbered sequels – "Portal" vs "Portal 2", "Doom" vs "Doom II"
2. Annual sports / service titles – "FIFA 22" vs "FIFA 23" etc.
3. Same-name remakes / reboots released years apart
4. Games with similar-sounding subtitles but different content
5. Identifiability – MatchResult.details is populated for every flagged pair
"""
from __future__ import annotations

import pytest

from game_library.duplicate.detector import DuplicateDetector, DetectorConfig
from game_library.duplicate.matcher import GameMatcher
from tests.conftest import make_game, make_library

# Default detection threshold used throughout these tests.
_THRESHOLD = 0.85


# ── Helpers ───────────────────────────────────────────────────────────────────

def _matcher_score(
    title_a: str,
    title_b: str,
    year_a: int | None = None,
    year_b: int | None = None,
    platforms: list[str] | None = None,
    developers: list[str] | None = None,
) -> float:
    """Return the raw matcher score for the given pair."""
    plats = platforms or ["PC"]
    devs = developers or []
    ga = make_game(title_a, year=year_a, platforms=plats, developers=devs)
    gb = make_game(title_b, year=year_b, platforms=plats, developers=devs)
    return GameMatcher().match(ga, gb).score


def _detect_group_count(
    title_a: str,
    year_a: int | None,
    title_b: str,
    year_b: int | None,
    platforms: list[str] | None = None,
    developers: list[str] | None = None,
    threshold: float = _THRESHOLD,
) -> int:
    """Run the full detector pipeline and return the number of duplicate groups."""
    plats = platforms or []
    devs = developers or []
    ga = make_game(title_a, year=year_a, platforms=plats, developers=devs)
    gb = make_game(title_b, year=year_b, platforms=plats, developers=devs)
    lib = make_library("test", [ga, gb])
    report = DuplicateDetector(DetectorConfig(threshold=threshold)).detect(lib)
    return report.group_count


# ── 1. Sequential numbered sequels ────────────────────────────────────────────

class TestSequentialSeriesNotDuplicate:
    """
    Numbered sequels in the same franchise must NOT be flagged as duplicates.

    Root cause without fix: ``token_set_ratio`` returns 1.0 when one title is a
    token-subset of the other (e.g. "doom" ⊆ "doom 2"), and ``partial_ratio``
    inflates scores when titles share a long common prefix ("fifa 2" in both
    "fifa 22" and "fifa 23").  The sequential-series cap in ``_title_score_keyed``
    clamps the title score to 0.60 whenever the normalised titles share the same
    base after stripping a trailing number, preventing the aggregate score from
    crossing the 0.85 threshold.
    """

    def test_doom_vs_doom_ii_consecutive_years(self):
        """Doom (1993) and Doom II (1994) are released a year apart – the
        tightest possible case for the year-score component."""
        score = _matcher_score(
            "Doom", "Doom II",
            year_a=1993, year_b=1994,
            developers=["id Software"],
        )
        assert score < _THRESHOLD, (
            f"Doom (1993) vs Doom II (1994) score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_portal_vs_portal_2(self):
        score = _matcher_score("Portal", "Portal 2", year_a=2007, year_b=2011,
                               developers=["Valve"])
        assert score < _THRESHOLD, f"Portal vs Portal 2 score {score:.3f} ≥ {_THRESHOLD}"

    def test_halo_vs_halo_2(self):
        score = _matcher_score("Halo: Combat Evolved", "Halo 2",
                               year_a=2001, year_b=2004)
        assert score < _THRESHOLD, f"Halo vs Halo 2 score {score:.3f} ≥ {_THRESHOLD}"

    def test_halo_2_vs_halo_3(self):
        score = _matcher_score("Halo 2", "Halo 3", year_a=2004, year_b=2007)
        assert score < _THRESHOLD, f"Halo 2 vs Halo 3 score {score:.3f} ≥ {_THRESHOLD}"

    def test_dark_souls_vs_dark_souls_ii(self):
        score = _matcher_score(
            "Dark Souls", "Dark Souls II",
            year_a=2011, year_b=2014,
            developers=["FromSoftware"],
        )
        assert score < _THRESHOLD, (
            f"Dark Souls vs Dark Souls II score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_dark_souls_ii_vs_dark_souls_iii(self):
        score = _matcher_score(
            "Dark Souls II", "Dark Souls III",
            year_a=2014, year_b=2016,
            developers=["FromSoftware"],
        )
        assert score < _THRESHOLD, (
            f"Dark Souls II vs Dark Souls III score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_final_fantasy_vii_vs_viii(self):
        score = _matcher_score(
            "Final Fantasy VII", "Final Fantasy VIII",
            year_a=1997, year_b=1999,
        )
        assert score < _THRESHOLD, (
            f"Final Fantasy VII vs VIII score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_mass_effect_2_vs_3(self):
        score = _matcher_score(
            "Mass Effect 2", "Mass Effect 3",
            year_a=2010, year_b=2012,
            developers=["BioWare"],
        )
        assert score < _THRESHOLD, (
            f"Mass Effect 2 vs 3 score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_borderlands_2_vs_3(self):
        score = _matcher_score("Borderlands 2", "Borderlands 3",
                               year_a=2012, year_b=2019)
        assert score < _THRESHOLD, (
            f"Borderlands 2 vs 3 score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_gta_iv_vs_gta_v(self):
        """GTA abbreviation expands to 'grand theft auto'; roman numerals
        convert IV→4 and V→5, so the sequential-series check applies."""
        score = _matcher_score(
            "Grand Theft Auto IV", "Grand Theft Auto V",
            year_a=2008, year_b=2013,
        )
        assert score < _THRESHOLD, (
            f"GTA IV vs GTA V score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_halflife_vs_halflife_2(self):
        score = _matcher_score(
            "Half-Life", "Half-Life 2",
            year_a=1998, year_b=2004,
            developers=["Valve"],
        )
        assert score < _THRESHOLD, (
            f"Half-Life vs Half-Life 2 score {score:.3f} ≥ {_THRESHOLD}"
        )


# ── 2. Annual sports / service titles ─────────────────────────────────────────

class TestAnnualSeriesNotDuplicate:
    """
    Annual titles that carry a release year in the name (e.g. "FIFA 22" vs
    "FIFA 23") must NOT be flagged as duplicates.  These are caught by the
    sequential-series cap when shared tokens exist in the token index (e.g.
    "fifa"), and never even become candidates when the titles share no long
    tokens (e.g. single-digit/short year tokens are below the 3-char minimum).
    """

    def test_fifa_22_vs_23(self):
        groups = _detect_group_count("FIFA 22", 2021, "FIFA 23", 2022)
        assert groups == 0, "FIFA 22 vs FIFA 23 was incorrectly flagged as duplicate"

    def test_fifa_23_vs_24(self):
        groups = _detect_group_count("FIFA 23", 2022, "FIFA 24", 2023)
        assert groups == 0, "FIFA 23 vs FIFA 24 was incorrectly flagged as duplicate"

    def test_nba_2k22_vs_23(self):
        groups = _detect_group_count("NBA 2K22", 2021, "NBA 2K23", 2022)
        assert groups == 0, "NBA 2K22 vs NBA 2K23 was incorrectly flagged as duplicate"

    def test_madden_nfl_22_vs_23(self):
        groups = _detect_group_count("Madden NFL 22", 2021, "Madden NFL 23", 2022)
        assert groups == 0, (
            "Madden NFL 22 vs Madden NFL 23 was incorrectly flagged as duplicate"
        )

    def test_pro_evolution_soccer_2022_vs_2023(self):
        """Full year in title – sequential-series cap applies."""
        groups = _detect_group_count(
            "Pro Evolution Soccer 2022", 2021,
            "Pro Evolution Soccer 2023", 2022,
        )
        assert groups == 0, (
            "PES 2022 vs PES 2023 was incorrectly flagged as duplicate"
        )

    def test_consecutive_entries_with_shared_platform_and_developer(self):
        """Worst-case for false positive: same developer, same platform,
        consecutive year (year_score=0.5).  Must still not cross threshold."""
        ga = make_game("FIFA 22", year=2021, platforms=["PC"],
                       developers=["EA Sports"], publishers=["EA"])
        gb = make_game("FIFA 23", year=2022, platforms=["PC"],
                       developers=["EA Sports"], publishers=["EA"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=_THRESHOLD)).detect(lib)
        assert report.group_count == 0, (
            f"FIFA 22 vs FIFA 23 with shared metadata should not be a duplicate "
            f"(groups={report.group_count})"
        )


# ── 3. Same-name remakes / reboots ────────────────────────────────────────────

class TestSameNameRemakesNotDuplicate:
    """
    When a franchise is rebooted with the exact same title (e.g. Doom 1993 and
    Doom 2016), the year distance alone (year_score=0.0 for |diff|>1) must keep
    the aggregate score below the threshold.
    """

    def test_doom_1993_vs_doom_2016(self):
        score = _matcher_score(
            "Doom", "Doom",
            year_a=1993, year_b=2016,
            developers=["id Software"],
        )
        assert score < _THRESHOLD, (
            f"Doom (1993) vs Doom (2016) score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_prey_2006_vs_2017(self):
        score = _matcher_score("Prey", "Prey", year_a=2006, year_b=2017)
        assert score < _THRESHOLD, (
            f"Prey (2006) vs Prey (2017) score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_tomb_raider_1996_vs_2013(self):
        score = _matcher_score("Tomb Raider", "Tomb Raider",
                               year_a=1996, year_b=2013)
        assert score < _THRESHOLD, (
            f"Tomb Raider (1996) vs Tomb Raider (2013) score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_same_title_unknown_years_not_forced_duplicate(self):
        """Without year info the year component is neutral (0.5).
        Two games with the same title but no year data are ambiguous – the
        detector should still flag them (title_score=1.0 drives score high);
        this test just ensures an *unrelated* same-name game with a known
        distant year is NOT flagged."""
        score = _matcher_score(
            "Battlefront", "Battlefront",
            year_a=2004, year_b=2015,
        )
        # year_score = 0.0 (11-year gap) prevents crossing threshold
        assert score < _THRESHOLD, (
            f"Battlefront (2004) vs Battlefront (2015) score {score:.3f} ≥ {_THRESHOLD}"
        )


# ── 4. Similar-subtitle variants ──────────────────────────────────────────────

class TestSimilarSubtitlesNotDuplicate:
    """
    Games in the same franchise with meaningfully different subtitles must NOT
    be grouped as duplicates even when they share many title tokens.
    """

    def test_assassins_creed_origins_vs_odyssey(self):
        groups = _detect_group_count(
            "Assassin's Creed Origins", 2017,
            "Assassin's Creed Odyssey", 2018,
            platforms=["PC"],
        )
        assert groups == 0, (
            "AC Origins vs AC Odyssey should not be a duplicate group"
        )

    def test_call_of_duty_mw_vs_black_ops(self):
        groups = _detect_group_count(
            "Call of Duty: Modern Warfare", 2019,
            "Call of Duty: Black Ops", 2010,
            platforms=["PC"],
        )
        assert groups == 0, "CoD MW vs CoD Black Ops should not be a duplicate"

    def test_need_for_speed_underground_vs_most_wanted(self):
        groups = _detect_group_count(
            "Need for Speed: Underground", 2003,
            "Need for Speed: Most Wanted", 2005,
            platforms=["PC"],
        )
        assert groups == 0, "NFS Underground vs NFS Most Wanted should not be a duplicate"

    def test_borderlands_2_vs_3_detector(self):
        groups = _detect_group_count(
            "Borderlands 2", 2012,
            "Borderlands 3", 2019,
            platforms=["PC"],
            developers=["Gearbox Software"],
        )
        assert groups == 0, "Borderlands 2 vs Borderlands 3 should not be a duplicate"

    def test_mass_effect_2_vs_3_detector(self):
        groups = _detect_group_count(
            "Mass Effect 2", 2010,
            "Mass Effect 3", 2012,
            platforms=["PC"],
            developers=["BioWare"],
        )
        assert groups == 0, "Mass Effect 2 vs Mass Effect 3 should not be a duplicate"


# ── 5. Paired releases – same franchise, different subtitle word ───────────────

class TestPairedReleasesNotDuplicate:
    """
    Paired releases that share a franchise name but differ by a subtitle word
    (colour, element, direction, etc.) must NOT be flagged as duplicates even
    when all metadata signals – year, platform, developer, publisher – are
    identical.

    Root cause without fix: ``token_set_ratio`` treats the shared franchise
    token ("pokemon") as a perfect intersection and returns a high score,
    while completely ignoring that the distinguishing tokens ("red"/"blue",
    "scarlet"/"violet") are unrelated words.  The distinct-subtitle cap in
    ``_title_score`` / ``_title_score_keyed`` clamps the title score to 0.65
    whenever both normalised titles contain tokens the other lacks (neither is
    a token-superset of the other).  With the cap the worst-case aggregate score
    (all non-title signals = 1.0) is  0.65 × 0.50 + 0.50 = 0.825 < 0.85.
    """

    def _worst_case_score(self, title_a: str, title_b: str) -> float:
        """Return the aggregate score for the hardest-to-separate metadata
        configuration: same year, same platform, same developer, same
        publisher."""
        ga = make_game(title_a, year=2022,
                       platforms=["Nintendo Switch"],
                       developers=["Game Freak"],
                       publishers=["Nintendo"])
        gb = make_game(title_b, year=2022,
                       platforms=["Nintendo Switch"],
                       developers=["Game Freak"],
                       publishers=["Nintendo"])
        return GameMatcher().match(ga, gb).score

    def test_pokemon_red_vs_blue_worst_case(self):
        """Hardest case: identical year/platform/developer/publisher."""
        score = self._worst_case_score("Pokémon Red", "Pokémon Blue")
        assert score < _THRESHOLD, (
            f"Pokémon Red vs Pokémon Blue score {score:.3f} ≥ {_THRESHOLD} "
            f"(false positive)"
        )

    def test_pokemon_scarlet_vs_violet_worst_case(self):
        score = self._worst_case_score("Pokémon Scarlet", "Pokémon Violet")
        assert score < _THRESHOLD, (
            f"Pokémon Scarlet vs Pokémon Violet score {score:.3f} ≥ {_THRESHOLD} "
            f"(false positive)"
        )

    def test_pokemon_red_vs_blue_detector(self):
        """Full detector pipeline with identical metadata."""
        ga = make_game("Pokémon Red", year=1996,
                       platforms=["Game Boy"], developers=["Game Freak"])
        gb = make_game("Pokémon Blue", year=1996,
                       platforms=["Game Boy"], developers=["Game Freak"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=_THRESHOLD)).detect(lib)
        assert report.group_count == 0, (
            "Pokémon Red vs Pokémon Blue was incorrectly flagged as a duplicate"
        )

    def test_pokemon_scarlet_vs_violet_detector(self):
        ga = make_game("Pokémon Scarlet", year=2022,
                       platforms=["Nintendo Switch"], developers=["Game Freak"])
        gb = make_game("Pokémon Violet", year=2022,
                       platforms=["Nintendo Switch"], developers=["Game Freak"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=_THRESHOLD)).detect(lib)
        assert report.group_count == 0, (
            "Pokémon Scarlet vs Pokémon Violet was incorrectly flagged as a duplicate"
        )

    def test_accent_variant_still_detected_as_duplicate(self):
        """Pokémon (accented) and Pokemon (plain) are the SAME game on different
        storefronts – the accent normalisation must still produce a duplicate."""
        ga = make_game("Pokémon Scarlet", year=2022,
                       platforms=["Nintendo Switch"], developers=["Game Freak"])
        gb = make_game("Pokemon Scarlet", year=2022,
                       platforms=["Nintendo Switch"], developers=["Game Freak"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=_THRESHOLD)).detect(lib)
        assert report.group_count == 1, (
            "Pokémon Scarlet vs Pokemon Scarlet should be detected as a duplicate "
            "(same title, only accent differs)"
        )

    def test_gold_vs_silver_not_duplicate(self):
        score = self._worst_case_score("Pokémon Gold", "Pokémon Silver")
        assert score < _THRESHOLD, (
            f"Pokémon Gold vs Pokémon Silver score {score:.3f} ≥ {_THRESHOLD}"
        )

    def test_sword_vs_shield_not_duplicate(self):
        score = self._worst_case_score("Pokémon Sword", "Pokémon Shield")
        assert score < _THRESHOLD, (
            f"Pokémon Sword vs Pokémon Shield score {score:.3f} ≥ {_THRESHOLD}"
        )


# ── 6. Identifiability: MatchResult.details populated ─────────────────────────

class TestMatchResultIdentifiability:
    """
    Every ``MatchResult`` stored in a ``DuplicateGroup.match_results`` list must
    carry a populated ``details`` dict so that callers can understand *why* two
    games were flagged as duplicates.

    The detector re-runs ``match_keyed`` with ``include_details=True`` for the
    small set of matched pairs after the hot scan loop completes.
    """

    def test_details_not_none_for_flagged_pair(self):
        """details must be a dict, not None, for every matched MatchResult."""
        ga = make_game("Portal 2", year=2011, platforms=["PC"],
                       developers=["Valve"])
        gb = make_game("Portal 2", year=2011, platforms=["PC"],
                       developers=["Valve Corporation"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=0.80)).detect(lib)

        assert report.group_count >= 1, "Expected at least one duplicate group"
        for group in report.groups:
            for mr in group.match_results:
                assert mr.details is not None, (
                    f"MatchResult.details is None for pair "
                    f"({mr.game_a_id}, {mr.game_b_id})"
                )

    def test_details_contain_all_expected_keys(self):
        """details must contain all nine breakdown keys."""
        ga = make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"])
        gb = make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=0.80)).detect(lib)

        assert report.group_count >= 1
        details = report.groups[0].match_results[0].details
        assert details is not None

        expected_keys = {
            "title_norm_a", "title_norm_b",
            "title_score",
            "year_a", "year_b", "year_score",
            "platform_score", "developer_score", "publisher_score",
        }
        missing = expected_keys - details.keys()
        assert not missing, f"details dict is missing keys: {missing}"

    def test_details_score_values_are_valid_floats(self):
        """Each *_score value in details must parse as a float in [0, 1]."""
        ga = make_game("Portal 2", year=2011, platforms=["PC"])
        gb = make_game("Portal 2", year=2011, platforms=["PC"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=0.80)).detect(lib)

        assert report.group_count >= 1
        details = report.groups[0].match_results[0].details
        assert details is not None

        for key in ("title_score", "year_score", "platform_score",
                    "developer_score", "publisher_score"):
            val = float(details[key])  # must not raise
            assert 0.0 <= val <= 1.0, f"details['{key}']={val} is outside [0, 1]"

    def test_details_title_norms_match_actual_normalized_titles(self):
        """title_norm_a / title_norm_b must reflect the normalised titles."""
        from game_library.utils.text_utils import normalize_title

        ga = make_game("The Witcher 3: Wild Hunt – Game of the Year Edition",
                       year=2015, platforms=["PC"])
        gb = make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"])
        lib = make_library("test", [ga, gb])
        report = DuplicateDetector(DetectorConfig(threshold=0.80)).detect(lib)

        assert report.group_count >= 1
        details = report.groups[0].match_results[0].details
        assert details is not None

        norms = {details["title_norm_a"], details["title_norm_b"]}
        # After GOTY edition stripping both normalise to the same base title
        assert normalize_title("The Witcher 3: Wild Hunt") in norms

    def test_no_details_in_hot_path_match_result(self):
        """GameMatcher.match() (not via detector) populates details by default."""
        ga = make_game("Portal 2", year=2011)
        gb = make_game("Portal 2", year=2011)
        result = GameMatcher().match(ga, gb)
        # match() always builds details (it is not the hot path)
        assert result.details is not None

    def test_match_keyed_without_include_details_gives_none(self):
        """match_keyed with include_details=False must leave details as None."""
        from game_library.utils.text_utils import normalize_title

        ga = make_game("Portal 2", year=2011)
        gb = make_game("Portal 2", year=2011)
        na = normalize_title(ga.Name)
        nb = normalize_title(gb.Name)
        result = GameMatcher().match_keyed(ga, gb, na, nb, include_details=False)
        assert result is not None
        assert result.details is None

    def test_match_keyed_with_include_details_gives_dict(self):
        """match_keyed with include_details=True must populate details."""
        from game_library.utils.text_utils import normalize_title

        ga = make_game("Portal 2", year=2011)
        gb = make_game("Portal 2", year=2011)
        na = normalize_title(ga.Name)
        nb = normalize_title(gb.Name)
        result = GameMatcher().match_keyed(ga, gb, na, nb, include_details=True)
        assert result is not None
        assert result.details is not None
        assert "title_score" in result.details
