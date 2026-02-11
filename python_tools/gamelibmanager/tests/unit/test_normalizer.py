"""Tests for TitleNormalizer."""

import pytest
from gamelibmanager.duplicates.normalizer import TitleNormalizer


class TestTitleNormalizer:
    def test_empty_string(self):
        assert TitleNormalizer.normalize("") == ""

    def test_lowercase(self):
        assert TitleNormalizer.normalize("DOOM") == "doom"

    def test_strip_article_the(self):
        result = TitleNormalizer.normalize("The Witcher 3")
        assert result == "witcher 3"

    def test_strip_article_a(self):
        result = TitleNormalizer.normalize("A Plague Tale")
        assert result == "plague tale"

    def test_strip_article_an(self):
        result = TitleNormalizer.normalize("An Evil Game")
        assert result == "evil game"

    def test_edition_goty(self):
        result = TitleNormalizer.normalize("Skyrim Game of the Year Edition")
        assert "game of the year" not in result
        assert "edition" not in result
        assert "skyrim" in result

    def test_edition_remastered(self):
        result = TitleNormalizer.normalize("Dark Souls Remastered")
        assert "remastered" not in result
        assert "dark souls" in result

    def test_edition_deluxe(self):
        result = TitleNormalizer.normalize("Cyberpunk 2077 Deluxe Edition")
        assert "deluxe" not in result
        assert "cyberpunk 2077" in result

    def test_edition_definitive(self):
        result = TitleNormalizer.normalize("Shadow of Mordor Definitive Edition")
        assert "definitive" not in result

    def test_edition_directors_cut(self):
        result = TitleNormalizer.normalize("Death Stranding Directors Cut")
        assert "directors" not in result
        assert "cut" not in result

    def test_roman_numeral_iii(self):
        result = TitleNormalizer.normalize("Witcher III")
        assert "3" in result
        assert "iii" not in result

    def test_roman_numeral_vii(self):
        result = TitleNormalizer.normalize("Final Fantasy VII")
        assert "7" in result

    def test_roman_numeral_ii(self):
        result = TitleNormalizer.normalize("Destiny II")
        assert "2" in result

    def test_roman_numeral_iv(self):
        result = TitleNormalizer.normalize("Civilization IV")
        assert "4" in result

    def test_roman_numeral_x_not_converted(self):
        """Single-char 'X' is ambiguous — preserved as letter."""
        result = TitleNormalizer.normalize("Final Fantasy X")
        assert result == "final fantasy x"

    def test_punctuation_removed(self):
        result = TitleNormalizer.normalize("Dragon Age: Origins")
        assert ":" not in result
        assert "dragon age origins" == result

    def test_unicode_diacritics(self):
        result = TitleNormalizer.normalize("Pokémon")
        assert result == "pokemon"

    def test_multiple_spaces_collapsed(self):
        result = TitleNormalizer.normalize("  Game   With   Spaces  ")
        assert "  " not in result

    def test_combined_normalization(self):
        result = TitleNormalizer.normalize(
            "The Witcher III: Wild Hunt - Game of the Year Edition"
        )
        assert result == "witcher 3 wild hunt"

    def test_normalize_batch(self):
        titles = ["The Witcher 3", "DOOM", "A Plague Tale"]
        results = TitleNormalizer.normalize_batch(titles)
        assert len(results) == 3
        assert results[0] == "witcher 3"
        assert results[1] == "doom"
        assert results[2] == "plague tale"

    def test_single_character(self):
        assert TitleNormalizer.normalize("X") == "x"

    def test_all_punctuation(self):
        result = TitleNormalizer.normalize("!@#$%")
        assert result == ""

    # ------------------------------------------------------------------ #
    # Unicode / international script tests
    # ------------------------------------------------------------------ #

    def test_japanese_katakana_preserved(self):
        """Dakuten (voiced marks) must not be stripped."""
        result = TitleNormalizer.normalize("ファイナルファンタジー VII")
        assert "ファイナルファンタジー" in result
        assert "7" in result

    def test_japanese_hiragana_preserved(self):
        result = TitleNormalizer.normalize("ぷよぷよテトリス")
        assert "ぷよぷよテトリス" == result

    def test_cyrillic_lowercased(self):
        result = TitleNormalizer.normalize("Метро: Исход")
        assert result == "метро исход"

    def test_korean_hangul_preserved(self):
        result = TitleNormalizer.normalize("메이플스토리")
        assert result == "메이플스토리"

    def test_chinese_characters_preserved(self):
        result = TitleNormalizer.normalize("原神 Genshin Impact")
        assert result == "原神 genshin impact"

    def test_emoji_stripped(self):
        result = TitleNormalizer.normalize("🎮 Super Mario Bros 🎮")
        assert result == "super mario bros"

    def test_emoji_only_returns_empty(self):
        result = TitleNormalizer.normalize("🎮🎮🎮")
        assert result == ""

    def test_accented_pokemon(self):
        """é decomposes and accent is stripped; matches 'Pokemon'."""
        assert TitleNormalizer.normalize("Pokémon") == "pokemon"
        assert TitleNormalizer.normalize("Pokemon") == "pokemon"

    def test_trademark_stripped(self):
        """™ should not expand to 'TM' in the output."""
        result = TitleNormalizer.normalize("NieR:Automata™")
        assert result == "nier automata"

    def test_registered_stripped(self):
        result = TitleNormalizer.normalize("Sonic® Adventure")
        assert result == "sonic adventure"

    def test_fullwidth_colon(self):
        """Fullwidth colon ： (U+FF1A) should be treated like regular colon."""
        result = TitleNormalizer.normalize("Nier：Automata")
        assert result == "nier automata"

    def test_mixed_script_title(self):
        """Title mixing Latin and CJK."""
        result = TitleNormalizer.normalize("真・三國無双 Dynasty Warriors")
        assert "dynasty warriors" in result
        # CJK characters preserved
        assert "真" in result

    # ------------------------------------------------------------------ #
    # Single-char roman numeral false-positive prevention
    # ------------------------------------------------------------------ #

    def test_pokemon_x_preserved(self):
        assert TitleNormalizer.normalize("Pokémon X") == "pokemon x"

    def test_mega_man_x_preserved(self):
        assert TitleNormalizer.normalize("Mega Man X") == "mega man x"

    def test_gta_v_preserved(self):
        assert TitleNormalizer.normalize("Grand Theft Auto V") == "grand theft auto v"

    def test_standalone_v_preserved(self):
        assert TitleNormalizer.normalize("V") == "v"

    # ------------------------------------------------------------------ #
    # Multi-char roman numeral regression
    # ------------------------------------------------------------------ #

    def test_roman_numeral_ix(self):
        assert "9" in TitleNormalizer.normalize("Star Wars IX")

    def test_roman_numeral_vi(self):
        assert "6" in TitleNormalizer.normalize("Final Fantasy VI")

    def test_roman_numeral_xv(self):
        assert "15" in TitleNormalizer.normalize("Final Fantasy XV")

    def test_roman_numeral_xi(self):
        assert "11" in TitleNormalizer.normalize("Final Fantasy XI")
