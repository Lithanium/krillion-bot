"""Text and table views for the stats-style commands (no Discord objects)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from .analytics import (
    WEEKDAYS,
    Streaks,
    Summary,
    TopEntry,
    VsOutcome,
    WeekRecap,
)
from .formatting import Cell, Table, signed
from .models import RatingEntry
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

HISTORY_PAGE = 15


def name_of(names: Names, user_id: int) -> str:
    return names.get(user_id, f"<@{user_id}>")


def _num(value: float | None, digits: int = 0) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def stats_text(name: str, s: Summary, opted_out: bool = False) -> str:
    lines = [f"**{name}** 🦐"]
    if s.rating is not None:
        rank = rank_for_rating(round(s.rating))
        peak = f", peak {round(s.peak)}" if s.peak is not None else ""
        lines.append(
            f"Rating **{round(s.rating)}** ({rank.title}{peak}) · "
            f"{s.rated_games} rated day{'s' if s.rated_games != 1 else ''}"
            + (f" · last {signed(s.last_delta)}" if s.last_delta is not None else "")
        )
    else:
        lines.append("Unrated — no closed day yet")
    wins = f"{s.wins} win{'s' if s.wins != 1 else ''}"
    if s.tied_wins:
        wins += f" (+{s.tied_wins} shared)"
    lines.append(
        f"{s.games} played · {wins} · Best {_num(s.best)} · Average {_num(s.average)} · "
        f"Median {_num(s.median)}"
    )
    lines.append(
        f"Streak {s.streak.current} (longest {s.streak.longest}) · "
        f"Perfect 700s: {s.perfect_days} (streak {s.perfect_streak.current}, "
        f"longest {s.perfect_streak.longest})"
    )
    if s.best_performance is not None:
        lines.append(
            f"Performance: last {_num(s.last_performance)} · best {_num(s.best_performance)}"
        )
    if s.tier_counts:
        tiers = " ".join(f"{emoji}×{n}" for emoji, n in s.tier_counts.most_common())
        lines.append(f"Rounds: {tiers}")
    if s.weekday_average:
        days = " · ".join(f"{WEEKDAYS[d]} {avg:.0f}" for d, avg in s.weekday_average.items())
        lines.append(f"By weekday: {days}")
    if opted_out:
        lines.append("_Hidden from public ratings boards (opted out)._")
    return "\n".join(lines)


def streak_text(name: str, play: Streaks, perfect: Streaks) -> str:
    return (
        f"**{name}** 🦐\n"
        f"Play streak: **{play.current}** day{'s' if play.current != 1 else ''} "
        f"(longest {play.longest})\n"
        f"Perfect-700 streak: **{perfect.current}** (longest {perfect.longest})"
    )


def skips_text(
    name: str, first: int | None, skipped: Sequence[int], calendar: PuzzleCalendar
) -> str:
    if first is None:
        return f"**{name}** hasn't shared a Krillion result yet. 🫧"
    if not skipped:
        return f"**{name}** has played every Krillion since #{first} — no skips! 🦐"
    shown = ", ".join(f"#{n} ({calendar.date_for(n):%a %d %b})" for n in skipped[:20])
    more = f" … and {len(skipped) - 20} more" if len(skipped) > 20 else ""
    return (
        f"**{name}** has skipped **{len(skipped)}** Krillion{'s' if len(skipped) != 1 else ''} "
        f"since #{first}:\n{shown}{more}"
    )


def top_table(entries: Sequence[TopEntry], names: Names, label: str, count_ties: bool) -> Table:
    rows = []
    place = 0
    previous: tuple[int, int] | None = None
    for idx, e in enumerate(entries, start=1):
        key = (e.total, e.solo) if count_ties else (e.solo, e.tied)
        if key != previous:
            place = idx
            previous = key
        rows.append(
            (
                Cell(str(place)),
                Cell(name_of(names, e.user_id)),
                Cell(str(e.solo)),
                Cell(str(e.tied)),
                Cell(str(e.total)),
            )
        )
    notes = ["_Ranked by wins including shared days._" if count_ties else "_Outright wins first._"]
    return Table(
        f"Krillion Winners — {label}",
        ("#", "Name", "Wins", "Shared", "Total"),
        rows,
        frozenset({0, 2, 3, 4}),
        notes,
    )


def vs_text(outcome: VsOutcome, names: Names, label: str, missing_is_loss: bool) -> str:
    lines = [f"**Krillion Head to Head** — {label} 🦐"]
    if len(outcome.players) == 2:
        a, b = outcome.players
        lines += [
            f"**{name_of(names, a.user_id)}**: {a.points:g} points, {a.wins} wins",
            f"**{name_of(names, b.user_id)}**: {b.points:g} points, {b.wins} wins",
            f"Ties: {a.ties}",
        ]
    else:
        place = 0
        previous: float | None = None
        for idx, p in enumerate(outcome.players, start=1):
            if p.points != previous:
                place = idx
                previous = p.points
            lines.append(
                f"`{place:>2}.` **{name_of(names, p.user_id)}** — {p.points:g} points · "
                f"{p.wins}W {p.losses}L {p.ties}T"
            )
        lines.append(f"Comparisons: {outcome.comparisons}")
    lines.append(f"Puzzles: {outcome.puzzles}")
    if missing_is_loss:
        lines.append("_A missing result counts as a loss._")
    return "\n".join(lines)


def history_page(
    name: str, entries: Sequence[RatingEntry], calendar: PuzzleCalendar, page: int
) -> tuple[str, int]:
    """One page of a diver's rating history (newest first) and the page count."""
    pages = max(1, -(-len(entries) // HISTORY_PAGE))
    page = min(max(1, page), pages)
    newest = list(reversed(entries))
    chunk = newest[(page - 1) * HISTORY_PAGE : page * HISTORY_PAGE]
    lines = [f"**{name}** — rating history (page {page}/{pages}) 🦐"]
    for e in chunk:
        perf = f" · perf {round(e.performance)}" if e.performance is not None else ""
        lines.append(
            f"`#{e.puzzle_number:<4}` {calendar.date_for(e.puzzle_number):%Y-%m-%d} · "
            f"{e.score:>3} pts · {e.placement}{_ordinal(e.placement)} · "
            f"{round(e.rating_before)} → **{round(e.rating_after)}** ({signed(e.delta)}){perf}"
        )
    if not chunk:
        lines.append("No rated days yet.")
    return "\n".join(lines), pages


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def rating_text(name: str, s: Summary, games: int) -> str:
    if s.rating is None:
        return f"**{name}** is unrated — no closed day yet. 🫧"
    rank = rank_for_rating(round(s.rating))
    lines = [
        f"**{name}** 🦐",
        f"Rating **{round(s.rating)}** · {rank.title} · peak {_num(s.peak)} · {games} rated days",
    ]
    if s.last_delta is not None:
        lines.append(f"Last change {signed(s.last_delta)}")
    if s.last_performance is not None:
        lines.append(
            f"Performance: last {_num(s.last_performance)} · best {_num(s.best_performance)}"
        )
    return "\n".join(lines)


# -- weekly recap ------------------------------------------------------------


def week_table(recap: WeekRecap, names: Names) -> Table:
    rows = []
    for idx, s in enumerate(recap.standings, start=1):
        wins = str(s.solo_wins) + (f" (+{s.tied_wins})" if s.tied_wins else "")
        rows.append(
            (
                Cell(str(idx)),
                Cell(name_of(names, s.user_id)),
                Cell(str(s.total)),
                Cell(f"{s.average:.0f}"),
                Cell(str(s.best)),
                Cell(str(s.days)),
                Cell(wins),
            )
        )
    state = "so far" if recap.in_progress else "final"
    title = f"Krillion Week of {recap.start:%d %b %Y} — {state}"
    header = ("#", "Name", "Total", "Avg", "Best", "Days", "Wins")
    return Table(title, header, rows, frozenset({0, 2, 3, 4, 5, 6}), [])


def week_text(recap: WeekRecap, names: Names, viewer: int | None = None) -> str:
    lines = [
        f"**Krillion week {recap.start:%d %b} – {recap.end:%d %b %Y}** "
        f"{'(in progress) ' if recap.in_progress else ''}🦐",
        f"{recap.players} diver{'s' if recap.players != 1 else ''} · {recap.results} results",
        "",
        "**Day by day**",
    ]
    for d in recap.days:
        if d.winners is None:
            lines.append(f"`{d.day:%a}` #{d.puzzle_number}: —")
            continue
        who = ", ".join(name_of(names, u) for u in d.winners.winners)
        tie = " (tie)" if d.winners.tied else ""
        lines.append(
            f"`{d.day:%a}` #{d.puzzle_number}: **{who}** {d.winners.score}{tie} · "
            f"{d.winners.participants} divers"
        )
    if recap.highest or recap.most_improved:
        lines += ["", "**Standouts**"]
    if recap.highest:
        uid, score, day = recap.highest
        lines.append(f"Highest score: **{name_of(names, uid)}** {score} on {day:%a}")
    if recap.most_improved:
        uid, gain = recap.most_improved
        lines.append(f"Most improved: **{name_of(names, uid)}** +{gain:.0f} avg vs last week")
    if recap.moves:
        lines += ["", "**Rating movers**"]
        best = recap.moves[:3]
        worst = [m for m in recap.moves[-3:] if m not in best]
        for m in best + list(reversed(worst)):
            lines.append(
                f"{name_of(names, m.user_id)}: {round(m.before)} → {round(m.after)} "
                f"({signed(m.delta)})"
            )
    if viewer is not None:
        mine = next((s for s in recap.standings if s.user_id == viewer), None)
        if mine is not None:
            rank = recap.standings.index(mine) + 1
            lines += [
                "",
                f"**Your week**: #{rank} · {mine.days} days · {mine.total} total · "
                f"avg {mine.average:.0f} · {mine.solo_wins} wins",
            ]
    return "\n".join(lines)


def ratings_title_note(include_inactive: bool, max_inactive: int) -> str | None:
    if include_inactive:
        return None
    return f"_Divers idle for {max_inactive}+ days are hidden; use `inactive: True` to show them._"


def settings_text(
    results_channel: int | None,
    leaderboard_channel: int | None,
    weekly_channel: int | None,
    admins: Sequence[int],
    bans: int,
    opted_out: int,
    current: int,
    today: date,
) -> str:
    def chan(cid: int | None) -> str:
        return f"<#{cid}>" if cid else "_not set_"

    who = ", ".join(f"<@{a}>" for a in admins) or "_none_"
    return (
        f"**Krillion settings** 🦐\n"
        f"Today: Krillion #{current} ({today:%a %d %b %Y})\n"
        f"Results read from: {chan(results_channel)} (empty = every channel)\n"
        f"Daily leaderboard posted to: {chan(leaderboard_channel)} "
        f"(empty = where results were shared)\n"
        f"Weekly recap posted to: {chan(weekly_channel)} (empty = off)\n"
        f"Admins: {who}\n"
        f"Banned: {bans} · Opted out of boards: {opted_out}"
    )
