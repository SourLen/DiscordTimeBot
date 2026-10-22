"""The bot class: wiring, extension loading and slash-command sync."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Config
from .storage import Storage, now_ts

log = logging.getLogger(__name__)

EXTENSIONS = (
    "timebot.cogs.tracking",
    "timebot.cogs.leaderboard",
    "timebot.cogs.milestones",
    "timebot.cogs.data",
    "timebot.cogs.digest",
)


def build_intents() -> discord.Intents:
    """The smallest intent set this bot needs.

    ``message_content`` is deliberately absent: every command is a slash
    command, so the bot never reads message text. ``members`` is privileged but
    only needs a toggle in the developer portal (no app review under 100
    guilds) and is what lets the bot see who is already in voice after a
    restart and resolve names on the leaderboard.
    """
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    intents.members = True
    return intents


class TimeBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=build_intents(),
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.config = config
        self.storage = Storage(config.database_path)
        self.started_at = now_ts()

    async def setup_hook(self) -> None:
        """Runs once, inside the event loop, before the gateway connects.

        discord.py 2.x replaced the old "create a task after ``run()``" pattern
        with this hook. The original bot's autosave task was scheduled *after*
        the blocking ``client.run()`` call and therefore never ran at all.
        """
        await self.storage.connect()
        await self._recover_from_downtime()

        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.debug("Loaded extension %s", extension)

        await self._sync_commands()

    async def _recover_from_downtime(self) -> None:
        """Close sessions left open by a crash, capped at the last heartbeat.

        Without this, a member who was in voice when the process died would
        either lose the session entirely or be credited for the whole outage.
        """
        raw_heartbeat = await self.storage.get_meta("heartbeat")
        if raw_heartbeat is None:
            closed = await self.storage.close_dangling_sessions(now_ts())
        else:
            closed = await self.storage.close_dangling_sessions(int(raw_heartbeat))
        if closed:
            log.info("Closed %d session(s) left open by a previous shutdown", closed)
        await self.storage.heartbeat()

    async def _sync_commands(self) -> None:
        if self.config.guild_ids:
            for guild_id in self.config.guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d command(s) to guild %s", len(synced), guild_id)
        else:
            synced = await self.tree.sync()
            log.info(
                "Synced %d global command(s); global propagation can take up to "
                "an hour. Set GUILD_IDS for instant updates while developing.",
                len(synced),
            )

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info(
            "Logged in as %s (id=%s) across %d guild(s)",
            self.user,
            self.user.id,
            len(self.guilds),
        )
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="voice channels"
            )
        )

    async def close(self) -> None:
        """Flush open sessions before disconnecting so no time is lost."""
        tracking = self.get_cog("Tracking")
        if tracking is not None:
            try:
                await tracking.flush_open_sessions()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - best effort on shutdown
                log.exception("Failed to flush open sessions during shutdown")
        await super().close()
        await self.storage.close()
