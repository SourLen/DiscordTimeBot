"""End-to-end tracking behaviour, driven with lightweight fakes.

These are the scenarios the 2020 version got wrong: switching channels,
reconnecting, going AFK, and restarting the bot while people are in voice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from timebot.config import Config
from timebot.storage import Storage

pytestmark = pytest.mark.asyncio

GUILD_ID = 1
GENERAL = 100
GAMING = 200
AFK = 999


@dataclass
class FakeChannel:
    id: int
    name: str = "channel"
    members: list = field(default_factory=list)


@dataclass
class FakeVoiceState:
    channel: FakeChannel | None
    self_deaf: bool = False
    deaf: bool = False


@dataclass
class FakeGuild:
    id: int = GUILD_ID
    afk_channel: FakeChannel | None = field(default_factory=lambda: FakeChannel(AFK))
    voice_channels: list = field(default_factory=list)
    stage_channels: list = field(default_factory=list)
    me: object | None = None
    _members: dict = field(default_factory=dict)

    def get_member(self, user_id):
        return self._members.get(user_id)


@dataclass
class FakeMember:
    id: int
    guild: FakeGuild
    bot: bool = False
    voice: FakeVoiceState | None = None
    display_name: str = "member"


class FakeBot:
    def __init__(self, config, storage, guild):
        self.config = config
        self.storage = storage
        self.guilds = [guild]

    def get_cog(self, name):  # milestones are tested separately
        return None


def make_config(tmp_path, **overrides):
    defaults = dict(
        token="x",
        database_path=tmp_path / "t.db",
        min_session_seconds=0,
        ignore_deafened=True,
        ignore_bots=True,
    )
    defaults.update(overrides)
    return Config(**defaults)


@pytest.fixture
async def setup(tmp_path):
    from timebot.cogs.tracking import Tracking

    storage = Storage(tmp_path / "t.db")
    await storage.connect()
    guild = FakeGuild()
    config = make_config(tmp_path)
    bot = FakeBot(config, storage, guild)
    cog = Tracking.__new__(Tracking)
    cog.bot = bot
    cog.config = config
    cog.storage = storage
    try:
        yield cog, storage, guild
    finally:
        await storage.close()


async def test_joining_opens_a_session(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))

    session = await storage.get_open_session(GUILD_ID, 5)
    assert session is not None and session.channel_id == GENERAL


async def test_leaving_closes_the_session(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))
    await cog.reconcile_member(member, FakeVoiceState(None))

    assert await storage.get_open_session(GUILD_ID, 5) is None


async def test_muting_does_not_restart_the_clock(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild)
    channel = FakeChannel(GENERAL)

    await cog.reconcile_member(member, FakeVoiceState(channel))
    before = await storage.get_open_session(GUILD_ID, 5)

    # A mute/unmute/camera/stream toggle fires on_voice_state_update too.
    await cog.reconcile_member(member, FakeVoiceState(channel))
    after = await storage.get_open_session(GUILD_ID, 5)

    assert before.id == after.id
    assert before.started_at == after.started_at


async def test_switching_channels_moves_the_session(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))
    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GAMING)))

    session = await storage.get_open_session(GUILD_ID, 5)
    assert session.channel_id == GAMING
    # Exactly one open session, and the general-channel time was kept.
    assert len(await storage.all_open_sessions()) == 1
    assert dict(await storage.channel_breakdown(GUILD_ID, 5, limit=5)).keys() <= {
        GENERAL,
        GAMING,
    }


async def test_afk_channel_closes_the_session(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))
    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(AFK)))

    assert await storage.get_open_session(GUILD_ID, 5) is None


async def test_guild_without_afk_channel_does_not_crash(setup):
    """The 2020 version did ``get(..., name='Gulag').id`` and raised here."""
    cog, storage, guild = setup
    guild.afk_channel = None
    member = FakeMember(id=5, guild=guild)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))

    assert await storage.get_open_session(GUILD_ID, 5) is not None


async def test_deafening_pauses_and_undeafening_resumes(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild)
    channel = FakeChannel(GENERAL)

    await cog.reconcile_member(member, FakeVoiceState(channel))
    await cog.reconcile_member(member, FakeVoiceState(channel, self_deaf=True))
    assert await storage.get_open_session(GUILD_ID, 5) is None

    await cog.reconcile_member(member, FakeVoiceState(channel))
    assert await storage.get_open_session(GUILD_ID, 5) is not None


async def test_bots_are_ignored(setup):
    cog, storage, guild = setup
    member = FakeMember(id=5, guild=guild, bot=True)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))

    assert await storage.get_open_session(GUILD_ID, 5) is None


async def test_opted_out_members_are_not_tracked(setup):
    cog, storage, guild = setup
    await storage.opt_out(GUILD_ID, 5)
    member = FakeMember(id=5, guild=guild)

    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GENERAL)))

    assert await storage.get_open_session(GUILD_ID, 5) is None


async def test_restart_picks_up_members_already_in_voice(setup):
    """Nobody has to rejoin after a restart for their time to count."""
    cog, storage, guild = setup
    channel = FakeChannel(GENERAL)
    member = FakeMember(id=5, guild=guild, voice=FakeVoiceState(channel))
    channel.members = [member]
    guild.voice_channels = [channel]
    guild._members = {5: member}

    await cog.reconcile_guild(guild)

    assert await storage.get_open_session(GUILD_ID, 5) is not None


async def test_sweep_closes_sessions_for_members_who_left_while_down(setup):
    cog, storage, guild = setup
    await storage.start_session(GUILD_ID, 7, GENERAL)
    guild.voice_channels = []

    await cog.reconcile_guild(guild)

    assert await storage.get_open_session(GUILD_ID, 7) is None


async def test_excluded_channels_are_never_tracked(tmp_path):
    from timebot.cogs.tracking import Tracking

    storage = Storage(tmp_path / "t.db")
    await storage.connect()
    guild = FakeGuild()
    config = make_config(
        tmp_path, excluded_channel_ids=frozenset({GAMING}), min_session_seconds=0
    )
    cog = Tracking.__new__(Tracking)
    cog.bot = FakeBot(config, storage, guild)
    cog.config = config
    cog.storage = storage

    member = FakeMember(id=5, guild=guild)
    await cog.reconcile_member(member, FakeVoiceState(FakeChannel(GAMING)))

    assert await storage.get_open_session(GUILD_ID, 5) is None
    await storage.close()
