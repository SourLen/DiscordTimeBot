"""Data ownership: export, opt-out and moderator resets."""

from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from ..durations import format_duration
from ..ui import ACCENT, channel_label, error_embed

log = logging.getLogger(__name__)


def _iso(timestamp: int | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


class Data(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = bot.config  # type: ignore[attr-defined]
        self.storage = bot.storage  # type: ignore[attr-defined]

    @app_commands.command(
        name="export", description="Download your tracked sessions as CSV."
    )
    @app_commands.guild_only()
    async def export(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        rows = await self.storage.export_sessions(guild.id, interaction.user.id)
        if not rows:
            await interaction.followup.send(
                embed=error_embed("You have no tracked sessions in this server."),
                ephemeral=True,
            )
            return

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["started_at_utc", "ended_at_utc", "seconds", "channel_id", "channel_name"]
        )
        for row in rows:
            writer.writerow(
                [
                    _iso(row.started_at),
                    _iso(row.ended_at),
                    row.seconds,
                    row.channel_id,
                    channel_label(guild, row.channel_id),
                ]
            )

        buffer.seek(0)
        file = discord.File(
            io.BytesIO(buffer.getvalue().encode("utf-8")),
            filename=f"voice-sessions-{guild.id}-{interaction.user.id}.csv",
        )
        await interaction.followup.send(
            f"{len(rows)} session(s) exported.", file=file, ephemeral=True
        )

    @app_commands.command(
        name="forget",
        description="Delete all of your tracked voice time and stop tracking you.",
    )
    @app_commands.guild_only()
    async def forget(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        guild = interaction.guild
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Delete your voice-time data?",
                description=(
                    "This removes every session recorded for you in "
                    f"**{guild.name}** and stops future tracking.\n"
                    "Use `/trackme` later if you change your mind."
                ),
                colour=discord.Colour.red(),
            ),
            view=_ConfirmForget(self.storage, interaction.user.id, guild.id),
            ephemeral=True,
        )

    @app_commands.command(
        name="trackme", description="Resume voice-time tracking after /forget."
    )
    @app_commands.guild_only()
    async def trackme(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        changed = await self.storage.opt_in(interaction.guild.id, interaction.user.id)
        message = (
            "Tracking re-enabled. Your time starts counting from now."
            if changed
            else "You were already being tracked."
        )
        await interaction.response.send_message(message, ephemeral=True)

        tracking = self.bot.get_cog("Tracking")
        member = interaction.guild.get_member(interaction.user.id)
        if changed and tracking is not None and member is not None:
            await tracking.reconcile_member(member, member.voice)  # type: ignore[attr-defined]

    @app_commands.command(
        name="resetmember",
        description="Delete a member's tracked voice time (moderators only).",
    )
    @app_commands.describe(member="The member whose data should be deleted.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def resetmember(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        assert interaction.guild is not None
        deleted = await self.storage.reset_member(interaction.guild.id, member.id)
        await interaction.response.send_message(
            f"Deleted {deleted} session(s) for {member.display_name}.", ephemeral=True
        )

    @app_commands.command(
        name="botinfo", description="Show how this bot is configured and tracking."
    )
    @app_commands.guild_only()
    async def botinfo(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        guild = interaction.guild
        config = self.config

        open_sessions = [
            session
            for session in await self.storage.all_open_sessions()
            if session.guild_id == guild.id
        ]
        afk = guild.afk_channel

        embed = discord.Embed(title="DiscordTimeBot", colour=ACCENT)
        embed.add_field(
            name="Currently tracking", value=f"{len(open_sessions)} member(s)"
        )
        embed.add_field(
            name="Deafened members",
            value="not counted" if config.ignore_deafened else "counted",
        )
        embed.add_field(
            name="AFK channel",
            value=(
                "not configured"
                if afk is None
                else f"{afk.name} ("
                f"{'counted' if config.track_afk_channel else 'not counted'})"
            ),
        )
        excluded = [
            channel_label(guild, channel_id)
            for channel_id in config.excluded_channel_ids
            if guild.get_channel(channel_id) is not None
        ]
        embed.add_field(
            name="Excluded channels",
            value=", ".join(excluded) if excluded else "none",
            inline=False,
        )
        embed.add_field(
            name="Minimum session",
            value=format_duration(config.min_session_seconds),
        )
        embed.add_field(
            name="Milestones",
            value=f"{len(config.milestones)} configured"
            if config.milestones_enabled
            else "disabled",
        )
        embed.add_field(
            name="Weekly digest",
            value="enabled" if config.digest_enabled else "disabled",
        )
        embed.set_footer(text="Use /forget to delete your data at any time.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class _ConfirmForget(discord.ui.View):
    """Two-step confirmation so a misclick cannot wipe a year of history."""

    def __init__(self, storage, user_id: int, guild_id: int) -> None:
        super().__init__(timeout=60)
        self.storage = storage
        self.user_id = user_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This confirmation is not yours.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Delete my data", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        deleted = await self.storage.opt_out(self.guild_id, self.user_id)
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"Deleted {deleted} session(s). You are no longer "
                "being tracked in this server.",
                colour=discord.Colour.green(),
            ),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(
                description="Nothing was deleted.", colour=discord.Colour.greyple()
            ),
            view=None,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Data(bot))
