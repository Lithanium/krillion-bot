import io
from datetime import date, datetime, timezone

import numpy as np
from PIL import Image

from krillion_bot import plot_stats
from krillion_bot.analytics import build_week_recap, summarize
from krillion_bot.models import RatingEntry, Result
from krillion_bot.plot_stats import stats_plot
from krillion_bot.plot_week import week_plot
from krillion_bot.puzzle import PuzzleCalendar

CALENDAR = PuzzleCalendar()
NOW = datetime(2026, 7, 18, tzinfo=timezone.utc)


def result(puzzle: int, user: int, score: int) -> Result:
    return Result(1, puzzle, user, score, "", 10, None, NOW)


def history(puzzle: int, user: int, before: float, after: float, perf: float | None) -> RatingEntry:
    return RatingEntry(puzzle, user, 500, 1, before, after, perf)


def png_image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    assert image.width > 300 and image.height > 150
    return image


def test_stats_plot_renders_seeded_dashboard_and_single_result():
    rows = [result(4, 1, 700), result(5, 1, 500), result(6, 1, 600)]
    all_rows = rows + [result(4, 2, 300), result(5, 2, 400), result(6, 2, 200)]
    entries = [
        history(4, 1, 1200, 1210, 1300),
        history(5, 1, 1210, 1220, 1320),
        history(6, 1, 1220, 1230, 1340),
    ]
    summary = summarize(1, all_rows, entries, CALENDAR, current_puzzle=6)
    assert png_image(stats_plot("alice", summary, rows, CALENDAR, date(2026, 7, 18)))

    one = [result(4, 1, 700)]
    single_summary = summarize(1, one, [], CALENDAR, current_puzzle=6)
    assert png_image(stats_plot("alice", single_summary, one, CALENDAR, date(2026, 7, 18)))


def test_week_plot_renders_with_viewer_and_unknown_user_label():
    rows = [
        result(4, 1, 700),
        result(4, 2, 400),
        result(5, 1, 500),
        result(5, 2, 600),
    ]
    entries = [
        history(4, 1, 1200, 1210, 1300),
        history(5, 1, 1210, 1220, 1320),
        history(4, 2, 1200, 1190, 1100),
        history(5, 2, 1190, 1200, 1150),
    ]
    recap = build_week_recap(
        rows, entries, CALENDAR, anchor=date(2026, 7, 15), today=date(2026, 7, 18)
    )
    assert png_image(week_plot(recap, {1: "alice", 2: "bob"}, {1: 1210, 2: 1190}, viewer=1))
    assert png_image(week_plot(recap, {}, {}, viewer=99))


def test_stats_plot_krillion_labels_and_weekday_bars(monkeypatch):
    rows = [
        Result(1, 54, 1, 220, "🌟🐟🐟🐟🐟⬛⬛", 10, None, NOW),
        Result(1, 61, 1, 340, "🌟🌟🐟🐟🐟🐟⬛", 10, None, NOW),
        Result(1, 55, 1, 210, "🐟" * 7, 10, None, NOW),
    ]
    monkeypatch.setattr(plot_stats, "png", lambda fig: fig)
    summary = summarize(1, rows, [], CALENDAR, 61)
    fig = stats_plot("alice", summary, rows, CALENDAR, date(2026, 9, 14))
    texts = [text.get_text() for ax in fig.axes for text in ax.texts]
    assert {
        "KRILLION ODDS",
        "1 in 7",
        "3/21 questions",
        "3 KRILLIONS",
        "0 KRILLIONS",
        "NO DATA",
        "AVG 280",
    } <= set(texts)
    dna = next(ax for ax in fig.axes if ax.get_title(loc="left").startswith("DAY DNA"))
    assert dna.get_title(loc="left") == "DAY DNA  ·  KRILLIONS + AVG SCORE"
    assert dna.patches[0].get_width() == 1
    assert dna.patches[2].get_width() == 0

    rows = rows[2:]
    summary = summarize(1, rows, [], CALENDAR, 61)
    fig = stats_plot("alice", summary, rows, CALENDAR, date(2026, 9, 14))
    texts = [text.get_text() for ax in fig.axes for text in ax.texts]
    assert {"—", "no krillions yet", "0 KRILLIONS"} <= set(texts)


def test_inflation_plot_renders_and_interpolates_gaps():
    from krillion_bot.analytics import rank_cutoffs
    from krillion_bot.plot_inflation import inflation_plot, interpolate

    entries = [
        RatingEntry(4, 1, 700, 1, 1200, 1210, 1650),
        RatingEntry(4, 2, 400, 2, 1200, 1190, 1300),
        RatingEntry(5, 1, 550, 1, 1210, 1220, 1500),
        RatingEntry(5, 2, 350, 2, 1190, 1180, 1250),
        RatingEntry(6, 1, 480, 1, 1220, 1230, 1400),
        RatingEntry(6, 2, 420, 2, 1180, 1170, 1350),
    ]
    cutoffs = rank_cutoffs(entries)
    assert png_image(inflation_plot(cutoffs, CALENDAR))

    nan = float("nan")
    filled = interpolate(np.array([0.0, 1.0, 2.0, 3.0, 4.0]), [1.0, nan, nan, 4.0, nan])
    assert list(filled)[:4] == [1.0, 2.0, 3.0, 4.0]
    assert np.isnan(filled[4])  # trailing nan stays empty
    uneven = interpolate(np.array([0.0, 1.0, 4.0]), [0.0, nan, 400.0])
    assert uneven[1] == 100.0  # placed by date, not by index

    assert inflation_plot({}, CALENDAR) is None


def test_ao_smooth_drops_extremes_and_keeps_short_edges():
    from krillion_bot.plot_inflation import ao_smooth

    assert ao_smooth([10.0, 50.0, 20.0, 30.0, 40.0], 3) == [10.0, 20.0, 30.0, 30.0, 40.0]
    # ao5 boundary: window of exactly 3 still drops the high and low
    assert ao_smooth([10.0, 20.0, 50.0], 5)[0] == 20.0
    # fewer than three observations in reach: raw value survives
    assert ao_smooth([10.0, 99.0], 3) == [10.0, 99.0]


def test_inflation_plot_renders_smoothed_and_shades_below_lowest_line():
    from krillion_bot.analytics import rank_cutoffs
    from krillion_bot.plot_inflation import inflation_plot

    entries = []
    for n in range(4, 12):
        entries += [
            RatingEntry(n, 1, 600 + (n % 3) * 30, 1, 1200, 1210, 1600),
            RatingEntry(n, 2, 400 + (n % 2) * 40, 2, 1200, 1190, 1300),
        ]
    data = inflation_plot(rank_cutoffs(entries), CALENDAR, ao=3)
    assert png_image(data)
