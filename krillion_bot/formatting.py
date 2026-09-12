"""Leaderboard rows plus plain-text renderers (Discord markdown)."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .storage import Player, RatingEntry, Result

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
PROVISIONAL_MARK = "?"
PROVISIONAL_NOTE = f"_{PROVISIONAL_MARK} = provisional rating (first few days move faster)._"


@dataclass(frozen=True)
class Row:
    """One leaderboard line, shared by the text and image renderers."""

    place: int
    name: str
    rating: str
    """Rating text, e.g. ``"1200?"`` (live) or ``"1200 → 1216"`` (final)."""
    tiers: str
    score: int
    delta: float


@dataclass(frozen=True)
class Board:
    title: str
    rows: list[Row]
    notes: list[str]
    """Footer lines (markdown)."""

    def text(self) -> str:
        return "\n".join([f"**{self.title}** 🦐", *(_row(r) for r in self.rows), *self.notes])


def _medal(place: int) -> str:
    return MEDALS.get(place, f"`{place:>2}.`")


def signed(value: float) -> str:
    rounded = round(value)
    return f"+{rounded}" if rounded >= 0 else str(rounded)


def _rating(value: float, provisional: bool) -> str:
    return f"{round(value)}{PROVISIONAL_MARK if provisional else ''}"


def _row(r: Row) -> str:
    cells = [f"{_medal(r.place)} **{r.name}** ({r.rating})"]
    if r.tiers:
        cells.append(r.tiers)
    cells.append(f"**{r.score}**  {signed(r.delta)}")
    return "  ".join(cells)


def final_board(
    puzzle_number: int,
    entries: list[RatingEntry],
    players: Mapping[int, Player],
    provisional: Collection[int] = (),
    tiers: Mapping[int, str] | None = None,
) -> Board:
    rows = []
    for e in entries:
        name = players[e.user_id].display_name if e.user_id in players else f"<@{e.user_id}>"
        after = _rating(e.rating_after, e.user_id in provisional)
        row = tiers.get(e.user_id, "") if tiers else ""
        rows.append(
            Row(e.placement, name, f"{round(e.rating_before)} → {after}", row, e.score, e.delta)
        )
    notes = []
    if len(entries) == 1:
        notes.append("_Only one diver today, so no rating change._")
    if any(e.user_id in provisional for e in entries):
        notes.append(PROVISIONAL_NOTE)
    return Board(f"Krillion #{puzzle_number} — final results", rows, notes)


def live_board(
    puzzle_number: int,
    results: list[Result],
    players: Mapping[int, Player],
    *,
    deltas: Mapping[int, float] | None = None,
    provisional: Collection[int] = (),
    reset_unix: int | None = None,
) -> Board:
    """``deltas``: projected rating change if the day closed with these results."""
    rows = []
    place = 0
    previous: int | None = None
    for idx, r in enumerate(results, start=1):
        if r.score != previous:
            place = idx
            previous = r.score
        player = players.get(r.user_id)
        name = player.display_name if player else f"<@{r.user_id}>"
        rating = _rating(player.rating, r.user_id in provisional) if player else "?"
        delta = deltas.get(r.user_id, 0.0) if deltas else 0.0
        rows.append(Row(place, name, rating, r.tiers, r.score, delta))
    notes = []
    if len(results) == 1:
        notes.append("_Only one diver so far, so no rating change yet._")
    if any(r.user_id in provisional for r in results):
        notes.append(PROVISIONAL_NOTE)
    if reset_unix is not None:
        notes.append(f"_Projected rating changes; closes <t:{reset_unix}:R>._")
    return Board(f"Krillion #{puzzle_number} — live", rows, notes)


def daily_leaderboard(
    puzzle_number: int,
    entries: list[RatingEntry],
    players: Mapping[int, Player],
    provisional: Collection[int] = (),
    tiers: Mapping[int, str] | None = None,
) -> str:
    return final_board(puzzle_number, entries, players, provisional, tiers).text()


def live_leaderboard(
    puzzle_number: int,
    results: list[Result],
    players: Mapping[int, Player],
    *,
    deltas: Mapping[int, float] | None = None,
    provisional: Collection[int] = (),
    reset_unix: int | None = None,
) -> str:
    if not results:
        return f"**Krillion #{puzzle_number}** — no results yet. 🫧"
    return live_board(
        puzzle_number,
        results,
        players,
        deltas=deltas,
        provisional=provisional,
        reset_unix=reset_unix,
    ).text()


def elo_leaderboard(
    players: list[Player],
    games: Mapping[int, int],
    provisional: Collection[int] = (),
) -> str:
    rated = [p for p in players if games.get(p.user_id, 0) > 0]
    if not rated:
        return "No rated players yet — share a Krillion result to get started. 🫧"
    lines = ["**Krillion Elo** 🦐"]
    for idx, p in enumerate(rated, start=1):
        lines.append(
            f"{_medal(idx)} **{p.display_name}** — {_rating(p.rating, p.user_id in provisional)}  "
            f"({games.get(p.user_id, 0)} played)"
        )
    if any(p.user_id in provisional for p in rated):
        lines.append(PROVISIONAL_NOTE)
    return "\n".join(lines)
