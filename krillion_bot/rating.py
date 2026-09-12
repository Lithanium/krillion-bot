"""Codeforces-style multiplayer rating for a daily free-for-all.

Ported from the LinkedIn Queens rating in mklol/tle-gf (``tle/util/akari_rating.py``,
``_akari_performance.py``, ``akari_ranks.py``). Each puzzle day is one contest:
every submitter is ranked against the others (higher score wins, ties share a
rank) and moves toward their expected-versus-actual rank using the exact
Codeforces formula — logistic win probabilities, expected-rank "seed",
geometric-mean target rank, binary-searched needed rating and the two CF
anti-inflation corrections — scaled by a small ``damping`` so a year of daily
"contests" doesn't swing wildly.

Absent players above the starting rating decay toward it, faster the longer the
streak, and the points they lose are shared equally among that day's
submitters, so the guild's total rating is conserved. Sub-default absentees
freeze rather than drift up.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

STARTING_RATING = 1200.0
DAMPING = 0.25
DECAY_BASE = 0.04
DECAY_MAX = 0.08
DECAY_GRACE = 0

_RATING_SCALE = 400.0
_SEARCH_LO = 1.0
_SEARCH_HI = 8000.0
_SEARCH_ITERS = 25


@dataclass(frozen=True)
class Rank:
    low: float
    high: float
    title: str
    abbr: str
    color: tuple[int, int, int]
    """Dark variant, legible on light table rows."""


RANKS = (
    Rank(-1e9, 1000, "Newbie", "N", (0x80, 0x80, 0x80)),
    Rank(1000, 1100, "Pupil", "P", (0x00, 0x80, 0x00)),
    Rank(1100, 1200, "Specialist", "S", (0x03, 0xA8, 0x9E)),
    Rank(1200, 1300, "Expert", "E", (0x00, 0x00, 0xFF)),
    Rank(1300, 1400, "Candidate Master", "CM", (0xAA, 0x00, 0xAA)),
    Rank(1400, 1500, "Master", "M", (0xFF, 0x8C, 0x00)),
    Rank(1500, 1600, "International Master", "IM", (0xF5, 0x75, 0x00)),
    Rank(1600, 1800, "Grandmaster", "GM", (0xFF, 0x30, 0x30)),
    Rank(1800, 2000, "International Grandmaster", "IGM", (0xFF, 0x00, 0x00)),
    Rank(2000, 1e9, "Legendary Grandmaster", "LGM", (0xCC, 0x00, 0x00)),
)


def rank_for_rating(rating: float) -> Rank:
    """Band covering ``rating`` (half-open ``[low, high)``); pass the rounded display value."""
    for rank in RANKS:
        if rank.low <= rating < rank.high:
            return rank
    raise ValueError(f"Rating {rating} outside known rank range")


def placements(scores: Mapping[int, int]) -> dict[int, int]:
    """Standard competition ranking: higher score is better, ties share the best rank."""
    ordered = sorted(scores.items(), key=lambda kv: -kv[1])
    result: dict[int, int] = {}
    rank = 0
    previous: int | None = None
    for idx, (player, score) in enumerate(ordered, start=1):
        if score != previous:
            rank = idx
            previous = score
        result[player] = rank
    return result


def _pow10(rating: float) -> float:
    return 10.0 ** (rating / _RATING_SCALE)


def _expected_seed(x_self: float, pow_others: list[float]) -> float:
    """1 + Σ P(other finishes above me)."""
    return 1.0 + sum(x / (x_self + x) for x in pow_others)


def _needed_rating(pow_others: list[float], target_seed: float) -> float:
    lo, hi = _SEARCH_LO, _SEARCH_HI
    for _ in range(_SEARCH_ITERS):
        mid = (lo + hi) / 2.0
        if _expected_seed(_pow10(mid), pow_others) < target_seed:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def _expected_losses(x_self: float, pow_field: list[float]) -> float:
    return sum(x / (x_self + x) for x in pow_field)


def event_performance(pow_field: list[float], rank: int) -> float:
    """Rating at which finishing ``rank`` in this field would have been par.

    Solves ``_expected_losses(P) == rank - 0.5`` over the whole field (self
    included as a sliding half-loss), which is finite for a win or a last
    place and identical for tied players.
    """
    target = rank - 0.5
    lo, hi = _SEARCH_LO, _SEARCH_HI
    for _ in range(_SEARCH_ITERS):
        mid = (lo + hi) / 2.0
        if _expected_losses(_pow10(mid), pow_field) < target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def compute_round(
    ratings: Mapping[int, float],
    ranks: Mapping[int, int],
    damping: float = DAMPING,
    performances: dict[int, float] | None = None,
) -> dict[int, float]:
    """One Codeforces rating round → ``{player: damped delta}``.

    ``ranks`` are 1-based with ties sharing a rank. If ``performances`` is a
    dict it is filled with each player's displayed event performance.
    """
    users = sorted(ratings)
    n = len(users)
    if n < 2:
        return {u: 0.0 for u in users}

    pows = {u: _pow10(ratings[u]) for u in users}
    pow_field = [pows[u] for u in users]
    deltas: dict[int, float] = {}
    for u in users:
        pow_others = [pows[o] for o in users if o != u]
        seed = _expected_seed(pows[u], pow_others)
        mid_rank = math.sqrt(ranks[u] * seed)
        need = _needed_rating(pow_others, mid_rank)
        if performances is not None:
            performances[u] = event_performance(pow_field, ranks[u])
        deltas[u] = (need - ratings[u]) / 2.0

    # CF correction 1: the field loses exactly n points in total.
    inc = -sum(deltas.values()) / n - 1.0
    for u in users:
        deltas[u] += inc

    # CF correction 2: the top-s by pre-contest rating must not gain on aggregate.
    by_rating = sorted(users, key=lambda u: ratings[u], reverse=True)
    s = round(min(n, 4 * round(math.sqrt(n))))
    if s > 0:
        top_sum = sum(deltas[u] for u in by_rating[:s])
        inc = min(max(-top_sum / s, -10.0), 0.0)
        for u in users:
            deltas[u] += inc

    return {u: damping * deltas[u] for u in users}


def decay_rate(
    skip_streak: int,
    base: float = DECAY_BASE,
    maximum: float = DECAY_MAX,
    grace: int = DECAY_GRACE,
) -> float:
    """Fraction of the gap to the starting rating closed on a skipped day."""
    return min(maximum, base * max(0, skip_streak - grace))


@dataclass(frozen=True)
class DayOutcome:
    deltas: dict[int, float]
    """Total change for each submitter (contest delta plus decay transfer share)."""
    performances: dict[int, float | None]
    """Event performance per submitter; ``None`` on a solo day."""
    decay: dict[int, float]
    """Change (≤ 0) for each absent player."""


def close_day(
    scores: Mapping[int, int],
    ratings: Mapping[int, float],
    absent: Mapping[int, tuple[float, int]],
    *,
    start_rating: float = STARTING_RATING,
    damping: float = DAMPING,
    decay_base: float = DECAY_BASE,
    decay_max: float = DECAY_MAX,
    decay_grace: int = DECAY_GRACE,
) -> DayOutcome:
    """Rate one puzzle day.

    ``scores``/``ratings`` cover the submitters; ``absent`` maps every other
    previously seen player to ``(rating, skip_streak)`` where the streak already
    counts this day. Absentees above ``start_rating`` lose ``decay_rate`` of
    their surplus; the pooled loss is split equally among the submitters.
    """
    players = list(scores)
    performances: dict[int, float | None] = {p: None for p in players}
    if len(players) >= 2:
        perfs: dict[int, float] = {}
        deltas = compute_round(ratings, placements(scores), damping, perfs)
        performances.update(perfs)
    else:
        deltas = {p: 0.0 for p in players}

    decay: dict[int, float] = {}
    pool = 0.0
    for uid, (rating, streak) in absent.items():
        raw = (start_rating - rating) * decay_rate(streak, decay_base, decay_max, decay_grace)
        decay[uid] = min(0.0, raw)
        pool -= decay[uid]
    if pool > 0 and players:
        share = pool / len(players)
        for p in players:
            deltas[p] += share
    return DayOutcome(deltas, performances, decay)
