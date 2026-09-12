import pytest

from krillion_bot.rating import (
    close_day,
    compute_round,
    event_performance,
    placements,
    rank_for_rating,
)


def test_placements_standard_competition_ranking():
    assert placements({1: 340, 2: 250, 3: 250, 4: 90}) == {1: 1, 2: 2, 3: 2, 4: 4}
    assert placements({7: 5}) == {7: 1}
    assert placements({}) == {}


def test_rank_bands():
    assert rank_for_rating(1199).abbr == "S"
    assert rank_for_rating(1200).abbr == "E"
    assert (rank_for_rating(1300).abbr, rank_for_rating(1300).title) == ("CM", "Candidate Master")
    assert rank_for_rating(2000).abbr == "LGM"
    assert rank_for_rating(-50).abbr == "N"


def test_compute_round_matches_queens_bot_engine():
    # Reference values from tle-gf's ``akari_rating.compute_round`` (default damping).
    ratings = {1: 1200.0, 2: 1200.0, 3: 1200.0, 4: 1200.0}
    perf: dict[int, float] = {}
    deltas = compute_round(ratings, {1: 1, 2: 2, 3: 2, 4: 4}, performances=perf)
    assert deltas == pytest.approx(
        {1: 24.261566108092666, 2: 1.016991650685668, 3: 1.016991650685668, 4: -27.295549409464}
    )
    assert perf == pytest.approx(
        {1: 1538.0391721874475, 2: 1288.7395794838667, 3: 1288.7395794838667, 4: 861.9607344120741}
    )
    mixed = compute_round({1: 1500.0, 2: 1300.0, 3: 1250.0, 4: 900.0}, {1: 2, 2: 1, 3: 3, 4: 4})
    assert mixed == pytest.approx(
        {
            1: -12.173616387881339,
            2: 36.95389050152153,
            3: -10.294573818333447,
            4: -15.485700295306742,
        }
    )


def test_compute_round_is_anti_inflationary():
    ratings = {i: 1200.0 + 50 * i for i in range(6)}
    ranks = {i: 6 - i for i in range(6)}
    deltas = compute_round(ratings, ranks)
    # Sum of raw deltas is forced to -n before 0.25 damping.
    assert sum(deltas.values()) == pytest.approx(-6 * 0.25)


def test_ties_get_identical_deltas_and_performance():
    perf: dict[int, float] = {}
    deltas = compute_round({1: 1200.0, 2: 1200.0, 3: 1200.0}, {1: 1, 2: 2, 3: 2}, performances=perf)
    assert deltas[2] == deltas[3] and perf[2] == perf[3]
    assert deltas[1] > deltas[2]


def test_event_performance_is_finite_at_both_ends():
    field = [10 ** (r / 400) for r in (1200.0, 1400.0, 1000.0)]
    first, last = event_performance(field, 1), event_performance(field, 3)
    assert 1 < last < first < 8000


def test_close_day_solo_is_a_no_op():
    out = close_day({1: 340}, {1: 1200.0}, {})
    assert out.deltas == {1: 0.0}
    assert out.performances == {1: None}
    assert out.decay == {}


def test_close_day_decay_moves_absentees_towards_start_and_pays_active():
    out = close_day({1: 300, 2: 200}, {1: 1200.0, 2: 1200.0}, {9: (1400.0, 1), 8: (1100.0, 5)})
    # 4% of the 200 points above 1200 on the first missed day; nobody drifts upward.
    assert out.decay == {9: pytest.approx(-8.0), 8: 0.0}
    contest = compute_round({1: 1200.0, 2: 1200.0}, {1: 1, 2: 2})
    assert out.deltas[1] == pytest.approx(contest[1] + 4.0)
    assert out.deltas[2] == pytest.approx(contest[2] + 4.0)


def test_close_day_decay_rate_grows_with_streak_up_to_cap():
    first = close_day({1: 1, 2: 0}, {1: 1200.0, 2: 1200.0}, {9: (1400.0, 1)}).decay[9]
    second = close_day({1: 1, 2: 0}, {1: 1200.0, 2: 1200.0}, {9: (1400.0, 2)}).decay[9]
    third = close_day({1: 1, 2: 0}, {1: 1200.0, 2: 1200.0}, {9: (1400.0, 3)}).decay[9]
    assert (first, second, third) == pytest.approx((-8.0, -16.0, -16.0))
