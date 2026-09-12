"""Multiplayer Elo for a daily free-for-all.

Every player who submitted a result that day is treated as having played one
game against every other submitter (win / draw / loss decided by score). The
per-opponent K is divided by the number of opponents so the largest possible
swing in a day is still that player's K.

Players with fewer than ``PROVISIONAL_GAMES`` rated days are *provisional*
and use the larger ``PROVISIONAL_K`` so their rating finds its level quickly.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations

STARTING_RATING = 1200.0
DEFAULT_K = 32.0
PROVISIONAL_K = 64.0
PROVISIONAL_GAMES = 5


def is_provisional(games_played: int, provisional_games: int = PROVISIONAL_GAMES) -> bool:
    return games_played < provisional_games


def k_factor(
    games_played: int,
    k: float = DEFAULT_K,
    provisional_k: float = PROVISIONAL_K,
    provisional_games: int = PROVISIONAL_GAMES,
) -> float:
    return provisional_k if is_provisional(games_played, provisional_games) else k


def expected_score(rating: float, opponent: float) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent - rating) / 400.0))


def actual_score(score: int, opponent_score: int) -> float:
    if score > opponent_score:
        return 1.0
    if score < opponent_score:
        return 0.0
    return 0.5


def rating_deltas(
    ratings: Mapping[int, float],
    scores: Mapping[int, int],
    k: float | Mapping[int, float] = DEFAULT_K,
) -> dict[int, float]:
    """Return ``{player: delta}`` for everyone in ``scores``.

    ``ratings`` must contain every key in ``scores``. ``k`` is either one
    K-factor for everyone or a per-player mapping (see :func:`k_factor`).
    A single submitter has nobody to be compared against and gets ``0.0``.
    """
    players = list(scores)
    deltas = {p: 0.0 for p in players}
    if len(players) < 2:
        return deltas
    opponents = len(players) - 1
    ks = {p: (k[p] if isinstance(k, Mapping) else k) / opponents for p in players}
    for a, b in combinations(players, 2):
        s_a = actual_score(scores[a], scores[b])
        e_a = expected_score(ratings[a], ratings[b])
        deltas[a] += ks[a] * (s_a - e_a)
        deltas[b] -= ks[b] * (s_a - e_a)
    return deltas


def placements(scores: Mapping[int, int]) -> dict[int, int]:
    """1-based placement, ties share the best rank (1, 1, 3, ...)."""
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
