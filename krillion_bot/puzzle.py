"""Which Krillion puzzle is live right now?

Krillion rolls over at midnight in America/New_York and numbers puzzles
consecutively from ``EPOCH_DATE`` (#1). Midnight New York is 2pm AEST while
the US is on daylight time and 3pm AEST during US standard time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("America/New_York")
DEFAULT_EPOCH = date(2026, 7, 16)


@dataclass(frozen=True)
class PuzzleCalendar:
    tz: ZoneInfo = DEFAULT_TZ
    epoch: date = DEFAULT_EPOCH

    def _local(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(self.tz)

    def date_for(self, number: int) -> date:
        return self.epoch + timedelta(days=number - 1)

    def number_for_date(self, day: date) -> int:
        return (day - self.epoch).days + 1

    def current(self, now: datetime) -> int:
        return self.number_for_date(self._local(now).date())

    def start(self, number: int) -> datetime:
        """First instant puzzle ``number`` is playable (aware, puzzle tz)."""
        return datetime.combine(self.date_for(number), time(0, 0), tzinfo=self.tz)

    def end(self, number: int) -> datetime:
        """The reset instant that closes puzzle ``number`` (aware, puzzle tz)."""
        return self.start(number + 1)

    def next_reset(self, now: datetime) -> datetime:
        return self.end(self.current(now))
