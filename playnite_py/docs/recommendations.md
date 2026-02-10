# Recommendation Engine

`playnite_py` uses a hybrid recommendation engine that combines four scoring signals. This document explains how each signal works and what you can do to improve the quality of your recommendations.

## Table of Contents

- [Algorithm Overview](#algorithm-overview)
- [Scoring Signals](#scoring-signals)
- [Recommendation Filters](#recommendation-filters)
- [Moods](#moods)
- [Improving Accuracy](#improving-accuracy)
- [Recommendation Scores](#recommendation-scores)

---

## Algorithm Overview

When you run `playnite recommend generate`, the engine performs three steps:

1. **Build a candidate list** — Apply hard filters (genre, platform, mood, completion time, difficulty, multiplayer, VR) to narrow the full library to eligible games.
2. **Score candidates** — Each candidate receives a combined score from four sub-signals: content similarity, collaborative filtering, temporal recency bonus, and popularity.
3. **Rank and explain** — Candidates are sorted by final score. Each recommendation includes a human-readable explanation of the primary reason it was chosen.

The engine requires at least a few games in your library with play history to produce meaningful results. Run `playnite recommend analyse` first to build your preference profile.

---

## Scoring Signals

### 1. Content Filter (default weight: 60%)

Computes TF-IDF cosine similarity between games based on their feature tokens: genres, mechanics, themes, tags, difficulty, session length, and boolean attributes (multiplayer support, VR compatibility). Games similar to ones you have played and enjoyed score higher.

### 2. Collaborative Filter (default weight: 25%)

Uses SVD (Singular Value Decomposition) matrix factorisation on your play history to find latent preference patterns. This catches correlations that are not obvious from tags alone — for example, if you play many precision platformers across different publishers, the collaborative filter can surface others in that group even if they share no explicit tags.

Requires at least a handful of rated or played games to produce meaningful scores. Falls back gracefully to 0 when there is not enough data.

### 3. Temporal Filter (default weight: 10%)

Applies a recency bonus to games you have not played recently. If you finished a long RPG last week, this signal temporarily reduces its score while boosting shorter or different-genre games, helping to diversify your session.

### 4. Popularity Signal (default weight: 5%)

Provides a small boost to widely-played or highly-rated titles. This acts as a tiebreaker and helps cold-start situations where there is no personal history to draw from.

### Configuring Weights

Weights are configurable in `config.json`. They must be non-negative and ideally sum to approximately 1.0:

```json
{
  "recommendations": {
    "content_weight": 0.60,
    "collaborative_weight": 0.25,
    "temporal_weight": 0.10,
    "popularity_weight": 0.05,
    "min_score_threshold": 0.05,
    "feedback_learning_rate": 0.1,
    "cold_start_strategy": "popular"
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `content_weight` | 0.60 | Weight for TF-IDF content similarity |
| `collaborative_weight` | 0.25 | Weight for SVD collaborative filter |
| `temporal_weight` | 0.10 | Weight for recency/diversity bonus |
| `popularity_weight` | 0.05 | Weight for global popularity signal |
| `min_score_threshold` | 0.05 | Games below this score are excluded |
| `feedback_learning_rate` | 0.1 | How quickly feedback adjusts genre weights |
| `cold_start_strategy` | `"popular"` | Strategy when history is sparse: `"popular"` or `"diverse"` |

---

## Recommendation Filters

Filters are applied as hard constraints before scoring. A game that does not pass a filter is excluded entirely regardless of its similarity score.

| Filter | CLI Flag | Behaviour |
|--------|----------|-----------|
| Genre | `--genre GENRE` | Only games in the specified genre |
| Platform | `--platform PLATFORM` | Only games on the specified platform |
| Session length | `--session quick\|deep` | `quick`: completion ≤ 1 h; `deep`: completion ≥ 3 h |
| Max completion time | `--max-hours N` | Exclude games longer than N hours (main story) |
| Min completion time | `--min-hours N` | Exclude games shorter than N hours (main story) |
| Difficulty | `--difficulty easy\|medium\|hard\|very hard` | Only games matching the difficulty level |
| Multiplayer | `--multiplayer` / `--no-multiplayer` | Require or exclude multiplayer support |
| VR | `--vr` | Only VR-compatible games |
| Mood | `--mood MOOD` | See [Moods](#moods) below |

**Lenient vs strict behaviour:**
- `session`, `max-hours`, `min-hours`, and `difficulty` filters are lenient: games with no value recorded for that field always pass through. Only games with an explicit conflicting value are excluded.
- `--multiplayer` / `--no-multiplayer` and `--vr` are strict: these flags check the boolean field directly.

---

## Moods

A mood applies a token-level boost/penalty to the content filter, steering recommendations toward or away from certain game characteristics without hard-excluding anything.

Set a mood for a single call:

```bash
playnite recommend generate --mood relaxed
```

Set a persistent mood on your profile (applies to all future calls):

```bash
playnite recommend mood relaxed
```

Clear the persistent mood:

```bash
playnite recommend mood clear
# or
playnite recommend clear-filters
```

List all moods with descriptions:

```bash
playnite recommend mood --list
```

### Available Moods

| Mood | What it surfaces |
|------|-----------------|
| `relaxed` | Slow-paced, casual, low-stress games |
| `excited` | Action-heavy, fast-paced, high-energy titles |
| `creative` | Building, crafting, sandbox, and creative games |
| `competitive` | PvP, leaderboards, ranked, and skill-intensive games |
| `nostalgic` | Retro, pixel-art, classic remakes |
| `adventurous` | Open-world, exploration, discovery |
| `casual` | Short sessions, low commitment, pick-up-and-play |
| `focused` | Deep single-player, story-rich, immersive titles |
| `social` | Co-op, multiplayer, party games |
| `spooky` | Horror, atmospheric, dark themes |
| `challenging` | High-difficulty, punishing, demanding games |

---

## Improving Accuracy

The recommendations get more accurate the more feedback you provide. Here are the most effective actions:

### 1. Record what you played

```bash
playnite recommend feedback "Hollow Knight" played
```

Marking games as `played` is the single strongest signal. The collaborative filter uses this data directly.

### 2. Like and dislike specific titles

```bash
playnite recommend feedback "Celeste" liked
playnite recommend feedback "Fortnite" disliked
```

`liked` and `disliked` adjust your genre and mechanic weights via the configured `feedback_learning_rate`.

### 3. Dismiss games you are not interested in

```bash
playnite recommend feedback "Some Game" dismissed
```

Dismissed games are deprioritised in future batches.

### 4. Add games to wishlist

```bash
playnite recommend feedback "Hades" added_to_wishlist
```

Wishlist additions act as a soft positive signal.

### 5. Re-run library analysis after importing new games

```bash
playnite recommend analyse
```

Any time you import new games or update metadata, re-run `analyse` to rebuild the preference weights.

### 6. Check your accuracy stats

```bash
playnite recommend stats
```

Once you have provided at least 10–20 feedback events, this command shows acceptance rate and play conversion rate. If either is low, consider adjusting scoring weights in `config.json`.

### 7. Use the discovery feed

```bash
playnite recommend feed
```

The feed surfaces games from five different angles simultaneously. Providing feedback on feed results trains the engine more broadly than a single filter-heavy `generate` call.

---

## Recommendation Scores

Each recommendation has a `final_score` between 0 and 1. The score bar in the table uses filled blocks (`▓`) to give a visual indication:

```
▓▓▓▓▓▓▓░░░  = 0.7 score
```

The `why recommended` column shows the primary reason: for example, "Similar to Hollow Knight" (content signal) or "Because you played Dead Cells" (collaborative signal).

Export full reasoning for all past batches:

```bash
playnite recommend export -o recommendations_history.json
```
