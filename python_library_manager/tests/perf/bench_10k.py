"""
10 000-game performance benchmark for the duplicate detector.

Usage
-----
Run directly (recommended)::

    python tests/perf/bench_10k.py

Or via pytest (output is captured unless you pass -s)::

    pytest tests/perf/bench_10k.py -v -s

Design
------
Title corpus: 100 prefixes × 100 suffixes → 10 000 unique "{prefix} {suffix}"
titles.  Each token appears in exactly 100 games (100 / 10 000 = 1 %).
The frequency-cap threshold is max(20, 10 000 // 50) = 200, so every token
survives the stop-word filter and is indexed for candidate generation.
Prefixes and suffixes are drawn from disjoint word pools, so no reversed pair
(e.g. "Quest Alpha") can arise as a valid title in the corpus.

Duplicate injection: 200 Library-B games are exact-title copies of the first
200 Library-A games (same title, different game ID and source name).  A
correct matching engine detects all 200 pairs (100 % recall) and produces
zero false positives—the distinct-subtitle cap (0.65) keeps every other
candidate pair below the 0.85 duplicate threshold.

Metrics reported
----------------
- Wall-clock time for each pipeline stage (norm_cache, meta_cache,
  token_index, candidate generation, scoring, grouping)
- Total detected groups and overall wall time
- Candidate pairs generated vs O(n²)/2 theoretical maximum
- True-positive recall  (injected duplicates found / 200)
- False-positive count  (detected pairs that are NOT injected duplicates)
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from game_library.duplicate.detector import DuplicateDetector, DetectorConfig, _UnionFind
from game_library.models.game import Game, ReleaseDate
from game_library.models.library import Library, LibrarySource


# ── Corpus vocabulary ─────────────────────────────────────────────────────────
# 100 prefixes and 100 suffixes drawn from disjoint thematic pools.
# After normalize_title each becomes a single lowercase token (no punctuation,
# no accents).  Both lists are verified disjoint at import time.

_PREFIXES: list[str] = [
    "Red", "Blue", "Green", "Black", "White",
    "Dark", "Light", "Solar", "Lunar", "Astral",
    "Iron", "Steel", "Stone", "Fire", "Ice",
    "Shadow", "Storm", "Wind", "Earth", "Thunder",
    "Crystal", "Diamond", "Gold", "Silver", "Bronze",
    "Jade", "Onyx", "Ember", "Frost", "Blaze",
    "Epic", "Ultra", "Super", "Hyper", "Mega",
    "Turbo", "Proto", "Alpha", "Beta", "Gamma",
    "Delta", "Sigma", "Omega", "Prime", "Zero",
    "Last", "First", "Final", "Eternal", "Infinite",
    "Lost", "Fallen", "Broken", "Shattered", "Rising",
    "Burning", "Frozen", "Hidden", "Ancient", "Sacred",
    "Urban", "Jungle", "Ocean", "Desert", "Arctic",
    "Volcanic", "Coastal", "Island", "Mountain", "Orbital",
    "Stellar", "Galactic", "Cosmic", "Plasma", "Fusion",
    "Atomic", "Nano", "Brave", "Noble", "Swift",
    "Bold", "Fierce", "Silent", "Wild", "Free",
    "True", "Pure", "Rapid", "Surge", "Core",
    "Edge", "Peak", "Drift", "Rush", "Blitz",
    "Cyber", "Pixel", "Quantum", "Neon", "Void",
]

_SUFFIXES: list[str] = [
    "Quest", "Wars", "Heroes", "Legends", "Arena",
    "Siege", "Force", "Strike", "Hunt", "Chase",
    "Run", "Chronicles", "Saga", "Tales", "Origins",
    "Reborn", "Awakened", "Unleashed", "Frontline", "Battleground",
    "Horizon", "Nexus", "Vanguard", "Echoes", "Fury",
    "Sentinel", "Renegade", "Uprising", "Revolution", "Conquest",
    "Dominion", "Empire", "Kingdom", "Realm", "Dynasty",
    "Command", "Control", "Protocol", "Project", "Operation",
    "Mission", "Directive", "Initiative", "Advance", "Assault",
    "Defense", "Resistance", "Rebellion", "Alliance", "Coalition",
    "Encounter", "Expedition", "Journey", "Odyssey", "Voyage",
    "Escape", "Rescue", "Survival", "Endurance", "Refuge",
    "Paradox", "Enigma", "Mystery", "Puzzle", "Riddle",
    "Legacy", "Heritage", "Destiny", "Prophecy", "Omen",
    "Trials", "Challenges", "Gauntlet", "Tournament", "Contest",
    "Rivalry", "Duel", "Battle", "Combat", "Clash",
    "Showdown", "Standoff", "Confrontation", "Skirmish", "Ambush",
    "Invasion", "Infiltration", "Extraction", "Aftermath", "Reckoning",
    "Havoc", "Mayhem", "Chaos", "Turmoil", "Pandemonium",
    "Redemption", "Salvation", "Liberation", "Freedom", "Justice",
]

assert len(_PREFIXES) == 100, f"Expected 100 prefixes, got {len(_PREFIXES)}"
assert len(_SUFFIXES) == 100, f"Expected 100 suffixes, got {len(_SUFFIXES)}"
assert len(set(_PREFIXES)) == 100, "Duplicate entries in _PREFIXES"
assert len(set(_SUFFIXES)) == 100, "Duplicate entries in _SUFFIXES"
_overlap = set(w.lower() for w in _PREFIXES) & set(w.lower() for w in _SUFFIXES)
assert not _overlap, f"Prefix/suffix overlap after lowercasing: {_overlap}"

_TITLES: list[str] = [f"{p} {s}" for p in _PREFIXES for s in _SUFFIXES]
assert len(_TITLES) == 10_000

# Number of duplicate pairs to inject
_N_DUPS = 200


# ── Game factory ──────────────────────────────────────────────────────────────

def _make_game(title: str, source: str) -> Game:
    g = Game(
        Id=str(uuid.uuid4()),
        Name=title,
        ReleaseDate=ReleaseDate(Year=2020),
    )
    g._platform_names = ["PC"]
    g._developer_names = ["Benchmark Studio"]
    g._publisher_names = ["Benchmark Publishing"]
    g._source_name = source
    return g


# ── Library builder ───────────────────────────────────────────────────────────

def build_corpus() -> tuple[Library, Library, set[tuple[str, str]]]:
    """
    Return (lib_a, lib_b, injected_pairs).

    lib_a  – 10 000 games, one per title in the 100×100 grid.
    lib_b  – 200 games, each an exact-title copy of the first 200 lib_a games
             (different ID, source name "Library-B").
    injected_pairs – set of (id_a, id_b) canonical duplicate pairs.
    """
    lib_a = Library(source=LibrarySource(name="Library-A", path="/bench/a", priority=0))
    lib_b = Library(source=LibrarySource(name="Library-B", path="/bench/b", priority=1))

    games_a: list[Game] = []
    for title in _TITLES:
        g = _make_game(title, "Library-A")
        lib_a.games[g.Id] = g
        games_a.append(g)

    injected_pairs: set[tuple[str, str]] = set()
    for g_a in games_a[:_N_DUPS]:
        g_b = _make_game(g_a.Name, "Library-B")
        lib_b.games[g_b.Id] = g_b
        key = (min(g_a.Id, g_b.Id), max(g_a.Id, g_b.Id))
        injected_pairs.add(key)

    return lib_a, lib_b, injected_pairs


# ── Staged benchmark ──────────────────────────────────────────────────────────

def run_staged(
    detector: DuplicateDetector,
    games: list[Game],
    threshold: float,
) -> dict[str, float]:
    """
    Run each pipeline stage individually and return a ``{stage: seconds}`` map.

    This reproduces the :meth:`DuplicateDetector.detect` hot path with explicit
    timing checkpoints.  Calling internal helpers directly is intentional here;
    this is a benchmarking script, not production code.
    """
    stages: dict[str, float] = {}

    t = time.perf_counter()
    norm_cache = detector._build_norm_cache(games)
    stages["norm_cache"] = time.perf_counter() - t

    t = time.perf_counter()
    meta_cache = detector._matcher.build_meta_cache(games)
    stages["meta_cache"] = time.perf_counter() - t

    t = time.perf_counter()
    token_index = detector._build_token_index(games, norm_cache)
    stages["token_index"] = time.perf_counter() - t

    t = time.perf_counter()
    candidates = list(detector._iter_candidate_pairs(games, norm_cache, token_index))
    stages["candidate_gen"] = time.perf_counter() - t

    game_index = {g.Id: g for g in games}
    uf = _UnionFind()
    n_above_threshold = 0

    t = time.perf_counter()
    for id_a, id_b in candidates:
        ga = game_index.get(id_a)
        gb = game_index.get(id_b)
        if ga is None or gb is None:
            continue
        result = detector._matcher.match_keyed(
            ga, gb,
            norm_cache.get(id_a, ""),
            norm_cache.get(id_b, ""),
            threshold=threshold,
            include_details=False,
            meta_a=meta_cache.get(id_a),
            meta_b=meta_cache.get(id_b),
        )
        if result is not None and result.score >= threshold:
            uf.union(id_a, id_b)
            n_above_threshold += 1
    stages["scoring"] = time.perf_counter() - t

    t = time.perf_counter()
    _ = uf.groups(list(game_index.keys()))
    stages["grouping"] = time.perf_counter() - t

    stages["_candidates"] = float(len(candidates))
    stages["_above_threshold"] = float(n_above_threshold)
    stages["_token_types"] = float(len(token_index))

    return stages


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  10 000-game Duplicate Detection Benchmark")
    print("=" * 60)
    print(f"  Corpus  : {len(_TITLES):,} games  (100 prefixes × 100 suffixes)")
    print(f"  Injected: {_N_DUPS} duplicate pairs  (exact-title copies in Library-B)")

    lib_a, lib_b, injected_pairs = build_corpus()
    all_games = list(lib_a.games.values()) + list(lib_b.games.values())
    n_total = len(all_games)
    o_n2_half = n_total * (n_total - 1) // 2

    config = DetectorConfig(threshold=0.85)
    detector = DuplicateDetector(config)

    # ── Full detect() for overall wall time ──────────────────────────────────
    t_wall = time.perf_counter()
    report = detector.detect(lib_a, lib_b)
    wall_time = time.perf_counter() - t_wall

    # ── Staged timing (second pass) ───────────────────────────────────────────
    stages = run_staged(detector, all_games, config.threshold)

    n_candidates = int(stages["_candidates"])
    n_scored = int(stages["_above_threshold"])
    reduction_pct = (1 - n_candidates / o_n2_half) * 100

    # ── Recall / precision ────────────────────────────────────────────────────
    detected_pairs: set[tuple[str, str]] = set()
    for grp in report.groups:
        for dup in grp.duplicates:
            key = (min(grp.master.Id, dup.Id), max(grp.master.Id, dup.Id))
            detected_pairs.add(key)

    true_positives = len(detected_pairs & injected_pairs)
    false_positives = len(detected_pairs - injected_pairs)
    recall_pct = 100.0 * true_positives / _N_DUPS

    # ── Report ────────────────────────────────────────────────────────────────
    stage_total = sum(v for k, v in stages.items() if not k.startswith("_"))

    print("\nStage timing")
    for stage in ("norm_cache", "meta_cache", "token_index", "candidate_gen", "scoring", "grouping"):
        print(f"  {stage:<18}: {stages[stage]:.3f} s")
    print(f"  {'─' * 26}")
    print(f"  {'staged total':<18}: {stage_total:.3f} s")
    print(f"  {'full detect()':<18}: {wall_time:.3f} s")

    print("\nToken index")
    print(f"  unique tokens    : {int(stages['_token_types']):,}")
    print(f"  max_count cap    : {max(20, n_total // 50):,}  (2% of {n_total:,} games)")

    print("\nCandidate pairs")
    print(f"  generated        : {n_candidates:,}")
    print(f"  vs O(n²) / 2     : {o_n2_half:,}")
    print(f"  reduction        : {reduction_pct:.1f} %")
    print(f"  above threshold  : {n_scored:,}")

    print("\nResults")
    print(f"  groups detected  : {report.group_count}")
    print(f"  injected dups    : {_N_DUPS}")
    print(f"  true positives   : {true_positives}  (recall: {recall_pct:.1f} %)")
    print(f"  false positives  : {false_positives}")

    if recall_pct < 100.0:
        missed = _N_DUPS - true_positives
        print(f"\n  WARNING: {missed} injected duplicate(s) were not detected!")
    if false_positives > 0:
        print(f"\n  WARNING: {false_positives} false positive(s) detected!")

    print()


# ── Pytest integration ────────────────────────────────────────────────────────

def test_bench_10k_smoke() -> None:
    """
    Smoke test: the full benchmark runs end-to-end and achieves 100 % recall
    with zero false positives.  Run with ``pytest tests/perf/bench_10k.py -v``.
    """
    lib_a, lib_b, injected_pairs = build_corpus()
    config = DetectorConfig(threshold=0.85)
    report = DuplicateDetector(config).detect(lib_a, lib_b)

    detected_pairs: set[tuple[str, str]] = set()
    for grp in report.groups:
        for dup in grp.duplicates:
            key = (min(grp.master.Id, dup.Id), max(grp.master.Id, dup.Id))
            detected_pairs.add(key)

    true_positives = len(detected_pairs & injected_pairs)
    false_positives = len(detected_pairs - injected_pairs)

    assert true_positives == _N_DUPS, (
        f"Expected {_N_DUPS} true positives, got {true_positives}"
    )
    assert false_positives == 0, (
        f"Expected 0 false positives, got {false_positives}"
    )


if __name__ == "__main__":
    main()
