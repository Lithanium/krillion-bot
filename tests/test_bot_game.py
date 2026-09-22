import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from test_bot import FakeMessage
from test_commands import ADMIN, Fake, post, run, share

AEST = ZoneInfo("Australia/Brisbane")
# Krillion #59 is Sat 12 Sept 2026 (NY); #60 is Sunday and closes Monday 14:00 AEST.
DURING_60 = datetime(2026, 9, 14, 9, 30, tzinfo=AEST)
AFTER_60 = datetime(2026, 9, 14, 14, 30, tzinfo=AEST)


class FakeChannel:
    def __init__(self, cid: int, messages=()):
        self.id = cid
        self.mention = f"<#{cid}>"
        self.sent: list = []
        self.messages = list(messages)

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    async def history(self, *, limit: int, oldest_first: bool):
        for m in self.messages[:limit]:
            yield m

    async def fetch_message(self, message_id: int):
        return next(m for m in self.messages if m.id == message_id)


def wire(bot, monkeypatch, channel: FakeChannel):
    async def messageable(channel_id: int):
        return channel if channel_id == channel.id else None

    monkeypatch.setattr(bot, "_messageable", messageable)


def test_banned_message_gets_reaction(bot):
    bot.service.storage.ban(1, 1, banned_by=ADMIN, reason=None, at=FakeMessage("x").created_at)
    msg = FakeMessage(share(58, 340))
    asyncio.run(bot.on_message(msg))
    assert msg.reactions == ["🚫"] and msg.replies == []
    assert bot.service.storage.get_result(1, 58, 1) is None


def test_results_channel_setting_overrides_env(bot):
    bot.service.storage.set_setting(1, "results_channel", "11")
    asyncio.run(bot.on_message(FakeMessage(share(58, 340), channel_id=10)))
    assert bot.service.storage.get_result(1, 58, 1) is None
    asyncio.run(bot.on_message(FakeMessage(share(58, 340), channel_id=11)))
    assert bot.service.storage.get_result(1, 58, 1).score == 340


def test_sunday_close_posts_weekly_recap(bot, monkeypatch):
    monkeypatch.setattr("krillion_bot.bot._now", lambda: AFTER_60)
    channel = FakeChannel(10)
    wire(bot, monkeypatch, channel)
    post(bot, 1, "alice", share(60, 700), DURING_60)
    post(bot, 2, "bob", share(60, 200), DURING_60)

    async def close_day():
        for day in bot.service.finalize_due(AFTER_60):
            await bot._announce(day)

    asyncio.run(close_day())
    assert len(channel.sent) == 1  # daily board only: no weekly channel configured

    bot.service.storage.set_setting(1, "weekly_channel", "10")
    asyncio.run(bot._announce_week(1, bot.service.calendar.date_for(60)))
    content, kwargs = channel.sent[-1]
    assert content is None
    assert kwargs["file"].filename == "krillion-week-2026-09-07.png"


def test_weekly_recap_skips_empty_week(bot, monkeypatch):
    channel = FakeChannel(10)
    wire(bot, monkeypatch, channel)
    bot.service.storage.set_setting(1, "weekly_channel", "10")
    asyncio.run(bot._announce_week(1, bot.service.calendar.date_for(60)))
    assert channel.sent == []


def test_import_channel_backfills_and_rates(bot, monkeypatch):
    monkeypatch.setattr("krillion_bot.bot._now", lambda: DURING_60)
    two_days = DURING_60 - timedelta(days=2)
    author = lambda uid, name: SimpleNamespace(id=uid, display_name=name, bot=False)  # noqa: E731
    messages = [
        SimpleNamespace(id=3, author=author(1, "alice"), content="gg", created_at=DURING_60),
        SimpleNamespace(
            id=2, author=author(1, "alice"), content=share(58, 640), created_at=two_days
        ),
        SimpleNamespace(id=1, author=author(2, "bob"), content=share(58, 100), created_at=two_days),
        SimpleNamespace(
            id=0,
            author=SimpleNamespace(id=9, bot=True, display_name="k"),
            content=share(58, 700),
            created_at=two_days,
        ),  # fmt: skip
    ]
    channel = FakeChannel(10, messages)
    a = Fake(ADMIN, name="admin")
    run(bot, "krillion admin import", a, channel, 100)
    assert a.deferred
    assert "Imported 2 new result(s)" in a.text and "1 closed day" in a.text
    assert bot.service.storage.is_finalized(1, 58)
    assert bot.service.storage.get_player(1, 1).rating > bot.service.storage.get_player(1, 2).rating


def test_reparse_corrects_edited_shares(bot, monkeypatch):
    monkeypatch.setattr("krillion_bot.bot._now", lambda: DURING_60)
    two_days = DURING_60 - timedelta(days=2)
    msg = FakeMessage(share(58, 100), author_id=1, id=5, created_at=two_days)
    asyncio.run(bot.on_message(msg))
    asyncio.run(bot.on_message(FakeMessage(share(58, 300), author_id=2, id=6, created_at=two_days)))
    bot.service.finalize_due(DURING_60)
    assert bot.service.storage.get_player(1, 2).rating > 1200
    msg.content = share(58, 640)  # the diver fixed their share afterwards
    channel = FakeChannel(10, [msg, SimpleNamespace(id=6, content=share(58, 300))])
    wire(bot, monkeypatch, channel)
    a = Fake(ADMIN, name="admin")
    run(bot, "krillion admin reparse", a, 58)
    assert "1 result(s) changed" in a.text and "1 closed day" in a.text
    assert bot.service.storage.get_result(1, 58, 1).score == 640
    assert bot.service.storage.get_player(1, 1).rating > bot.service.storage.get_player(1, 2).rating
