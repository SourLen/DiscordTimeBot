"""Entry point: ``python -m timebot``."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

import discord

from .bot import TimeBot
from .config import ConfigError, load_config, load_dotenv

log = logging.getLogger("timebot")


def configure_logging(level: str) -> None:
    discord.utils.setup_logging(level=getattr(logging, level, logging.INFO), root=True)


def install_shutdown_handlers(bot: TimeBot) -> None:
    """Close the bot cleanly on SIGTERM as well as SIGINT.

    ``Client.run()`` installs handlers for us, but this process drives
    ``Client.start()`` directly so it can control the exit code. Without this,
    ``systemctl stop`` would kill the process mid-session and every member
    currently in voice would lose time back to the last heartbeat.
    """
    loop = asyncio.get_running_loop()

    def _shutdown(signal_name: str) -> None:
        log.info("Received %s, shutting down.", signal_name)
        loop.create_task(bot.close())

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        with contextlib.suppress(NotImplementedError):  # not available on Windows
            loop.add_signal_handler(sig, _shutdown, name)


async def run() -> int:
    load_dotenv()
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    configure_logging(config.log_level)

    bot = TimeBot(config)
    install_shutdown_handlers(bot)
    try:
        await bot.start(config.token)
    except discord.LoginFailure:
        log.error("Discord rejected the token. Check DISCORD_TOKEN in your .env.")
        return 2
    except discord.PrivilegedIntentsRequired:
        log.error(
            "The Server Members Intent is not enabled. Open "
            "https://discord.com/developers/applications -> your app -> Bot -> "
            "Privileged Gateway Intents and turn on 'Server Members Intent'."
        )
        return 2
    finally:
        if not bot.is_closed():
            await bot.close()
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
