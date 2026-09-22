import io

from PIL import Image

from krillion_bot.charts import HEIGHT, WIDTH, rating_chart
from krillion_bot.models import RatingEntry


def entry(n: int, after: float, perf: float | None) -> RatingEntry:
    return RatingEntry(n, 1, 500, 1, after - 10, after, perf)


def test_chart_needs_two_days():
    assert rating_chart("x", []) is None
    assert rating_chart("x", [entry(1, 1210, 1300)]) is None


def test_chart_renders_png():
    entries = [entry(n, 1200 + 30 * n, 1250 + 40 * n) for n in range(1, 40)]
    for performances in (False, True):
        png = rating_chart("alice — Krillion rating", entries, performances=performances)
        assert png is not None
        img = Image.open(io.BytesIO(png))
        assert img.format == "PNG" and img.size == (WIDTH, HEIGHT)


def test_chart_without_performance_data():
    png = rating_chart("x", [entry(1, 1200, None), entry(2, 1195, None)], performances=True)
    assert png is not None
