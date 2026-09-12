from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .elo import STARTING_RATING

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    display_name TEXT    NOT NULL,
    rating       REAL    NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS results (
    guild_id      INTEGER NOT NULL,
    puzzle_number INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    score         INTEGER NOT NULL,
    tiers         TEXT    NOT NULL DEFAULT '',
    channel_id    INTEGER NOT NULL,
    message_id    INTEGER,
    submitted_at  TEXT    NOT NULL,
    PRIMARY KEY (guild_id, puzzle_number, user_id)
);

CREATE TABLE IF NOT EXISTS finalized_days (
    guild_id      INTEGER NOT NULL,
    puzzle_number INTEGER NOT NULL,
    finalized_at  TEXT    NOT NULL,
    PRIMARY KEY (guild_id, puzzle_number)
);

CREATE TABLE IF NOT EXISTS rating_history (
    guild_id      INTEGER NOT NULL,
    puzzle_number INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    score         INTEGER NOT NULL,
    placement     INTEGER NOT NULL,
    rating_before REAL    NOT NULL,
    rating_after  REAL    NOT NULL,
    PRIMARY KEY (guild_id, puzzle_number, user_id)
);
"""


@dataclass(frozen=True)
class Result:
    guild_id: int
    puzzle_number: int
    user_id: int
    score: int
    tiers: str
    channel_id: int
    message_id: int | None
    submitted_at: datetime


@dataclass(frozen=True)
class Player:
    guild_id: int
    user_id: int
    display_name: str
    rating: float


@dataclass(frozen=True)
class RatingEntry:
    puzzle_number: int
    user_id: int
    score: int
    placement: int
    rating_before: float
    rating_after: float

    @property
    def delta(self) -> float:
        return self.rating_after - self.rating_before


@dataclass(frozen=True)
class PlayerStats:
    games: int
    wins: int
    best_score: int | None
    average_score: float | None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Storage:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- players ---------------------------------------------------------

    def upsert_player(self, guild_id: int, user_id: int, display_name: str) -> Player:
        self._conn.execute(
            """
            INSERT INTO players (guild_id, user_id, display_name, rating)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET display_name = excluded.display_name
            """,
            (guild_id, user_id, display_name, STARTING_RATING),
        )
        player = self.get_player(guild_id, user_id)
        assert player is not None
        return player

    def get_player(self, guild_id: int, user_id: int) -> Player | None:
        row = self._conn.execute(
            "SELECT * FROM players WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        ).fetchone()
        return Player(**row) if row else None

    def players(self, guild_id: int, user_ids: Iterable[int] | None = None) -> list[Player]:
        if user_ids is None:
            rows = self._conn.execute(
                "SELECT * FROM players WHERE guild_id = ? ORDER BY rating DESC, display_name",
                (guild_id,),
            ).fetchall()
        else:
            ids = list(user_ids)
            if not ids:
                return []
            marks = ",".join("?" * len(ids))
            rows = self._conn.execute(
                f"SELECT * FROM players WHERE guild_id = ? AND user_id IN ({marks}) "
                "ORDER BY rating DESC, display_name",
                (guild_id, *ids),
            ).fetchall()
        return [Player(**r) for r in rows]

    def set_rating(self, guild_id: int, user_id: int, rating: float) -> None:
        self._conn.execute(
            "UPDATE players SET rating = ? WHERE guild_id = ? AND user_id = ?",
            (rating, guild_id, user_id),
        )

    # -- results ---------------------------------------------------------

    def add_result(self, result: Result) -> bool:
        """Insert ``result``; returns ``False`` if the user already has one for that puzzle."""
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO results
                (guild_id, puzzle_number, user_id, score, tiers, channel_id, message_id,
                 submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.guild_id,
                result.puzzle_number,
                result.user_id,
                result.score,
                result.tiers,
                result.channel_id,
                result.message_id,
                _iso(result.submitted_at),
            ),
        )
        return cur.rowcount == 1

    def get_result(self, guild_id: int, puzzle_number: int, user_id: int) -> Result | None:
        row = self._conn.execute(
            "SELECT * FROM results WHERE guild_id = ? AND puzzle_number = ? AND user_id = ?",
            (guild_id, puzzle_number, user_id),
        ).fetchone()
        return self._result(row) if row else None

    def remove_result(self, guild_id: int, puzzle_number: int, user_id: int) -> Result | None:
        """Delete a user's result for a puzzle, returning it (or ``None`` if there was none)."""
        existing = self.get_result(guild_id, puzzle_number, user_id)
        if existing is not None:
            self._conn.execute(
                "DELETE FROM results WHERE guild_id = ? AND puzzle_number = ? AND user_id = ?",
                (guild_id, puzzle_number, user_id),
            )
        return existing

    def results_for(self, guild_id: int, puzzle_number: int) -> list[Result]:
        rows = self._conn.execute(
            """
            SELECT * FROM results WHERE guild_id = ? AND puzzle_number = ?
            ORDER BY score DESC, submitted_at ASC
            """,
            (guild_id, puzzle_number),
        ).fetchall()
        return [self._result(r) for r in rows]

    def unfinalized_puzzles(self) -> list[tuple[int, int]]:
        """``(guild_id, puzzle_number)`` pairs that have results but no finalization."""
        rows = self._conn.execute(
            """
            SELECT DISTINCT r.guild_id, r.puzzle_number
            FROM results r
            LEFT JOIN finalized_days f
                   ON f.guild_id = r.guild_id AND f.puzzle_number = r.puzzle_number
            WHERE f.puzzle_number IS NULL
            ORDER BY r.guild_id, r.puzzle_number
            """
        ).fetchall()
        return [(r["guild_id"], r["puzzle_number"]) for r in rows]

    def is_finalized(self, guild_id: int, puzzle_number: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM finalized_days WHERE guild_id = ? AND puzzle_number = ?",
            (guild_id, puzzle_number),
        ).fetchone()
        return row is not None

    def latest_puzzle(self, guild_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT MAX(puzzle_number) AS n FROM results WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        return row["n"]

    # -- finalization ----------------------------------------------------

    def finalize(
        self,
        guild_id: int,
        puzzle_number: int,
        entries: Iterable[RatingEntry],
        finalized_at: datetime,
    ) -> None:
        entries = list(entries)
        with self._conn:
            self._conn.execute("BEGIN")
            for e in entries:
                self._conn.execute(
                    """
                    INSERT INTO rating_history
                        (guild_id, puzzle_number, user_id, score, placement,
                         rating_before, rating_after)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        puzzle_number,
                        e.user_id,
                        e.score,
                        e.placement,
                        e.rating_before,
                        e.rating_after,
                    ),
                )
                self._conn.execute(
                    "UPDATE players SET rating = ? WHERE guild_id = ? AND user_id = ?",
                    (e.rating_after, guild_id, e.user_id),
                )
            self._conn.execute(
                "INSERT INTO finalized_days (guild_id, puzzle_number, finalized_at) "
                "VALUES (?, ?, ?)",
                (guild_id, puzzle_number, _iso(finalized_at)),
            )

    def finalized_puzzles(self, guild_id: int) -> list[tuple[int, datetime]]:
        """``(puzzle_number, finalized_at)`` for every closed day in the guild, oldest first."""
        rows = self._conn.execute(
            "SELECT puzzle_number, finalized_at FROM finalized_days WHERE guild_id = ? "
            "ORDER BY puzzle_number",
            (guild_id,),
        ).fetchall()
        return [(r["puzzle_number"], _from_iso(r["finalized_at"])) for r in rows]

    def reset_ratings(self, guild_id: int) -> None:
        """Wipe rating history and finalizations; everyone goes back to the starting rating."""
        with self._conn:
            self._conn.execute("BEGIN")
            self._conn.execute("DELETE FROM rating_history WHERE guild_id = ?", (guild_id,))
            self._conn.execute("DELETE FROM finalized_days WHERE guild_id = ?", (guild_id,))
            self._conn.execute(
                "UPDATE players SET rating = ? WHERE guild_id = ?", (STARTING_RATING, guild_id)
            )

    def history_for(self, guild_id: int, puzzle_number: int) -> list[RatingEntry]:
        rows = self._conn.execute(
            """
            SELECT puzzle_number, user_id, score, placement, rating_before, rating_after
            FROM rating_history WHERE guild_id = ? AND puzzle_number = ?
            ORDER BY placement ASC, score DESC
            """,
            (guild_id, puzzle_number),
        ).fetchall()
        return [RatingEntry(**r) for r in rows]

    def stats_for(self, guild_id: int, user_id: int) -> PlayerStats:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS games,
                   COALESCE(SUM(CASE WHEN placement = 1 THEN 1 ELSE 0 END), 0) AS wins,
                   MAX(score) AS best,
                   AVG(score) AS avg
            FROM rating_history WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()
        return PlayerStats(
            games=row["games"],
            wins=row["wins"],
            best_score=row["best"],
            average_score=row["avg"],
        )

    def games_played(self, guild_id: int, up_to_puzzle: int | None = None) -> dict[int, int]:
        """Rated days per user, optionally only counting puzzles ``<= up_to_puzzle``."""
        params: tuple[int, ...] = (guild_id,)
        where = "guild_id = ?"
        if up_to_puzzle is not None:
            where += " AND puzzle_number <= ?"
            params += (up_to_puzzle,)
        rows = self._conn.execute(
            f"SELECT user_id, COUNT(*) AS n FROM rating_history WHERE {where} GROUP BY user_id",
            params,
        ).fetchall()
        return {r["user_id"]: r["n"] for r in rows}

    @staticmethod
    def _result(row: sqlite3.Row) -> Result:
        return Result(
            guild_id=row["guild_id"],
            puzzle_number=row["puzzle_number"],
            user_id=row["user_id"],
            score=row["score"],
            tiers=row["tiers"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            submitted_at=_from_iso(row["submitted_at"]),
        )
