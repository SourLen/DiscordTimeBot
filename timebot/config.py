"""Configuration, loaded from environment variables (or a local ``.env``)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .durations import DurationError, parse_duration

log = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when the environment does not describe a runnable bot."""


@dataclass(frozen=True)
class Milestone:
    """A voice-time threshold that grants a role once reached."""

    seconds: int
    role_name: str


@dataclass(frozen=True)
class Config:
    token: str
    database_path: Path
    guild_ids: tuple[int, ...] = ()
    excluded_channel_ids: frozenset[int] = frozenset()
    track_afk_channel: bool = False
    ignore_deafened: bool = True
    ignore_bots: bool = True
    min_session_seconds: int = 10
    reconcile_interval_seconds: int = 300
    milestones: tuple[Milestone, ...] = ()
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    digest_channel_id: int | None = None
    digest_weekday: int = 0  # Monday
    digest_hour: int = 18
    log_level: str = "INFO"

    @property
    def digest_enabled(self) -> bool:
        return self.digest_channel_id is not None

    @property
    def milestones_enabled(self) -> bool:
        return bool(self.milestones)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    if raw.lower() in {"1", "true", "yes", "on"}:
        return True
    if raw.lower() in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _env_id_list(name: str) -> tuple[int, ...]:
    raw = _env(name)
    if not raw:
        return ()
    ids: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError as exc:
            raise ConfigError(f"{name} contains a non-numeric id: {chunk!r}") from exc
    return tuple(ids)


def _parse_milestones(raw: str | None) -> tuple[Milestone, ...]:
    """Parse ``"10h=Regular,100h=Veteran"`` into sorted milestones."""
    if not raw:
        return ()

    milestones: list[Milestone] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        separator = "=" if "=" in chunk else ":"
        if separator not in chunk:
            raise ConfigError(
                f"MILESTONES entry {chunk!r} must look like '10h=Role Name'"
            )
        duration, _, role_name = chunk.partition(separator)
        role_name = role_name.strip()
        if not role_name:
            raise ConfigError(f"MILESTONES entry {chunk!r} is missing a role name")
        try:
            seconds = parse_duration(duration)
        except DurationError as exc:
            raise ConfigError(f"MILESTONES entry {chunk!r}: {exc}") from exc
        if seconds <= 0:
            raise ConfigError(f"MILESTONES entry {chunk!r} must be a positive duration")
        milestones.append(Milestone(seconds=seconds, role_name=role_name))

    milestones.sort(key=lambda m: m.seconds)
    return tuple(milestones)


def _parse_timezone(raw: str | None) -> ZoneInfo:
    if not raw:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"TIMEZONE {raw!r} is not a known IANA zone") from exc


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    """Minimal ``.env`` loader so the bot has no hard dependency on python-dotenv.

    Existing environment variables always win, which keeps container and systemd
    deployments predictable.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def load_config() -> Config:
    """Build a :class:`Config` from the process environment."""
    token = _env("DISCORD_TOKEN")
    if not token:
        raise ConfigError(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in."
        )
    if token in {"YourTokenHere", "your-token-here"}:
        raise ConfigError("DISCORD_TOKEN still holds the placeholder value.")

    digest_weekday = _env_int("DIGEST_WEEKDAY", 0)
    if not 0 <= digest_weekday <= 6:
        raise ConfigError("DIGEST_WEEKDAY must be 0 (Monday) through 6 (Sunday)")
    digest_hour = _env_int("DIGEST_HOUR", 18)
    if not 0 <= digest_hour <= 23:
        raise ConfigError("DIGEST_HOUR must be between 0 and 23")

    digest_channel_ids = _env_id_list("DIGEST_CHANNEL_ID")
    if len(digest_channel_ids) > 1:
        raise ConfigError("DIGEST_CHANNEL_ID accepts a single channel id")

    return Config(
        token=token,
        database_path=Path(_env("DATABASE_PATH", "data/timebot.db")),
        guild_ids=_env_id_list("GUILD_IDS"),
        excluded_channel_ids=frozenset(_env_id_list("EXCLUDED_CHANNEL_IDS")),
        track_afk_channel=_env_bool("TRACK_AFK_CHANNEL", False),
        ignore_deafened=_env_bool("IGNORE_DEAFENED", True),
        ignore_bots=_env_bool("IGNORE_BOTS", True),
        min_session_seconds=_env_int("MIN_SESSION_SECONDS", 10, minimum=0),
        reconcile_interval_seconds=_env_int(
            "RECONCILE_INTERVAL_SECONDS", 300, minimum=30
        ),
        milestones=_parse_milestones(_env("MILESTONES")),
        timezone=_parse_timezone(_env("TIMEZONE")),
        digest_channel_id=digest_channel_ids[0] if digest_channel_ids else None,
        digest_weekday=digest_weekday,
        digest_hour=digest_hour,
        log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
    )
