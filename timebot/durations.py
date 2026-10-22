"""Duration parsing and formatting helpers.

Kept free of any discord.py imports so it can be unit tested on its own.
"""

from __future__ import annotations

import re

_DURATION_RE = re.compile(
    r"^\s*(?:(?P<weeks>\d+)\s*w)?"
    r"\s*(?:(?P<days>\d+)\s*d)?"
    r"\s*(?:(?P<hours>\d+)\s*h)?"
    r"\s*(?:(?P<minutes>\d+)\s*m)?"
    r"\s*(?:(?P<seconds>\d+)\s*s)?\s*$",
    re.IGNORECASE,
)

_UNIT_SECONDS = {
    "weeks": 604800,
    "days": 86400,
    "hours": 3600,
    "minutes": 60,
    "seconds": 1,
}


class DurationError(ValueError):
    """Raised when a duration string cannot be parsed."""


def parse_duration(text: str) -> int:
    """Parse ``"1w2d3h4m5s"`` style input into a number of seconds.

    A bare integer is interpreted as seconds so that ``"3600"`` keeps working.
    """
    text = text.strip()
    if not text:
        raise DurationError("empty duration")
    if text.isdigit():
        return int(text)

    match = _DURATION_RE.match(text)
    if match is None or not any(match.groupdict().values()):
        raise DurationError(f"cannot parse duration: {text!r}")

    return sum(
        int(value) * _UNIT_SECONDS[unit]
        for unit, value in match.groupdict().items()
        if value is not None
    )


def format_duration(seconds: float, *, max_units: int = 2) -> str:
    """Render a duration as a short human string, e.g. ``"3d 4h"``.

    ``max_units`` limits how many components are shown so leaderboard rows stay
    the same width. Durations under a minute always render as seconds.
    """
    total = int(max(0, seconds))
    if total < 60:
        return f"{total}s"

    parts: list[str] = []
    for label, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        value, total = divmod(total, size)
        if value:
            parts.append(f"{value}{label}")
        if len(parts) == max_units:
            break
    return " ".join(parts) if parts else "0s"


def format_clock(seconds: float) -> str:
    """Render a duration as ``HH:MM:SS``, with days split off when present."""
    total = int(max(0, seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}d {clock}" if days else clock
