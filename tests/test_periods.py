from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from timebot.periods import PERIODS, previous_week_window, resolve_window

BERLIN = ZoneInfo("Europe/Berlin")
# Wednesday, 15 October 2025, 20:30 local time.
NOW = datetime(2025, 10, 15, 20, 30, tzinfo=BERLIN)


def _local(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=BERLIN)


def test_all_starts_at_the_epoch():
    since, until = resolve_window("all", BERLIN, now=NOW)
    assert since == 0
    assert until == int(NOW.timestamp())


def test_today_starts_at_local_midnight():
    since, _ = resolve_window("today", BERLIN, now=NOW)
    assert _local(since) == datetime(2025, 10, 15, 0, 0, tzinfo=BERLIN)


def test_week_starts_on_monday():
    since, _ = resolve_window("week", BERLIN, now=NOW)
    assert _local(since) == datetime(2025, 10, 13, 0, 0, tzinfo=BERLIN)


def test_month_and_year():
    assert _local(resolve_window("month", BERLIN, now=NOW)[0]) == datetime(
        2025, 10, 1, tzinfo=BERLIN
    )
    assert _local(resolve_window("year", BERLIN, now=NOW)[0]) == datetime(
        2025, 1, 1, tzinfo=BERLIN
    )


def test_previous_week_is_a_full_monday_to_monday_span():
    since, until = previous_week_window(BERLIN, now=NOW)
    assert _local(since) == datetime(2025, 10, 6, tzinfo=BERLIN)
    assert _local(until) == datetime(2025, 10, 13, tzinfo=BERLIN)


def test_window_spanning_a_dst_change_is_still_seven_days_of_wall_clock():
    # Germany left DST on 26 October 2025, so this week is 169 real hours.
    after_dst = datetime(2025, 10, 29, 12, 0, tzinfo=BERLIN)
    since, until = previous_week_window(BERLIN, now=after_dst)
    assert _local(since) == datetime(2025, 10, 20, tzinfo=BERLIN)
    assert until - since == 7 * 24 * 3600 + 3600


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        resolve_window("fortnight", BERLIN, now=NOW)


def test_every_declared_period_resolves():
    for period in PERIODS:
        since, until = resolve_window(period, BERLIN, now=NOW)
        assert since <= until
