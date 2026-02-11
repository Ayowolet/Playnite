"""Title normalization for duplicate matching."""

from __future__ import annotations

import re
import unicodedata


class TitleNormalizer:
    """Normalizes game titles for comparison.

    Steps applied in order:
    1. Unicode NFKD + strip diacritics
    2. Lowercase
    3. Strip leading articles: "the ", "a ", "an "
    4. Remove edition suffixes (GOTY, Remastered, Deluxe, etc.)
    5. Normalize roman numerals to arabic
    6. Strip punctuation
    7. Collapse whitespace
    """

    _ARTICLES = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)

    _EDITIONS = re.compile(
        r"\b(game\s+of\s+the\s+year|goty|definitive|remastered|"
        r"deluxe|ultimate|enhanced|complete|collectors?|anniversary|"
        r"directors?\s*cut|gold|platinum|standard|special|premium|"
        r"legendary|limited)\s*(edition)?\b",
        re.IGNORECASE,
    )

    # Order matters: longer numerals must be checked first.
    _ROMAN_MAP = [
        ("xviii", "18"), ("xvii", "17"), ("xvi", "16"), ("xv", "15"),
        ("xiv", "14"), ("xiii", "13"), ("xii", "12"), ("xi", "11"),
        ("ix", "9"), ("viii", "8"), ("vii", "7"),
        ("vi", "6"), ("iv", "4"), ("iii", "3"), ("ii", "2"),
    ]

    _PUNCTUATION = re.compile(r"[^\w\s]")
    _MULTI_SPACE = re.compile(r"\s+")
    # Symbols that NFKD expands into letters (™→TM, ®→(R), etc.)
    _SYMBOL_JUNK = re.compile(r"[\u2122\u00ae\u00a9]")

    @classmethod
    def _is_latin_diacritic(cls, c: str) -> bool:
        """Return True for combining marks used as Latin/Greek/Cyrillic diacritics.

        Preserves CJK voiced marks (dakuten U+3099, handakuten U+309A)
        and other non-Latin combining characters.
        """
        cp = ord(c)
        return (
            0x0300 <= cp <= 0x036F    # Combining Diacritical Marks
            or 0x1AB0 <= cp <= 0x1AFF  # Combining Diacritical Marks Extended
            or 0x1DC0 <= cp <= 0x1DFF  # Combining Diacritical Marks Supplement
            or 0x20D0 <= cp <= 0x20FF  # Combining Diacritical Marks for Symbols
            or 0xFE20 <= cp <= 0xFE2F  # Combining Half Marks
        )

    @classmethod
    def normalize(cls, title: str) -> str:
        if not title:
            return ""
        # 0. Strip symbols that NFKD would expand into misleading letters
        title = cls._SYMBOL_JUNK.sub("", title)

        # 1. Unicode NFKD – strip only Latin diacritical combining marks
        #    (preserves Japanese dakuten, Korean jamo, etc.)
        nfkd = unicodedata.normalize("NFKD", title)
        stripped = "".join(
            c for c in nfkd
            if unicodedata.category(c) != "Mn" or not cls._is_latin_diacritic(c)
        )
        # Recompose non-Latin combining marks (e.g. dakuten back to ジ,
        # Hangul jamo back to syllable blocks)
        stripped = unicodedata.normalize("NFC", stripped)

        # 2. Lowercase
        s = stripped.lower()

        # 3. Remove leading articles
        s = cls._ARTICLES.sub("", s)

        # 4. Remove edition suffixes
        s = cls._EDITIONS.sub("", s)

        # 5. Roman numerals → arabic (word-boundary aware)
        for roman, arabic in cls._ROMAN_MAP:
            s = re.sub(rf"\b{roman}\b", arabic, s)

        # 6. Strip punctuation
        s = cls._PUNCTUATION.sub(" ", s)

        # 7. Collapse whitespace
        s = cls._MULTI_SPACE.sub(" ", s).strip()

        return s

    @classmethod
    def normalize_batch(cls, titles: list[str]) -> list[str]:
        return [cls.normalize(t) for t in titles]
