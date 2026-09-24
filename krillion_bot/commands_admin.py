"""``/krillion admin`` subgroup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .discord_util import alert, guild_of, ok, reply

if TYPE_CHECKING:
    from .bot import KrillionBot


def register(bot: KrillionBot, parent: app_commands.Group) -> None:
    storage = bot.service.storage
    admin = app_commands.Group(
        name="admin", description="[Admin] Ban and unban divers.", parent=parent
    )

    async def gate(interaction: discord.Interaction) -> int | None:
        """The guild id if the caller is an admin, else ``None`` after replying."""
        guild_id = guild_of(interaction)
        if not bot.is_admin(interaction.user, guild_id):
            await reply(interaction, alert("Only Krillion admins can do that."), ephemeral=True)
            return None
        return guild_id

    # -- people ----------------------------------------------------------

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
        if reason:
            text += f"\nReason: {reason}"
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
