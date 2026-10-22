from timebot.tracker import TrackingRules, VoiceSnapshot, plan_transition

AFK = 111
GENERAL = 222
EXCLUDED = 333

RULES = TrackingRules(
    excluded_channel_ids=frozenset({EXCLUDED}),
    afk_channel_id=AFK,
    track_afk_channel=False,
    ignore_deafened=True,
)


def test_not_connected_is_not_tracked():
    assert RULES.target_channel(VoiceSnapshot(channel_id=None)) is None


def test_normal_channel_is_tracked():
    assert RULES.target_channel(VoiceSnapshot(channel_id=GENERAL)) == GENERAL


def test_afk_channel_is_skipped_by_default():
    assert RULES.target_channel(VoiceSnapshot(channel_id=AFK)) is None


def test_afk_channel_can_be_opted_in():
    rules = TrackingRules(afk_channel_id=AFK, track_afk_channel=True)
    assert rules.target_channel(VoiceSnapshot(channel_id=AFK)) == AFK


def test_excluded_channel_is_skipped():
    assert RULES.target_channel(VoiceSnapshot(channel_id=EXCLUDED)) is None


def test_deafened_pauses_the_clock():
    assert RULES.target_channel(VoiceSnapshot(GENERAL, self_deaf=True)) is None
    assert RULES.target_channel(VoiceSnapshot(GENERAL, server_deaf=True)) is None


def test_deafened_can_still_count():
    rules = TrackingRules(ignore_deafened=False)
    assert rules.target_channel(VoiceSnapshot(GENERAL, self_deaf=True)) == GENERAL


def test_transition_join():
    t = plan_transition(open_channel_id=None, target_channel_id=GENERAL)
    assert (t.close, t.open_channel_id) == (False, GENERAL)


def test_transition_leave():
    t = plan_transition(open_channel_id=GENERAL, target_channel_id=None)
    assert (t.close, t.open_channel_id) == (True, None)


def test_transition_switch_channel_closes_and_reopens():
    t = plan_transition(open_channel_id=GENERAL, target_channel_id=EXCLUDED)
    assert (t.close, t.open_channel_id) == (True, EXCLUDED)


def test_transition_same_channel_is_a_noop():
    # Mute, camera, stream and server-move events all land here; the original
    # bot restarted the clock on some of them.
    t = plan_transition(open_channel_id=GENERAL, target_channel_id=GENERAL)
    assert t.is_noop


def test_transition_idle_stays_idle():
    assert plan_transition(open_channel_id=None, target_channel_id=None).is_noop
