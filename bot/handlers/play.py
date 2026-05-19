"""
Play command handlers: /play, /vplay, /song, /radio, /replay, /restart
Handles: YouTube, Spotify, SoundCloud, playlists, Telegram files, direct URLs.
"""

import logging
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message, Audio, Voice, Video

from bot.config.config import Config
from bot.helpers.decorators import (
    banned_check, maintenance_check, rate_limit, group_only
)
from bot.helpers.keyboard import now_playing_kb, search_results_kb
from bot.helpers.formatters import now_playing_text
from bot.helpers.youtube import get_track_info, search_youtube, get_playlist_tracks, fetch_lyrics
from bot.helpers.spotify import (
    is_spotify_url, parse_spotify_url,
    get_spotify_track, get_spotify_playlist, get_spotify_album,
)
from bot.streaming import engine, queue as queue_engine
from bot.database import mongodb, redis_db

log = logging.getLogger(__name__)

# Temporary search cache: message_id → results list
_search_cache: dict = {}


# ── /play ─────────────────────────────────────────────────────────────────────

async def cmd_play(client: Client, message: Message):
    """Main play command — routes to appropriate source."""
    chat_id = message.chat.id
    user    = message.from_user

    # Source from reply (Telegram file)
    if message.reply_to_message:
        replied = message.reply_to_message
        file_obj: Optional[Audio | Voice | Video] = (
            replied.audio or replied.voice or replied.video
        )
        if file_obj:
            await _play_telegram_file(client, message, file_obj, chat_id, user)
            return

    # Source from text argument
    query = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""
    if not query:
        await message.reply_text(
            "🎵 **Usage:** `/play [song name or URL]`\n"
            "You can also reply to an audio/voice message with `/play`."
        )
        return

    await _resolve_and_play(client, message, query, chat_id, user, video=False)


async def cmd_vplay(client: Client, message: Message):
    """Video play command."""
    chat_id = message.chat.id
    user    = message.from_user
    query   = " ".join(message.command[1:]).strip()
    if not query:
        await message.reply_text("🎬 **Usage:** `/vplay [song name or URL]`")
        return
    await _resolve_and_play(client, message, query, chat_id, user, video=True)


async def cmd_song(client: Client, message: Message):
    """Search YouTube and present clickable results."""
    query = " ".join(message.command[1:]).strip()
    if not query:
        await message.reply_text("🔍 **Usage:** `/song [song name]`")
        return

    searching_msg = await message.reply_text(f"🔍 Searching for **{query}**...")
    results = await search_youtube(query, limit=5)
    if not results:
        await searching_msg.edit_text("❌ No results found. Try a different query.")
        return

    _search_cache[searching_msg.id] = results
    text = "**🔎 Search Results:**\n\n"
    for i, r in enumerate(results):
        text += f"`{i + 1}.` {r['title'][:45]} `[{r['duration_str']}]`\n"

    await searching_msg.edit_text(
        text,
        reply_markup=search_results_kb(results, message.chat.id),
    )


async def cmd_radio(client: Client, message: Message):
    """Play a radio/live stream URL."""
    chat_id = message.chat.id
    user    = message.from_user
    url     = " ".join(message.command[1:]).strip()
    if not url or not url.startswith("http"):
        await message.reply_text(
            "📻 **Usage:** `/radio [stream URL]`\n"
            "_e.g. /radio https://stream.example.com/live.mp3_"
        )
        return

    track = {
        "title":          "📻 Radio Stream",
        "uploader":       url,
        "duration":       0,
        "duration_str":   "Live",
        "stream_url":     url,
        "url":            url,
        "source":         "Radio",
        "thumbnail":      "",
        "requester_id":   user.id,
        "requester_name": user.first_name,
    }

    status_msg = await message.reply_text("📻 Starting radio stream...")
    ok = await engine.play(chat_id, track)
    if ok:
        await status_msg.edit_text(
            now_playing_text(track, volume=await redis_db.get_volume(chat_id)),
            reply_markup=now_playing_kb(chat_id),
        )
    else:
        await status_msg.edit_text("❌ Failed to start radio stream. Check the URL and try again.")


async def cmd_replay(client: Client, message: Message):
    """Replay the currently playing track from the beginning."""
    chat_id = message.chat.id
    current = await queue_engine.get_current(chat_id)
    if not current:
        await message.reply_text("❌ Nothing is currently playing.")
        return
    current_copy = dict(current)
    current_copy["stream_url"] = None  # force re-resolve
    ok = await engine.play(chat_id, current_copy)
    if ok:
        await message.reply_text(f"🔄 Replaying **{current.get('title', 'track')}**.")
    else:
        await message.reply_text("❌ Failed to replay. Try again.")


# ── Internal resolution helpers ───────────────────────────────────────────────

async def _resolve_and_play(
    client: Client,
    message: Message,
    query: str,
    chat_id: int,
    user,
    video: bool = False,
):
    req_id   = user.id
    req_name = user.first_name

    status_msg = await message.reply_text("🔍 Processing your request...")

    # ── Spotify ──
    if is_spotify_url(query):
        parsed = parse_spotify_url(query)
        if not parsed:
            await status_msg.edit_text("❌ Invalid Spotify URL.")
            return
        sp_type, sp_id = parsed

        if sp_type == "track":
            track = await get_spotify_track(sp_id)
            if not track:
                await status_msg.edit_text("❌ Could not fetch Spotify track.")
                return
            track["requester_id"]   = req_id
            track["requester_name"] = req_name
            await _enqueue_and_play(message, status_msg, chat_id, track, video)

        elif sp_type in ("playlist", "album"):
            tracks = (
                await get_spotify_playlist(sp_id)
                if sp_type == "playlist"
                else await get_spotify_album(sp_id)
            )
            if not tracks:
                await status_msg.edit_text("❌ Could not fetch Spotify playlist/album.")
                return
            for t in tracks:
                t["requester_id"]   = req_id
                t["requester_name"] = req_name
            first, rest = tracks[0], tracks[1:]
            await status_msg.edit_text(f"📋 Adding {len(tracks)} tracks to queue...")
            await _enqueue_and_play(message, status_msg, chat_id, first, video)
            if rest:
                await queue_engine.add_tracks(chat_id, rest)
                await message.reply_text(
                    f"✅ Added **{len(rest)}** more tracks to queue.",
                )
        return

    # ── YouTube playlist ──
    if "youtube.com/playlist" in query or "list=" in query:
        await status_msg.edit_text("📋 Fetching playlist...")
        tracks = await get_playlist_tracks(query, limit=Config.QUEUE_LIMIT)
        if not tracks:
            await status_msg.edit_text("❌ Could not load playlist.")
            return
        for t in tracks:
            t["requester_id"]   = req_id
            t["requester_name"] = req_name
        first, rest = tracks[0], tracks[1:]
        await _enqueue_and_play(message, status_msg, chat_id, first, video)
        if rest:
            await queue_engine.add_tracks(chat_id, rest)
            await message.reply_text(f"✅ Added **{len(rest)}** more tracks to queue.")
        return

    # ── Direct URL / search query ──
    track = await get_track_info(query, req_id, req_name)
    if not track:
        await status_msg.edit_text(
            "❌ Could not find that track. Try a different search term."
        )
        return
    if track.get("error") == "duration_exceeded":
        dur = track.get("duration", 0) / 60
        await status_msg.edit_text(
            f"❌ Track is **{dur:.1f} min** long.\n"
            f"Maximum allowed duration: **{Config.DURATION_LIMIT} min**."
        )
        return

    await _enqueue_and_play(message, status_msg, chat_id, track, video)


async def _enqueue_and_play(message, status_msg, chat_id, track, video):
    if engine.is_active(chat_id):
        # Bot already streaming — add to queue
        pos = await queue_engine.add_track(chat_id, track)
        await status_msg.edit_text(
            f"📋 **Added to Queue** (position #{pos})\n\n"
            f"🎵 {track.get('title', 'Unknown')}\n"
            f"⏱ {track.get('duration_str', '??:??')}"
        )
    else:
        # Start fresh
        ok = await engine.play(chat_id, track, video=video)
        if ok:
            vol = await redis_db.get_volume(chat_id)
            await status_msg.edit_text(
                now_playing_text(track, volume=vol),
                reply_markup=now_playing_kb(chat_id),
            )
        else:
            await status_msg.edit_text(
                "❌ Failed to start playback. "
                "Make sure I am in the voice chat and have the necessary permissions."
            )


async def _play_telegram_file(client, message, file_obj, chat_id, user):
    """Stream a Telegram audio/voice/video file."""
    status_msg = await message.reply_text("📥 Downloading file...")
    file_path  = await client.download_media(file_obj, file_name=f"cache/tg_{file_obj.file_id[:8]}")

    title = getattr(file_obj, "title", None) or getattr(file_obj, "file_name", "Telegram Audio")
    duration = getattr(file_obj, "duration", 0)

    track = {
        "title":          title,
        "uploader":       user.first_name,
        "duration":       duration,
        "duration_str":   f"{duration // 60:02d}:{duration % 60:02d}",
        "stream_url":     file_path,
        "url":            f"tg://{file_obj.file_id}",
        "source":         "Telegram",
        "thumbnail":      "",
        "file_path":      file_path,
        "requester_id":   user.id,
        "requester_name": user.first_name,
    }

    if engine.is_active(chat_id):
        pos = await queue_engine.add_track(chat_id, track)
        await status_msg.edit_text(
            f"📋 Added Telegram file to queue at position **#{pos}**."
        )
    else:
        ok = await engine.play(chat_id, track)
        if ok:
            vol = await redis_db.get_volume(chat_id)
            await status_msg.edit_text(
                now_playing_text(track, volume=vol),
                reply_markup=now_playing_kb(chat_id),
            )
        else:
            await status_msg.edit_text("❌ Failed to stream file.")


# ── Apply decorators & register ────────────────────────────────────────────────

_play_decorators  = [banned_check, maintenance_check, group_only, rate_limit("play", 3, 10)]
_vplay_decorators = [banned_check, maintenance_check, group_only, rate_limit("vplay", 2, 15)]


def register(app: Client) -> None:
    """Register all play handlers with the Pyrogram app."""

    @app.on_message(filters.command("play") & filters.group)
    @banned_check
    @maintenance_check
    @rate_limit("play", 3, 10)
    async def _play(c, m): await cmd_play(c, m)

    @app.on_message(filters.command("vplay") & filters.group)
    @banned_check
    @maintenance_check
    @rate_limit("vplay", 2, 15)
    async def _vplay(c, m): await cmd_vplay(c, m)

    @app.on_message(filters.command("song") & filters.group)
    @banned_check
    @maintenance_check
    @rate_limit("song", 3, 10)
    async def _song(c, m): await cmd_song(c, m)

    @app.on_message(filters.command("radio") & filters.group)
    @banned_check
    @maintenance_check
    @rate_limit("radio", 2, 15)
    async def _radio(c, m): await cmd_radio(c, m)

    @app.on_message(filters.command("replay") & filters.group)
    @banned_check
    @maintenance_check
    async def _replay(c, m): await cmd_replay(c, m)
  
