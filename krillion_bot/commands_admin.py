"""``/krillion admin`` subgroup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .commands import PUZZLE_DESCRIBE
from .discord_util import alert, guild_of, ok, reply, resolve_puzzle
from .service import MAX_OVERRIDE_RATING, MIN_OVERRIDE_RATING

if TYPE_CHECKING:
    from .bot import KrillionBot


def register(bot: KrillionBot, parent: app_commands.Group) -> None:
    service = bot.service
    storage = service.storage
    calendar = service.calendar
    admin = app_commands.Group(
        name="admin", description="[Admin] Manage diver results, bans, and ratings.", parent=parent
    )

    async def gate(interaction: discord.Interaction) -> int | None:
        """The guild id if the caller is an admin, else ``None`` after replying."""
        guild_id = guild_of(interaction)
        if not bot.is_admin(interaction.user, guild_id):
            await reply(interaction, alert("Only Krillion admins can do that."), ephemeral=True)
            return None
        return guild_id

    # -- people ----------------------------------------------------------

    @app_commands.describe(
        member="Whose rating to set", rating="New rating", reason="Why (optional)"
    )
    @admin.command(description="[Admin] Override a diver's rating until their next rated day.")
    async def setrating(
        interaction: discord.Interaction,
        member: discord.Member,
        rating: app_commands.Range[float, MIN_OVERRIDE_RATING, MAX_OVERRIDE_RATING],
        reason: str | None = None,
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        try:
            change = service.set_rating_override(
                guild_id,
                member.id,
                member.display_name,
                rating,
                interaction.user.id,
                reason,
                bot.now(),
            )
        except ValueError as error:
            await reply(interaction, alert(str(error)), ephemeral=True)
            return
        text = (
            f"Set `{member.display_name}`'s rating "
            f"{change.old_rating:.0f} → {change.new_rating:.0f}."
        )
        if reason:
            text += f"\nReason: {reason}"
        await reply(interaction, ok(text))

    @app_commands.describe(member="Whose rating overrides to clear")
    @admin.command(description="[Admin] Clear a diver's overrides and recompute ratings.")
    async def clearrating(interaction: discord.Interaction, member: discord.Member) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        change = service.clear_rating_overrides(guild_id, member.id)
        await reply(
            interaction,
            ok(
                f"Cleared `{member.display_name}`'s rating overrides: "
                f"{change.old_rating:.0f} → {change.new_rating:.0f}.\n"
                f"Ratings replayed across {change.replayed_days} closed day(s)."
            ),
        )

    @app_commands.describe(member="Who to ban", reason="Why (optional)")
    @admin.command(description="[Admin] Block a diver's results and hide them.")
    async def ban(
        interaction: discord.Interaction, member: discord.Member, reason: str | None = None
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        if not storage.ban(guild_id, member.id, interaction.user.id, reason, bot.now()):
            await reply(
                interaction, alert(f"`{member.display_name}` is already banned."), ephemeral=True
            )
            return
        text = f"Banned `{member.display_name}` from Krillion tracking."
        outcome = service.invalidate(guild_id, calendar.current(bot.now()), member.id)
        if outcome is not None:
            text += (
                f"\nRemoved their Krillion #{outcome.removed.puzzle_number} result "
                f"({outcome.removed.score} pts)."
            )
            if outcome.replayed_days:
                text += f"\nRatings replayed across {outcome.replayed_days} closed day(s)."
            else:
                text += " They can post a corrected result."
        if reason:
            text += f"\nReason: {reason}"
        await reply(interaction, ok(text))

    @app_commands.describe(
        member="Whose result to remove",
        **PUZZLE_DESCRIBE,
        reason="Shown in the confirmation",
    )
    @admin.command(description="[Admin] Remove a diver's result for a day.")
    async def invalidate(
        interaction: discord.Interaction,
        member: discord.Member,
        puzzle: int | None = None,
        date: str | None = None,
        reason: str | None = None,
    ) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        n, error = resolve_puzzle(calendar, bot.now(), puzzle, date)
        if n is None:
            await reply(interaction, alert(error or "Bad puzzle."), ephemeral=True)
            return
        outcome = service.invalidate(guild_id, n, member.id)
        if outcome is None:
            await reply(
                interaction,
                alert(f"`{member.display_name}` has no Krillion #{n} result."),
                ephemeral=True,
            )
            return
        text = (
            f"Removed `{member.display_name}`'s Krillion #{n} result ({outcome.removed.score} pts)."
        )
        if reason:
            text += f"\nReason: {reason}"
        if outcome.replayed_days:
            text += f"\nRatings replayed across {outcome.replayed_days} closed day(s)."
        else:
            text += " They can post a corrected result."
        await reply(interaction, ok(text))

    @app_commands.describe(member="Who to unban")
    @admin.command(description="[Admin] Lift a diver's ban.")
    async def unban(interaction: discord.Interaction, member: discord.Member) -> None:
        guild_id = await gate(interaction)
        if guild_id is None:
            return
        if not storage.unban(guild_id, member.id):
            await reply(
                interaction, alert(f"`{member.display_name}` is not banned."), ephemeral=True
            )
            return
        await reply(
            interaction, ok(f"Unbanned `{member.display_name}`; their results count again.")
        )
