import pytest

from krillion_bot.elo import (
    PROVISIONAL_GAMES,
    PROVISIONAL_K,
    STARTING_RATING,
    expected_score,
    is_provisional,
    k_factor,
    placements,
    rating_deltas,
)


def test_everyone_starts_at_1200():
    assert STARTING_RATING == 1200


def test_expected_score_symmetry():
    assert expected_score(1200, 1200) == pytest.approx(0.5)
    assert expected_score(1400, 1200) + expected_score(1200, 1400) == pytest.approx(1.0)
    assert expected_score(1400, 1200) == pytest.approx(0.76, abs=0.01)


def test_two_equal_players_full_k_swing():
    ratings = {1: 1200.0, 2: 1200.0}
    deltas = rating_deltas(ratings, {1: 340, 2: 120}, k=32)
    assert deltas[1] == pytest.approx(16)
    assert deltas[2] == pytest.approx(-16)


def test_single_player_no_change():
    assert rating_deltas({1: 1200.0}, {1: 340}) == {1: 0.0}


def test_tie_between_equal_players_no_change():
    deltas = rating_deltas({1: 1200.0, 2: 1200.0}, {1: 300, 2: 300})
    assert deltas[1] == pytest.approx(0)
    assert deltas[2] == pytest.approx(0)


def test_zero_sum():
    ratings = {1: 1300.0, 2: 1200.0, 3: 1150.0, 4: 1000.0}
    scores = {1: 200, 2: 400, 3: 400, 4: 100}
    deltas = rating_deltas(ratings, scores)
    assert sum(deltas.values()) == pytest.approx(0)


def test_upset_moves_more_than_expected_win():
    favourite, underdog = 1, 2
    ratings = {favourite: 1500.0, underdog: 1100.0}
    upset = rating_deltas(ratings, {favourite: 100, underdog: 300})
    expected = rating_deltas(ratings, {favourite: 300, underdog: 100})
    assert upset[underdog] > expected[favourite] > 0
    assert upset[underdog] == pytest.approx(-upset[favourite])


def test_change_depends_on_field():
    ratings = {1: 1200.0, 2: 1200.0, 3: 1200.0, 4: 1200.0}
    scores = {1: 500, 2: 300, 3: 200, 4: 100}
    deltas = rating_deltas(ratings, scores, k=32)
    # Winner of a 4-way beats 3 opponents at 32/3 each -> +16, last place -16.
    assert deltas[1] == pytest.approx(16)
    assert deltas[4] == pytest.approx(-16)
    assert deltas[2] == pytest.approx(16 / 3)
    assert deltas[3] == pytest.approx(-16 / 3)
    # Max swing per day is bounded by k regardless of field size.
    assert all(abs(d) <= 32 for d in deltas.values())


def test_provisional_k_factor():
    assert (PROVISIONAL_GAMES, PROVISIONAL_K) == (5, 64)
    assert is_provisional(0) and is_provisional(4)
    assert not is_provisional(5)
    assert k_factor(0) == 64
    assert k_factor(4) == 64
    assert k_factor(5) == 32
    assert k_factor(0, k=20, provisional_k=50, provisional_games=3) == 50
    assert k_factor(3, k=20, provisional_k=50, provisional_games=3) == 20
    assert k_factor(0, provisional_games=0) == 32


def test_per_player_k_mapping():
    ratings = {1: 1200.0, 2: 1200.0}
    deltas = rating_deltas(ratings, {1: 340, 2: 120}, k={1: 64.0, 2: 32.0})
    assert deltas[1] == pytest.approx(32)
    assert deltas[2] == pytest.approx(-16)


def test_placements_with_ties():
    assert placements({1: 300, 2: 300, 3: 100, 4: 500}) == {4: 1, 1: 2, 2: 2, 3: 4}
