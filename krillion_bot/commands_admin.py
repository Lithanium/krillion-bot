"""``/krillion admin`` and ``/krillion config`` subgroups.

Result surgery (add/remove/delete/reparse/import), bans, delegated admins and
per-server channel settings. ``/invalidate`` stays as a top-level alias of
``/krillion admin remove``.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .commands import PUZZLE_DESCRIBE, expose
from .discord_util import SERVER_ONLY, reply, resolve_puzzle
from .parser import MAX_DAY_SCORE

if TYPE_CHECKING:
    from .bot import KrillionBot

log = logging.getLogger(__name__)

IMPORT_LIMIT = 5000
CHANNEL_KEYS = {
    "results": "results_channel",
    "leaderboard": "leaderboard_channel",
    "weekly": "weekly_channel",
}
CHANNEL_CHOICES = [
    app_commands.Choice(name="Results are read from", value="results"),
    app_commands.Choice(name="Daily leaderboard is posted to", value="leaderboard"),
    app_commands.Choice(name="Weekly recap is posted to", value="weekly"),
]


def register(bot: KrillionBot, parent: app_commands.Group) -> None:
    tree = bot.tree
    service = bot.service
    storage = service.storage
    calendar = service.calendar
    admin = app_commands.Group(
        name="admin", description="[Admin] Fix results, ban divers, import history.", parent=parent
    )
    config = app_commands.Group(
        name="config", description="[Admin] Channel settings for this server.", parent=parent
    )

    async def gate(interaction: discord.Interaction) -> int | None:
        """The guild id if this is an admin in a server, else ``None`` after replying."""
        guild_id = interaction.guild_id
        if guild_id is None:
            await reply(interaction, SERVER_ONLY, ephemeral=True)
            return None
        if not bot.is_admin(interaction.user, guild_id):
            await reply(interaction, "Only Krillion admins can do that.", ephemeral=True)
            return None
        return guild_id

    # -- results ---------------------------------------------------------

    @app_commands.describe(
        member="Whose score to remove",
        puzzle=PUZZLE_DESCRIBE["puzzle"],
        reason="Shown in the confirmation message",
        date=PUZZLE_DESCRIBE["date"],
    )
    async def remove(
        interaction: discord.Interaction,
        member: discord.Member,
        puzzle: int | None = None,
        reason: str | None = None,
        date: str | None = None,
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        n, error = resolve_puzzle(calendar, bot.now(), puzzle, date)
        if n is None:
            await reply(interaction, error or "Bad puzzle.", ephemeral=True)
            return
        outcome = service.invalidate(guild_id, n, member.id)
        if outcome is None:
            await reply(
                interaction,
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
            text += f"\nRatings recalculated across {outcome.replayed_days} closed day(s)."
        else:
            text += " They can post a corrected result."
        log.info(
            "Admin %s invalidated puzzle #%d for user %s in guild %s",
            interaction.user.id,
            n,
            member.id,
            guild_id,
        )
        await reply(interaction, text)

    expose(
        admin,
        tree,
        remove,
        name="remove",
        description="[Admin] Remove a misreported score.",
        legacy="invalidate",
    )

    @app_commands.describe(
        member="Who the score belongs to",
        score=f"Day score, 0–{MAX_DAY_SCORE}",
        puzzle=PUZZLE_DESCRIBE["puzzle"],
        date=PUZZLE_DESCRIBE["date"],
        tiers="Emoji result row from the share (optional)",
    )
    async def add(
        interaction: discord.Interaction,
        member: discord.Member,
        score: app_commands.Range[int, 0, MAX_DAY_SCORE],
        puzzle: int | None = None,
        date: str | None = None,
        tiers: str = "",
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        now = bot.now()
        n, error = resolve_puzzle(calendar, now, puzzle, date)
        if n is None:
            await reply(interaction, error or "Bad puzzle.", ephemeral=True)
            return
        if n > calendar.current(now):
            await reply(interaction, f"Krillion #{n} isn't out yet.", ephemeral=True)
            return
        outcome = service.add_manual(
            guild_id=guild_id,
            user_id=member.id,
            display_name=member.display_name,
            puzzle_number=n,
            score=score,
            tiers=tiers.strip(),
            channel_id=interaction.channel_id or 0,
            now=now,
        )
        if outcome is None:
            await reply(
                interaction,
                f"**{member.display_name}** already has a Krillion #{n} result; remove it first.",
                ephemeral=True,
            )
            return
        text = f"➕ Added Krillion #{n} score **{score}** for **{member.display_name}**."
        if outcome.replayed_days:
            text += f"\nRatings recalculated across {outcome.replayed_days} closed day(s)."
        await reply(interaction, text)

    expose(admin, tree, add, name="add", description="[Admin] Record a score by hand.")

    @app_commands.describe(
        start="First puzzle number to wipe",
        end="Last puzzle number to wipe (default: same as start)",
    )
    async def delete(interaction: discord.Interaction, start: int, end: int | None = None) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        low, high = sorted((start, end if end is not None else start))
        outcome = service.delete_puzzles(guild_id, low, high)
        span = f"#{low}" if low == high else f"#{low}–#{high}"
        if not outcome.removed:
            await reply(interaction, f"No results stored for Krillion {span}.", ephemeral=True)
            return
        text = f"🗑️ Deleted {outcome.removed} result(s) for Krillion {span}."
        if outcome.recomputed:
            text += f"\nRatings recalculated across {outcome.replayed_days} closed day(s)."
        log.info("Admin %s deleted %s in guild %s", interaction.user.id, span, guild_id)
        await reply(interaction, text)

    expose(
        admin,
        tree,
        delete,
        name="delete",
        description="[Admin] Wipe every result for a puzzle or range of puzzles.",
    )

    async def recompute(interaction: discord.Interaction) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        await interaction.response.defer(thinking=True)
        days = service.replay(guild_id, bot.now())
        await interaction.followup.send(f"♻️ Ratings recomputed across {days} closed day(s).")

    expose(
        admin, tree, recompute, name="recompute", description="[Admin] Replay every day's rating."
    )

    @app_commands.describe(**PUZZLE_DESCRIBE)
    async def reparse(
        interaction: discord.Interaction, puzzle: int | None = None, date: str | None = None
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        n, error = resolve_puzzle(calendar, bot.now(), puzzle, date)
        if n is None:
            await reply(interaction, error or "Bad puzzle.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        changed = 0
        for parsed, r in await bot.refetch_results(guild_id, n):
            if parsed is not None and parsed.puzzle_number == n:
                changed += service.correct(guild_id, n, r.user_id, parsed.score, parsed.tiers)
        text = f"🔎 Re-read Krillion #{n}: {changed} result(s) changed."
        if changed and storage.is_finalized(guild_id, n):
            text += f" Ratings recalculated across {service.replay(guild_id)} closed day(s)."
        await interaction.followup.send(text)

    expose(
        admin,
        tree,
        reparse,
        name="reparse",
        description="[Admin] Re-read a day's original share messages.",
    )

    @app_commands.describe(
        channel="Channel to scan for Krillion shares",
        limit=f"How many messages back to read (default {IMPORT_LIMIT})",
    )
    async def import_history(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: app_commands.Range[int, 1, 50000] = IMPORT_LIMIT,
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        await interaction.response.defer(thinking=True)
        added = await bot.import_channel(guild_id, channel, limit)
        days = service.replay(guild_id, bot.now())
        await interaction.followup.send(
            f"📥 Imported {added} new result(s) from {channel.mention}; "
            f"ratings recomputed across {days} closed day(s)."
        )

    expose(
        admin,
        tree,
        import_history,
        name="import",
        description="[Admin] Backfill results from a channel's history.",
    )

    async def export(interaction: discord.Interaction) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        names = {p.user_id: p.display_name for p in storage.players(guild_id)}
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["puzzle", "date", "user_id", "name", "score", "tiers", "submitted_at"])
        for r in storage.results_between(guild_id):
            writer.writerow(
                [
                    r.puzzle_number,
                    calendar.date_for(r.puzzle_number).isoformat(),
                    r.user_id,
                    names.get(r.user_id, ""),
                    r.score,
                    r.tiers,
                    r.submitted_at.isoformat(),
                ]
            )
        data = io.BytesIO(buf.getvalue().encode("utf-8"))
        await interaction.response.send_message(
            "📤 Every stored Krillion result.",
            file=discord.File(data, filename=f"krillion-{guild_id}.csv"),
            ephemeral=True,
        )

    expose(admin, tree, export, name="export", description="[Admin] Download all results as CSV.")

    # -- people ----------------------------------------------------------

    @app_commands.describe(member="Who to ban", reason="Why (optional)")
    async def ban(
        interaction: discord.Interaction, member: discord.Member, reason: str | None = None
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        if not storage.ban(guild_id, member.id, interaction.user.id, reason, bot.now()):
            await reply(
                interaction, f"**{member.display_name}** is already banned.", ephemeral=True
            )
            return
        text = f"🚫 **{member.display_name}** is banned from Krillion tracking."
        if reason:
            text += f"\nReason: {reason}"
        await reply(interaction, text)

    @app_commands.describe(member="Who to unban")
    async def unban(interaction: discord.Interaction, member: discord.Member) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        if not storage.unban(guild_id, member.id):
            await reply(interaction, f"**{member.display_name}** isn't banned.", ephemeral=True)
            return
        await reply(interaction, f"✅ **{member.display_name}** can share Krillion results again.")

    async def bans(interaction: discord.Interaction) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        rows = storage.bans(guild_id)
        if not rows:
            await reply(interaction, "Nobody is banned. 🦐", ephemeral=True)
            return
        lines = ["**Banned from Krillion tracking**"]
        for b in rows:
            why = f" — {b.reason}" if b.reason else ""
            lines.append(f"<@{b.user_id}> (by <@{b.banned_by}>, {b.banned_at:%Y-%m-%d}){why}")
        await reply(interaction, "\n".join(lines), ephemeral=True)

    expose(
        admin, tree, ban, name="ban", description="[Admin] Block a diver's results and hide them."
    )
    expose(admin, tree, unban, name="unban", description="[Admin] Lift a ban.")
    expose(admin, tree, bans, name="bans", description="[Admin] List banned divers.")

    @app_commands.describe(action="What to do", member="Who (not needed for list)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="list", value="list"),
        ]
    )
    async def admins(
        interaction: discord.Interaction, action: str, member: discord.Member | None = None
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        if action == "list" or member is None:
            who = ", ".join(f"<@{a}>" for a in sorted(bot.admin_ids(guild_id))) or "_none_"
            await reply(interaction, f"Krillion admins: {who}", ephemeral=True)
            return
        if action == "add":
            done = storage.add_admin(guild_id, member.id)
            verb = "is now" if done else "was already"
        else:
            done = storage.remove_admin(guild_id, member.id)
            verb = "is no longer" if done else "wasn't"
        await reply(interaction, f"**{member.display_name}** {verb} a Krillion admin.")

    expose(admin, tree, admins, name="admins", description="[Admin] Manage delegated admins.")

    # -- config ----------------------------------------------------------

    @app_commands.describe(
        setting="Which channel setting", channel="The channel (leave empty to clear)"
    )
    @app_commands.choices(setting=CHANNEL_CHOICES)
    async def channel(
        interaction: discord.Interaction,
        setting: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        key = CHANNEL_KEYS[setting]
        storage.set_setting(guild_id, key, str(channel.id) if channel else None)
        label = next(c.name for c in CHANNEL_CHOICES if c.value == setting)
        where = channel.mention if channel else "_default_"
        await reply(interaction, f"⚙️ {label}: {where}")

    expose(config, tree, channel, name="channel", description="[Admin] Set or clear a channel.")
