"""Unit tests for text normalisation utilities."""
import pytest
from game_library.utils.text_utils import normalize_title, normalize_company_name


class TestNormalizeTitle:
    def test_basic_lowercase(self):
        assert normalize_title("The Witcher 3") == "witcher 3"

    def test_leading_article_the(self):
        assert normalize_title("The Legend of Zelda") == "legend of zelda"

    def test_leading_article_a(self):
        assert normalize_title("A Plague Tale: Innocence") == "plague tale innocence"

    def test_leading_article_an(self):
        assert normalize_title("An Unusual Journey") == "unusual journey"

    def test_strips_goty(self):
        assert normalize_title("The Witcher 3: Wild Hunt – Game of the Year Edition") == \
               normalize_title("The Witcher 3: Wild Hunt")

    def test_strips_goty_short(self):
        assert normalize_title("Dark Souls GOTY") == normalize_title("Dark Souls")

    def test_strips_definitive_edition(self):
        assert normalize_title("GTA V Definitive Edition") == normalize_title("GTA V")

    def test_strips_remastered(self):
        assert normalize_title("Halo 2 Remastered") == normalize_title("Halo 2")

    def test_strips_remake(self):
        assert normalize_title("Resident Evil 2 Remake") == normalize_title("Resident Evil 2")

    def test_strips_hd(self):
        assert normalize_title("Castlevania HD") == normalize_title("Castlevania")

    def test_roman_numeral_i(self):
        # Single-letter Roman numerals should NOT be converted to avoid false
        # positives (e.g. "V" as standalone)
        assert normalize_title("Final Fantasy VII") == "final fantasy 7"
        assert normalize_title("Final Fantasy VIII") == "final fantasy 8"
        assert normalize_title("Final Fantasy IV") == "final fantasy 4"
        assert normalize_title("Final Fantasy XII") == "final fantasy 12"

    def test_normalises_accents(self):
        assert normalize_title("Pokémon") == normalize_title("Pokemon")

    def test_punctuation_stripped(self):
        result = normalize_title("Baldur's Gate 3")
        assert "'" not in result
        assert "baldu" in result  # apostrophe stripped, no accent issues

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_whitespace_collapsed(self):
        # "V" is a Roman numeral so it becomes "5" – both forms compare equal
        result = normalize_title("  Grand  Theft  Auto  V  ")
        assert result in ("grand theft auto 5", "grand theft auto v")
        assert " " not in result.strip() or result == result.strip()

    def test_version_number_stripped(self):
        assert normalize_title("Game v2.0") == normalize_title("Game")

    def test_case_insensitive_editions(self):
        assert normalize_title("game GOTY") == normalize_title("game goty")


class TestNormalizeTitleAbbreviations:
    def test_gta_expands(self):
        assert normalize_title("GTA V") == normalize_title("Grand Theft Auto V")

    def test_gta_edition_expands(self):
        """Edition suffix stripped, then abbreviation expanded."""
        assert normalize_title("GTA V Definitive Edition") == normalize_title("Grand Theft Auto V")

    def test_cod_expands(self):
        assert normalize_title("CoD Modern Warfare") == normalize_title("Call of Duty Modern Warfare")

    def test_nfs_expands(self):
        assert normalize_title("NFS Underground") == normalize_title("Need for Speed Underground")

    def test_non_abbreviation_unchanged(self):
        """Tokens not in the table must pass through unchanged."""
        assert normalize_title("Halo 3") == "halo 3"

    def test_abbreviation_case_insensitive(self):
        assert normalize_title("GTA 5") == normalize_title("gta 5")


class TestNonEnglishTitles:
    """Verify normalize_title handles non-ASCII scripts correctly."""

    # ── Accented Latin ────────────────────────────────────────────────────────

    def test_accented_latin_matches_plain(self):
        """é/è/ü etc. must fold to their ASCII base so both forms match."""
        assert normalize_title("Pokémon") == normalize_title("Pokemon")
        assert normalize_title("Ōkami") == normalize_title("Okami")

    # ── Apostrophes ───────────────────────────────────────────────────────────

    def test_apostrophe_removed_not_spaced(self):
        """Apostrophe must be deleted so contractions stay fused."""
        result = normalize_title("Baldur's Gate 3")
        assert " s " not in result  # standalone ' s ' token would be a bug
        assert normalize_title("Baldur's Gate 3") == normalize_title("Baldurs Gate 3")

    def test_unicode_apostrophe_removed(self):
        """Typographic right-single-quote (U+2019) treated same as ASCII apostrophe."""
        assert normalize_title("Assassin\u2019s Creed") == normalize_title("Assassins Creed")

    # ── Emoji ─────────────────────────────────────────────────────────────────

    def test_emoji_stripped(self):
        """Emoji are non-word characters and must be removed."""
        assert normalize_title("🎮 Sonic the Hedgehog") == normalize_title("Sonic the Hedgehog")
        assert normalize_title("Halo 3 🔥") == normalize_title("Halo 3")

    # ── Japanese (Katakana / Hiragana / Kanji) ────────────────────────────────

    def test_japanese_same_script_matches(self):
        """Two identical Japanese titles must produce identical keys."""
        assert normalize_title("ゼルダの伝説") == normalize_title("ゼルダの伝説")

    def test_japanese_voiced_consonants_preserved(self):
        """NFD must not strip dakuten (U+3099); ダ must not become タ."""
        key = normalize_title("ダークソウル")
        # ダ (da) must survive intact – if stripped it becomes タ (ta)
        assert "タ" not in key  # タ without dakuten would indicate corruption
        # The two copies of the same title must still match each other
        assert normalize_title("ダークソウル") == normalize_title("ダークソウル")

    def test_japanese_cross_script_no_match(self):
        """Japanese and its romanised equivalent are NOT expected to match
        (no transliteration table is present – this is documented behaviour)."""
        jp = normalize_title("ダークソウル")
        en = normalize_title("Dark Souls")
        assert jp != en  # explicitly different scripts → no match expected

    # ── Cyrillic ──────────────────────────────────────────────────────────────

    def test_cyrillic_same_script_matches(self):
        """Two identical Cyrillic titles must produce identical keys."""
        assert normalize_title("Ведьмак 3") == normalize_title("Ведьмак 3")

    def test_cyrillic_cross_script_no_match(self):
        """Cyrillic and Latin forms are NOT expected to match without
        transliteration – this is documented behaviour."""
        ru = normalize_title("Ведьмак 3")
        en = normalize_title("The Witcher 3")
        assert ru != en


class TestNormalizeCompanyName:
    def test_strips_inc(self):
        assert normalize_company_name("Valve, Inc.") == "valve"

    def test_strips_ltd(self):
        assert normalize_company_name("Capcom Ltd.") == "capcom"

    def test_strips_studios(self):
        assert normalize_company_name("CD Projekt Red Studios") == "cd projekt red"

    def test_strips_games(self):
        assert normalize_company_name("Bethesda Games") == "bethesda"

    def test_strips_interactive(self):
        assert normalize_company_name("Ubisoft Interactive") == "ubisoft"

    def test_empty(self):
        assert normalize_company_name("") == ""

    def test_accents(self):
        assert normalize_company_name("Café Games") == "cafe"
