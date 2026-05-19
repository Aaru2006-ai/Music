"""
Background scheduled jobs using APScheduler.
Jobs: stream watchdog, cache cleanup, analytics aggregation, auto-leave idle chats.
"""

import asyncio
import logging
import os
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config.config import Config
from bot.database import redis_db, mongodb
from bot.streaming import engine, queue as queue_engine

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")
_bot_client = None   # set via init()


def init(bot) -> None:
    """Call after bot.start() to wire up the scheduler's bot reference."""
    global _bot_client
    _bot_client = bot


def start() -> None:
    if not scheduler.running:
        scheduler.start()
        log.info("Background scheduler started.")


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Background scheduler stopped.")


# ── Job: Dead stream watchdog (every 60 s) ────────────────────────────────────

@scheduler.scheduled_job("interval", seconds=60, id="stream_watchdog")
async def stream_watchdog():
    """
    Check all active streams tracked in Redis.
    If a stream has been 'active' but the engine shows no call,
    clean up stale state to prevent ghost entries.
    """
    try:
        streams = await redis_db.get_all_active_streams()
        for stream in streams:
            chat_id = stream.get("chat_id") or stream.get("requester_id")
            if not chat_id:
                continue
            if not engine.is_active(int(chat_id)):
                log.info("[WATCHDOG] Cleaning stale stream for chat %s", chat_id)
                await redis_db.delete_active_stream(int(chat_id))
    except Exception as e:
        log.error("[WATCHDOG] Error: %s", e)


# ── Job: Cache directory cleanup (every 2 hours) ─────────────────────────────

CACHE_DIR   = os.path.join(os.path.dirname(__file__), "../../cache")
MAX_AGE_SEC = 7200  # 2 hours


@scheduler.scheduled_job("interval", hours=2, id="cache_cleanup")
async def cache_cleanup():
    """Remove downloaded audio files older than MAX_AGE_SEC."""
    if not os.path.isdir(CACHE_DIR):
        return
    now   = time.time()
    count = 0
    try:
        for fname in os.listdir(CACHE_DIR):
            fpath = os.path.join(CACHE_DIR, fname)
            if os.path.isfile(fpath):
                age = now - os.path.getmtime(fpath)
                if age > MAX_AGE_SEC:
                    os.remove(fpath)
                    count += 1
        if count:
            log.info("[CACHE CLEANUP] Removed %d old file(s).", count)
    except Exception as e:
        log.error("[CACHE CLEANUP] Error: %s", e)


# ── Job: Auto-leave idle voice chats (every 5 min) ───────────────────────────

IDLE_TIMEOUT = 300  # seconds of queue-empty inactivity before leaving


@scheduler.scheduled_job("interval", minutes=5, id="idle_leave")
async def idle_leave():
    """Leave voice chats where queue has been empty for IDLE_TIMEOUT seconds."""
    if not Config.AUTO_LEAVING_ASSISTANT:
        return
    try:
        streams = await redis_db.get_all_active_streams()
        now = time.time()
        for stream in streams:
            chat_id  = stream.get("chat_id")
            if not chat_id:
                continue
            chat_id  = int(chat_id)
            is_empty = await queue_engine.is_empty(chat_id)
            if not is_empty:
                continue
            # Check when queue became empty (stored in stream data)
            empty_since = stream.get("empty_since")
            if not empty_since:
                stream["empty_since"] = now
                await redis_db.set_active_stream(chat_id, stream)
                continue
            if now - float(empty_since) > IDLE_TIMEOUT:
                log.info("[IDLE LEAVE] Leaving idle chat %d", chat_id)
                await engine.stop(chat_id)
    except Exception as e:
        log.error("[IDLE LEAVE] Error: %s", e)


# ── Job: Daily analytics snapshot (every day at midnight UTC) ─────────────────

@scheduler.scheduled_job("cron", hour=0, minute=0, id="daily_analytics")
async def daily_analytics():
    """Log daily stats to the logs channel."""
    if not _bot_client:
        return
    try:
        stats  = await mongodb.get_stats()
        active = engine.get_active_count()
        text = (
            f"📊 **Daily Stats Snapshot**\n\n"
            f"👤 Users: `{stats.get('users', 0):,}`\n"
            f"💬 Chats: `{stats.get('chats', 0):,}`\n"
            f"🎵 Active Streams: `{active}`\n"
            f"📂 Playlists: `{stats.get('playlists', 0):,}`\n"
        )
        await _bot_client.bot.send_message(Config.LOG_GROUP_ID, text)
    except Exception as e:
        log.error("[ANALYTICS] Daily snapshot error: %s", e)


# ── Job: MongoDB old history cleanup (weekly) ────────────────────────────────

@scheduler.scheduled_job("cron", day_of_week="sun", hour=3, id="db_cleanup")
async def db_cleanup():
    """Prune playback_history older than 30 days to keep the DB lean."""
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = await mongodb.db().playback_history.delete_many(
            {"played_at": {"$lt": cutoff}}
        )
        log.info("[DB CLEANUP] Deleted %d old history entries.", result.deleted_count)
    except Exception as e:
        log.error("[DB CLEANUP] Error: %s", e)
