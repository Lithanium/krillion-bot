"""Plain-text renderers for leaderboards (Discord markdown)."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from .storage import Player, RatingEntry, Result

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
PROVISIONAL_MARK = "?"
PROVISIONAL_NOTE = f"_{PROVISIONAL_MARK} = provisional rating (first few days move faster)._"


def _medal(place: int) -> str:
    return MEDALS.get(place, f"`{place:>2}.`")


def _signed(value: float) -> str:
    rounded = round(value)
    return f"+{rounded}" if rounded >= 0 else str(rounded)


def _rating(value: float, provisional: bool) -> str:
    return f"{round(value)}{PROVISIONAL_MARK if provisional else ''}"


def _row(place: int, name: str, rating: str, tiers: str, score: int, delta: float) -> str:
    """One table-ish line: rank, name (rating), emoji row, score, rating change."""
    cells = [f"{_medal(place)} **{name}** ({rating})"]
    if tiers:
        cells.append(tiers)
    cells.append(f"**{score}**  {_signed(delta)}")
    return "  ".join(cells)


def daily_leaderboard(
    puzzle_number: int,
    entries: list[RatingEntry],
    players: Mapping[int, Player],
    provisional: Collection[int] = (),
    tiers: Mapping[int, str] | None = None,
) -> str:
    lines = [f"**Krillion #{puzzle_number} — final results** 🦐"]
    for e in entries:
        name = players[e.user_id].display_name if e.user_id in players else f"<@{e.user_id}>"
        after = _rating(e.rating_after, e.user_id in provisional)
        rating = f"{round(e.rating_before)} → {after}"
        row = tiers.get(e.user_id, "") if tiers else ""
        lines.append(_row(e.placement, name, rating, row, e.score, e.delta))
    if len(entries) == 1:
        lines.append("_Only one diver today, so no rating change._")
    if any(e.user_id in provisional for e in entries):
        lines.append(PROVISIONAL_NOTE)
    return "\n".join(lines)


def live_leaderboard(
    puzzle_number: int,
    results: list[Result],
    players: Mapping[int, Player],
    *,
    deltas: Mapping[int, float] | None = None,
    provisional: Collection[int] = (),
    reset_unix: int | None = None,
) -> str:
    """``deltas``: projected rating change if the day closed with these results."""
    if not results:
        return f"**Krillion #{puzzle_number}** — no results yet. 🫧"
    lines = [f"**Krillion #{puzzle_number} — live** 🦐"]
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
        lines.append(_row(place, name, rating, r.tiers, r.score, delta))
    if len(results) == 1:
        lines.append("_Only one diver so far, so no rating change yet._")
    if any(r.user_id in provisional for r in results):
        lines.append(PROVISIONAL_NOTE)
    if reset_unix is not None:
        lines.append(f"_Projected rating changes; closes <t:{reset_unix}:R>._")
    return "\n".join(lines)


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
