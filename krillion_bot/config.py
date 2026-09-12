from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, '#' comments, no interpolation.

    Existing environment variables win over the file.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int_or_none(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


@dataclass(frozen=True)
class Config:
    token: str
    database_path: Path
    leaderboard_channel_id: int | None
    results_channel_id: int | None
    late_grace_minutes: int
    elo_k: float
    puzzle_tz: ZoneInfo
    epoch_date: date
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not set (put it in .env or the environment)")
        return cls(
            token=token,
            database_path=Path(os.environ.get("DATABASE_PATH", "data/krillion.sqlite3")),
            leaderboard_channel_id=_int_or_none(os.environ.get("LEADERBOARD_CHANNEL_ID")),
            results_channel_id=_int_or_none(os.environ.get("RESULTS_CHANNEL_ID")),
            late_grace_minutes=int(os.environ.get("LATE_GRACE_MINUTES", "10")),
            elo_k=float(os.environ.get("ELO_K", "32")),
            puzzle_tz=ZoneInfo(os.environ.get("KRILLION_TIMEZONE", "America/New_York")),
            epoch_date=date.fromisoformat(os.environ.get("KRILLION_EPOCH_DATE", "2026-07-16")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
