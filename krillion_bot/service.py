"""Discord-agnostic game logic: accept submissions, close days, run Elo."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .elo import (
    DEFAULT_K,
    PROVISIONAL_GAMES,
    PROVISIONAL_K,
    is_provisional,
    k_factor,
    placements,
    rating_deltas,
)
from .parser import ParsedResult, parse_result
from .puzzle import PuzzleCalendar
from .storage import Player, RatingEntry, Result, Storage


class SubmitStatus(Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    TOO_LATE = "too_late"
    NOT_YET = "not_yet"
    NOT_A_RESULT = "not_a_result"


@dataclass(frozen=True)
class SubmitOutcome:
    status: SubmitStatus
    parsed: ParsedResult | None
    current_puzzle: int
    existing: Result | None = None


@dataclass(frozen=True)
class FinalizedDay:
    guild_id: int
    puzzle_number: int
    channel_id: int
    entries: list[RatingEntry]
    players: dict[int, Player]
    provisional: frozenset[int]
    """Players still provisional after this day."""


class KrillionService:
    def __init__(
        self,
        storage: Storage,
        calendar: PuzzleCalendar | None = None,
        *,
        grace: timedelta = timedelta(minutes=10),
        k: float = DEFAULT_K,
        provisional_k: float = PROVISIONAL_K,
        provisional_games: int = PROVISIONAL_GAMES,
    ) -> None:
        self.storage = storage
        self.calendar = calendar or PuzzleCalendar()
        self.grace = grace
        self.k = k
        self.provisional_k = provisional_k
        self.provisional_games = provisional_games

    def is_provisional(self, games_played: int) -> bool:
        return is_provisional(games_played, self.provisional_games)

    def provisional_players(
        self, guild_id: int, user_ids: Iterable[int], *, as_of_puzzle: int | None = None
    ) -> frozenset[int]:
        """Which of ``user_ids`` are provisional (optionally right after ``as_of_puzzle``)."""
        games = self.storage.games_played(guild_id, as_of_puzzle)
        return frozenset(uid for uid in user_ids if self.is_provisional(games.get(uid, 0)))

    # -- submissions -----------------------------------------------------

    def is_open(self, puzzle_number: int, now: datetime) -> bool:
        """A puzzle accepts results from its start until reset + grace."""
        if now < self.calendar.start(puzzle_number):
            return False
        return now < self.calendar.end(puzzle_number) + self.grace

    def submit(
        self,
        *,
        guild_id: int,
        user_id: int,
        display_name: str,
        text: str,
        channel_id: int,
        message_id: int | None,
        now: datetime,
    ) -> SubmitOutcome:
        current = self.calendar.current(now)
        parsed = parse_result(text)
        if parsed is None:
            return SubmitOutcome(SubmitStatus.NOT_A_RESULT, None, current)
        n = parsed.puzzle_number
        if n > current:
            return SubmitOutcome(SubmitStatus.NOT_YET, parsed, current)
        if not self.is_open(n, now) or self.storage.is_finalized(guild_id, n):
            return SubmitOutcome(SubmitStatus.TOO_LATE, parsed, current)
        self.storage.upsert_player(guild_id, user_id, display_name)
        result = Result(
            guild_id=guild_id,
            puzzle_number=n,
            user_id=user_id,
            score=parsed.score,
            tiers=parsed.tiers,
            channel_id=channel_id,
            message_id=message_id,
            submitted_at=now,
        )
        if not self.storage.add_result(result):
            existing = self.storage.get_result(guild_id, n, user_id)
            return SubmitOutcome(SubmitStatus.DUPLICATE, parsed, current, existing)
        return SubmitOutcome(SubmitStatus.ACCEPTED, parsed, current)

    # -- finalization ----------------------------------------------------

    def next_finalize_at(self, now: datetime) -> datetime:
        return self.calendar.next_reset(now) + self.grace

    def due_puzzles(self, now: datetime) -> list[tuple[int, int]]:
        return [
            (guild_id, n)
            for guild_id, n in self.storage.unfinalized_puzzles()
            if not self.is_open(n, now)
        ]

    def finalize(self, guild_id: int, puzzle_number: int, now: datetime) -> FinalizedDay | None:
        results = self.storage.results_for(guild_id, puzzle_number)
        if not results or self.storage.is_finalized(guild_id, puzzle_number):
            return None
        players = {
            p.user_id: p for p in self.storage.players(guild_id, [r.user_id for r in results])
        }
        scores = {r.user_id: r.score for r in results}
        ratings = {uid: players[uid].rating for uid in scores}
        games = self.storage.games_played(guild_id)
        ks = {
            uid: k_factor(games.get(uid, 0), self.k, self.provisional_k, self.provisional_games)
            for uid in scores
        }
        deltas = rating_deltas(ratings, scores, ks)
        places = placements(scores)
        entries = [
            RatingEntry(
                puzzle_number=puzzle_number,
                user_id=r.user_id,
                score=r.score,
                placement=places[r.user_id],
                rating_before=ratings[r.user_id],
                rating_after=ratings[r.user_id] + deltas[r.user_id],
            )
            for r in results
        ]
        self.storage.finalize(guild_id, puzzle_number, entries, now)
        # Post to the channel the day's results were mostly shared in.
        channel_counts: dict[int, int] = {}
        for r in results:
            channel_counts[r.channel_id] = channel_counts.get(r.channel_id, 0) + 1
        channel_id = max(channel_counts, key=lambda c: channel_counts[c])
        updated = {
            p.user_id: p for p in self.storage.players(guild_id, [r.user_id for r in results])
        }
        provisional = frozenset(uid for uid in scores if self.is_provisional(games.get(uid, 0) + 1))
        return FinalizedDay(guild_id, puzzle_number, channel_id, entries, updated, provisional)

    def finalize_due(self, now: datetime) -> list[FinalizedDay]:
        done: list[FinalizedDay] = []
        for guild_id, n in self.due_puzzles(now):
            day = self.finalize(guild_id, n, now)
            if day is not None:
                done.append(day)
        return done
