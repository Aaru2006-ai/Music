"""
Core streaming engine powered by PyTgCalls + FFmpeg.
Manages voice-chat lifecycle: join, stream, pause, resume, seek, skip, stop.
Auto-advances to next track when current finishes.
"""

import asyncio
import logging
import os
from typing import Dict, Optional

from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.types.input_stream.quality import HighQualityAudio


from bot.config.config import Config
from bot.database import redis_db, mongodb
from bot.helpers import youtube as yt
from bot.streaming import queue as queue_engine

log = logging.getLogger(__name__)

# Maps PyTgCalls instance per client
_call_py: Optional[PyTgCalls] = None

# chat_id → True if assistant is active
_active_chats: Dict[int, bool] = {}


# ── Initialise ─────────────────────────────────────────────────────────────────

def init_pytgcalls(assistant: Client) -> PyTgCalls:
    """Create and configure the PyTgCalls instance bound to the userbot."""
    global _call_py
    _call_py = PyTgCalls(assistant)

    @_call_py.on_stream_end()
    async def _on_stream_end(_, update: StreamEnded):
        log.info("Stream ended in chat %d — advancing queue.", update.chat_id)
        await _advance(update.chat_id)

    @_call_py.on_closed_voice_chat()
    async def _on_vc_closed(_, chat_id: int):
        log.info("Voice chat closed in %d.", chat_id)
        await _cleanup(chat_id)

    return _call_py


def call_py() -> PyTgCalls:
    if _call_py is None:
        raise RuntimeError("PyTgCalls not initialised. Call init_pytgcalls() first.")
    return _call_py


# ── Play ───────────────────────────────────────────────────────────────────────

async def play(
    chat_id: int,
    track: dict,
    video: bool = False,
    reply_fn=None,
) -> bool:
    """
    Resolve stream URL and start/resume playback in `chat_id`.
    `reply_fn` is an optional coroutine(text) for sending now-playing messages.
    """
    stream_url = track.get("stream_url")
    if not stream_url:
        track_info = await yt.get_track_info(
            track.get("url") or track.get("search_query") or track.get("title", ""),
            track.get("requester_id", 0),
            track.get("requester_name", "Unknown"),
        )
        if not track_info or track_info.get("error"):
            log.warning("Could not resolve stream for: %s", track.get("title"))
            return False
        stream_url = track_info.get("stream_url", "")
        track.update(track_info)

    if not stream_url:
        log.error("Empty stream URL for track: %s", track.get("title"))
        return False

    quality = (
        AudioQuality.HIGH if Config.STREAM_QUALITY >= 128 else AudioQuality.MEDIUM
    )

    media = MediaStream(
        stream_url,
        audio_parameters=quality,
        video_flags=MediaStream.IGNORE if not video else None,
    )

    try:
        if _active_chats.get(chat_id):
            await call_py().change_stream(chat_id, media)
        else:
            await call_py().join_group_call(chat_id, media)
            _active_chats[chat_id] = True

        await queue_engine.set_current(chat_id, track)
        await redis_db.set_active_stream(chat_id, track)
        await redis_db.set_paused(chat_id, False)
        await mongodb.increment_play(
            track.get("requester_id", 0),
            chat_id,
            track.get("title", "Unknown"),
        )
        await mongodb.add_to_history(chat_id, track)

        log.info("[PLAY] %s in chat %d", track.get("title"), chat_id)
        return True

    except Exception as e:
        log.error("[PLAY] Error in chat %d: %s", chat_id, e, exc_info=True)
        _active_chats.pop(chat_id, None)
        return False


# ── Controls ───────────────────────────────────────────────────────────────────

async def pause(chat_id: int) -> bool:
    if not _active_chats.get(chat_id):
        return False
    try:
        await call_py().pause_stream(chat_id)
        await redis_db.set_paused(chat_id, True)
        log.info("[PAUSE] chat %d", chat_id)
        return True
    except Exception as e:
        log.error("[PAUSE] %d: %s", chat_id, e)
        return False


async def resume(chat_id: int) -> bool:
    if not _active_chats.get(chat_id):
        return False
    try:
        await call_py().resume_stream(chat_id)
        await redis_db.set_paused(chat_id, False)
        log.info("[RESUME] chat %d", chat_id)
        return True
    except Exception as e:
        log.error("[RESUME] %d: %s", chat_id, e)
        return False


async def skip(chat_id: int) -> Optional[dict]:
    """Skip current track and play next. Returns new current track or None."""
    loop = await redis_db.get_loop(chat_id)
    if loop:
        current = await queue_engine.get_current(chat_id)
        if current:
            await play(chat_id, current)
            return current

    next_track = await queue_engine.get_next(chat_id)
    if next_track:
        await play(chat_id, next_track)
        return next_track
    else:
        await stop(chat_id)
        return None


async def stop(chat_id: int) -> bool:
    """Stop playback, clear queue, leave VC."""
    try:
        if _active_chats.get(chat_id):
            await call_py().leave_group_call(chat_id)
    except Exception:
        pass
    await _cleanup(chat_id)
    log.info("[STOP] chat %d", chat_id)
    return True


async def seek(chat_id: int, seconds: int) -> bool:
    """Seek to absolute position in seconds."""
    current = await queue_engine.get_current(chat_id)
    if not current:
        return False
    stream_url = current.get("stream_url", "")
    if not stream_url:
        return False
    quality = AudioQuality.HIGH if Config.STREAM_QUALITY >= 128 else AudioQuality.MEDIUM
    media = MediaStream(
        stream_url,
        audio_parameters=quality,
        ffmpeg_parameters=f"-ss {seconds}",
        video_flags=MediaStream.IGNORE,
    )
    try:
        await call_py().change_stream(chat_id, media)
        return True
    except Exception as e:
        log.error("[SEEK] %d: %s", chat_id, e)
        return False


async def set_volume(chat_id: int, volume: int) -> bool:
    """Set playback volume (0–200)."""
    volume = max(0, min(200, volume))
    try:
        await call_py().change_volume_call(chat_id, volume)
        await redis_db.set_volume(chat_id, volume)
        return True
    except Exception as e:
        log.error("[VOLUME] %d: %s", chat_id, e)
        return False


async def mute(chat_id: int) -> bool:
    try:
        await call_py().mute_stream(chat_id)
        return True
    except Exception:
        return False


async def unmute(chat_id: int) -> bool:
    try:
        await call_py().unmute_stream(chat_id)
        return True
    except Exception:
        return False


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _advance(chat_id: int) -> None:
    """Called automatically when a stream ends."""
    loop = await redis_db.get_loop(chat_id)
    if loop:
        current = await queue_engine.get_current(chat_id)
        if current:
            await asyncio.sleep(0.5)
            await play(chat_id, current)
            return

    next_track = await queue_engine.get_next(chat_id)
    if next_track:
        await asyncio.sleep(0.5)
        await play(chat_id, next_track)
    else:
        log.info("[AUTO-STOP] Queue empty in chat %d.", chat_id)
        await _cleanup(chat_id)


async def _cleanup(chat_id: int) -> None:
    _active_chats.pop(chat_id, None)
    await redis_db.delete_active_stream(chat_id)
    await redis_db.set_paused(chat_id, False)
    await queue_engine.clear_queue(chat_id)


def is_active(chat_id: int) -> bool:
    return bool(_active_chats.get(chat_id))


def get_active_count() -> int:
    return len(_active_chats)
      
