from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands

from .config import Config
from .formatting import Board, elo_leaderboard, final_board, live_board
from .puzzle import PuzzleCalendar
from .render import render_board
from .service import FinalizedDay, KrillionService, SubmitStatus
from .storage import Storage

log = logging.getLogger(__name__)

_POLL_CAP = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def board_message(board: Board, filename: str) -> dict[str, Any]:
    """kwargs for ``send``: the board as a PNG attachment, or as text if that fails.

    Notes carrying a Discord timestamp can't go in the image, so they stay as text.
    """
    try:
        png = render_board(board)
    except Exception:
        log.exception("Rendering leaderboard image failed; sending text")
        png = None
    if png is None:
        return {"content": board.text()}
    timed = [n for n in board.notes if "<t:" in n]
    return {
        "content": "\n".join(timed) or None,
        "file": discord.File(io.BytesIO(png), filename=filename),
    }


class KrillionBot(discord.Client):
    def __init__(self, config: Config, service: KrillionService) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = False
        super().__init__(intents=intents)
        self.config = config
        self.service = service
        self.tree = app_commands.CommandTree(self)
        self._register_commands()
        self._scheduler: asyncio.Task[None] | None = None

    # -- lifecycle -------------------------------------------------------

    async def setup_hook(self) -> None:
        await self.tree.sync()
        self._scheduler = asyncio.create_task(self._finalize_loop(), name="finalize-loop")

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info(
            "Logged in as %s (%s); current puzzle #%d",
            self.user,
            self.user.id,
            self.service.calendar.current(_now()),
        )

    async def close(self) -> None:
        if self._scheduler is not None:
            self._scheduler.cancel()
        await super().close()

    def is_admin(self, user: discord.abc.User) -> bool:
        return user.id in self.config.admin_user_ids

    # -- results ingestion ----------------------------------------------

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if (
            self.config.results_channel_id is not None
            and message.channel.id != self.config.results_channel_id
        ):
            return
        outcome = self.service.submit(
            guild_id=message.guild.id,
            user_id=message.author.id,
            display_name=message.author.display_name,
            text=message.content,
            channel_id=message.channel.id,
            message_id=message.id,
            now=message.created_at,
        )
        if outcome.status is SubmitStatus.NOT_A_RESULT:
            if "krillion" in message.content.lower():
                log.info(
                    "Message %s in %s mentions Krillion but did not parse as a result",
                    message.id,
                    message.channel.id,
                )
            return
        assert outcome.parsed is not None
        n = outcome.parsed.puzzle_number
        log.info(
            "Krillion #%d from %s in guild %s: %s (%s)",
            n,
            message.author.id,
            message.guild.id,
            outcome.status.value,
            outcome.parsed.score,
        )
        try:
            if outcome.status is SubmitStatus.ACCEPTED:
                await message.add_reaction("🦐")
                await message.reply(
                    f"Received Krillion #{n} score from **{message.author.display_name}**: "
                    f"{outcome.parsed.score} 🦐",
                    mention_author=False,
                )
            elif outcome.status is SubmitStatus.DUPLICATE:
                assert outcome.existing is not None
                await message.add_reaction("⚠️")
                await message.reply(
                    f"Already have your Krillion #{n} result ({outcome.existing.score}) — "
                    "keeping the first one.",
                    mention_author=False,
                )
            elif outcome.status is SubmitStatus.TOO_LATE:
                await message.add_reaction("⏰")
                await message.reply(
                    f"Krillion #{n} has already closed — today's puzzle is "
                    f"#{outcome.current_puzzle}.",
                    mention_author=False,
                )
            elif outcome.status is SubmitStatus.NOT_YET:
                await message.add_reaction("❓")
                await message.reply(
                    f"Krillion #{n} isn't out yet — today's puzzle is #{outcome.current_puzzle}.",
                    mention_author=False,
                )
        except discord.HTTPException:
            log.exception("Failed to respond to submission in %s", message.channel.id)

    # -- daily close -----------------------------------------------------

    async def _finalize_loop(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                for day in self.service.finalize_due(_now()):
                    await self._announce(day)
            except Exception:
                log.exception("Finalization failed")
            now = _now()
            wake = min(self.service.next_finalize_at(now), now + _POLL_CAP)
            await asyncio.sleep(max(1.0, (wake - now).total_seconds() + 1))

    async def _announce(self, day: FinalizedDay) -> None:
        channel_id = self.config.leaderboard_channel_id or day.channel_id
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.HTTPException:
                log.error("Cannot find channel %s for leaderboard", channel_id)
                return
        if not isinstance(channel, discord.abc.Messageable):
            log.error("Channel %s is not messageable", channel_id)
            return
        tiers = {
            r.user_id: r.tiers
            for r in self.service.storage.results_for(day.guild_id, day.puzzle_number)
        }
        board = final_board(day.puzzle_number, day.entries, day.players, day.provisional, tiers)
        await channel.send(**board_message(board, f"krillion-{day.puzzle_number}.png"))
        log.info("Posted Krillion #%d results for guild %s", day.puzzle_number, day.guild_id)

    # -- slash commands --------------------------------------------------

    def _register_commands(self) -> None:
        tree = self.tree
        service = self.service
        storage = self.service.storage
        calendar: PuzzleCalendar = self.service.calendar

        @tree.command(name="leaderboard", description="Today's Krillion scores (or a past puzzle).")
        @app_commands.describe(puzzle="Puzzle number, e.g. 58 (default: today's)")
        async def leaderboard(interaction: discord.Interaction, puzzle: int | None = None) -> None:
            if interaction.guild_id is None:
                await interaction.response.send_message("Use this in a server.", ephemeral=True)
                return
            now = _now()
            n = puzzle if puzzle is not None else calendar.current(now)
            guild_id = interaction.guild_id
            if storage.is_finalized(guild_id, n):
                entries = storage.history_for(guild_id, n)
                ids = [e.user_id for e in entries]
                players = {p.user_id: p for p in storage.players(guild_id, ids)}
                provisional = service.provisional_players(guild_id, ids, as_of_puzzle=n)
                tiers = {r.user_id: r.tiers for r in storage.results_for(guild_id, n)}
                board = final_board(n, entries, players, provisional, tiers)
                await interaction.response.send_message(**board_message(board, f"krillion-{n}.png"))
                return
            results = storage.results_for(guild_id, n)
            if not results:
                await interaction.response.send_message(f"**Krillion #{n}** — no results yet. 🫧")
                return
            ids = [r.user_id for r in results]
            players = {p.user_id: p for p in storage.players(guild_id, ids)}
            reset_unix = (
                int(service.next_finalize_at(now).timestamp())
                if n == calendar.current(now)
                else None
            )
            board = live_board(
                n,
                results,
                players,
                deltas=service.projected_deltas(guild_id, results),
                provisional=service.provisional_players(guild_id, ids),
                reset_unix=reset_unix,
            )
            await interaction.response.send_message(
                **board_message(board, f"krillion-{n}-live.png")
            )

        @tree.command(name="elo", description="Krillion Elo rankings for this server.")
        async def elo(interaction: discord.Interaction) -> None:
            if interaction.guild_id is None:
                await interaction.response.send_message("Use this in a server.", ephemeral=True)
                return
            players = storage.players(interaction.guild_id)
            games = storage.games_played(interaction.guild_id)
            provisional = service.provisional_players(
                interaction.guild_id, [p.user_id for p in players]
            )
            await interaction.response.send_message(elo_leaderboard(players, games, provisional))

        @tree.command(name="stats", description="Krillion stats for you or another diver.")
        @app_commands.describe(member="Whose stats (default: you)")
        async def stats(
            interaction: discord.Interaction, member: discord.Member | None = None
        ) -> None:
            if interaction.guild_id is None:
                await interaction.response.send_message("Use this in a server.", ephemeral=True)
                return
            target = member or interaction.user
            player = storage.get_player(interaction.guild_id, target.id)
            if player is None:
                await interaction.response.send_message(
                    f"**{target.display_name}** hasn't shared a Krillion result yet. 🫧",
                    ephemeral=True,
                )
                return
            s = storage.stats_for(interaction.guild_id, target.id)
            avg = f"{s.average_score:.0f}" if s.average_score is not None else "—"
            best = str(s.best_score) if s.best_score is not None else "—"
            rating = f"**{round(player.rating)}**"
            if service.is_provisional(s.games):
                rating += f" (provisional, {s.games}/{service.provisional_games} days)"
            await interaction.response.send_message(
                f"**{player.display_name}** 🦐\n"
                f"Elo {rating} · {s.games} played · {s.wins} wins\n"
                f"Best {best} · Average {avg}"
            )

        @tree.command(name="invalidate", description="[Admin] Remove a misreported score.")
        @app_commands.describe(
            member="Whose score to remove",
            puzzle="Puzzle number (default: today's)",
            reason="Shown in the confirmation message",
        )
        async def invalidate(
            interaction: discord.Interaction,
            member: discord.Member,
            puzzle: int | None = None,
            reason: str | None = None,
        ) -> None:
            if interaction.guild_id is None:
                await interaction.response.send_message("Use this in a server.", ephemeral=True)
                return
            if not self.is_admin(interaction.user):
                await interaction.response.send_message(
                    "Only bot admins can invalidate scores.", ephemeral=True
                )
                return
            n = puzzle if puzzle is not None else calendar.current(_now())
            outcome = service.invalidate(interaction.guild_id, n, member.id)
            if outcome is None:
                await interaction.response.send_message(
                    f"**{member.display_name}** has no Krillion #{n} result to remove.",
                    ephemeral=True,
                )
                return
            text = (
                f"🗑️ **{member.display_name}**'s Krillion #{n} score ({outcome.removed.score}) "
                f"was invalidated by {interaction.user.mention}."
            )
            if reason:
                text += f"\nReason: {reason}"
            if outcome.replayed_days:
                text += f"\nElo recalculated across {outcome.replayed_days} closed day(s)."
            else:
                text += " They can post a corrected result."
            log.info(
                "Admin %s invalidated puzzle #%d for user %s in guild %s",
                interaction.user.id,
                n,
                member.id,
                interaction.guild_id,
            )
            await interaction.response.send_message(text)

        @tree.command(name="puzzle", description="Which Krillion puzzle is live and when it resets")
        async def puzzle(interaction: discord.Interaction) -> None:
            now = _now()
            n = calendar.current(now)
            reset = int(calendar.next_reset(now).timestamp())
            await interaction.response.send_message(
                f"Krillion **#{n}** is live. Resets <t:{reset}:t> (<t:{reset}:R>)."
            )


def build(config: Config) -> KrillionBot:
    storage = Storage(config.database_path)
    calendar = PuzzleCalendar(tz=config.puzzle_tz, epoch=config.epoch_date)
    service = KrillionService(
        storage,
        calendar,
        grace=timedelta(minutes=config.late_grace_minutes),
        k=config.elo_k,
        provisional_k=config.provisional_k,
        provisional_games=config.provisional_games,
    )
    return KrillionBot(config, service)
