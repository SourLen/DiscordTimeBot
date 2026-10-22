"""Weekly digest: post last week's leaderboard into a configured channel."""

from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..durations import format_duration
from ..periods import previous_week_window
from ..ui import leaderboard_embed, member_label

log = logging.getLogger(__name__)

DIGEST_META_KEY = "last_digest_week"
CHECK_INTERVAL_SECONDS = 600


class Digest(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = bot.config  # type: ignore[attr-defined]
        self.storage = bot.storage  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        if self.config.digest_enabled:
            self.digest_loop.start()

    async def cog_unload(self) -> None:
        self.digest_loop.cancel()

    # ---------------------------------------------------------------- posting

    def _is_due(self, moment: datetime) -> bool:
        return (
            moment.weekday() == self.config.digest_weekday
            and moment.hour >= self.config.digest_hour
        )

    @staticmethod
    def _week_key(moment: datetime) -> str:
        year, week, _ = moment.isocalendar()
        return f"{year}-W{week:02d}"

    async def build_embed(self, guild: discord.Guild) -> discord.Embed:
        since, until = previous_week_window(self.config.timezone)
        rows = await self.storage.leaderboard(
            guild.id, since=since, until=until, limit=10
        )

        embed = leaderboard_embed(guild, rows, period_label="last week")
        embed.title = "📊 Weekly voice recap"
        if rows:
            total = sum(row.seconds for row in rows)
            embed.add_field(
                name="Top 10 combined",
                value=format_duration(total, max_units=3),
                inline=True,
            )
            embed.add_field(
                name="Member of the week",
                value=member_label(guild, rows[0].user_id),
                inline=True,
            )
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def post_digest(self) -> bool:
        channel = self.bot.get_channel(self.config.digest_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.config.digest_channel_id)
            except discord.HTTPException:
                log.warning(
                    "DIGEST_CHANNEL_ID %s is not reachable",
                    self.config.digest_channel_id,
                )
                return False

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            log.warning("DIGEST_CHANNEL_ID must point at a text channel in a guild")
            return False

        try:
            await channel.send(embed=await self.build_embed(channel.guild))
        except discord.HTTPException:
            log.exception("Failed to post weekly digest")
            return False
        return True

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def digest_loop(self) -> None:
        moment = datetime.now(self.config.timezone)
        if not self._is_due(moment):
            return

        week_key = self._week_key(moment)
        if await self.storage.get_meta(DIGEST_META_KEY) == week_key:
            return

        # Claim the week before posting so a send failure cannot turn into a
        # retry loop that spams the channel once it recovers.
        await self.storage.set_meta(DIGEST_META_KEY, week_key)
        if await self.post_digest():
            log.info("Posted weekly digest for %s", week_key)

    @digest_loop.before_loop
    async def _before_digest(self) -> None:
        await self.bot.wait_until_ready()

    # --------------------------------------------------------------- command

    @app_commands.command(
        name="digest", description="Post last week's voice recap right now."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def digest(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer()
        await interaction.followup.send(embed=await self.build_embed(interaction.guild))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Digest(bot))
