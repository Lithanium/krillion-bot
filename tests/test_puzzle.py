from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from krillion_bot.puzzle import PuzzleCalendar

AEST = ZoneInfo("Australia/Brisbane")
CAL = PuzzleCalendar()


def test_epoch_is_puzzle_one():
    assert CAL.number_for_date(date(2026, 7, 16)) == 1
    assert CAL.date_for(1) == date(2026, 7, 16)


def test_known_puzzle_number():
    # Sept 11 2026, 22:03 New York (Sept 12, 12:03pm AEST) was Krillion #58.
    assert CAL.current(datetime(2026, 9, 12, 2, 3, tzinfo=timezone.utc)) == 58


def test_resets_at_2pm_aest_during_us_daylight_time():
    before = datetime(2026, 9, 12, 13, 59, 59, tzinfo=AEST)
    after = datetime(2026, 9, 12, 14, 0, 0, tzinfo=AEST)
    assert CAL.current(before) == 58
    assert CAL.current(after) == 59
    assert CAL.end(58) == after
    assert CAL.next_reset(before) == after


def test_resets_at_3pm_aest_during_us_standard_time():
    # US DST ends 1 Nov 2026; midnight EST == 3pm AEST.
    at = datetime(2026, 11, 20, 15, 0, 0, tzinfo=AEST)
    assert CAL.current(at) == CAL.current(at.replace(hour=14)) + 1


def test_naive_datetimes_are_treated_as_utc():
    assert CAL.current(datetime(2026, 9, 12, 2, 3)) == 58


def test_start_and_end_are_consecutive():
    for n in (1, 58, 200):
        assert CAL.end(n) == CAL.start(n + 1)
        assert CAL.current(CAL.start(n)) == n
        assert CAL.current(CAL.end(n)) == n + 1
