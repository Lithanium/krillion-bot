"""``/krillion`` slash-command group: the public commands.

Admin and config subgroups live in :mod:`commands_admin`.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from . import analytics
from .charts import rating_chart
from .discord_util import (
    alert,
    board_message,
    guild_of,
    info,
    ok,
    png_file,
    reply,
    resolve_puzzle,
    send_pages,
    send_plot,
)
from .formatting import final_table, live_table, ratings_table
from .plot_stats import stats_plot
from .service import MAX_INACTIVE_DAYS, SubmitStatus
from .views import (
    TIMEFRAME_LABEL,
    history_pages,
    rating_embed,
    settings_embed,
    skips_pages,
    streak_embed,
    top_pages,
    vs_pages,
)

if TYPE_CHECKING:
    from .bot import KrillionBot

TIMEFRAME_CHOICES = [
    app_commands.Choice(name=label, value=value) for value, label in TIMEFRAME_LABEL.items()
]

PUZZLE_DESCRIBE = {
    "puzzle": "Puzzle number, e.g. 58 (default: today's)",
    "date": "Puzzle date as YYYY-MM-DD (instead of a number)",
}


def register(bot: KrillionBot) -> app_commands.Group:
    service = bot.service
    storage = service.storage
    calendar = service.calendar
    group = app_commands.Group(
        name="krillion",
        description="Krillion daily puzzle: results, ratings and stats.",
        guild_only=True,
    )

    def names_for(guild_id: int) -> dict[int, str]:
        return {p.user_id: p.display_name for p in storage.players(guild_id)}

    def today() -> date:
        return calendar.date_for(calendar.current(bot.now()))

    # -- boards ----------------------------------------------------------

    @group.command(description="Today's Krillion scores (or a past puzzle).")
    @app_commands.describe(**PUZZLE_DESCRIBE)
    async def leaderboard(
        interaction: discord.Interaction, puzzle: int | None = None, date: str | None = None
    ) -> None:
        guild_id = guild_of(interaction)
        now = bot.now()
        n, error = resolve_puzzle(calendar, now, puzzle, date)
        if n is None:
            await reply(interaction, alert(error or "Bad puzzle."), ephemeral=True)
            return
        if storage.is_finalized(guild_id, n):
            entries = storage.history_for(guild_id, n)
            players = {
                p.user_id: p for p in storage.players(guild_id, [e.user_id for e in entries])
            }
            tiers = {r.user_id: r.tiers for r in storage.results_for(guild_id, n)}
            board = final_table(n, calendar.date_for(n), entries, players, tiers)
            await interaction.response.send_message(**board_message(board, f"krillion-{n}.png"))
            return
        results = storage.results_for(guild_id, n)
        if not results:
            await reply(interaction, info(f"No results for Krillion #{n} yet."))
            return
        players = {p.user_id: p for p in storage.players(guild_id, [r.user_id for r in results])}
        reset_unix = (
            int(service.next_finalize_at(now).timestamp()) if n == calendar.current(now) else None
        )
        outcome = service.rate_day(guild_id, n, results)
        board = live_table(
            n,
            results,
            players,
            deltas=outcome.deltas,
            performances=outcome.performances,
            reset_unix=reset_unix,
        )
        await interaction.response.send_message(**board_message(board, f"krillion-{n}-live.png"))

    @group.command(description="Krillion rating rankings for this server.")
    @app_commands.describe(inactive=f"Also list divers idle for {MAX_INACTIVE_DAYS}+ days")
    async def ratings(interaction: discord.Interaction, inactive: bool = False) -> None:
        guild_id = guild_of(interaction)
        players = service.ranked_players(guild_id, bot.now(), inactive)
        table = ratings_table(players, storage.games_played(guild_id))
        if table is None:
            await reply(interaction, info("No rated divers yet — finish a day first."))
            return
        await interaction.response.send_message(**board_message(table, "krillion-ratings.png"))

    @group.command(description="Who wins the most Krillion days.")
    @app_commands.describe(
        timeframe="Which puzzles to count (default: all time)",
        ties="Rank by total wins including shared days",
    )
    @app_commands.choices(timeframe=TIMEFRAME_CHOICES)
    async def top(
        interaction: discord.Interaction, timeframe: str = "all", ties: bool = False
    ) -> None:
        guild_id = guild_of(interaction)
        low, high = analytics.puzzle_range(calendar, timeframe, today())
        hidden = storage.hidden_users(guild_id)
        rows = [r for r in storage.results_between(guild_id, low, high) if r.user_id not in hidden]
        entries = analytics.top(rows, count_ties=ties)
        if not entries:
            await reply(
                interaction, info(f"No contested Krillion days {TIMEFRAME_LABEL[timeframe]}.")
            )
            return
        await send_pages(
            interaction, top_pages(entries, names_for(guild_id), TIMEFRAME_LABEL[timeframe], ties)
        )

    # -- personal --------------------------------------------------------

    @group.command(description="Krillion stats for you or another diver.")
    @app_commands.describe(member="Whose stats (default: you)")
    async def stats(interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        guild_id = guild_of(interaction)
        target = member or interaction.user
        player = storage.get_player(guild_id, target.id)
        rows = storage.results_for_user(guild_id, target.id)
        if player is None or not rows:
            await reply(
                interaction,
                alert(f"`{target.display_name}` hasn't shared a Krillion result yet."),
                ephemeral=True,
            )
            return
        summary = analytics.summarize(
            target.id,
            storage.results_between(guild_id),
            storage.history_for_user(guild_id, target.id),
            calendar,
            calendar.current(bot.now()),
        )
        await send_plot(
            interaction,
            "krillion-stats.png",
            stats_plot,
            player.display_name,
            summary,
            rows,
            calendar,
            today(),
        )

    async def rating_like(
        interaction: discord.Interaction, member: discord.Member | None, performance: bool
    ) -> None:
        guild_id = guild_of(interaction)
        target = member or interaction.user
        history = storage.history_for_user(guild_id, target.id)
        name = target.display_name
        if not history:
            await reply(interaction, alert(f"`{name}` has no rated Krillion days yet."))
            return
        summary = analytics.summarize(target.id, [], history, calendar, calendar.current(bot.now()))
        await interaction.response.defer()
        png = await asyncio.to_thread(
            rating_chart, name, history, calendar, performances=performance
        )
        if png is None:
            await interaction.followup.send(
                embed=alert(f"`{name}` has no contested Krillion days to plot yet.")
            )
            return
        contested = [e for e in history if e.performance is not None]
        games = len(contested) if performance else len(history)
        embed = rating_embed(name, summary, games, performance=performance)
        file = png_file(png, "krillion-rating.png")
        embed.set_image(url=f"attachment://{file.filename}")
        await interaction.followup.send(embed=embed, file=file)

    @group.command(description="Rating graph for a diver.")
    @app_commands.describe(member="Whose rating (default: you)")
    async def rating(
        interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        await rating_like(interaction, member, performance=False)

    @group.command(description="Rating graph with each day's performance marked.")
    @app_commands.describe(member="Whose performances (default: you)")
    async def performance(
        interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        await rating_like(interaction, member, performance=True)

    @group.command(description="A diver's rated days, newest first.")
    @app_commands.describe(member="Whose history (default: you)", page="Page number")
    async def history(
        interaction: discord.Interaction, member: discord.Member | None = None, page: int = 1
    ) -> None:
        target = member or interaction.user
        entries = storage.history_for_user(guild_of(interaction), target.id)
        if not entries:
            await reply(
                interaction, info(f"`{target.display_name}` has no rated Krillion days yet.")
            )
            return
        await send_pages(
            interaction, history_pages(target.display_name, entries, calendar), page=page
        )

    @group.command(description="Current and longest daily streaks.")
    @app_commands.describe(member="Whose streak (default: you)")
    async def streak(
        interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        rows = storage.results_for_user(guild_of(interaction), target.id)
        current = calendar.current(bot.now())
        play = analytics.streaks((r.puzzle_number for r in rows), current)
        perfect = analytics.streaks(analytics.perfect_puzzles(rows), current)
        await reply(interaction, streak_embed(target.display_name, play, perfect))

    @group.command(description="Puzzles a diver missed since they started.")
    @app_commands.describe(member="Whose skips (default: you)")
    async def skips(interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        target = member or interaction.user
        rows = storage.results_for_user(guild_of(interaction), target.id)
        first, skipped = analytics.skipped_puzzles(
            (r.puzzle_number for r in rows), calendar.current(bot.now())
        )
        await send_pages(interaction, skips_pages(target.display_name, first, skipped, calendar))

    # -- comparisons -----------------------------------------------------

    @group.command(description="Head-to-head record between divers.")
    @app_commands.describe(
        player1="First diver",
        player2="Second diver",
        player3="Third diver (optional)",
        player4="Fourth diver (optional)",
        timeframe="Which puzzles to compare (default: all time)",
        missing="Count a puzzle someone skipped as a loss for them",
    )
    @app_commands.choices(timeframe=TIMEFRAME_CHOICES)
    async def vs(
        interaction: discord.Interaction,
        player1: discord.Member,
        player2: discord.Member,
        player3: discord.Member | None = None,
        player4: discord.Member | None = None,
        timeframe: str = "all",
        missing: bool = False,
    ) -> None:
        guild_id = guild_of(interaction)
        members = [m for m in (player1, player2, player3, player4) if m is not None]
        ids = [m.id for m in members]
        if len(set(ids)) != len(ids):
            await reply(interaction, alert("Pick different divers to compare."), ephemeral=True)
            return
        low, high = analytics.puzzle_range(calendar, timeframe, today())
        rows = {uid: storage.results_for_user(guild_id, uid, low, high) for uid in ids}
        outcome = analytics.head_to_head(rows, missing_is_loss=missing)
        if outcome.puzzles == 0:
            await reply(interaction, info(f"No puzzles in common {TIMEFRAME_LABEL[timeframe]}."))
            return
        names = {m.id: m.display_name for m in members}
        await send_pages(
            interaction, vs_pages(outcome, names, TIMEFRAME_LABEL[timeframe], missing, rows)
        )

    @group.command(description="Weekly recap: daily winners and standings.")
    @app_commands.describe(when="A date in the week (YYYY-MM-DD) or 'last' (default: this week)")
    async def week(interaction: discord.Interaction, when: str | None = None) -> None:
        guild_id = guild_of(interaction)
        now_day = today()
        if when is None:
            anchor = now_day
        elif when.lower() == "last":
            anchor = now_day - timedelta(days=7)
        else:
            try:
                anchor = date.fromisoformat(when)
            except ValueError:
                await reply(
                    interaction, alert(f"`{when}` is not a date (`YYYY-MM-DD`)."), ephemeral=True
                )
                return
        recap = bot.week_recap(guild_id, anchor, now_day)
        if recap.results == 0:
            await reply(
                interaction, info(f"No Krillion results for the week of {recap.start:%b %d, %Y}.")
            )
            return
        await interaction.response.defer()
        await interaction.followup.send(
            file=await bot.week_image(guild_id, recap, interaction.user.id)
        )

    # -- participation ---------------------------------------------------

    @group.command(description="Which Krillion puzzle is live and when it resets.")
    async def puzzle(interaction: discord.Interaction) -> None:
        now = bot.now()
        n = calendar.current(now)
        reset = int(calendar.next_reset(now).timestamp())
        await reply(
            interaction, info(f"Krillion **#{n}** is live. Resets <t:{reset}:t> (<t:{reset}:R>).")
        )

    @group.command(description="Record a 0 for today so it counts.")
    async def giveup(interaction: discord.Interaction) -> None:
        outcome = service.give_up(
            guild_id=guild_of(interaction),
            user_id=interaction.user.id,
            display_name=interaction.user.display_name,
            channel_id=interaction.channel_id or 0,
            now=bot.now(),
        )
        n = outcome.current_puzzle
        if outcome.status is SubmitStatus.ACCEPTED:
            await reply(
                interaction,
                ok(
                    f"Recorded a give-up (score 0) for `{interaction.user.display_name}` "
                    f"on Krillion #{n}."
                ),
            )
        elif outcome.status is SubmitStatus.DUPLICATE and outcome.existing is not None:
            await reply(
                interaction,
                alert(f"You already have a Krillion #{n} result ({outcome.existing.score})."),
                ephemeral=True,
            )
        elif outcome.status is SubmitStatus.BANNED:
            await reply(
                interaction, alert("You're banned from Krillion tracking here."), ephemeral=True
            )
        else:
            await reply(
                interaction, alert(f"Krillion #{n} isn't accepting results."), ephemeral=True
            )

    @group.command(description="Show yourself on public boards.")
    async def register(interaction: discord.Interaction) -> None:
        if storage.opt_in(guild_of(interaction), interaction.user.id):
            await reply(interaction, ok("You're back on the public Krillion boards."))
        else:
            await reply(
                interaction, alert("You're already on the public Krillion boards."), ephemeral=True
            )

    @group.command(description="Hide yourself from the ratings and winners boards.")
    async def unregister(interaction: discord.Interaction) -> None:
        if storage.opt_out(guild_of(interaction), interaction.user.id, bot.now()):
            await reply(
                interaction,
                ok(
                    "You're hidden from the ratings and winners boards. Your results still "
                    "count; `/krillion register` undoes this."
                ),
                ephemeral=True,
            )
        else:
            await reply(
                interaction, alert("You're already hidden from the boards."), ephemeral=True
            )

    @group.command(description="How Krillion is configured here.")
    async def show(interaction: discord.Interaction) -> None:
        guild_id = guild_of(interaction)
        await reply(
            interaction,
            settings_embed(
                bot.channel_setting(guild_id, "results_channel"),
                bot.channel_setting(guild_id, "leaderboard_channel"),
                bot.channel_setting(guild_id, "weekly_channel"),
                sorted(bot.admin_ids(guild_id)),
                len(storage.bans(guild_id)),
                len(storage.opted_out(guild_id)),
                calendar.current(bot.now()),
                today(),
            ),
            ephemeral=True,
        )

    bot.tree.add_command(group)
    return group
