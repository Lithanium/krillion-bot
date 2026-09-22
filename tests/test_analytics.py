from datetime import date, datetime, timezone

from krillion_bot import analytics as a
from krillion_bot.models import RatingEntry, Result
from krillion_bot.puzzle import PuzzleCalendar

CAL = PuzzleCalendar()
AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


def res(user: int, puzzle: int, score: int, tiers: str = "") -> Result:
    return Result(1, puzzle, user, score, tiers, 10, None, AT)


def entry(user: int, puzzle: int, before: float, after: float, perf: float | None = None):
    return RatingEntry(puzzle, user, 500, 1, before, after, perf)


# -- streaks / skips --------------------------------------------------------


def test_streaks_count_consecutive_puzzles():
    assert a.streaks([1, 2, 3, 5, 6], current_puzzle=6) == a.Streaks(current=2, longest=3)


def test_streak_survives_unplayed_current_puzzle():
    assert a.streaks([4, 5, 6], current_puzzle=7).current == 3
    assert a.streaks([4, 5, 6], current_puzzle=8).current == 0


def test_streaks_empty():
    assert a.streaks([], current_puzzle=10) == a.Streaks(0, 0)


def test_skipped_puzzles_exclude_today_and_are_newest_first():
    first, skipped = a.skipped_puzzles([3, 4, 7], current_puzzle=9)
    assert first == 3
    assert skipped == [8, 6, 5]
    assert a.skipped_puzzles([], current_puzzle=9) == (None, [])


# -- winners / top ------------------------------------------------------------


def test_day_winners_need_two_players_and_share_ties():
    rows = [res(1, 5, 700), res(2, 5, 700), res(3, 5, 100), res(1, 6, 400), res(2, 7, 300)]
    rows.append(res(3, 7, 500))
    winners = a.day_winners(rows)
    assert set(winners) == {5, 7}
    assert winners[5].winners == (1, 2) and winners[5].tied and winners[5].participants == 3
    assert winners[7].winners == (3,) and not winners[7].tied


def test_top_orders_by_outright_then_shared():
    rows = [
        res(1, 1, 700),
        res(2, 1, 700),
        res(1, 2, 700),
        res(2, 2, 600),
        res(2, 3, 700),
        res(1, 3, 100),
        res(2, 4, 700),
        res(1, 4, 100),
    ]
    board = a.top(rows)
    assert [(e.user_id, e.solo, e.tied) for e in board] == [(2, 2, 1), (1, 1, 1)]
    assert board[0].total == 3
    assert [e.user_id for e in a.top(rows, count_ties=True)] == [2, 1]


# -- head to head -------------------------------------------------------------


def test_head_to_head_common_puzzles_only():
    rows = {
        1: [res(1, 1, 700), res(1, 2, 500), res(1, 3, 600)],
        2: [res(2, 1, 600), res(2, 2, 500)],
    }
    out = a.head_to_head(rows)
    assert out.puzzles == 2 and out.comparisons == 2
    alice, bob = out.players
    assert (alice.user_id, alice.points, alice.wins, alice.ties) == (1, 1.5, 1, 1)
    assert (bob.user_id, bob.points, bob.losses) == (2, 0.5, 1)


def test_head_to_head_missing_as_loss():
    rows = {1: [res(1, 1, 700), res(1, 3, 600)], 2: [res(2, 1, 600)]}
    out = a.head_to_head(rows, missing_is_loss=True)
    assert out.puzzles == 2
    assert out.players[0].wins == 2 and out.players[1].losses == 2


def test_head_to_head_three_players():
    rows = {
        1: [res(1, 1, 700)],
        2: [res(2, 1, 500)],
        3: [res(3, 1, 500)],
    }
    out = a.head_to_head(rows)
    assert [p.user_id for p in out.players] == [1, 2, 3]
    assert out.comparisons == 3
    assert out.players[1].ties == 1 and out.players[1].points == 0.5


# -- timeframes ---------------------------------------------------------------


def test_puzzle_range():
    today = date(2026, 9, 12)  # Saturday, #59
    assert a.puzzle_range(CAL, "all", today) == (None, None)
    assert a.puzzle_range(CAL, "week", today) == (54, 59)  # Monday 7 Sept
    assert a.puzzle_range(CAL, "month", today) == (48, 59)
    assert a.puzzle_range(CAL, "7d", today) == (53, 59)
    assert a.puzzle_range(CAL, "year", today)[0] == CAL.number_for_date(date(2026, 1, 1))


# -- summary ------------------------------------------------------------------


def test_summarize_wins_use_whole_field():
    rows = [
        res(1, 56, 700, "🦑🦑🦑🦑🦑🦑🦑"),
        res(2, 56, 300),
        res(1, 57, 400, "🦑🐟"),
        res(2, 57, 400),
        res(1, 58, 200),
    ]
    history = [entry(1, 56, 1200, 1250, 1400), entry(1, 57, 1250, 1240, 1180)]
    s = a.summarize(1, rows, history, CAL, current_puzzle=58)
    assert (s.games, s.rated_games, s.wins, s.tied_wins) == (3, 2, 1, 1)
    assert (s.best, s.average, s.median) == (700, (700 + 400 + 200) / 3, 400)
    assert s.perfect_days == 1 and s.perfect_streak.longest == 1
    assert s.streak == a.Streaks(3, 3)
    assert s.tier_counts["🦑"] == 8 and s.tier_counts["🐟"] == 1
    assert (s.rating, s.peak, s.last_delta) == (1240, 1250, -10)
    assert (s.last_performance, s.best_performance) == (1180, 1400)
    assert set(s.weekday_average) == {CAL.date_for(n).weekday() for n in (56, 57, 58)}


def test_summarize_unrated_player():
    s = a.summarize(9, [], [], CAL, current_puzzle=58)
    assert s.games == 0 and s.best is None and s.rating is None and s.streak == a.Streaks(0, 0)


# -- weekly recap -------------------------------------------------------------


def test_week_bounds_monday_to_sunday():
    assert a.week_bounds(date(2026, 9, 12)) == (date(2026, 9, 7), date(2026, 9, 13))
    assert a.week_bounds(date(2026, 9, 7)) == (date(2026, 9, 7), date(2026, 9, 13))


def test_week_recap():
    # Week of Mon 7 Sept 2026 = puzzles #54..#60; previous week #47..#53.
    rows = [
        res(1, 47, 100),
        res(1, 48, 100),
        res(1, 54, 700),
        res(2, 54, 500),
        res(1, 55, 300),
        res(2, 55, 600),
        res(2, 56, 650),
        res(3, 56, 650),
    ]
    history = [entry(1, 54, 1200, 1230), entry(2, 54, 1200, 1170), entry(2, 55, 1170, 1210)]
    recap = a.build_week_recap(rows, history, CAL, date(2026, 9, 12), today=date(2026, 9, 12))
    assert (recap.start, recap.end, recap.in_progress) == (
        date(2026, 9, 7),
        date(2026, 9, 13),
        True,
    )
    assert [d.puzzle_number for d in recap.days] == [54, 55, 56, 57, 58, 59]
    assert recap.days[0].winners is not None and recap.days[0].winners.winners == (1,)
    assert recap.days[2].winners is not None and recap.days[2].winners.tied
    assert recap.days[3].winners is None
    assert recap.results == 6 and recap.players == 3
    assert [s.user_id for s in recap.standings] == [2, 1, 3]
    top = recap.standings[0]
    assert (top.total, top.days, top.best, top.solo_wins, top.tied_wins) == (1750, 3, 650, 1, 1)
    assert recap.highest == (1, 700, date(2026, 9, 7))
    assert recap.most_improved == (1, (700 + 300) / 2 - 100)
    assert [(m.user_id, m.before, m.after) for m in recap.moves] == [
        (1, 1200, 1230),
        (2, 1200, 1210),
    ]
    assert recap.moves[1].delta == 10


def test_week_recap_finished_week():
    recap = a.build_week_recap([], [], CAL, date(2026, 9, 1), today=date(2026, 9, 12))
    assert not recap.in_progress and recap.results == 0 and recap.standings == []
