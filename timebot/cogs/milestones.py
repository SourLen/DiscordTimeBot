"""Milestone roles: grant a role once a member crosses a voice-time threshold.

Configured through the ``MILESTONES`` environment variable, e.g.::

    MILESTONES=10h=Regular,100h=Veteran,500h=Voice Gremlin

Roles are looked up by name and must already exist and sit below the bot's own
top role; the bot never creates or reorders roles on its own.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..durations import format_duration
from ..ui import ACCENT, error_embed

log = logging.getLogger(__name__)


class Milestones(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = bot.config  # type: ignore[attr-defined]
        self.storage = bot.storage  # type: ignore[attr-defined]

    # ----------------------------------------------------------------- grants

    async def check_member(self, member: discord.Member) -> list[str]:
        """Grant any newly earned milestone roles. Returns the role names given."""
        if not self.config.milestones_enabled or member.bot:
            return []

        guild = member.guild
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return []

        total = await self.storage.total_for(guild.id, member.id)
        already = await self.storage.granted_milestones(guild.id, member.id)
        granted: list[str] = []

        for milestone in self.config.milestones:
            if milestone.seconds > total or milestone.seconds in already:
                continue

            role = discord.utils.get(guild.roles, name=milestone.role_name)
            if role is None:
                log.warning(
                    "Milestone role %r does not exist in guild %s",
                    milestone.role_name,
                    guild.id,
                )
                continue
            if role >= me.top_role:
                log.warning(
                    "Cannot assign %r in guild %s: role is not below the bot's top role",
                    role.name,
                    guild.id,
                )
                continue

            if role not in member.roles:
                try:
                    await member.add_roles(
                        role,
                        reason=f"Voice-time milestone: "
                        f"{format_duration(milestone.seconds, max_units=3)}",
                    )
                except discord.HTTPException:
                    log.exception("Failed to grant %r to %s", role.name, member.id)
                    continue
                granted.append(role.name)

            await self.storage.record_milestone(guild.id, member.id, milestone.seconds)

        return granted

    # --------------------------------------------------------------- commands

    @app_commands.command(
        name="milestones",
        description="Show the voice-time milestones and your progress.",
    )
    @app_commands.describe(member="Whose progress to show (defaults to you).")
    @app_commands.guild_only()
    async def milestones(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        assert interaction.guild is not None
        if not self.config.milestones_enabled:
            await interaction.response.send_message(
                embed=error_embed(
                    "No milestones are configured. Set `MILESTONES` in the "
                    "bot's environment, e.g. `10h=Regular,100h=Veteran`."
                ),
                ephemeral=True,
            )
            return

        target = member or interaction.user
        total = await self.storage.total_for(interaction.guild.id, target.id)

        lines = []
        next_up: tuple[int, str] | None = None
        for milestone in self.config.milestones:
            reached = total >= milestone.seconds
            mark = "✅" if reached else "▫️"
            threshold = format_duration(milestone.seconds, max_units=2)
            lines.append(f"{mark} `{threshold:>6}` — **{milestone.role_name}**")
            if not reached and next_up is None:
                next_up = (milestone.seconds - total, milestone.role_name)

        embed = discord.Embed(
            title=f"Milestones — {target.display_name}",
            description="\n".join(lines),
            colour=ACCENT,
        )
        embed.add_field(
            name="Voice time", value=format_duration(total, max_units=3), inline=True
        )
        if next_up is not None:
            remaining, role_name = next_up
            embed.add_field(
                name="Next role",
                value=f"{role_name} in {format_duration(remaining, max_units=2)}",
                inline=True,
            )
        else:
            embed.add_field(name="Next role", value="All milestones reached 🎉")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="syncroles",
        description="Re-check milestone roles for every tracked member.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def syncroles(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not self.config.milestones_enabled:
            await interaction.response.send_message(
                embed=error_embed("No milestones are configured."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        rows = await self.storage.leaderboard(guild.id)

        checked = 0
        granted = 0
        for row in rows:
            member = guild.get_member(row.user_id)
            if member is None:
                continue
            checked += 1
            granted += len(await self.check_member(member))

        await interaction.followup.send(
            f"Checked {checked} member(s), granted {granted} role(s).", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Milestones(bot))
