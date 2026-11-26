import io

from PIL import Image

from krillion_bot.charts import TEXT, name_color, rating_chart, safe_name
from krillion_bot.models import RatingEntry
from krillion_bot.puzzle import PuzzleCalendar


def entry(n: int, after: float, perf: float | None) -> RatingEntry:
    return RatingEntry(n, 1, 500, 1, after - 10, after, perf)


def test_rating_chart_without_points_returns_none():
    calendar = PuzzleCalendar()
    assert rating_chart("x", [], calendar, performances=False) is None
    assert rating_chart("x", [entry(1, 1210, None)], calendar, performances=True) is None


def test_rating_chart_renders_rating_and_performance_pngs():
    calendar = PuzzleCalendar()
    entries = [entry(n, 1200 + 30 * n, 1250 + 40 * n) for n in range(1, 4)]
    for performances in (False, True):
        png = rating_chart("alice — Krillion rating", entries, calendar, performances=performances)
        assert png is not None
        image = Image.open(io.BytesIO(png))
        assert image.format == "PNG"
        assert image.width > 300 and image.height > 150


def test_rating_chart_can_plot_a_single_rating_point():
    png = rating_chart("x", [entry(1, 1200, None)], PuzzleCalendar(), performances=False)
    assert png is not None
    assert Image.open(io.BytesIO(png)).format == "PNG"


def test_chart_name_helpers_follow_rank_bands_and_strip_symbols():
    assert name_color(None) == TEXT
    assert name_color(999) != name_color(1300)
    assert name_color(1300) != name_color(1800)
    assert safe_name("A😀\nB\u0000\u200b  C") == "A B C"
    assert safe_name("🦐") == "Player"


def test_performance_chart_plots_each_player_and_skips_empty_ones():
    from krillion_bot.charts import performance_chart

    calendar = PuzzleCalendar()
    alice = [entry(n, 1200 + 30 * n, 1250 + 40 * n) for n in range(1, 5)]
    bob = [entry(n, 1300, 1100 + 10 * n) for n in (1, 3, 4)]  # missed a day
    carol = [entry(1, 1200, None)]  # solo days only: no line
    png = performance_chart([("alice", alice), ("bob", bob), ("carol", carol)], calendar)
    assert png is not None
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG" and image.width > 300
    assert performance_chart([("carol", carol)], calendar) is None


def test_ratings_chart_plots_every_rated_day_including_solo():
    from krillion_bot.charts import ratings_chart

    calendar = PuzzleCalendar()
    alice = [entry(n, 1200 + 30 * n, None) for n in range(1, 4)]  # solo days still count
    bob = [entry(n, 1300, 1150) for n in range(1, 4)]
    png = ratings_chart([("alice", alice), ("bob", bob)], calendar)
    assert png is not None and Image.open(io.BytesIO(png)).format == "PNG"
    assert ratings_chart([("carol", [])], calendar) is None
