import pytest

from timebot.storage import Storage

GUILD = 1
ALICE = 10
BOB = 20
GENERAL = 100
GAMING = 200

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def storage(tmp_path):
    store = Storage(tmp_path / "test.db")
    await store.connect()
    try:
        yield store
    finally:
        await store.close()


async def test_session_round_trip(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=1000)
    assert (await storage.get_open_session(GUILD, ALICE)).channel_id == GENERAL

    credited = await storage.end_session(GUILD, ALICE, ended_at=1600)
    assert credited == 600
    assert await storage.get_open_session(GUILD, ALICE) is None
    assert await storage.total_for(GUILD, ALICE, until=2000) == 600


async def test_short_sessions_are_discarded(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=1000)
    assert await storage.end_session(GUILD, ALICE, ended_at=1005, min_seconds=10) == 0
    assert await storage.total_for(GUILD, ALICE, until=2000) == 0


async def test_starting_twice_closes_the_previous_session(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=1000)
    await storage.start_session(GUILD, ALICE, GAMING, started_at=1500)

    open_session = await storage.get_open_session(GUILD, ALICE)
    assert open_session.channel_id == GAMING
    # The first 500s are kept, not double counted and not lost.
    assert await storage.total_for(GUILD, ALICE, until=1500) == 500


async def test_open_sessions_count_up_to_now(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=1000)
    assert await storage.total_for(GUILD, ALICE, until=1300) == 300


async def test_window_clamps_sessions_that_straddle_the_edge(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=1000)
    await storage.end_session(GUILD, ALICE, ended_at=2000)

    # Window covers only the second half of the session.
    assert await storage.total_for(GUILD, ALICE, since=1500, until=3000) == 500
    # Window entirely before the session.
    assert await storage.total_for(GUILD, ALICE, since=0, until=900) == 0


async def test_leaderboard_orders_and_limits(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=0)
    await storage.end_session(GUILD, ALICE, ended_at=100)
    await storage.start_session(GUILD, BOB, GENERAL, started_at=0)
    await storage.end_session(GUILD, BOB, ended_at=300)

    rows = await storage.leaderboard(GUILD, until=1000)
    assert [(r.user_id, r.seconds) for r in rows] == [(BOB, 300), (ALICE, 100)]
    assert len(await storage.leaderboard(GUILD, until=1000, limit=1)) == 1


async def test_rank_of(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=0)
    await storage.end_session(GUILD, ALICE, ended_at=100)
    await storage.start_session(GUILD, BOB, GENERAL, started_at=0)
    await storage.end_session(GUILD, BOB, ended_at=300)

    assert await storage.rank_of(GUILD, ALICE, until=1000) == (2, 100, 2)
    assert await storage.rank_of(GUILD, 999, until=1000) is None


async def test_channel_breakdown(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=0)
    await storage.end_session(GUILD, ALICE, ended_at=100)
    await storage.start_session(GUILD, ALICE, GAMING, started_at=200)
    await storage.end_session(GUILD, ALICE, ended_at=700)

    assert await storage.channel_breakdown(GUILD, ALICE, until=1000) == [
        (GAMING, 500),
        (GENERAL, 100),
    ]


async def test_crash_recovery_caps_at_the_heartbeat(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=1000)
    # Bot died at 1200 but is only restarted much later.
    closed = await storage.close_dangling_sessions(1200)

    assert closed == 1
    assert await storage.total_for(GUILD, ALICE, until=99999) == 200


async def test_crash_recovery_never_produces_negative_time(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=5000)
    await storage.close_dangling_sessions(1000)
    assert await storage.total_for(GUILD, ALICE, until=99999) == 0


async def test_opt_out_deletes_and_blocks(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=0)
    await storage.end_session(GUILD, ALICE, ended_at=100)

    assert await storage.opt_out(GUILD, ALICE) == 1
    assert await storage.is_opted_out(GUILD, ALICE) is True
    assert await storage.total_for(GUILD, ALICE, until=1000) == 0

    assert await storage.opt_in(GUILD, ALICE) is True
    assert await storage.is_opted_out(GUILD, ALICE) is False


async def test_guilds_are_isolated(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=0)
    await storage.end_session(GUILD, ALICE, ended_at=100)
    await storage.start_session(2, ALICE, GENERAL, started_at=0)
    await storage.end_session(2, ALICE, ended_at=900)

    assert await storage.total_for(GUILD, ALICE, until=1000) == 100
    assert await storage.total_for(2, ALICE, until=1000) == 900


async def test_milestones_are_recorded_once(storage):
    await storage.record_milestone(GUILD, ALICE, 3600)
    await storage.record_milestone(GUILD, ALICE, 3600)
    assert await storage.granted_milestones(GUILD, ALICE) == {3600}


async def test_export_sessions(storage):
    await storage.start_session(GUILD, ALICE, GENERAL, started_at=0)
    await storage.end_session(GUILD, ALICE, ended_at=100)

    rows = await storage.export_sessions(GUILD, ALICE)
    assert len(rows) == 1
    assert rows[0].seconds == 100
    assert rows[0].channel_id == GENERAL
