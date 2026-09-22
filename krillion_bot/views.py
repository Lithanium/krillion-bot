"""Embed views for the stats-style commands, in the tle-gf Akari layout."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import discord

from .analytics import Streaks, Summary, TopEntry, VsOutcome
from .discord_util import info, number_pages, ok, pages, rank_color
from .formatting import signed
from .models import RatingEntry, Result
from .puzzle import PuzzleCalendar
from .rating import rank_for_rating

Names = Mapping[int, str]

TIMEFRAME_LABEL = {
    "all": "all time",
    "week": "this week",
    "month": "this month",
    "year": "this year",
    "7d": "last 7 days",
    "30d": "last 30 days",
}

PER_PAGE = 10
HISTORY_PAGE = 15
DOT = " \N{MIDDLE DOT} "


def name_of(names: Names, user_id: int) -> str:
    return names.get(user_id, f"<@{user_id}>")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _rated(value: float) -> str:
    return f"{round(value)} ({rank_for_rating(round(value)).abbr})"


def streak_embed(name: str, play: Streaks, perfect: Streaks) -> discord.Embed:
    lines = [
        f"`{name}`: **{play.current}** consecutive day(s)",
        f"Longest streak: **{play.longest}** day(s)",
        f"Perfect-700 streak: **{perfect.current}** (longest **{perfect.longest}**)",
    ]
    return info("\n".join(lines), title="Krillion Streak")


def skips_pages(
    name: str, first: int | None, skipped: Sequence[int], calendar: PuzzleCalendar
) -> list[discord.Embed]:
    if first is None:
        return [info(f"No Krillion results found for `{name}`.")]
    if not skipped:
        return [ok(f"`{name}` has played every Krillion since **#{first}** — no skips!")]
    lines = [
        f"**#{n}**{DOT}{calendar.date_for(n).isoformat()}{DOT}{calendar.date_for(n):%A}"
        for n in skipped
    ]
    title = f"Krillion skipped days — {name} ({_plural(len(skipped), 'day')})"
    lead = f"Since first submission: **#{first}**{DOT}**{calendar.date_for(first).isoformat()}**"
    return pages(title, lines, HISTORY_PAGE, lead=lead)


def top_pages(
    entries: Sequence[TopEntry], names: Names, label: str, count_ties: bool
) -> list[discord.Embed]:
    lines = []
    place = 0
    previous: tuple[int, int] | None = None
    for idx, e in enumerate(entries, start=1):
        key = (e.total, e.solo) if count_ties else (e.solo, e.tied)
        if key != previous:
            place = idx
            previous = key
        name = name_of(names, e.user_id)
        if count_ties:
            lines.append(
                f"**#{place}** `{name}` — **{e.total}** wins ({e.solo} solo, {e.tied} tied)"
            )
        else:
            lines.append(f"**#{place}** `{name}` — **{e.solo}** wins")
    suffix = f"{label.title()}, With Ties" if count_ties else label.title()
    return pages(f"Krillion Winners ({suffix})", lines, PER_PAGE)


def vs_pages(
    outcome: VsOutcome,
    names: Names,
    label: str,
    missing_is_loss: bool,
    rows: Mapping[int, Sequence[Result]],
) -> list[discord.Embed]:
    title = f"Krillion Head to Head ({label.title()})"
    if len(outcome.players) != 2:
        lines = []
        place = 0
        previous: float | None = None
        for idx, p in enumerate(outcome.players, start=1):
            if p.points != previous:
                place = idx
                previous = p.points
            lines.append(
                f"**#{place}** `{name_of(names, p.user_id)}` — **{p.points:g}** points"
                f"{DOT}{p.wins}W {p.losses}L {p.ties}T"
            )
        lines.append(f"Comparisons: **{outcome.comparisons}**{DOT}Puzzles: **{outcome.puzzles}**")
        if missing_is_loss:
            lines.append("_A missing result counts as a loss._")
        return [info("\n".join(lines), title=title)]

    a, b = outcome.players
    summary = [
        f"`{name_of(names, a.user_id)}`: **{a.points:g}** points, **{a.wins}** wins",
        f"`{name_of(names, b.user_id)}`: **{b.points:g}** points, **{b.wins}** wins",
        f"Ties: **{a.ties}**",
        f"Puzzles: **{outcome.puzzles}**",
    ]
    if missing_is_loss:
        summary.append("_A missing result counts as a loss._")
    scores = {uid: {r.puzzle_number: r.score for r in rs} for uid, rs in rows.items()}
    numbers = set(scores[a.user_id]) | set(scores[b.user_id])
    if not missing_is_loss:
        numbers = set(scores[a.user_id]) & set(scores[b.user_id])
    matchups = sorted(numbers, reverse=True)

    def column(uid: int, chunk: Sequence[int]) -> str:
        cells = []
        for n in chunk:
            score = scores[uid].get(n)
            cells.append(f"**#{n}** {'no result' if score is None else f'{score} pts'}")
        return "\n".join(cells)

    out = []
    for start in range(0, max(len(matchups), 1), PER_PAGE):
        chunk = matchups[start : start + PER_PAGE]
        e = info("\n".join(summary), title=title)
        if chunk:
            e.add_field(name=name_of(names, a.user_id), value=column(a.user_id, chunk))
            e.add_field(name=name_of(names, b.user_id), value=column(b.user_id, chunk))
        out.append(e)
    return number_pages(out)


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def history_pages(
    name: str, entries: Sequence[RatingEntry], calendar: PuzzleCalendar
) -> list[discord.Embed]:
    """Rated days, newest first: ``#58 · 2026-09-11 · 340 pts · 2nd · 1200 ─ +12 → 1212 (E)``."""
    lines = []
    for e in reversed(entries):
        perf = f"{DOT}perf {round(e.performance)}" if e.performance is not None else ""
        lines.append(
            f"**#{e.puzzle_number}**{DOT}{calendar.date_for(e.puzzle_number).isoformat()}"
            f"{DOT}{e.score} pts{DOT}{e.placement}{_ordinal(e.placement)}"
            f"{DOT}{round(e.rating_before)} \N{HORIZONTAL BAR} **{round(e.delta):+}** "
            f"\N{RIGHTWARDS ARROW} {_rated(e.rating_after)}{perf}"
        )
    title = f"Krillion rating history — {name} ({_plural(len(entries), 'rated day')})"
    return pages(title, lines, HISTORY_PAGE)


def rating_embed(name: str, s: Summary, games: int, *, performance: bool) -> discord.Embed:
    """``/krillion rating`` and ``/krillion performance`` header; the plot hangs below it."""
    assert s.rating is not None
    if performance and s.last_performance is not None and s.best_performance is not None:
        e = discord.Embed(
            title=f"Krillion performance — {name}", color=rank_color(s.last_performance)
        )
        e.add_field(name="Last performance", value=_rated(s.last_performance))
        e.add_field(name="Best performance", value=_rated(s.best_performance))
        e.add_field(name="Contests", value=str(games))
        return e
    e = discord.Embed(title=f"Krillion rating — {name}", color=rank_color(s.rating))
    e.add_field(name="Rating", value=_rated(s.rating))
    e.add_field(name="Peak", value=_rated(s.peak if s.peak is not None else s.rating))
    e.add_field(name="Games", value=str(games))
    e.add_field(name="Last change", value=signed(s.last_delta) if s.last_delta is not None else "—")
    e.add_field(
        name="Last performance",
        value=_rated(s.last_performance) if s.last_performance is not None else "—",
    )
    return e


def settings_embed(
    results_channel: int | None,
    leaderboard_channel: int | None,
    weekly_channel: int | None,
    admins: Sequence[int],
    bans: int,
    opted_out: int,
    current: int,
    today: date,
) -> discord.Embed:
    def chan(cid: int | None, default: str) -> str:
        return f"<#{cid}>" if cid else f"`{default}`"

    who = ", ".join(f"<@{a}>" for a in admins) or "`none`"
    lines = [
        f"today: **Krillion #{current}** ({today:%a %d %b %Y})",
        f"results channel: {chan(results_channel, 'every channel')}",
        f"leaderboard channel: {chan(leaderboard_channel, 'where results were shared')}",
        f"weekly recap channel: {chan(weekly_channel, 'off')}",
        f"admins: {who}",
        f"banned: `{bans}`{DOT}hidden from boards: `{opted_out}`",
    ]
    return info("\n".join(lines), title="Krillion settings")
