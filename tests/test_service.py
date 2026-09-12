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
    """Service with the provisional phase disabled (plain K=32)."""
    return KrillionService(
        Storage(":memory:"), PuzzleCalendar(), grace=timedelta(minutes=10), provisional_games=0
    )


@pytest.fixture
def provisional_service() -> KrillionService:
    """Defaults: first 5 rated days use K=64."""
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
    assert day.provisional == frozenset()

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


def test_provisional_players_use_higher_k(provisional_service):
    service = provisional_service
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 120))
    day = service.finalize_due(RESET_59 + timedelta(minutes=10))[0]
    assert day.provisional == {1, 2}
    assert service.storage.get_player(GUILD, 1).rating == pytest.approx(1232)
    assert service.storage.get_player(GUILD, 2).rating == pytest.approx(1168)
    assert service.provisional_players(GUILD, [1, 2]) == {1, 2}
    assert service.provisional_players(GUILD, [1, 2], as_of_puzzle=57) == {1, 2}


def test_player_becomes_established_after_five_days(provisional_service):
    service = provisional_service
    cal = service.calendar
    # alice and bob tie every day, so ratings stay 1200 and only the game count matters.
    for n in range(58, 63):
        now = cal.start(n) + timedelta(hours=1)
        submit(service, 1, "alice", share(n, 300), now=now)
        submit(service, 2, "bob", share(n, 300), now=now)
        service.finalize_due(cal.end(n) + timedelta(minutes=10))
    assert service.storage.games_played(GUILD) == {1: 5, 2: 5}
    assert service.provisional_players(GUILD, [1, 2]) == frozenset()
    assert service.provisional_players(GUILD, [1, 2], as_of_puzzle=61) == {1, 2}

    # Day 6: carol is new (K=64) while alice and bob are established (K=32).
    now = cal.start(63) + timedelta(hours=1)
    submit(service, 1, "alice", share(63, 500), now=now)
    submit(service, 2, "bob", share(63, 300), now=now)
    submit(service, 3, "carol", share(63, 100), now=now)
    day = service.finalize_due(cal.end(63) + timedelta(minutes=10))[0]
    assert day.provisional == {3}
    deltas = {e.user_id: e.delta for e in day.entries}
    # alice beats two equal-rated opponents: 32/2 * (0.5 + 0.5) = +16
    assert deltas[1] == pytest.approx(16)
    assert deltas[2] == pytest.approx(0)
    # carol loses both with K=64: 64/2 * (-0.5 - 0.5) = -32
    assert deltas[3] == pytest.approx(-32)


def test_invalidate_open_day_allows_resubmit(service):
    submit(service, 1, "alice", share(58, 700))
    assert service.invalidate(GUILD, 58, 2) is None
    out = service.invalidate(GUILD, 58, 1)
    assert out is not None and out.removed.score == 700 and out.replayed_days == 0
    assert service.storage.get_result(GUILD, 58, 1) is None
    assert submit(service, 1, "alice", share(58, 340)).status is SubmitStatus.ACCEPTED


def test_invalidate_closed_day_replays_elo(service):
    cal = service.calendar
    # #58: alice 340, bob 120, mallory 700 (bogus). #59: alice 200 vs bob 250.
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 120))
    submit(service, 3, "mallory", share(58, 700))
    service.finalize_due(cal.end(58) + timedelta(minutes=10))
    now59 = cal.start(59) + timedelta(hours=1)
    submit(service, 1, "alice", share(59, 200), now=now59)
    submit(service, 2, "bob", share(59, 250), now=now59)
    service.finalize_due(cal.end(59) + timedelta(minutes=10))
    assert service.storage.get_player(GUILD, 3).rating == pytest.approx(1216)

    out = service.invalidate(GUILD, 58, 3)
    assert out is not None and out.replayed_days == 2

    # Same ratings as if mallory had never played #58.
    clean = KrillionService(Storage(":memory:"), PuzzleCalendar(), provisional_games=0)
    submit(clean, 1, "alice", share(58, 340))
    submit(clean, 2, "bob", share(58, 120))
    clean.finalize_due(cal.end(58) + timedelta(minutes=10))
    submit(clean, 1, "alice", share(59, 200), now=now59)
    submit(clean, 2, "bob", share(59, 250), now=now59)
    clean.finalize_due(cal.end(59) + timedelta(minutes=10))
    for uid in (1, 2):
        assert service.storage.get_player(GUILD, uid).rating == pytest.approx(
            clean.storage.get_player(GUILD, uid).rating
        )
    assert service.storage.get_player(GUILD, 3).rating == 1200
    assert service.storage.games_played(GUILD) == {1: 2, 2: 2}
    assert [e.user_id for e in service.storage.history_for(GUILD, 58)] == [1, 2]
    assert service.storage.is_finalized(GUILD, 58) and service.storage.is_finalized(GUILD, 59)
    # Nothing is left dangling for the scheduler to re-close.
    assert service.finalize_due(cal.end(59) + timedelta(days=1)) == []


def test_invalidate_only_result_leaves_day_empty(service):
    submit(service, 1, "alice", share(58, 700))
    service.finalize_due(RESET_59 + timedelta(minutes=10))
    out = service.invalidate(GUILD, 58, 1)
    assert out is not None and out.replayed_days == 0
    assert not service.storage.is_finalized(GUILD, 58)
    assert service.storage.history_for(GUILD, 58) == []
    assert submit(
        service, 1, "alice", share(58, 340), now=RESET_59 + timedelta(hours=1)
    ).status is (SubmitStatus.TOO_LATE)


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
    deltas = service.projected_deltas(GUILD, results)
    live = live_leaderboard(58, results, players, deltas=deltas, reset_unix=1_800_000_000)
    assert "Krillion #58 — live" in live
    assert "🥇 **alice** (1200)  🦑🦑🦑🦑🦑🐟🫧  **340**  +16" in live
    assert "🥈 **bob** (1200)  🦑🦑🦑🦑🦑🐟🫧  **120**  -16" in live
    assert "<t:1800000000:R>" in live
    assert live_leaderboard(59, [], players) == "**Krillion #59** — no results yet. 🫧"

    day = service.finalize_due(RESET_59 + timedelta(minutes=10))[0]
    tiers = {r.user_id: r.tiers for r in results}
    final = daily_leaderboard(58, day.entries, day.players, tiers=tiers)
    assert "Krillion #58 — final results" in final
    assert "🥇 **alice** (1200 → 1216)  🦑🦑🦑🦑🦑🐟🫧  **340**  +16" in final
    assert "🥈 **bob** (1200 → 1184)  🦑🦑🦑🦑🦑🐟🫧  **120**  -16" in final

    board = elo_leaderboard(service.storage.players(GUILD), service.storage.games_played(GUILD))
    assert board.splitlines()[1] == "🥇 **alice** — 1216  (1 played)"
    assert "provisional" not in board


def test_formatting_marks_provisional(provisional_service):
    service = provisional_service
    submit(service, 1, "alice", share(58, 340))
    submit(service, 2, "bob", share(58, 120))
    day = service.finalize_due(RESET_59 + timedelta(minutes=10))[0]
    final = daily_leaderboard(58, day.entries, day.players, day.provisional)
    assert "🥇 **alice** (1200 → 1232?)  " in final and "  **340**  +32" in final
    assert "🥈 **bob** (1200 → 1168?)  " in final and "  **120**  -32" in final
    assert final.splitlines()[-1].startswith("_? = provisional rating")

    players = service.storage.players(GUILD)
    board = elo_leaderboard(players, service.storage.games_played(GUILD), {1})
    assert "🥇 **alice** — 1232?  (1 played)" in board
    assert "🥈 **bob** — 1168  (1 played)" in board
