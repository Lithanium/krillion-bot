"""Leaderboard tables (Queens-bot layout) plus their plain-text fallback.

Every board is a :class:`Table` of coloured :class:`Cell` values so the PNG
renderer and the Discord-markdown fallback show the same thing: rank, name with
current rating and rank abbreviation, the result's emoji row, score, event
performance and rating change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from .rating import rank_for_rating
from .storage import Player, RatingEntry, Result

Color = tuple[int, int, int]

BLACK: Color = (0, 0, 0)
DELTA_GRAY: Color = (128, 128, 128)
DELTA_GREEN: Color = (0, 128, 0)

RESULT_HEADER = ("#", "Name", "Result", "Score", "Perf", "Δ")
RESULT_RIGHT = frozenset({0, 3, 4, 5})
RATING_HEADER = ("#", "Name", "Rating", "Games")
RATING_RIGHT = frozenset({0, 3})


@dataclass(frozen=True)
class Cell:
    text: str
    color: Color = BLACK
    emoji: bool = False
    """Draw with the colour-emoji font (a Krillion result row)."""


@dataclass(frozen=True)
class Table:
    title: str
    header: tuple[str, ...]
    rows: list[tuple[Cell, ...]]
    right: frozenset[int]
    """Right-aligned column indexes."""
    notes: list[str]
    """Footer lines (markdown)."""

    def text(self) -> str:
        lines = [f"**{self.title}** 🦐"]
        for row in self.rows:
            rank, name, *rest = row
            cells = [f"`{rank.text:>2}.`", f"**{name.text}**", *(c.text for c in rest if c.text)]
            lines.append("  ".join(cells))
        return "\n".join([*lines, *self.notes])


def signed(value: float) -> str:
    rounded = round(value)
    return f"+{rounded}" if rounded >= 0 else str(rounded)


def rating_color(rating: float) -> Color:
    return rank_for_rating(round(rating)).color


def name_cell(name: str, rating: float) -> Cell:
    rank = rank_for_rating(round(rating))
    return Cell(f"{name} ({round(rating)} {rank.abbr})", rank.color)


def perf_cell(performance: float | None) -> Cell:
    if performance is None:
        return Cell("")
    return Cell(str(round(performance)), rating_color(performance))


def delta_cell(delta: float) -> Cell:
    return Cell(signed(delta), DELTA_GREEN if round(delta) > 0 else DELTA_GRAY)


def result_row(
    place: int,
    name: str,
    rating: float,
    tiers: str,
    score: int,
    performance: float | None,
    delta: float,
) -> tuple[Cell, ...]:
    return (
        Cell(str(place)),
        name_cell(name, rating),
        Cell(tiers, emoji=True),
        Cell(str(score)),
        perf_cell(performance),
        delta_cell(delta),
    )


def _decay_note(decay: Mapping[int, float], submitters: int) -> str | None:
    pool = -sum(decay.values())
    if round(pool) <= 0 or not submitters:
        return None
    absent = sum(1 for d in decay.values() if round(d) < 0)
    who = f"{absent} inactive diver's" if absent == 1 else f"{absent} inactive divers'"
    return f"_Δ includes +{round(pool / submitters)} each from {who} rating decay._"


def final_table(
    puzzle_number: int,
    puzzle_date: date,
    entries: list[RatingEntry],
    players: Mapping[int, Player],
    tiers: Mapping[int, str] | None = None,
    decay: Mapping[int, float] | None = None,
) -> Table:
    rows = []
    for e in entries:
        name = players[e.user_id].display_name if e.user_id in players else f"<@{e.user_id}>"
        row = tiers.get(e.user_id, "") if tiers else ""
        rows.append(
            result_row(e.placement, name, e.rating_before, row, e.score, e.performance, e.delta)
        )
    notes = []
    if len(entries) == 1 and round(entries[0].delta) == 0:
        notes.append("_Only one diver today, so no rating change._")
    if decay:
        note = _decay_note(decay, len(entries))
        if note:
            notes.append(note)
    title = f"Krillion #{puzzle_number} {puzzle_date.isoformat()} Results"
    return Table(title, RESULT_HEADER, rows, RESULT_RIGHT, notes)


def live_table(
    puzzle_number: int,
    results: list[Result],
    players: Mapping[int, Player],
    *,
    deltas: Mapping[int, float] | None = None,
    performances: Mapping[int, float | None] | None = None,
    reset_unix: int | None = None,
) -> Table:
    """``deltas``/``performances``: projected values if the day closed with these results."""
    rows = []
    place = 0
    previous: int | None = None
    for idx, r in enumerate(results, start=1):
        if r.score != previous:
            place = idx
            previous = r.score
        player = players.get(r.user_id)
        name = player.display_name if player else f"<@{r.user_id}>"
        rating = player.rating if player else 1200.0
        perf = performances.get(r.user_id) if performances else None
        delta = deltas.get(r.user_id, 0.0) if deltas else 0.0
        rows.append(result_row(place, name, rating, r.tiers, r.score, perf, delta))
    notes = []
    solo_delta = deltas.get(results[0].user_id, 0.0) if deltas and results else 0.0
    if len(results) == 1 and round(solo_delta) == 0:
        notes.append("_Only one diver so far, so no rating change yet._")
    if reset_unix is not None:
        notes.append(f"_Projected rating changes; closes <t:{reset_unix}:R>._")
    return Table(f"Krillion #{puzzle_number} — live", RESULT_HEADER, rows, RESULT_RIGHT, notes)


def ratings_table(players: list[Player], games: Mapping[int, int]) -> Table | None:
    """Server ranking of everyone who has finished at least one closed day."""
    rated = [p for p in players if games.get(p.user_id, 0) > 0]
    if not rated:
        return None
    rows = []
    for idx, p in enumerate(rated, start=1):
        rank = rank_for_rating(round(p.rating))
        rows.append(
            (
                Cell(str(idx)),
                Cell(p.display_name, rank.color),
                Cell(f"{round(p.rating)} · {rank.abbr}", rank.color),
                Cell(str(games[p.user_id])),
            )
        )
    return Table("Krillion Ratings", RATING_HEADER, rows, RATING_RIGHT, [])
