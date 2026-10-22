"""Voice-state tracking: the part that actually records time."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from ..storage import now_ts
from ..tracker import TrackingRules, VoiceSnapshot, plan_transition

log = logging.getLogger(__name__)


class Tracking(commands.Cog):
    """Keeps the stored sessions in sync with who is actually in voice.

    Every path -- gateway event, startup, periodic sweep -- funnels into
    :meth:`reconcile_member`, so there is exactly one place where a session can
    be opened or closed.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = bot.config  # type: ignore[attr-defined]
        self.storage = bot.storage  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.reconcile_loop.change_interval(
            seconds=self.config.reconcile_interval_seconds
        )
        self.reconcile_loop.start()

    async def cog_unload(self) -> None:
        self.reconcile_loop.cancel()

    # ------------------------------------------------------------------ rules

    def rules_for(self, guild: discord.Guild) -> TrackingRules:
        afk = guild.afk_channel
        return TrackingRules(
            excluded_channel_ids=self.config.excluded_channel_ids,
            afk_channel_id=afk.id if afk else None,
            track_afk_channel=self.config.track_afk_channel,
            ignore_deafened=self.config.ignore_deafened,
        )

    @staticmethod
    def snapshot(state: discord.VoiceState | None) -> VoiceSnapshot:
        if state is None:
            return VoiceSnapshot(channel_id=None)
        return VoiceSnapshot(
            channel_id=state.channel.id if state.channel else None,
            self_deaf=bool(state.self_deaf),
            server_deaf=bool(state.deaf),
        )

    async def is_trackable(self, member: discord.Member) -> bool:
        if member.bot and self.config.ignore_bots:
            return False
        return not await self.storage.is_opted_out(member.guild.id, member.id)

    # ------------------------------------------------------------ reconcile

    async def reconcile_member(
        self, member: discord.Member, state: discord.VoiceState | None
    ) -> int:
        """Align the stored session with ``state``. Returns seconds credited."""
        guild = member.guild
        if await self.is_trackable(member):
            target = self.rules_for(guild).target_channel(self.snapshot(state))
        else:
            target = None

        open_session = await self.storage.get_open_session(guild.id, member.id)
        open_channel_id = open_session.channel_id if open_session else None
        transition = plan_transition(
            open_channel_id=open_channel_id, target_channel_id=target
        )
        if transition.is_noop:
            return 0

        credited = 0
        if transition.close:
            credited = await self.storage.end_session(
                guild.id, member.id, min_seconds=self.config.min_session_seconds
            )
            if credited:
                log.debug("Credited %ss to %s in %s", credited, member.id, guild.id)

        if transition.open_channel_id is not None:
            await self.storage.start_session(
                guild.id, member.id, transition.open_channel_id
            )

        if credited:
            await self._announce_milestones(member)
        return credited

    async def _announce_milestones(self, member: discord.Member) -> None:
        cog = self.bot.get_cog("Milestones")
        if cog is not None:
            await cog.check_member(member)  # type: ignore[attr-defined]

    # --------------------------------------------------------------- events

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        del before  # the stored session is the source of truth, not the event
        try:
            await self.reconcile_member(member, after)
        except Exception:
            log.exception("Failed to reconcile voice state for %s", member.id)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.reconcile_all()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.reconcile_guild(guild)

    # ----------------------------------------------------------------- sweeps

    async def reconcile_guild(self, guild: discord.Guild) -> None:
        """Pick up everyone currently in voice, including after a restart."""
        seen: set[int] = set()
        for channel in [*guild.voice_channels, *guild.stage_channels]:
            for member in channel.members:
                seen.add(member.id)
                await self.reconcile_member(member, member.voice)

        # Anyone with an open session who is no longer in voice (missed event
        # or a disconnect while the bot was down) gets closed out here.
        for session in await self.storage.all_open_sessions():
            if session.guild_id != guild.id or session.user_id in seen:
                continue
            member = guild.get_member(session.user_id)
            if member is None:
                await self.storage.end_session(
                    guild.id,
                    session.user_id,
                    min_seconds=self.config.min_session_seconds,
                )
            else:
                await self.reconcile_member(member, member.voice)

    async def reconcile_all(self) -> None:
        for guild in self.bot.guilds:
            try:
                await self.reconcile_guild(guild)
            except Exception:
                log.exception("Failed to reconcile guild %s", guild.id)
        await self.storage.heartbeat()

    async def flush_open_sessions(self) -> None:
        """Close every open session. Called on shutdown so nothing is lost."""
        moment = now_ts()
        closed = await self.storage.close_dangling_sessions(moment)
        await self.storage.heartbeat(moment)
        if closed:
            log.info("Flushed %d open session(s) on shutdown", closed)

    @tasks.loop(seconds=300)
    async def reconcile_loop(self) -> None:
        """Heartbeat plus a self-heal sweep.

        The heartbeat bounds how much time an unclean shutdown can lose, and
        the sweep repairs state if a gateway event was ever missed.
        """
        await self.reconcile_all()

    @reconcile_loop.before_loop
    async def _before_reconcile(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracking(bot))
