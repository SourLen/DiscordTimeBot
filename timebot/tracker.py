"""The rule that decides whether a voice state counts as tracked time.

Deliberately expressed over plain values rather than discord.py objects: the
original bot's tracking bugs all lived in branchy event handling that could not
be exercised without a live gateway connection. This module can.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceSnapshot:
    """The parts of a ``discord.VoiceState`` that tracking actually depends on."""

    channel_id: int | None
    self_deaf: bool = False
    server_deaf: bool = False

    @property
    def deafened(self) -> bool:
        return self.self_deaf or self.server_deaf


@dataclass(frozen=True)
class TrackingRules:
    excluded_channel_ids: frozenset[int] = frozenset()
    afk_channel_id: int | None = None
    track_afk_channel: bool = False
    ignore_deafened: bool = True

    def target_channel(self, snapshot: VoiceSnapshot) -> int | None:
        """The channel whose time should be credited, or ``None`` for no credit.

        A member counts when they are connected to a voice channel that is not
        excluded, not the guild AFK channel (unless configured otherwise), and
        -- by default -- while they can actually hear the channel.
        """
        channel_id = snapshot.channel_id
        if channel_id is None:
            return None
        if channel_id in self.excluded_channel_ids:
            return None
        if not self.track_afk_channel and channel_id == self.afk_channel_id:
            return None
        if self.ignore_deafened and snapshot.deafened:
            return None
        return channel_id


@dataclass(frozen=True)
class Transition:
    """What to do with the stored session given current state."""

    close: bool
    open_channel_id: int | None

    @property
    def is_noop(self) -> bool:
        return not self.close and self.open_channel_id is None


def plan_transition(
    *, open_channel_id: int | None, target_channel_id: int | None
) -> Transition:
    """Reconcile the stored open session against what should be tracked now.

    This single comparison replaces the original bot's eight-way ``if`` ladder
    over ``before``/``after``, which silently dropped members who disconnected
    while the bot was down and double-counted members who switched channels.
    """
    if open_channel_id == target_channel_id:
        return Transition(close=False, open_channel_id=None)
    if target_channel_id is None:
        return Transition(close=True, open_channel_id=None)
    if open_channel_id is None:
        return Transition(close=False, open_channel_id=target_channel_id)
    return Transition(close=True, open_channel_id=target_channel_id)
