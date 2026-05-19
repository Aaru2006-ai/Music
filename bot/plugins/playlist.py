"""
Playlist plugin: /saveplaylist, /loadplaylist, /myplaylists, /deleteplaylist
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.helpers.decorators import banned_check, maintenance_check, group_only
from bot.helpers.keyboard import playlist_kb
from bot.streaming import queue as queue_engine, engine
from bot.helpers.formatters import now_playing_text
from bot.helpers.keyboard import now_playing_kb
from bot.database import mongodb, redis_db

log = logging.getLogger(__name__)


async def cmd_saveplaylist(client: Client, message: Message):
    """Save current queue as a named playlist."""
    user_id = message.from_user.id
    args    = message.command[1:]
    if not args:
        await message.reply_text(
            "💾 **Usage:** `/saveplaylist [name]`\n"
            "Saves the current queue as a named playlist."
        )
        return

    name   = " ".join(args).strip()[:50]
    tracks = await queue_engine.peek_queue(message.chat.id)
    current = await queue_engine.get_current(message.chat.id)

    all_tracks = []
    if current:
        all_tracks.append(current)
    all_tracks.extend(tracks)

    if not all_tracks:
        await message.reply_text("📭 Queue is empty — nothing to save.")
        return

    playlist_id = await mongodb.create_playlist(user_id, name, all_tracks)
    await message.reply_text(
        f"✅ **Playlist Saved!**\n\n"
        f"📂 Name: **{name}**\n"
        f"🎵 Tracks: `{len(all_tracks)}`\n\n"
        f"Load it anytime with `/loadplaylist {name}`"
    )


async def cmd_myplaylists(client: Client, message: Message):
    """List all saved playlists for the user."""
    user_id   = message.from_user.id
    playlists = await mongodb.get_user_playlists(user_id)
    if not playlists:
        await message.reply_text(
            "📂 You have no saved playlists.\n"
            "Save one with `/saveplaylist [name]`."
        )
        return
    await message.reply_text(
        f"📂 **Your Playlists** ({len(playlists)} total):",
        reply_markup=playlist_kb(playlists, user_id),
    )


async def cmd_loadplaylist(client: Client, message: Message):
    """Load a saved playlist into the current chat's queue."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    args    = message.command[1:]

    if not args:
        await message.reply_text("📂 **Usage:** `/loadplaylist [name]`")
        return

    name     = " ".join(args).strip()
    playlist = await mongodb.get_playlist(user_id, name)

    if not playlist:
        await message.reply_text(
            f"❌ No playlist named **{name}** found.\n"
            "Check your playlists with `/myplaylists`."
        )
        return

    tracks = playlist.get("tracks", [])
    if not tracks:
        await message.reply_text("⚠️ That playlist is empty.")
        return

    # Tag requester info
    req_name = message.from_user.first_name
    for t in tracks:
        t["requester_id"]   = user_id
        t["requester_name"] = req_name

    status_msg = await message.reply_text(f"📋 Loading **{name}** ({len(tracks)} tracks)...")

    if engine.is_active(chat_id):
        await queue_engine.add_tracks(chat_id, tracks)
        await status_msg.edit_text(
            f"✅ Added **{len(tracks)}** tracks from **{name}** to queue."
        )
    else:
        first  = tracks[0]
        rest   = tracks[1:]
        ok     = await engine.play(chat_id, first)
        if ok:
            if rest:
                await queue_engine.add_tracks(chat_id, rest)
            vol = await redis_db.get_volume(chat_id)
            await status_msg.edit_text(
                now_playing_text(first, queue_count=len(rest), volume=vol),
                reply_markup=now_playing_kb(chat_id),
            )
        else:
            await status_msg.edit_text("❌ Failed to start playlist playback.")


async def cmd_deleteplaylist(client: Client, message: Message):
    """Delete a saved playlist."""
    user_id = message.from_user.id
    args    = message.command[1:]

    if not args:
        await message.reply_text("🗑 **Usage:** `/deleteplaylist [name]`")
        return

    name    = " ".join(args).strip()
    removed = await mongodb.delete_playlist(user_id, name)
    if removed:
        await message.reply_text(f"🗑 Deleted playlist **{name}**.")
    else:
        await message.reply_text(f"❌ No playlist named **{name}** found.")


def register(app: Client) -> None:
    @app.on_message(filters.command("saveplaylist") & filters.group)
    @banned_check
    @maintenance_check
    async def _save(c, m): await cmd_saveplaylist(c, m)

    @app.on_message(filters.command("myplaylists"))
    @banned_check
    async def _mypl(c, m): await cmd_myplaylists(c, m)

    @app.on_message(filters.command("loadplaylist") & filters.group)
    @banned_check
    @maintenance_check
    async def _load(c, m): await cmd_loadplaylist(c, m)

    @app.on_message(filters.command("deleteplaylist"))
    @banned_check
    async def _del(c, m): await cmd_deleteplaylist(c, m)
          
