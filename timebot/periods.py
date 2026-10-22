"""Named leaderboard windows ("today", "this week", ...).

Windows are resolved in a configured timezone so that "today" means the local
day on the server, not a UTC day that rolls over mid-evening in Europe.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PERIODS: tuple[str, ...] = ("all", "today", "week", "month", "year")

PERIOD_LABELS: dict[str, str] = {
    "all": "all time",
    "today": "today",
    "week": "this week",
    "month": "this month",
    "year": "this year",
}


def resolve_window(
    period: str, tz: ZoneInfo, *, now: datetime | None = None
) -> tuple[int, int]:
    """Return ``(since, until)`` as Unix seconds for a named period.

    ``since`` is inclusive, ``until`` exclusive. ``all`` starts at the epoch.
    """
    period = period.lower()
    if period not in PERIODS:
        raise ValueError(f"unknown period: {period!r}")

    moment = (now or datetime.now(tz)).astimezone(tz)
    until = int(moment.timestamp())

    if period == "all":
        return 0, until

    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start = midnight
    elif period == "week":
        start = midnight - timedelta(days=midnight.weekday())
    elif period == "month":
        start = midnight.replace(day=1)
    else:  # year
        start = midnight.replace(month=1, day=1)

    return int(start.timestamp()), until


def previous_week_window(tz: ZoneInfo, *, now: datetime | None = None) -> tuple[int, int]:
    """The full Monday-to-Sunday week before the current one."""
    moment = (now or datetime.now(tz)).astimezone(tz)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    this_week = midnight - timedelta(days=midnight.weekday())
    last_week = this_week - timedelta(days=7)
    return int(last_week.timestamp()), int(this_week.timestamp())
