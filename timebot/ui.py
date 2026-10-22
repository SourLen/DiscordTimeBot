"""Embed builders shared by the command cogs."""

from __future__ import annotations

import discord

from .durations import format_duration
from .storage import LeaderboardRow

ACCENT = discord.Colour(0x5865F2)
MEDALS = ("🥇", "🥈", "🥉")


def member_label(guild: discord.Guild | None, user_id: int) -> str:
    """Prefer a cached display name, fall back to a mention.

    Mentions render correctly even when the member cache is cold, so the
    leaderboard never degrades into raw snowflakes.
    """
    member = guild.get_member(user_id) if guild else None
    if member is not None:
        return member.display_name
    return f"<@{user_id}>"


def channel_label(guild: discord.Guild | None, channel_id: int) -> str:
    channel = guild.get_channel(channel_id) if guild else None
    return channel.name if channel is not None else f"deleted channel ({channel_id})"


def leaderboard_embed(
    guild: discord.Guild,
    rows: list[LeaderboardRow],
    *,
    period_label: str,
    highlight_user_id: int | None = None,
) -> discord.Embed:
    """Render a whole leaderboard as one embed.

    The original bot sent one message per entry, which ran straight into the
    channel rate limit for anything past a handful of members.
    """
    embed = discord.Embed(
        title=f"Voice time — {period_label}",
        colour=ACCENT,
    )
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

    if not rows:
        embed.description = "No tracked voice time yet for this period."
        return embed

    lines = []
    for index, row in enumerate(rows, start=1):
        prefix = MEDALS[index - 1] if index <= 3 else f"`{index:>2}.`"
        name = member_label(guild, row.user_id)
        if highlight_user_id is not None and row.user_id == highlight_user_id:
            name = f"**{name}**"
        lines.append(f"{prefix} {name} — {format_duration(row.seconds)}")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(rows)} members shown")
    return embed


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {message}", colour=discord.Colour.orange())
