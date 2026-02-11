"""
Text normalisation utilities for game title comparison.

``normalize_title`` is the canonical function used by both the duplicate
detector and the library merger to produce a stable comparison key from a
raw game title.
"""
from __future__ import annotations

import re
import unicodedata

# Articles that are irrelevant when sorting / comparing
_ARTICLES = frozenset({"the", "a", "an"})

# Trailing edition/version suffixes that should be stripped for comparison.
# Listed from most to least specific to avoid partial matches.
_EDITION_PATTERNS: list[str] = [
    r"\s*[\(\[]?game\s+of\s+the\s+year\s+edition[\)\]]?",
    r"\s*[\(\[]?goty[\)\]]?",
    r"\s*[\(\[]?complete\s+edition[\)\]]?",
    r"\s*[\(\[]?definitive\s+edition[\)\]]?",
    r"\s*[\(\[]?enhanced\s+edition[\)\]]?",
    r"\s*[\(\[]?anniversary\s+edition[\)\]]?",
    r"\s*[\(\[]?special\s+edition[\)\]]?",
    r"\s*[\(\[]?gold\s+edition[\)\]]?",
    r"\s*[\(\[]?deluxe\s+edition[\)\]]?",
    r"\s*[\(\[]?ultimate\s+edition[\)\]]?",
    r"\s*[\(\[]?collector[']?s\s+edition[\)\]]?",
    r"\s*[\(\[]?premium\s+edition[\)\]]?",
    r"\s*[\(\[]?extended\s+edition[\)\]]?",
    r"\s*[\(\[]?director[']?s\s+cut[\)\]]?",
    r"\s*[\(\[]?remastered[\)\]]?",
    r"\s*[\(\[]?remaster[\)\]]?",
    r"\s*[\(\[]?remake[\)\]]?",
    r"\s*[\(\[]?hd[\)\]]?",
    r"\s*[\(\[]?4k[\)\]]?",
    r"\s*v?\d+\.\d+[\.\d]*$",  # trailing version numbers like v2.0
    r"\s*[\(\[]\d+[\)\]]$",    # trailing (year) or [year] at end
]

_COMPILED_EDITIONS = [re.compile(p, re.IGNORECASE) for p in _EDITION_PATTERNS]

# Characters to keep: alphanumeric and spaces only after stripping unicode
_KEEP_PATTERN = re.compile(r"[^\w\s]")
_SPACE_PATTERN = re.compile(r"\s+")

# Apostrophes and their Unicode lookalikes – removed entirely so that
# "Baldur's Gate 3" and "Baldurs Gate 3" produce the same key.
_APOSTROPHE_PATTERN = re.compile(r"['\u2018\u2019\u02bc]")

# Common gaming abbreviations expanded to their full form so that
# e.g. "GTA V" and "Grand Theft Auto V" normalise to the same string.
# Keys are already lower-cased; values contain only alpha+spaces.
# The list is intentionally conservative to minimise false positives.
_GAME_ABBREVIATIONS: dict[str, str] = {
    "gta":  "grand theft auto",
    "cod":  "call of duty",
    "nfs":  "need for speed",
    "kh":   "kingdom hearts",
    "dmc":  "devil may cry",
    "mgs":  "metal gear solid",
    "botw": "breath of the wild",
    "totk": "tears of the kingdom",
    "eso":  "elder scrolls online",
}

# Roman numerals → arabic (up to XII) for canonical comparison
_ROMAN: dict[str, str] = {
    "xii": "12", "xi": "11", "x": "10",
    "ix": "9", "viii": "8", "vii": "7", "vi": "6",
    "iv": "4", "v": "5",
    "iii": "3", "ii": "2",
}
_ROMAN_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_ROMAN.keys(), key=len, reverse=True)) + r")\b"
)


def nfc_lower(s: str) -> str:
    """Return *s* NFC-normalised then lower-cased.

    Use this instead of plain ``.lower()`` whenever two strings from different
    sources are compared for equality (e.g. entity-name lookups, filter
    matching).  NFC normalization ensures that é stored as U+00E9 and é stored
    as U+0065 + U+0301 (combining) compare as equal.
    """
    return unicodedata.normalize("NFC", s).lower()


def normalize_title(title: str) -> str:
    """
    Return a stable, comparison-ready form of *title*.

    Steps applied:

    1. Unicode NFD decomposition → strip **only** Latin accent combining marks
       (U+0300–U+036F).  Non-Latin combining marks (e.g. Japanese dakuten
       U+3099) are preserved.  The result is NFC-recomposed so that partially-
       decomposed forms are not left as loose combining characters.
    2. ASCII lower-case.
    3. Remove apostrophes entirely so "Baldur's" and "Baldurs" compare equal.
    4. Strip edition / version suffixes *before* punctuation removal so that
       patterns like ``v2.0`` are matched while the dot is still present.
    5. Strip punctuation (keep alphanumerics and spaces).
    6. Remove leading articles (The, A, An).
    7. Normalise Roman numerals to Arabic.
    8. Expand common gaming abbreviations (e.g. ``gta`` → ``grand theft auto``).
    9. Collapse whitespace.
    """
    if not title:
        return ""

    # 1. NFD → strip only Latin diacritics (U+0300–U+036F); preserve
    #    non-Latin combining marks such as the Japanese dakuten (U+3099).
    #    NFC-recompose afterwards so no dangling combining chars remain.
    normalized = unicodedata.normalize("NFD", title)
    normalized = "".join(c for c in normalized if not ("\u0300" <= c <= "\u036f"))
    normalized = unicodedata.normalize("NFC", normalized)

    # 2. Lower-case
    normalized = normalized.lower()

    # 3. Remove apostrophes entirely (before punctuation step so no space is
    #    inserted in their place)
    normalized = _APOSTROPHE_PATTERN.sub("", normalized)

    # 4. Strip edition / version suffixes *before* punctuation removal
    prev = None
    while prev != normalized:
        prev = normalized
        for pattern in _COMPILED_EDITIONS:
            normalized = pattern.sub("", normalized).strip()

    # 5. Strip punctuation (keep alphanumerics and spaces)
    normalized = _KEEP_PATTERN.sub(" ", normalized)

    # 6. Remove leading article
    words = _SPACE_PATTERN.sub(" ", normalized).strip().split()
    if words and words[0] in _ARTICLES:
        words = words[1:]

    # 7. Roman numerals → Arabic
    joined = " ".join(words)
    joined = _ROMAN_PATTERN.sub(lambda m: _ROMAN[m.group(1)], joined)

    # 8. Expand common gaming abbreviations (whole-word, lower-cased already)
    joined = " ".join(_GAME_ABBREVIATIONS.get(w, w) for w in joined.split())

    # 9. Collapse whitespace
    return _SPACE_PATTERN.sub(" ", joined).strip()


def normalize_company_name(name: str) -> str:
    """
    Strip common legal suffixes and normalise a company name for comparison.
    """
    if not name:
        return ""
    suffixes = [
        r",?\s*inc\.?$", r",?\s*llc\.?$", r",?\s*ltd\.?$",
        r",?\s*limited$", r",?\s*corporation$", r",?\s*corp\.?$", r",?\s*co\.?$",
        r",?\s*gmbh$", r",?\s*s\.a\.?$", r",?\s*studios?$",
        r",?\s*games?$", r",?\s*entertainment$", r",?\s*interactive$",
        r",?\s*software$", r",?\s*digital$", r",?\s*productions?$",
    ]
    normalized = unicodedata.normalize("NFD", name)
    normalized = "".join(c for c in normalized if not ("\u0300" <= c <= "\u036f"))
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = normalized.lower().strip()
    for suffix in suffixes:
        normalized = re.sub(suffix, "", normalized, flags=re.IGNORECASE).strip()
    normalized = _KEEP_PATTERN.sub(" ", normalized)
    return _SPACE_PATTERN.sub(" ", normalized).strip()
