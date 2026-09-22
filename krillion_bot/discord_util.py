"""Small Discord-facing helpers shared by the bot and its command modules."""

from __future__ import annotations

import io
import logging
from datetime import date, datetime, timezone
from typing import Any

import discord

from .formatting import Table
from .puzzle import PuzzleCalendar
from .render import render_table

log = logging.getLogger(__name__)

SERVER_ONLY = "Use this in a server."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def board_message(table: Table, filename: str) -> dict[str, Any]:
    """kwargs for ``send``: the table as a PNG attachment, or as text if that fails.

    Notes carrying a Discord timestamp can't go in the image, so they stay as text.
    """
    try:
        png = render_table(table)
    except Exception:
        log.exception("Rendering leaderboard image failed; sending text")
        png = None
    if png is None:
        return {"content": table.text()}
    timed = [n for n in table.notes if "<t:" in n]
    return {
        "content": "\n".join(timed) or None,
        "file": discord.File(io.BytesIO(png), filename=filename),
    }


def png_file(png: bytes, filename: str) -> discord.File:
    return discord.File(io.BytesIO(png), filename=filename)


def resolve_puzzle(
    calendar: PuzzleCalendar, now: datetime, puzzle: int | None, day: str | None
) -> tuple[int | None, str | None]:
    """Turn a ``puzzle`` number or ``YYYY-MM-DD`` ``day`` into a puzzle number.

    Returns ``(number, error)``; with neither given, today's puzzle.
    """
    if puzzle is not None and day is not None:
        return None, "Give either a puzzle number or a date, not both."
    if day is not None:
        try:
            parsed = date.fromisoformat(day)
        except ValueError:
            return None, f"`{day}` is not a date (`YYYY-MM-DD`)."
        return calendar.number_for_date(parsed), None
    if puzzle is not None:
        if puzzle < 1:
            return None, "Puzzle numbers start at 1."
        return puzzle, None
    return calendar.current(now), None


async def reply(interaction: discord.Interaction, content: str, *, ephemeral: bool = False) -> None:
    await interaction.response.send_message(content, ephemeral=ephemeral)
