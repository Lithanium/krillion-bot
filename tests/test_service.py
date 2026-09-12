from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from krillion_bot.formatting import daily_leaderboard, elo_leaderboard, live_leaderboard
from krillion_bot.puzzle import PuzzleCalendar
from krillion_bot.service import KrillionService, SubmitStatus
from krillion_bot.storage import Storage

AEST = ZoneInfo("Australia/Brisbane")
GUILD = 1
CHANNEL = 10

# Krillion #58 is live from 11 Sept 2026 14:00 AEST until 12 Sept 14:00 AEST
# (midnight to midnight, New York).
DURING_58 = datetime(2026, 9, 12, 9, 30, tzinfo=AEST)
RESET_59 = datetime(2026, 9, 12, 14, 0, tzinfo=AEST)


def share(n: int, score: int) -> str:
    return f"Krillion #{n} 🦐\n{score}\n\n🦑🦑🦑🦑🦑🐟🫧"


@pytest.fixture
def service() -> KrillionService:
    return KrillionService(Storage(":memory:"), PuzzleCalendar(), grace=timedelta(minutes=10))


def submit(service, user, name, text, now=DURING_58):
    return service.submit(
        guild_id=GUILD,
        user_id=user,
        display_name=name,
        text=text,
        channel_id=CHANNEL,
        message_id=None,
        now=now,
    )


def test_accepts_todays_result(service):
    out = submit(service, 1, "alice", share(58, 340))
    assert out.status is SubmitStatus.ACCEPTED
    assert out.current_puzzle == 58
    stored = service.storage.get_result(GUILD, 58, 1)
    assert stored is not None and stored.score == 340 and stored.tiers == "🦑🦑🦑🦑🦑🐟🫧"
    assert service.storage.get_player(GUILD, 1).rating == 1200


def test_ignores_chatter(service):
    assert submit(service, 1, "alice", "good morning").status is SubmitStatus.NOT_A_RESULT


def test_duplicate_keeps_first(service):
    submit(service, 1, "alice", share(58, 340))
    out = submit(service, 1, "alice", share(58, 600))
    assert out.status is SubmitStatus.DUPLICATE
    assert out.existing.score == 340
    assert service.storage.get_result(GUILD, 58, 1).score == 340


def test_rejects_wrong_day(service):
    assert submit(service, 1, "alice", share(57, 340)).status is SubmitStatus.TOO_LATE
    assert submit(service, 1, "alice", share(59, 340)).status is SubmitStatus.NOT_YET


def test_grace_period_after_reset(service):
    just_after = RESET_59 + timedelta(minutes=5)
    assert submit(service, 1, "alice", share(58, 340), now=just_after).status is (
        SubmitStatus.ACCEPTED
    )
    assert submit(service, 2, "bob", share(59, 200), now=just_after).status is (
        SubmitStatus.ACCEPTED
    )
    too_late = RESET_59 + timedelta(minutes=10)
    assert submit(service, 3, "carol", share(58, 340), now=too_late).status is (
        SubmitStatus.TOO_LATE
    )


def test_nothing_due_while_day_open(service):
    submit(service, 1, "alice", share(58, 340))
    assert service.finalize_due(RESET_59 + timedelta(minutes=9)) == []
    assert service.next_finalize_at(DURING_58) == RESET_59 + timedelta(minutes=10)


def test_finalize_applies_elo_and_posts_once(service):
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 120))
    submit(service, 3, "carol", share(58, 120))

    close = RESET_59 + timedelta(minutes=10)
    days = service.finalize_due(close)
    assert len(days) == 1
    day = days[0]
    assert (day.guild_id, day.puzzle_number, day.channel_id) == (GUILD, 58, CHANNEL)
    by_user = {e.user_id: e for e in day.entries}
    assert by_user[1].placement == 1
    assert by_user[2].placement == 2 and by_user[3].placement == 2
    assert by_user[1].delta == pytest.approx(16)
    assert by_user[2].delta == pytest.approx(-8)
    assert by_user[3].delta == pytest.approx(-8)
    assert service.storage.get_player(GUILD, 1).rating == pytest.approx(1216)
    assert service.storage.get_player(GUILD, 2).rating == pytest.approx(1192)

    # Idempotent: a second pass does nothing, and late results are refused.
    assert service.finalize_due(close + timedelta(hours=1)) == []
    assert submit(service, 4, "dave", share(58, 700), now=close).status is SubmitStatus.TOO_LATE


def test_finalizes_missed_days_after_downtime(service):
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 100))
    later = RESET_59 + timedelta(days=1, hours=1)
    submit(service, 1, "alice", share(59, 200), now=RESET_59 + timedelta(hours=2))
    submit(service, 2, "bob", share(59, 250), now=RESET_59 + timedelta(hours=2))
    days = service.finalize_due(later)
    assert [d.puzzle_number for d in days] == [58, 59]
    # alice won #58 (+16) then lost #59 to a slightly lower-rated bob.
    alice = service.storage.get_player(GUILD, 1).rating
    bob = service.storage.get_player(GUILD, 2).rating
    assert alice < 1216 and bob > 1184
    assert alice + bob == pytest.approx(2400)


def test_stats_and_games(service):
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 100))
    service.finalize_due(RESET_59 + timedelta(minutes=10))
    s = service.storage.stats_for(GUILD, 1)
    assert (s.games, s.wins, s.best_score, s.average_score) == (1, 1, 340, 340)
    assert service.storage.games_played(GUILD) == {1: 1, 2: 1}


def test_guilds_are_isolated(service):
    submit(service, 1, "alice", share(58, 340))
    other = service.submit(
        guild_id=2,
        user_id=1,
        display_name="alice",
        text=share(58, 340),
        channel_id=99,
        message_id=None,
        now=DURING_58,
    )
    assert other.status is SubmitStatus.ACCEPTED
    assert service.storage.results_for(2, 58)[0].channel_id == 99


def test_formatting(service):
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 120))
    results = service.storage.results_for(GUILD, 58)
    players = {p.user_id: p for p in service.storage.players(GUILD)}
    live = live_leaderboard(58, results, players, reset_unix=1_800_000_000)
    assert "Krillion #58 — live" in live
    assert "🥇 **alice** — 340" in live and "🥈 **bob** — 120" in live
    assert "<t:1800000000:R>" in live
    assert live_leaderboard(59, [], players) == "**Krillion #59** — no results yet. 🫧"

    day = service.finalize_due(RESET_59 + timedelta(minutes=10))[0]
    final = daily_leaderboard(58, day.entries, day.players)
    assert "Krillion #58 — final results" in final
    assert "🥇 **alice** — 340  (1200 → 1216, +16)" in final
    assert "🥈 **bob** — 120  (1200 → 1184, -16)" in final

    board = elo_leaderboard(service.storage.players(GUILD), service.storage.games_played(GUILD))
    assert board.splitlines()[1] == "🥇 **alice** — 1216  (1 played)"
