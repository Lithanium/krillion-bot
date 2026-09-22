"""Matplotlib base for the tle-gf style dashboards, plus the rating graph.

Everything here draws on an explicit :class:`Figure` with the Agg canvas, so
rendering is safe to run off the event loop and never touches pyplot state.
Player names are drawn in their rank colour; :func:`safe_name` strips what the
Agg text renderer cannot shape (control characters, colour emoji).
"""

from __future__ import annotations

import io
import unicodedata
from collections.abc import Sequence
from datetime import timedelta

import matplotlib
from matplotlib import dates as mdates
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .models import RatingEntry
from .puzzle import PuzzleCalendar
from .rating import RANKS, rank_for_rating

matplotlib.use("Agg")

BG = "#F4F6FA"
PANEL = "#FFFFFF"
TEXT = "#172033"
MUTED = "#667085"
GRID = "#DCE6E1"
RED = "#C63C55"
GREEN = "#16845B"
DARK = "#0C6444"
BLUE = "#356B9E"
AMBER = "#A46100"
LINE_COLORS = ("#5d4dff", "#009ccc", "#00ba6a", "#b99d27", "#cb2aff")
WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
DPI = 100


def hex_color(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def band_color(rgb: tuple[int, int, int]) -> str:
    """Lighten a rank colour into a pastel band."""
    r, g, b = (int(c + (255 - c) * 0.72) for c in rgb)
    return hex_color((r, g, b))


def name_color(rating: float | None) -> str:
    return hex_color(rank_for_rating(round(rating)).color) if rating is not None else TEXT


def safe_name(value: str) -> str:
    """Single line, no control/format characters or symbols Agg draws as boxes."""
    chars = []
    for ch in str(value):
        category = unicodedata.category(ch)
        if ch.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
        elif category[0] != "C" and category != "So" and ord(ch) < 0x10000:
            chars.append(ch)
    return "".join(chars).strip() or "Player"


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def figure(width: float, height: float) -> Figure:
    fig = Figure(figsize=(width, height), dpi=DPI, facecolor=BG)
    FigureCanvasAgg(fig)
    return fig


def png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    return buf.getvalue()


def style(ax: Axes) -> None:
    ax.set_facecolor(PANEL)
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def panel(fig: Figure, rect: tuple[float, float, float, float], title: str, accent: str) -> Axes:
    ax = fig.add_axes(rect)
    style(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 1.045, title, transform=ax.transAxes, color=TEXT, fontsize=10, weight="bold")
    ax.axvline(0, color=accent, linewidth=5)
    return ax


def kpi_strip(fig: Figure, entries: Sequence[tuple[str, str, str]], accent: str) -> None:
    """One banded row of ``(value, label, colour)`` triples."""
    ax = fig.add_axes((0.04, 0.875, 0.92, 0.05))
    style(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axvline(0, color=accent, linewidth=5)
    width = 1 / max(1, len(entries))
    for i, (value, label, color) in enumerate(entries):
        x = width * i + 0.022
        ax.text(x, 0.5, value, va="center", color=color, fontsize=15, weight="bold")
        ax.text(
            x + 0.022 + 0.011 * len(value),
            0.46,
            label,
            va="center",
            color=MUTED,
            fontsize=8,
            weight="bold",
        )


def empty_note(ax: Axes, text: str) -> None:
    ax.text(0.04, 0.5, text, va="center", color=MUTED, fontsize=9, style="italic")


def draw_names(
    ax: Axes,
    x: float,
    y: float,
    parts: Sequence[tuple[str, str]],
    *,
    fontsize: float = 10,
    weight: str = "normal",
    sep: str = " + ",
) -> None:
    """``parts`` are ``(name, colour)``; each name is drawn in its own colour."""
    renderer = ax.figure.canvas.get_renderer()
    ax_width = ax.get_window_extent(renderer).width
    pieces = []
    for i, (name, color) in enumerate(parts):
        if i:
            pieces.append((sep, MUTED))
        pieces.append((name, color))
    for text, color in pieces:
        t = ax.text(x, y, text, va="center", color=color, fontsize=fontsize, weight=weight)
        x += t.get_window_extent(renderer).width / ax_width


# -- rating graph --------------------------------------------------------------


def rating_chart(
    name: str, entries: Sequence[RatingEntry], calendar: PuzzleCalendar, *, performances: bool
) -> bytes | None:
    """Rating (or per-day performance) over time on the Codeforces rank bands.

    ``None`` when ``performances`` is asked for but every rated day was solo.
    """
    if performances:
        points = [
            (calendar.date_for(e.puzzle_number), e.performance)
            for e in entries
            if e.performance is not None
        ]
    else:
        points = [(calendar.date_for(e.puzzle_number), e.rating_after) for e in entries]
    if not points:
        return None
    days = [d for d, _ in points]
    values = [v for _, v in points]
    fig = figure(9, 4.5)
    ax = fig.add_axes((0.08, 0.14, 0.9, 0.76))
    ax.set_facecolor(PANEL)
    ax.plot(
        days,
        values,
        color=LINE_COLORS[0],
        linestyle="-",
        marker="o",
        markersize=3,
        markerfacecolor="white",
        markeredgewidth=0.5,
        zorder=3,
    )
    lo = min(min(values) - 50, 1100)
    hi = max(max(values) + 50, 1500)
    ax.set_ylim(lo, hi)
    for rank in RANKS:
        ax.axhspan(rank.low, rank.high, facecolor=band_color(rank.color), alpha=0.8, zorder=0)
    pad = timedelta(days=3 if len(days) == 1 else 0)
    ax.set_xlim(days[0] - pad, days[-1] + pad)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.grid(axis="x", color=PANEL, linewidth=0.5)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    current = entries[-1].rating_after
    what = "performance" if performances else "rating"
    ax.set_title(
        f"{safe_name(name)} ({round(current)})  ·  Krillion {what}",
        loc="left",
        color=name_color(current),
        fontsize=10,
        weight="bold",
    )
    return png(fig)
