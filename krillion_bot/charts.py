"""Rating graph in the Codeforces style, drawn with Pillow.

Rank bands are shaded behind a line of the diver's rating after each rated day;
with ``performances`` each day's event performance is drawn as a small dot.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

from PIL import Image, ImageDraw

from .models import RatingEntry
from .rating import RANKS
from .render import FRAME, SMOKE, _text_font

WIDTH, HEIGHT = 900, 420
PAD_L, PAD_R, PAD_T, PAD_B = 60, 20, 50, 40
LINE = (30, 30, 30)
DOT = (200, 40, 40)
GRID = (255, 255, 255)


def _band_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Lighten the rank's text colour into a pastel background."""
    r, g, b = (int(c + (255 - c) * 0.72) for c in color)
    return (r, g, b)


def rating_chart(
    title: str, entries: Sequence[RatingEntry], *, performances: bool = False
) -> bytes | None:
    if len(entries) < 2:
        return None
    ratings = [e.rating_after for e in entries]
    values = list(ratings)
    if performances:
        values += [e.performance for e in entries if e.performance is not None]
    lo = min(values) - 40
    hi = max(values) + 40
    lo = min(lo, 1150)
    hi = max(hi, 1250)
    plot_w = WIDTH - PAD_L - PAD_R
    plot_h = HEIGHT - PAD_T - PAD_B
    n = len(entries)

    def x_at(i: int) -> float:
        return PAD_L + (plot_w * i / (n - 1))

    def y_at(v: float) -> float:
        return PAD_T + plot_h * (hi - v) / (hi - lo)

    img = Image.new("RGB", (WIDTH, HEIGHT), FRAME)
    draw = ImageDraw.Draw(img)
    for rank in RANKS:
        top, bottom = min(rank.high, hi), max(rank.low, lo)
        if top <= bottom:
            continue
        draw.rectangle(
            (PAD_L, y_at(top), WIDTH - PAD_R, y_at(bottom)), fill=_band_color(rank.color)
        )
    small = _text_font("regular", 13)
    step = 100 if hi - lo > 300 else 50
    tick = int(lo // step + 1) * step
    while tick < hi:
        y = y_at(tick)
        draw.line((PAD_L, y, WIDTH - PAD_R, y), fill=GRID, width=1)
        draw.text((8, y - 7), str(tick), font=small, fill=SMOKE)
        tick += step
    if performances:
        for i, e in enumerate(entries):
            if e.performance is not None:
                x, y = x_at(i), y_at(e.performance)
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=DOT)
    points = [(x_at(i), y_at(r)) for i, r in enumerate(ratings)]
    draw.line(points, fill=LINE, width=2, joint="curve")
    for x, y in points:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=LINE, outline=SMOKE)
    bold = _text_font("bold", 18)
    draw.text((PAD_L, 14), title, font=bold, fill=SMOKE)
    first, last = entries[0].puzzle_number, entries[-1].puzzle_number
    draw.text((PAD_L, HEIGHT - PAD_B + 10), f"#{first}", font=small, fill=SMOKE)
    label = f"#{last}"
    draw.text(
        (WIDTH - PAD_R - small.getlength(label), HEIGHT - PAD_B + 10), label, font=small, fill=SMOKE
    )
    if performances:
        draw.text(
            (PAD_L + 80, HEIGHT - PAD_B + 10),
            "line: rating · dots: daily performance",
            font=small,
            fill=SMOKE,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
