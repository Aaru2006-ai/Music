#!/usr/bin/env python3
"""
Telegram Music Bot — Enterprise Grade
Heroku-ready, async, production deployment.

Usage:
    python -m bot        (recommended)
    python main.py
"""

import asyncio
import logging
import sys

from bot.config.config import Config
from bot.core.bot import MusicBot
from bot.helpers.logger import setup_logger


async def main() -> None:
    setup_logger()
    log = logging.getLogger("main")

    log.info("=" * 50)
    log.info("  Telegram Music Bot  v%s", Config.BOT_VERSION)
    log.info("=" * 50)

    # Validate env vars — exits on failure
    Config.validate()

    bot = MusicBot()
    try:
        await bot.start()
        # Keep alive
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        log.info("Interrupt received — shutting down gracefully.")
    except Exception as exc:
        log.critical("Fatal unhandled error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
