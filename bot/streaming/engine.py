"""
Core streaming engine powered by PyTgCalls + FFmpeg.
"""

import asyncio
import logging
from typing import Dict, Optional

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality
from pytgcalls.types.stream import StreamAudioEnded

from bot.database import redis_db, mongodb
from bot.helpers import youtube as yt
from bot.streaming import queue as queue_engine

log = logging.getLogger(__name__)

_call_py: Optional[PyTgCalls] = None
_active_chats: Dict[int, bool] = {}


# ── Initialise ────────────────────────────────────────────────────────────────

def init_pytgcalls(assistant: Client) -> PyTgCalls:

    global _call_py

    _call_py = PyTgCalls(assistant)

    @_call_py.on_stream_end()
    async def _on_stream_end(_, update: StreamAudioEnded):

        log.info(
            "Stream ended in chat %d — advancing queue.",
            update.chat_id
        )

        await _advance(update.chat_id)

    return _call_py


def call_py() -> PyTgCalls:

    if _call_py is None:
        raise RuntimeError(
            "PyTgCalls not initialised."
        )

    return _call_py


# ── Play ──────────────────────────────────────────────────────────────────────

async def play(
    chat_id: int,
    track: dict,
    video: bool = False,
    reply_fn=None,
) -> bool:

    stream_url = track.get("stream_url")

    if not stream_url:

        track_info = await yt.get_track_info(
            track.get("url")
            or track.get("search_query")
            or track.get("title", ""),

            track.get("requester_id", 0),
            track.get("requester_name", "Unknown"),
        )

        if not track_info or track_info.get("error"):

            log.warning(
                "Could not resolve stream for: %s",
                track.get("title")
            )

            return False

        stream_url = track_info.get(
            "stream_url",
            ""
        )

        track.update(track_info)

    if not stream_url:

        log.error(
            "Empty stream URL for track: %s",
            track.get("title")
        )

        return False

    quality = AudioQuality.HIGH

    media = MediaStream(
        
        stream_url,
        audio_parameters=quality,
    )

    try:

        if _active_chats.get(chat_id):

            await call_py().change_stream(
                chat_id,
                media
            )

        else:

            await call_py().join_group_call(
                chat_id,
                media
            )

            _active_chats[chat_id] = True

        await queue_engine.set_current(
            chat_id,
            track
        )

        await redis_db.set_active_stream(
            chat_id,
            track
        )

        await redis_db.set_paused(
            chat_id,
            False
        )

        await mongodb.increment_play(
            track.get("requester_id", 0),
            chat_id,
            track.get("title", "Unknown"),
        )

        await mongodb.add_to_history(
            chat_id,
            track
        )

        log.info(
            "[PLAY] %s in chat %d",
            track.get("title"),
            chat_id
        )

        return True

    except Exception as e:

        log.error(
            "[PLAY] Error in chat %d: %s",
            chat_id,
            e,
            exc_info=True
        )

        _active_chats.pop(
            chat_id,
            None
        )

        return False
