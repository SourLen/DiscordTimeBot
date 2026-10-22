"""Slash commands for looking at tracked time."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..durations import format_clock, format_duration
from ..periods import PERIOD_LABELS, resolve_window
from ..storage import now_ts
from ..ui import ACCENT, channel_label, leaderboard_embed, member_label

log = logging.getLogger(__name__)

PERIOD_CHOICES = [
    app_commands.Choice(name=label, value=key) for key, label in PERIOD_LABELS.items()
]


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = bot.config  # type: ignore[attr-defined]
        self.storage = bot.storage  # type: ignore[attr-defined]

    def window(self, period: str) -> tuple[int, int]:
        return resolve_window(period, self.config.timezone)

    @app_commands.command(
        name="time", description="Show how long a member has spent in voice."
    )
    @app_commands.describe(
        member="Whose time to show (defaults to you).",
        period="Which time window to count.",
    )
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.guild_only()
    async def time(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        assert interaction.guild is not None
        target = member or interaction.user
        period_key = period.value if period else "all"
        since, until = self.window(period_key)

        seconds = await self.storage.total_for(
            interaction.guild.id, target.id, since=since, until=until
        )
        embed = discord.Embed(
            title=f"{target.display_name} — {PERIOD_LABELS[period_key]}",
            description=f"**{format_duration(seconds, max_units=3)}**"
            f"\n`{format_clock(seconds)}`",
            colour=ACCENT,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        open_session = await self.storage.get_open_session(
            interaction.guild.id, target.id
        )
        if open_session is not None:
            live = now_ts() - open_session.started_at
            embed.add_field(
                name="Currently in voice",
                value=f"{channel_label(interaction.guild, open_session.channel_id)}"
                f" for {format_duration(live)}",
                inline=False,
            )

        rank = await self.storage.rank_of(
            interaction.guild.id, target.id, since=since, until=until
        )
        if rank is not None:
            place, _, population = rank
            embed.set_footer(text=f"Rank {place} of {population}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="top", description="Show the voice-time leaderboard.")
    @app_commands.describe(
        limit="How many members to list (1-25, default 10).",
        period="Which time window to count.",
    )
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.guild_only()
    async def top(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        assert interaction.guild is not None
        period_key = period.value if period else "all"
        since, until = self.window(period_key)

        rows = await self.storage.leaderboard(
            interaction.guild.id, since=since, until=until, limit=limit
        )
        embed = leaderboard_embed(
            interaction.guild,
            rows,
            period_label=PERIOD_LABELS[period_key],
            highlight_user_id=interaction.user.id,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="rank", description="Show where a member places on the leaderboard."
    )
    @app_commands.describe(
        member="Whose rank to show (defaults to you).",
        period="Which time window to count.",
    )
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.guild_only()
    async def rank(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        assert interaction.guild is not None
        target = member or interaction.user
        period_key = period.value if period else "all"
        since, until = self.window(period_key)

        result = await self.storage.rank_of(
            interaction.guild.id, target.id, since=since, until=until
        )
        if result is None:
            await interaction.response.send_message(
                f"{target.display_name} has no tracked voice time "
                f"{PERIOD_LABELS[period_key]}.",
                ephemeral=True,
            )
            return

        place, seconds, population = result
        await interaction.response.send_message(
            embed=discord.Embed(
                description=(
                    f"**{target.display_name}** is **#{place}** of {population} "
                    f"{PERIOD_LABELS[period_key]} with "
                    f"{format_duration(seconds, max_units=3)}."
                ),
                colour=ACCENT,
            )
        )

    @app_commands.command(
        name="stats",
        description="Full breakdown of a member's voice time across periods.",
    )
    @app_commands.describe(member="Whose stats to show (defaults to you).")
    @app_commands.guild_only()
    async def stats(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer()

        guild = interaction.guild
        target = member or interaction.user

        embed = discord.Embed(title=f"Voice stats — {target.display_name}", colour=ACCENT)
        embed.set_thumbnail(url=target.display_avatar.url)

        for period_key in ("today", "week", "month", "all"):
            since, until = self.window(period_key)
            seconds = await self.storage.total_for(
                guild.id, target.id, since=since, until=until
            )
            embed.add_field(
                name=PERIOD_LABELS[period_key].title(),
                value=format_duration(seconds, max_units=2),
                inline=True,
            )

        since, until = self.window("all")
        channels = await self.storage.channel_breakdown(
            guild.id, target.id, since=since, until=until, limit=5
        )
        if channels:
            embed.add_field(
                name="Favourite channels",
                value="\n".join(
                    f"`{format_duration(seconds):>8}`  {channel_label(guild, channel_id)}"
                    for channel_id, seconds in channels
                ),
                inline=False,
            )

        result = await self.storage.rank_of(guild.id, target.id)
        if result is not None:
            place, _, population = result
            embed.set_footer(text=f"All-time rank {place} of {population}")

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="serverstats", description="Aggregate voice activity for this server."
    )
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.guild_only()
    async def serverstats(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer()

        guild = interaction.guild
        period_key = period.value if period else "week"
        since, until = self.window(period_key)
        rows = await self.storage.leaderboard(guild.id, since=since, until=until)

        total = sum(row.seconds for row in rows)
        embed = discord.Embed(
            title=f"{guild.name} — {PERIOD_LABELS[period_key]}", colour=ACCENT
        )
        embed.add_field(
            name="Total voice time", value=format_duration(total, max_units=3)
        )
        embed.add_field(name="Active members", value=str(len(rows)))
        embed.add_field(
            name="Average per member",
            value=format_duration(total / len(rows)) if rows else "—",
        )
        if rows:
            embed.add_field(
                name="Most active",
                value=f"{member_label(guild, rows[0].user_id)} — "
                f"{format_duration(rows[0].seconds, max_units=3)}",
                inline=False,
            )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leaderboard(bot))
