import pytest

from timebot.durations import (
    DurationError,
    format_clock,
    format_duration,
    parse_duration,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30s", 30),
        ("5m", 300),
        ("2h", 7200),
        ("1d", 86400),
        ("1w", 604800),
        ("1h30m", 5400),
        ("1d2h3m4s", 93784),
        ("  10H  ", 36000),
        ("3600", 3600),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "10x", "h"])
def test_parse_duration_rejects_garbage(text):
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0s"),
        (45, "45s"),
        (60, "1m"),
        (3600, "1h"),
        (3661, "1h 1m"),
        (90061, "1d 1h"),
        (-5, "0s"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_format_duration_respects_max_units():
    assert format_duration(90061, max_units=3) == "1d 1h 1m"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00:00"), (61, "00:01:01"), (3661, "01:01:01"), (90061, "1d 01:01:01")],
)
def test_format_clock(seconds, expected):
    assert format_clock(seconds) == expected
