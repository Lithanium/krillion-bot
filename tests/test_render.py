import asyncio
from pathlib import Path

import pytest
from test_bot import NOW, FakeInteraction, FakeMessage, run_command

import krillion_bot.render as render
from krillion_bot.formatting import Board, Row
from krillion_bot.render import render_board

BOARD = Board(
    "Krillion #58 — live",
    [
        Row(1, "alice", "1200?", "🦑🦑🦑🦑🦑🐟🫧", 340, 16.0),
        Row(2, "bob", "1200?", "🫧🫧🐟🫧🫧🤡⬛", 120, -16.0),
        Row(3, "carol", "1200?", "", 0, -32.0),
    ],
    ["_? = provisional rating._", "_Closes <t:1800000000:R>._"],
)

HAVE_EMOJI_FONT = any(p.is_file() for p in render.EMOJI_FONT_PATHS)


@pytest.fixture(autouse=True)
def clear_font_cache():
    render._emoji_font.cache_clear()
    yield
    render._emoji_font.cache_clear()


def test_render_without_emoji_font_returns_none(monkeypatch):
    monkeypatch.setattr(render, "EMOJI_FONT_PATHS", (Path("/nonexistent/NotoColorEmoji.ttf"),))
    assert render_board(BOARD) is None


@pytest.mark.skipif(not HAVE_EMOJI_FONT, reason="Noto Color Emoji font not installed")
def test_render_produces_png():
    png = render_board(BOARD)
    assert png is not None and png.startswith(b"\x89PNG\r\n\x1a\n")


def test_leaderboard_command_falls_back_to_text(bot, monkeypatch):
    monkeypatch.setattr(render, "EMOJI_FONT_PATHS", ())
    monkeypatch.setattr("krillion_bot.bot._now", lambda: NOW)
    asyncio.run(bot.on_message(FakeMessage("Krillion #58 🦐\n340\n\n🦑🦑🦑🦑🦑🐟🫧")))
    interaction = FakeInteraction(user_id=1)
    run_command(bot, "leaderboard", interaction, None)
    (text, _ephemeral), *_ = interaction.sent
    assert "Krillion #58 — live" in text
    assert "🥇 **alice** (1200?)  🦑🦑🦑🦑🦑🐟🫧  **340**  +0" in text
    assert "<t:" in text


@pytest.mark.skipif(not HAVE_EMOJI_FONT, reason="Noto Color Emoji font not installed")
def test_leaderboard_command_sends_image(bot, monkeypatch):
    monkeypatch.setattr("krillion_bot.bot._now", lambda: NOW)
    asyncio.run(bot.on_message(FakeMessage("Krillion #58 🦐\n340\n\n🦑🦑🦑🦑🦑🐟🫧")))
    sent = {}

    async def capture(content=None, **kwargs):
        sent.update(kwargs, content=content)

    interaction = FakeInteraction(user_id=1)
    interaction.response.send_message = capture
    run_command(bot, "leaderboard", interaction, None)
    assert sent["file"].filename == "krillion-58-live.png"
    assert sent["content"].startswith("_Projected rating changes; closes <t:")


def test_leaderboard_command_empty_day(bot, monkeypatch):
    monkeypatch.setattr("krillion_bot.bot._now", lambda: NOW)
    interaction = FakeInteraction(user_id=1)
    run_command(bot, "leaderboard", interaction, None)
    assert interaction.sent == [("**Krillion #58** — no results yet. 🫧", False)]
