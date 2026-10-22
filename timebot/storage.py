"""SQLite persistence for voice sessions.

Everything is stored as closed or open *sessions* rather than a single running
total. That costs a little space and buys three things the original bot could
not do: leaderboards over arbitrary time windows, a per-channel breakdown, and
crash recovery that neither loses nor invents time.

All timestamps are integer Unix seconds in UTC.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    started_at  INTEGER NOT NULL,
    ended_at    INTEGER,
    seconds     INTEGER
);

-- At most one open session per member per guild.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open
    ON sessions (guild_id, user_id) WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_guild_time
    ON sessions (guild_id, started_at);

CREATE INDEX IF NOT EXISTS idx_sessions_user
    ON sessions (guild_id, user_id, started_at);

CREATE TABLE IF NOT EXISTS optouts (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS milestones_granted (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    threshold   INTEGER NOT NULL,
    granted_at  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, threshold)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class LeaderboardRow:
    user_id: int
    seconds: int


@dataclass(frozen=True)
class OpenSession:
    id: int
    guild_id: int
    user_id: int
    channel_id: int
    started_at: int


@dataclass(frozen=True)
class SessionRow:
    guild_id: int
    user_id: int
    channel_id: int
    started_at: int
    ended_at: int | None
    seconds: int


def now_ts() -> int:
    """Current UTC Unix timestamp as an integer."""
    return int(time.time())


class Storage:
    """Async wrapper around a single SQLite connection.

    sqlite3 calls are short, so they run on a worker thread behind one lock
    instead of pulling in an async driver. That keeps the runtime dependency
    list at exactly one package (discord.py).
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ setup

    async def connect(self) -> None:
        if self._conn is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await asyncio.to_thread(self._open)
        await asyncio.to_thread(self._migrate, self._conn)
        log.info("Database ready at %s", self.path)

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    async def close(self) -> None:
        if self._conn is None:
            return
        conn, self._conn = self._conn, None
        await asyncio.to_thread(conn.close)

    # --------------------------------------------------------------- plumbing

    async def _run(self, func, *args):
        if self._conn is None:
            raise RuntimeError("Storage.connect() has not been awaited")
        async with self._lock:
            return await asyncio.to_thread(func, self._conn, *args)

    # ----------------------------------------------------------------- meta

    async def get_meta(self, key: str) -> str | None:
        def _get(conn: sqlite3.Connection) -> str | None:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

        return await self._run(_get)

    async def set_meta(self, key: str, value: str) -> None:
        def _set(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

        await self._run(_set)

    async def heartbeat(self, when: int | None = None) -> None:
        """Record that the bot was alive, so a crash can be bounded later."""
        await self.set_meta("heartbeat", str(when if when is not None else now_ts()))

    # ------------------------------------------------------------- opt-outs

    async def is_opted_out(self, guild_id: int, user_id: int) -> bool:
        def _check(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                "SELECT 1 FROM optouts WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            return row is not None

        return await self._run(_check)

    async def opt_out(self, guild_id: int, user_id: int) -> int:
        """Delete every stored session for a member and stop tracking them."""

        def _opt_out(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            deleted = cursor.rowcount
            conn.execute(
                "DELETE FROM milestones_granted WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO optouts (guild_id, user_id, created_at) "
                "VALUES (?, ?, ?)",
                (guild_id, user_id, now_ts()),
            )
            conn.commit()
            return deleted

        return await self._run(_opt_out)

    async def opt_in(self, guild_id: int, user_id: int) -> bool:
        def _opt_in(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
                "DELETE FROM optouts WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

        return await self._run(_opt_in)

    # ------------------------------------------------------------- sessions

    async def get_open_session(self, guild_id: int, user_id: int) -> OpenSession | None:
        def _get(conn: sqlite3.Connection) -> OpenSession | None:
            row = conn.execute(
                "SELECT id, guild_id, user_id, channel_id, started_at FROM sessions "
                "WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL",
                (guild_id, user_id),
            ).fetchone()
            return OpenSession(**dict(row)) if row else None

        return await self._run(_get)

    async def all_open_sessions(self) -> list[OpenSession]:
        def _all(conn: sqlite3.Connection) -> list[OpenSession]:
            rows = conn.execute(
                "SELECT id, guild_id, user_id, channel_id, started_at FROM sessions "
                "WHERE ended_at IS NULL"
            ).fetchall()
            return [OpenSession(**dict(row)) for row in rows]

        return await self._run(_all)

    async def start_session(
        self, guild_id: int, user_id: int, channel_id: int, started_at: int | None = None
    ) -> None:
        """Open a session, replacing any session left open for that member."""
        started = started_at if started_at is not None else now_ts()

        def _start(conn: sqlite3.Connection) -> None:
            with conn:
                conn.execute(
                    "UPDATE sessions SET ended_at = ?, "
                    "seconds = MAX(0, ? - started_at) "
                    "WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL",
                    (started, started, guild_id, user_id),
                )
                conn.execute(
                    "INSERT INTO sessions (guild_id, user_id, channel_id, started_at) "
                    "VALUES (?, ?, ?, ?)",
                    (guild_id, user_id, channel_id, started),
                )

        await self._run(_start)

    async def end_session(
        self,
        guild_id: int,
        user_id: int,
        ended_at: int | None = None,
        *,
        min_seconds: int = 0,
    ) -> int:
        """Close the open session and return the seconds credited (0 if none)."""
        ended = ended_at if ended_at is not None else now_ts()

        def _end(conn: sqlite3.Connection) -> int:
            with conn:
                row = conn.execute(
                    "SELECT id, started_at FROM sessions "
                    "WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL",
                    (guild_id, user_id),
                ).fetchone()
                if row is None:
                    return 0

                seconds = max(0, ended - row["started_at"])
                if seconds < min_seconds:
                    # Channel hopping and reconnect blips are noise, not time.
                    conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
                    return 0

                conn.execute(
                    "UPDATE sessions SET ended_at = ?, seconds = ? WHERE id = ?",
                    (ended, seconds, row["id"]),
                )
                return seconds

        return await self._run(_end)

    async def close_dangling_sessions(self, ended_at: int) -> int:
        """Close sessions left open by a crash, capped at the last heartbeat.

        Returns the number of sessions closed.
        """

        def _close(conn: sqlite3.Connection) -> int:
            with conn:
                cursor = conn.execute(
                    "UPDATE sessions SET ended_at = MAX(started_at, ?), "
                    "seconds = MAX(0, ? - started_at) WHERE ended_at IS NULL",
                    (ended_at, ended_at),
                )
                return cursor.rowcount

        return await self._run(_close)

    # ---------------------------------------------------------------- queries

    async def leaderboard(
        self,
        guild_id: int,
        *,
        since: int = 0,
        until: int | None = None,
        limit: int | None = None,
    ) -> list[LeaderboardRow]:
        """Total tracked seconds per member, clamped to ``[since, until)``.

        Sessions that straddle a window edge are counted only for their
        overlapping part, and still-open sessions count up to ``until``.
        """
        end = until if until is not None else now_ts()

        def _board(conn: sqlite3.Connection) -> list[LeaderboardRow]:
            sql = (
                "SELECT user_id, "
                "SUM(MIN(COALESCE(ended_at, ?), ?) - MAX(started_at, ?)) AS secs "
                "FROM sessions "
                "WHERE guild_id = ? AND started_at < ? AND COALESCE(ended_at, ?) > ? "
                "GROUP BY user_id HAVING secs > 0 ORDER BY secs DESC"
            )
            params: list[int] = [end, end, since, guild_id, end, end, since]
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [LeaderboardRow(row["user_id"], int(row["secs"])) for row in rows]

        return await self._run(_board)

    async def total_for(
        self, guild_id: int, user_id: int, *, since: int = 0, until: int | None = None
    ) -> int:
        end = until if until is not None else now_ts()

        def _total(conn: sqlite3.Connection) -> int:
            row = conn.execute(
                "SELECT COALESCE(SUM(MIN(COALESCE(ended_at, ?), ?) "
                "- MAX(started_at, ?)), 0) AS secs FROM sessions "
                "WHERE guild_id = ? AND user_id = ? "
                "AND started_at < ? AND COALESCE(ended_at, ?) > ?",
                (end, end, since, guild_id, user_id, end, end, since),
            ).fetchone()
            return max(0, int(row["secs"]))

        return await self._run(_total)

    async def rank_of(
        self, guild_id: int, user_id: int, *, since: int = 0, until: int | None = None
    ) -> tuple[int, int, int] | None:
        """Return ``(rank, seconds, population)`` or ``None`` if untracked."""
        rows = await self.leaderboard(guild_id, since=since, until=until)
        for index, row in enumerate(rows, start=1):
            if row.user_id == user_id:
                return index, row.seconds, len(rows)
        return None

    async def channel_breakdown(
        self,
        guild_id: int,
        user_id: int,
        *,
        since: int = 0,
        until: int | None = None,
        limit: int = 5,
    ) -> list[tuple[int, int]]:
        """Top channels for a member as ``(channel_id, seconds)`` pairs."""
        end = until if until is not None else now_ts()

        def _breakdown(conn: sqlite3.Connection) -> list[tuple[int, int]]:
            rows = conn.execute(
                "SELECT channel_id, "
                "SUM(MIN(COALESCE(ended_at, ?), ?) - MAX(started_at, ?)) AS secs "
                "FROM sessions WHERE guild_id = ? AND user_id = ? "
                "AND started_at < ? AND COALESCE(ended_at, ?) > ? "
                "GROUP BY channel_id HAVING secs > 0 ORDER BY secs DESC LIMIT ?",
                (end, end, since, guild_id, user_id, end, end, since, limit),
            ).fetchall()
            return [(row["channel_id"], int(row["secs"])) for row in rows]

        return await self._run(_breakdown)

    async def export_sessions(
        self, guild_id: int, user_id: int | None = None
    ) -> list[SessionRow]:
        def _export(conn: sqlite3.Connection) -> list[SessionRow]:
            if user_id is None:
                rows = conn.execute(
                    "SELECT guild_id, user_id, channel_id, started_at, ended_at, "
                    "seconds FROM sessions WHERE guild_id = ? ORDER BY started_at",
                    (guild_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT guild_id, user_id, channel_id, started_at, ended_at, "
                    "seconds FROM sessions WHERE guild_id = ? AND user_id = ? "
                    "ORDER BY started_at",
                    (guild_id, user_id),
                ).fetchall()
            return [
                SessionRow(
                    guild_id=row["guild_id"],
                    user_id=row["user_id"],
                    channel_id=row["channel_id"],
                    started_at=row["started_at"],
                    ended_at=row["ended_at"],
                    seconds=int(row["seconds"] or 0),
                )
                for row in rows
            ]

        return await self._run(_export)

    async def reset_member(self, guild_id: int, user_id: int) -> int:
        def _reset(conn: sqlite3.Connection) -> int:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                conn.execute(
                    "DELETE FROM milestones_granted WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                return cursor.rowcount

        return await self._run(_reset)

    # ------------------------------------------------------------ milestones

    async def granted_milestones(self, guild_id: int, user_id: int) -> set[int]:
        def _granted(conn: sqlite3.Connection) -> set[int]:
            rows = conn.execute(
                "SELECT threshold FROM milestones_granted "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchall()
            return {int(row["threshold"]) for row in rows}

        return await self._run(_granted)

    async def record_milestone(self, guild_id: int, user_id: int, threshold: int) -> None:
        def _record(conn: sqlite3.Connection) -> None:
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO milestones_granted "
                    "(guild_id, user_id, threshold, granted_at) VALUES (?, ?, ?, ?)",
                    (guild_id, user_id, threshold, now_ts()),
                )

        await self._run(_record)
