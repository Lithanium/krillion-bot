from datetime import timedelta

import pytest
from test_bot import make_config

from krillion_bot.bot import KrillionBot
from krillion_bot.puzzle import PuzzleCalendar
from krillion_bot.service import KrillionService
from krillion_bot.storage import Storage


@pytest.fixture
def bot(tmp_path):
    cfg = make_config(tmp_path)
    service = KrillionService(Storage(":memory:"), PuzzleCalendar(), grace=timedelta(minutes=10))
    return KrillionBot(cfg, service)
