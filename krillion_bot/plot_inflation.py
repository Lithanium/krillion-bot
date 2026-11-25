"""``/krillion inflation`` chart: score cutoffs per rank performance over time.

Every rank above Newbie gets one line: the lowest score that reached that
rank's performance floor on each puzzle. Puzzles with no qualifying score are
skipped, and lines join straight across the gap. The band from a rank's line
up to the next rank's line (the top rank: up to the maximum score) is shaded in
the rank's colour — the scores that would have performed as that rank.
"""

from __future__ import annotations

import numpy as np
from matplotlib import dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon

from .charts import GREEN, GRID, MUTED, PANEL, figure, hex_color, png
from .parser import MAX_DAY_SCORE
from .puzzle import PuzzleCalendar
from .rating import Rank

FILL_ALPHA = 0.35
MARKER_SIZE = 12


def interpolate(xs: np.ndarray, values: list[float]) -> np.ndarray:
    """``values`` at ``xs`` with ``nan`` gaps linearly interpolated along ``xs``.

    The leading and trailing ``nan`` runs stay empty.
    """
    y = np.asarray(values, dtype=float)
    valid = np.isfinite(y)
    if not valid.any():
        return y
    filled = np.interp(xs, xs[valid], y[valid]).astype(float)
    first = int(np.argmax(valid))
    last = len(valid) - 1 - int(np.argmax(valid[::-1]))
    filled[:first] = np.nan
    filled[last + 1 :] = np.nan
    return filled


def _fill_between(ax, xs: np.ndarray, upper: list[float], lower: list[float], color: str) -> None:
    """Shade between two gappy series, interpolating each across its own gaps.

    Skipping days differ per rank, so each series is first interpolated over
    the shared date grid; the band is then drawn only where both have data.
    """
    up = interpolate(xs, upper)
    down = interpolate(xs, lower)
    both = np.isfinite(up) & np.isfinite(down)
    start: int | None = None
    segments: list[tuple[int, int]] = []
    for i, inside in enumerate(both):
        if inside and start is None:
            start = i
        elif not inside and start is not None:
            segments.append((start, i - 1))
            start = None
    if start is not None:
        segments.append((start, len(both) - 1))
    for first, last in segments:
        part = slice(first, last + 1)
        vertices = list(zip(xs[part], up[part], strict=True)) + list(
            zip(xs[part][::-1], down[part][::-1], strict=True)
        )
        ax.add_patch(
            Polygon(vertices, closed=True, facecolor=color, alpha=FILL_ALPHA, edgecolor="none")
        )


def inflation_plot(cutoffs: dict[Rank, dict[int, int]], calendar: PuzzleCalendar) -> bytes | None:
    """One panel with every rank's cutoff line, ``None`` when no rank has data."""
    ranks = sorted(cutoffs, key=lambda r: r.low)
    if not any(cutoffs[rank] for rank in ranks):
        return None
    puzzles = sorted({n for rank in ranks for n in cutoffs[rank]})
    days = [calendar.date_for(n) for n in puzzles]
    xs = mdates.date2num(days)
    grid = {n: i for i, n in enumerate(puzzles)}

    series: dict[Rank, list[float]] = {}
    for rank in ranks:
        values = [float("nan")] * len(puzzles)
        for n, score in cutoffs[rank].items():
            values[grid[n]] = float(score)
        series[rank] = values

    fig = figure(16, 9)
    ax = fig.add_axes((0.05, 0.09, 0.90, 0.74), facecolor=PANEL)
    fig.text(
        0.05,
        0.945,
        "KRILLION  /  PERFORMANCE INFLATION",
        color=GREEN,
        fontsize=11,
        weight="bold",
    )
    fig.text(
        0.05,
        0.905,
        "Lowest daily score reaching each rank's performance floor  ·  bands are the scores "
        "performing as that rank  ·  lines join across days with no qualifying score",
        color=MUTED,
        fontsize=9,
    )

    ceiling = [float(MAX_DAY_SCORE)] * len(puzzles)
    bounds = [series[rank] for rank in ranks[1:]] + [ceiling]
    for rank, upper in zip(ranks, bounds, strict=True):
        _fill_between(ax, xs, upper, series[rank], hex_color(rank.color))

    for rank in ranks:
        color = hex_color(rank.color)
        values = np.asarray(series[rank])
        observed = np.isfinite(values)
        ax.plot(xs[observed], values[observed], color=color, linewidth=2, zorder=3)
        ax.scatter(xs[observed], values[observed], color=color, s=MARKER_SIZE, zorder=4)

    ax.set_ylim(0, MAX_DAY_SCORE)
    ax.set_yticks(range(0, MAX_DAY_SCORE + 1, 100))
    ax.tick_params(axis="y", colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.xaxis_date()
    locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.tick_params(axis="x", colors=MUTED, labelsize=8, length=0)
    ax.margins(x=0.02)

    handles = [
        Line2D([], [], color=hex_color(rank.color), linewidth=2.5, label=rank.abbr)
        for rank in reversed(ranks)
    ]
    fig.legend(
        handles=handles,
        loc="upper right",
        bbox_to_anchor=(0.95, 0.97),
        ncol=len(handles),
        frameon=False,
        fontsize=8,
        columnspacing=0.9,
        handlelength=1.4,
    )
    fig.text(
        0.05,
        0.025,
        "SCORE OUT OF "
        f"{MAX_DAY_SCORE}  ·  ABBREVIATIONS: "
        + "  ".join(f"{rank.abbr} {rank.title}" for rank in reversed(ranks)),
        color=MUTED,
        fontsize=6.5,
    )
    return png(fig)
