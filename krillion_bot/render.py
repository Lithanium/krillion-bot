"""Render a leaderboard :class:`Board` as a PNG table.

Needs Pillow plus two fonts: a regular text font (DejaVu Sans, or Pillow's
bundled fallback) and Noto Color Emoji for the result rows. Without the emoji
font :func:`render_board` returns ``None`` and callers fall back to text.
"""

from __future__ import annotations

import io
import logging
import re
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .formatting import Board, signed

log = logging.getLogger(__name__)

_FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
EMOJI_FONT_PATHS = (
    _FONT_DIR / "NotoColorEmoji.ttf",
    Path("/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
)
TEXT_FONT_PATHS = {
    "regular": (
        _FONT_DIR / "DejaVuSans.ttf",
        Path("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ),
    "bold": (
        _FONT_DIR / "DejaVuSans-Bold.ttf",
        Path("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
}
# Noto Color Emoji is a bitmap (CBDT) font shipped at exactly this pixel size.
_EMOJI_NATIVE = 109

FONT = 22
EMOJI = 26
PAD = 18
GAP = 26
ROW_H = 44
HEADER_H = 40
TITLE_H = 54

BG = (30, 31, 34)
ROW_A = (43, 45, 49)
ROW_B = (49, 51, 56)
TEXT = (242, 243, 245)
MUTED = (148, 155, 164)
HEADER = (181, 186, 193)
GREEN = (87, 242, 135)
RED = (237, 66, 69)
RANK = {1: (241, 196, 15), 2: (185, 187, 190), 3: (205, 127, 50)}

_MARKDOWN = re.compile(r"[*_`]")


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


@cache
def _text_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    path = _first_existing(TEXT_FONT_PATHS[style])
    if path is not None:
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


@cache
def _emoji_font() -> ImageFont.FreeTypeFont | None:
    path = _first_existing(EMOJI_FONT_PATHS)
    if path is None:
        log.warning("No Noto Color Emoji font found; leaderboard images disabled")
        return None
    return ImageFont.truetype(str(path), _EMOJI_NATIVE)


def _emoji_strip(text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Render ``text`` with the bitmap emoji font, scaled down to ``EMOJI`` px tall."""
    left, top, right, bottom = font.getbbox(text)
    canvas = Image.new("RGBA", (max(right, 1), max(bottom, 1)), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((0, 0), text, font=font, embedded_color=True)
    scale = EMOJI / _EMOJI_NATIVE
    size = (max(1, round(right * scale)), max(1, round(bottom * scale)))
    return canvas.resize(size, Image.Resampling.LANCZOS)


def _plain(note: str) -> str:
    return _MARKDOWN.sub("", note)


def render_board(board: Board) -> bytes | None:
    """PNG bytes for ``board``, or ``None`` if the emoji font is unavailable."""
    emoji_font = _emoji_font()
    if emoji_font is None:
        return None
    bold = _text_font("bold", FONT)
    small = _text_font("regular", FONT - 5)
    title_font = _text_font("bold", FONT + 4)

    rows = board.rows
    strips = {i: _emoji_strip(r.tiers, emoji_font) for i, r in enumerate(rows) if r.tiers}
    notes = [_plain(n) for n in board.notes if "<t:" not in n]

    def width(font: ImageFont.FreeTypeFont, text: str) -> int:
        return int(font.getlength(text))

    col_rank = max(width(bold, "#"), *(width(bold, str(r.place)) for r in rows))
    col_name = max(
        width(bold, "Name"),
        *(width(bold, r.name) + width(small, f"  ({r.rating})") for r in rows),
    )
    col_result = max(width(bold, "Result"), *(s.width for s in strips.values()), 0)
    col_score = max(width(bold, "Score"), *(width(bold, str(r.score)) for r in rows))
    col_delta = max(width(bold, "Δ"), *(width(bold, signed(r.delta)) for r in rows))
    columns = [col_rank, col_name, col_result, col_score, col_delta]

    table_w = sum(columns) + GAP * (len(columns) - 1)
    img_w = max(table_w, width(title_font, board.title), *(width(small, n) for n in notes), 0)
    img_w += PAD * 2
    notes_h = (FONT + 6) * len(notes) + (PAD // 2 if notes else 0)
    img_h = TITLE_H + HEADER_H + ROW_H * len(rows) + notes_h + PAD

    img = Image.new("RGB", (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    draw.text((PAD, (TITLE_H - FONT - 4) // 2), board.title, font=title_font, fill=TEXT)

    x_rank = PAD
    x_name = x_rank + col_rank + GAP
    x_result = x_name + col_name + GAP
    x_score = x_result + col_result + GAP
    x_delta = x_score + col_score + GAP
    right_score = x_score + col_score
    right_delta = x_delta + col_delta

    y = TITLE_H
    draw.rectangle((0, y, img_w, y + HEADER_H), fill=ROW_A)
    ty = y + (HEADER_H - FONT) // 2 - 2
    draw.text((x_rank, ty), "#", font=bold, fill=HEADER)
    draw.text((x_name, ty), "Name", font=bold, fill=HEADER)
    if col_result:
        draw.text((x_result, ty), "Result", font=bold, fill=HEADER)
    draw.text((right_score, ty), "Score", font=bold, fill=HEADER, anchor="ra")
    draw.text((right_delta, ty), "Δ", font=bold, fill=HEADER, anchor="ra")
    y += HEADER_H

    for i, r in enumerate(rows):
        draw.rectangle((0, y, img_w, y + ROW_H), fill=ROW_B if i % 2 == 0 else ROW_A)
        ty = y + (ROW_H - FONT) // 2 - 2
        draw.text((x_rank, ty), str(r.place), font=bold, fill=RANK.get(r.place, MUTED))
        draw.text((x_name, ty), r.name, font=bold, fill=TEXT)
        draw.text((x_name + width(bold, r.name), ty + 3), f"  ({r.rating})", font=small, fill=MUTED)
        strip = strips.get(i)
        if strip is not None:
            img.paste(strip, (x_result, y + (ROW_H - strip.height) // 2), strip)
        draw.text((right_score, ty), str(r.score), font=bold, fill=TEXT, anchor="ra")
        delta = round(r.delta)
        colour = GREEN if delta > 0 else RED if delta < 0 else MUTED
        draw.text((right_delta, ty), signed(r.delta), font=bold, fill=colour, anchor="ra")
        y += ROW_H

    y += PAD // 2
    for note in notes:
        draw.text((PAD, y), note, font=small, fill=MUTED)
        y += FONT + 6

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
