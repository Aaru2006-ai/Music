"""
Queue management: /queue, /remove, /clearqueue, /history
Inline callback handler for all button interactions.
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from bot.helpers.decorators import banned_check, maintenance_check, admin_only
from bot.helpers.keyboard import (
    now_playing_kb, queue_kb, settings_kb, help_kb, close_kb, HELP_TEXTS
)
from bot.helpers.formatters import format_queue, now_playing_text, HELP_TEXTS as HT
from bot.streaming import engine, queue as queue_engine
from bot.database import redis_db, mongodb

log = logging.getLogger(__name__)

# search_cache reference (populated in play.py)
_search_results_cache: dict = {}


# ── /queue ────────────────────────────────────────────────────────────────────

async def cmd_queue(client: Client, message: Message, page: int = 1):
    chat_id = message.chat.id
    current = await queue_engine.get_current(chat_id)
    tracks, total_pages, total = queue_engine.paginate_queue(chat_id, page)
    chat = await client.get_chat(chat_id)
    text = format_queue(current, tracks, page, total_pages, chat.title or "Queue")
    await message.reply_text(
        text,
        reply_markup=queue_kb(chat_id, page, total_pages),
    )


# ── /remove ───────────────────────────────────────────────────────────────────

async def cmd_remove(client: Client, message: Message):
    chat_id = message.chat.id
    args = message.command[1:]
    if not args or not args[0].isdigit():
        await message.reply_text("🗑 **Usage:** `/remove [position]`\nExample: `/remove 2`")
        return
    pos = int(args[0])
    removed = await queue_engine.remove_track(chat_id, pos)
    if removed:
        await message.reply_text(f"🗑 Removed **{removed.get('title', 'track')}** from queue.")
    else:
        await message.reply_text(f"❌ No track at position `{pos}`.")


# ── /clearqueue ────────────────────────────────────────────────────────────────

async def cmd_clearqueue(client: Client, message: Message):
    chat_id = message.chat.id
    count   = await queue_engine.clear_queue(chat_id)
    await message.reply_text(f"🗑 Cleared **{count}** track(s) from the queue.")


# ── /history ──────────────────────────────────────────────────────────────────

async def cmd_history(client: Client, message: Message):
    chat_id = message.chat.id
    history = await mongodb.get_history(chat_id, limit=15)
    if not history:
        await message.reply_text("📜 No playback history yet.")
        return
    lines = ["**📜 Recent Playback History:**\n"]
    for i, t in enumerate(history, 1):
        title = t.get("title", "Unknown")[:40]
        dur   = t.get("duration_str", "??:??")
        lines.append(f"`{i}.` {title} `[{dur}]`")
    await message.reply_text("\n".join(lines))


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(client: Client, message: Message):
    text = (
        f"**🎵 Welcome to MusicBot!**\n\n"
        f"I can stream music in Telegram voice chats.\n"
        f"Choose a category below to see commands:"
    )
    await message.reply_text(text, reply_markup=help_kb())


# ── /settings ─────────────────────────────────────────────────────────────────

async def cmd_settings(client: Client, message: Message):
    chat_id  = message.chat.id
    settings = await mongodb.get_chat_settings(chat_id)
    await message.reply_text(
        "⚙️ **Chat Settings**\nToggle options below:",
        reply_markup=settings_kb(chat_id, settings),
    )


# ── Inline Callbacks ──────────────────────────────────────────────────────────

async def handle_callback(client: Client, query: CallbackQuery):
    data    = query.data
    user_id = query.from_user.id

    # ── close ──
    if data == "close":
        try:
            await query.message.delete()
        except Exception:
            await query.answer("Closed.", show_alert=False)
        return

    parts = data.split(":")

    # ── Playback controls ──
    if parts[0] == "pause":
        chat_id = int(parts[1])
        ok = await engine.pause(chat_id)
        await query.answer("⏸ Paused" if ok else "❌ Failed")
        if ok:
            await query.message.edit_reply_markup(
                now_playing_kb(chat_id, paused=True)
            )
        return

    if parts[0] == "resume":
        chat_id = int(parts[1])
        ok = await engine.resume(chat_id)
        await query.answer("▶️ Resumed" if ok else "❌ Failed")
        if ok:
            await query.message.edit_reply_markup(
                now_playing_kb(chat_id, paused=False)
            )
        return

    if parts[0] == "skip":
        chat_id    = int(parts[1])
        next_track = await engine.skip(chat_id)
        if next_track:
            vol  = await redis_db.get_volume(chat_id)
            await query.message.edit_text(
                now_playing_text(next_track, volume=vol),
                reply_markup=now_playing_kb(chat_id),
            )
            await query.answer("⏭ Skipped!")
        else:
            await query.answer("📭 Queue is empty.")
            try:
                await query.message.delete()
            except Exception:
                pass
        return

    if parts[0] == "stop":
        chat_id = int(parts[1])
        await engine.stop(chat_id)
        await query.answer("⏹ Stopped.")
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if parts[0] == "loop":
        chat_id = int(parts[1])
        cur = await redis_db.get_loop(chat_id)
        await redis_db.set_loop(chat_id, not cur)
        await query.answer(f"🔁 Loop {'On' if not cur else 'Off'}")
        return

    if parts[0] == "shuffle":
        chat_id = int(parts[1])
        count   = await queue_engine.shuffle_queue(chat_id)
        await query.answer(f"🔀 Shuffled {count} tracks")
        return

    if parts[0] == "mute":
        chat_id = int(parts[1])
        await engine.mute(chat_id)
        await query.answer("🔇 Muted")
        return

    if parts[0] == "unmute":
        chat_id = int(parts[1])
        await engine.unmute(chat_id)
        await query.answer("🔊 Unmuted")
        return

    if parts[0] == "vol_up":
        chat_id = int(parts[1])
        vol = min(200, await redis_db.get_volume(chat_id) + 10)
        await engine.set_volume(chat_id, vol)
        await query.answer(f"🔊 Volume: {vol}%")
        return

    if parts[0] == "vol_down":
        chat_id = int(parts[1])
        vol = max(0, await redis_db.get_volume(chat_id) - 10)
        await engine.set_volume(chat_id, vol)
        await query.answer(f"🔉 Volume: {vol}%")
        return

    # ── Queue pagination ──
    if parts[0] == "queue":
        chat_id     = int(parts[1])
        page        = int(parts[2]) if len(parts) > 2 else 1
        current     = await queue_engine.get_current(chat_id)
        tracks, total_pages, _ = queue_engine.paginate_queue(chat_id, page)
        chat_obj    = await client.get_chat(chat_id)
        text        = format_queue(current, tracks, page, total_pages, chat_obj.title or "Queue")
        await query.message.edit_text(text, reply_markup=queue_kb(chat_id, page, total_pages))
        await query.answer()
        return

    # ── Clear queue ──
    if parts[0] == "clear_queue":
        chat_id = int(parts[1])
        count   = await queue_engine.clear_queue(chat_id)
        await query.answer(f"🗑 Cleared {count} tracks")
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Lyrics ──
    if parts[0] == "lyrics":
        from bot.helpers.youtube import fetch_lyrics
        chat_id = int(parts[1])
        current = await queue_engine.get_current(chat_id)
        if not current:
            await query.answer("❌ Nothing is playing.", show_alert=True)
            return
        await query.answer("🎵 Fetching lyrics...")
        lyrics = await fetch_lyrics(current.get("title", ""))
        if lyrics:
            await query.message.reply_text(
                f"🎵 **Lyrics: {current['title']}**\n\n{lyrics[:3500]}",
                reply_markup=close_kb(),
            )
        else:
            await query.answer("❌ Lyrics not found.", show_alert=True)
        return

    # ── Download ──
    if parts[0] == "download":
        chat_id = int(parts[1])
        current = await queue_engine.get_current(chat_id)
        if not current:
            await query.answer("❌ Nothing is playing.", show_alert=True)
            return
        await query.answer("⬇️ Use /play with the URL to download.", show_alert=True)
        return

    # ── Search result selection ──
    if parts[0] == "play_result":
        from bot.streaming.engine import play as eng_play, is_active
        chat_id = int(parts[1])
        idx     = int(parts[2])
        # Try to fetch from message ID cache
        results_key = query.message.id
        results = _search_results_cache.get(results_key, [])
        if idx >= len(results):
            await query.answer("❌ Expired result.", show_alert=True)
            return
        track = results[idx]
        track["requester_id"]   = user_id
        track["requester_name"] = query.from_user.first_name
        if is_active(chat_id):
            pos = await queue_engine.add_track(chat_id, track)
            await query.message.edit_text(
                f"📋 Added **{track['title']}** to queue at position #{pos}."
            )
        else:
            ok = await eng_play(chat_id, track)
            if ok:
                vol = await redis_db.get_volume(chat_id)
                await query.message.edit_text(
                    now_playing_text(track, volume=vol),
                    reply_markup=now_playing_kb(chat_id),
                )
            else:
                await query.message.edit_text("❌ Failed to start playback.")
        await query.answer()
        return

    # ── Help categories ──
    if parts[0] == "help":
        cat  = parts[1] if len(parts) > 1 else "music"
        text = HT.get(cat, "❌ Unknown category.")
        await query.message.edit_text(text, reply_markup=help_kb())
        await query.answer()
        return

    # ── Settings toggles ──
    if parts[0] == "setting":
        key     = parts[1]
        chat_id = int(parts[2])
        settings = await mongodb.get_chat_settings(chat_id)
        new_val  = not settings.get(key, False)
        await mongodb.update_chat_setting(chat_id, key, new_val)
        if key == "loop":
            await redis_db.set_loop(chat_id, new_val)
        elif key == "shuffle":
            await redis_db.set_shuffle(chat_id, new_val)
        settings[key] = new_val
        await query.message.edit_reply_markup(settings_kb(chat_id, settings))
        await query.answer(f"{'✅' if new_val else '❌'} {key.replace('_', ' ').title()}")
        return

    await query.answer("⚠️ Unknown action.", show_alert=True)


# ── Register ───────────────────────────────────────────────────────────────────

def register(app: Client, search_cache: dict = None) -> None:
    if search_cache is not None:
        _search_results_cache.update(search_cache)

    @app.on_message(filters.command("queue") & filters.group)
    @banned_check
    async def _queue(c, m): await cmd_queue(c, m)

    @app.on_message(filters.command("remove") & filters.group)
    @banned_check
    @admin_only
    async def _remove(c, m): await cmd_remove(c, m)

    @app.on_message(filters.command("clearqueue") & filters.group)
    @banned_check
    @admin_only
    async def _clearqueue(c, m): await cmd_clearqueue(c, m)

    @app.on_message(filters.command("history") & filters.group)
    @banned_check
    async def _history(c, m): await cmd_history(c, m)

    @app.on_message(filters.command("help"))
    @banned_check
    async def _help(c, m): await cmd_help(c, m)

    @app.on_message(filters.command("settings") & filters.group)
    @banned_check
    @admin_only
    async def _settings(c, m): await cmd_settings(c, m)

    @app.on_callback_query()
    async def _callbacks(c, q): await handle_callback(c, q)
      
