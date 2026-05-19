"""
MusicBot core class — manages Pyrogram bot + userbot clients,
PyTgCalls, database connections, handler registration, and lifecycle.
"""

import asyncio
import logging
import time
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import FloodWait

from bot.config.config import Config
from bot.database import mongodb, redis_db
from bot.streaming.engine import init_pytgcalls
from bot.handlers import play, controls, queue_handler, admin

log = logging.getLogger(__name__)

_start_time: float = 0.0


class MusicBot:
    def __init__(self):
        # Main bot client (commands)
        self.bot = Client(
            "musicbot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=4,
            sleep_threshold=60,
        )

        # Userbot assistant (joins voice chats)
        self.assistant = Client(
            "assistant",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=Config.STRING_SESSION,
            workers=4,
            sleep_threshold=60,
        )

        self.call_py = None

    async def start(self) -> None:
        global _start_time

        log.info("Connecting to MongoDB...")
        await mongodb.connect()

        log.info("Connecting to Redis...")
        await redis_db.connect()

        # Load ban cache into Redis
        log.info("Loading ban cache...")
        bans = await mongodb.get_all_bans()
        await redis_db.load_ban_cache([b["user_id"] for b in bans])

        # Load sudo users from DB
        log.info("Loading sudo users...")
        sudo_from_db = await mongodb.get_sudo_users()
        for uid in sudo_from_db:
            if uid not in Config.SUDO_USERS:
                Config.SUDO_USERS.append(uid)

        # Start clients
        log.info("Starting bot client...")
        await self.bot.start()
        log.info("Starting assistant client...")
        await self.assistant.start()

        # Init PyTgCalls
        log.info("Initialising PyTgCalls...")
        self.call_py = init_pytgcalls(self.assistant)
        await self.call_py.start()

        # Register all handlers
        self._register_handlers()

        _start_time = time.time()

        # Notify logs channel
        await self._send_startup_message()

        log.info("✅ %s v%s is online!", Config.BOT_NAME, Config.BOT_VERSION)

    async def stop(self) -> None:
        log.info("Shutting down...")
        try:
            if self.call_py:
                await self.call_py.stop()
        except Exception:
            pass
        try:
            await self.bot.stop()
        except Exception:
            pass
        try:
            await self.assistant.stop()
        except Exception:
            pass
        await redis_db.disconnect()
        await mongodb.disconnect()
        log.info("Shutdown complete.")

    def _register_handlers(self) -> None:
        log.info("Registering command handlers...")
        play.register(self.bot)
        controls.register(self.bot)
        queue_handler.register(self.bot)
        admin.register(self.bot)
        log.info("All handlers registered.")

    async def _send_startup_message(self) -> None:
        if not Config.LOG_GROUP_ID:
            return
        try:
            me = await self.bot.get_me()
            active_streams = 0  # freshly started
            text = (
                f"🚀 **{Config.BOT_NAME} Started**\n\n"
                f"**Version:** `{Config.BOT_VERSION}`\n"
                f"**Bot:** @{me.username}\n"
                f"**Time:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
                f"**Streams:** `{active_streams}`\n"
                f"**Maintenance:** `{'ON' if Config.MAINTENANCE else 'OFF'}`"
            )
            await self.bot.send_message(Config.LOG_GROUP_ID, text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            log.warning("Could not send startup message: %s", e)


def get_uptime() -> str:
    """Return human-readable uptime string."""
    if not _start_time:
        return "Not started"
    elapsed = int(time.time() - _start_time)
    d, r    = divmod(elapsed, 86400)
    h, r    = divmod(r, 3600)
    m, s    = divmod(r, 60)
    parts   = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)
  
