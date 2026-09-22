"""Seven-day player dashboard for ``/krillion stats``."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import date, timedelta

from matplotlib import dates as mdates
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.offsetbox import AnnotationBbox, OffsetImage

from .analytics import Summary
from .charts import (
    AMBER,
    BG,
    BLUE,
    DARK,
    GREEN,
    GRID,
    MUTED,
    PANEL,
    RED,
    TEXT,
    WEEKDAYS,
    figure,
    name_color,
    png,
    safe_name,
    style,
)
from .models import Result
from .parser import MAX_DAY_SCORE
from .puzzle import PuzzleCalendar
from .rating import rank_for_rating
from .render import emoji_font, emoji_strip

TREND_POINTS = 35


def _kpi(fig: Figure, x: float, label: str, value: str, detail: str, color: str) -> None:
    ax = fig.add_axes((x, 0.745, 0.215, 0.115))
    style(ax)
    ax.text(0.06, 0.77, label, transform=ax.transAxes, color=MUTED, fontsize=8, weight="bold")
    ax.text(0.06, 0.42, value, transform=ax.transAxes, color=color, fontsize=20, weight="bold")
    ax.text(0.06, 0.12, detail, transform=ax.transAxes, color=TEXT, fontsize=8)
    ax.axvline(0, color=color, linewidth=5)


def _day_status(score: int | None, day: date, today: date) -> tuple[str, str]:
    if score is not None:
        if score == MAX_DAY_SCORE:
            return "PERFECT", GREEN
        return f"{score} PTS", AMBER
    if day > today:
        return "UP NEXT", MUTED
    if day == today:
        return "OPEN", BLUE
    return "MISSED", RED


def _week_strip(fig: Figure, scores: dict[date, int], week: Sequence[date], today: date) -> None:
    for i, day in enumerate(week):
        ax = fig.add_axes((0.04 + i * 0.132, 0.535, 0.118, 0.145))
        style(ax)
        score = scores.get(day)
        status, color = _day_status(score, day, today)
        ax.axhline(1, color=color, linewidth=5)
        ax.text(
            0.08, 0.78, WEEKDAYS[i], transform=ax.transAxes, color=TEXT, fontsize=9, weight="bold"
        )
        ax.text(
            0.92, 0.78, f"{day:%d}", transform=ax.transAxes, color=MUTED, fontsize=8, ha="right"
        )
        ax.text(
            0.08,
            0.43,
            "—" if score is None else str(score),
            transform=ax.transAxes,
            color=color if score is not None else MUTED,
            fontsize=14,
            weight="bold",
        )
        ax.text(0.08, 0.12, status, transform=ax.transAxes, color=color, fontsize=7, weight="bold")


def _trend(fig: Figure, rows: Sequence[Result], calendar: PuzzleCalendar) -> None:
    ax = fig.add_axes((0.04, 0.09, 0.575, 0.375))
    style(ax)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    recent = rows[-TREND_POINTS:]
    perfect = [r for r in recent if r.score == MAX_DAY_SCORE]
    other = [r for r in recent if r.score != MAX_DAY_SCORE]
    if perfect:
        ax.scatter(
            [calendar.date_for(r.puzzle_number) for r in perfect],
            [r.score for r in perfect],
            color=GREEN,
            s=34,
            alpha=0.92,
            edgecolors=PANEL,
            linewidths=0.6,
            label="Perfect",
            zorder=4,
        )
    if other:
        ax.scatter(
            [calendar.date_for(r.puzzle_number) for r in other],
            [r.score for r in other],
            color=AMBER,
            marker="x",
            s=34,
            linewidths=1.2,
            label="Score",
            zorder=3,
        )
    if len(recent) >= 3:
        window = min(7, max(3, len(recent) // 3))
        scores = [r.score for r in recent]
        rolling = [
            statistics.fmean(scores[i - window + 1 : i + 1]) for i in range(window - 1, len(scores))
        ]
        ax.plot(
            [calendar.date_for(r.puzzle_number) for r in recent[window - 1 :]],
            rolling,
            color=DARK,
            linewidth=2.2,
            label=f"{window}-day average",
            zorder=5,
        )
    else:
        ax.text(
            0.5, 0.88, "A few more days unlock the average line", transform=ax.transAxes,
            color=MUTED, fontsize=8, ha="center",
        )  # fmt: skip
    ax.set_ylim(0, MAX_DAY_SCORE * 1.1)
    ax.set_yticks(range(0, MAX_DAY_SCORE + 1, 100))
    ax.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.8)
    first = calendar.date_for(recent[0].puzzle_number)
    last = calendar.date_for(recent[-1].puzzle_number)
    pad = timedelta(days=3 if first == last else 0)
    ax.set_xlim(first - pad, last + pad)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.set_ylabel("SCORE  ·  HIGHER ↑", color=MUTED, fontsize=8, weight="bold")
    ax.set_title(
        f"SCORE TREND  ·  LAST {len(recent)} RESULTS", color=TEXT, fontsize=10, weight="bold",
        loc="left", pad=13,
    )  # fmt: skip
    legend = ax.legend(loc="lower right", frameon=False, fontsize=8)
    for text in legend.get_texts():
        text.set_color(MUTED)


def _weekday_dna(
    fig: Figure, summary: Summary, rows: Sequence[Result], calendar: PuzzleCalendar
) -> None:
    ax = fig.add_axes((0.66, 0.09, 0.30, 0.375))
    style(ax)
    counts = [0] * 7
    for r in rows:
        counts[calendar.date_for(r.puzzle_number).weekday()] += 1
    averages = [summary.weekday_average.get(d) for d in range(7)]
    strengths = [max(0.025, a / MAX_DAY_SCORE) if a is not None else 0 for a in averages]
    colors = [
        GREEN if a is not None and a >= 600 else BLUE if a is not None and a >= 400 else AMBER
        for a in averages
    ]
    bars = ax.barh(range(7), strengths, height=0.57, color=colors)
    ax.set_yticks(range(7))
    ax.set_yticklabels(WEEKDAYS, color=TEXT, fontsize=8, weight="bold")
    ax.tick_params(length=0)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.43)
    for bar, avg, n, strength in zip(bars, averages, counts, strengths, strict=True):
        y = bar.get_y() + bar.get_height() / 2
        if avg is None:
            ax.text(0.04, y, "NO DATA", va="center", color=MUTED, fontsize=7)
            continue
        ax.text(
            0.04, y, f"AVG {avg:.0f}", va="center", fontsize=7, weight="bold",
            color=PANEL if strength >= 0.39 else TEXT,
        )  # fmt: skip
        ax.text(1.40, y, f"{n} PLAYED", va="center", ha="right", color=TEXT, fontsize=7)
    ax.set_title(
        "DAY DNA  ·  AVERAGE BY WEEKDAY", color=TEXT, fontsize=10, weight="bold", loc="left", pad=13
    )


def _tier_footer(fig: Figure, ax: Axes, summary: Summary) -> None:
    """Tier-emoji tallies drawn with the colour-emoji font (skipped without it)."""
    font = emoji_font()
    if font is None or not summary.tier_counts:
        return
    x = 0.42
    for emoji, count in summary.tier_counts.most_common():
        strip = emoji_strip(emoji, font)
        box = OffsetImage(strip, zoom=0.5)
        ax.add_artist(
            AnnotationBbox(
                box, (x, 0.5), xycoords=ax.transAxes, frameon=False, pad=0, box_alignment=(0, 0.5)
            )
        )
        ax.text(
            x + 0.024, 0.5, f"×{count}", transform=ax.transAxes, va="center", color=TEXT, fontsize=9
        )
        x += 0.065


def stats_plot(
    name: str, summary: Summary, rows: Sequence[Result], calendar: PuzzleCalendar, today: date
) -> bytes:
    """``rows`` are the diver's own results, oldest first (at least one)."""
    fig = figure(16, 10)
    header = fig.add_axes((0.04, 0.89, 0.92, 0.075))
    header.set_facecolor(BG)
    header.axis("off")
    header.text(
        0, 0.72, "KRILLION  /  7-DAY PLAYER DASHBOARD", color=GREEN, fontsize=10, weight="bold"
    )
    header.text(
        0, 0.08, safe_name(name), color=name_color(summary.rating), fontsize=24, weight="bold"
    )
    week_start = today - timedelta(days=today.weekday())
    header.text(
        1, 0.18, f"LATEST WEEK  ·  {week_start:%b %d, %Y}", color=MUTED, fontsize=9, weight="bold",
        ha="right",
    )  # fmt: skip

    if summary.rating is not None:
        rating = f"{round(summary.rating)} ({rank_for_rating(round(summary.rating)).abbr})"
        peak = round(summary.peak) if summary.peak is not None else round(summary.rating)
        delta = summary.last_delta or 0.0
        rating_detail = f"peak {peak} · last {delta:+.0f}"
    else:
        rating, rating_detail = "unrated", "finish a contested day"
    _kpi(fig, 0.04, "RATING", rating, rating_detail, name_color(summary.rating))
    first = calendar.date_for(rows[0].puzzle_number)
    _kpi(
        fig, 0.275, "DAYS PLAYED", str(summary.games),
        f"since {first:%b %d, %Y} · {summary.wins} wins · {summary.tied_wins} tied", BLUE,
    )  # fmt: skip
    _kpi(
        fig, 0.51, "BEST SCORE", str(summary.best),
        f"avg {summary.average:.0f} · median {summary.median:.0f} · {summary.perfect_days} perfect",
        GREEN,
    )  # fmt: skip
    _kpi(
        fig, 0.745, "STREAK", str(summary.streak.current),
        f"longest {summary.streak.longest} · perfect {summary.perfect_streak.current}"
        f" (best {summary.perfect_streak.longest})",
        RED,
    )  # fmt: skip

    week = [week_start + timedelta(days=i) for i in range(7)]
    scores = {calendar.date_for(r.puzzle_number): r.score for r in rows}
    played = [d for d in week if d in scores]
    week_summary = f"{len(played)}/{sum(1 for d in week if d <= today)} PLAYED"
    if played:
        week_summary += (
            f"  ·  {sum(scores[d] for d in played)} PTS  ·  {max(scores[d] for d in played)} BEST"
        )
    fig.text(0.04, 0.695, week_summary, color=TEXT, fontsize=9, weight="bold")
    _week_strip(fig, scores, week, today)
    _trend(fig, rows, calendar)
    _weekday_dna(fig, summary, rows, calendar)
    footer = fig.add_axes((0.04, 0.02, 0.92, 0.035))
    footer.set_facecolor(BG)
    footer.axis("off")
    footer.text(
        0, 0.5, "PERFECT DAYS SCORE 700  ·  WEEK RUNS MONDAY → SUNDAY", transform=footer.transAxes,
        va="center", color=MUTED, fontsize=7, weight="bold",
    )  # fmt: skip
    _tier_footer(fig, footer, summary)
    return png(fig)
