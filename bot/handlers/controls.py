"""
Playback control handlers: /pause, /resume, /skip, /stop, /seek,
/loop, /shuffle, /volume, /speed, /mute, /unmute
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.helpers.decorators import (
    banned_check, maintenance_check, admin_only, rate_limit
)
from bot.helpers.keyboard import now_playing_kb
from bot.helpers.formatters import now_playing_text
from bot.streaming import engine, queue as queue_engine
from bot.database import redis_db, mongodb

log = logging.getLogger(__name__)


# ── /pause ─────────────────────────────────────────────────────────────────────

async def cmd_pause(client: Client, message: Message):
    chat_id = message.chat.id
    if not engine.is_active(chat_id):
        await message.reply_text("❌ Nothing is currently playing.")
        return
    if await redis_db.is_paused(chat_id):
        await message.reply_text("⚠️ Playback is already paused. Use /resume to continue.")
        return
    ok = await engine.pause(chat_id)
    if ok:
        await message.reply_text("⏸ **Paused.** Use /resume to continue.")
    else:
        await message.reply_text("❌ Failed to pause. Please try again.")


# ── /resume ────────────────────────────────────────────────────────────────────

async def cmd_resume(client: Client, message: Message):
    chat_id = message.chat.id
    if not engine.is_active(chat_id):
        await message.reply_text("❌ No active stream to resume.")
        return
    if not await redis_db.is_paused(chat_id):
        await message.reply_text("▶️ Playback is already running.")
        return
    ok = await engine.resume(chat_id)
    if ok:
        current = await queue_engine.get_current(chat_id)
        text = f"▶️ **Resumed:** {current.get('title', 'track')}" if current else "▶️ Resumed."
        await message.reply_text(text)
    else:
        await message.reply_text("❌ Failed to resume.")


# ── /skip ─────────────────────────────────────────────────────────────────────

async def cmd_skip(client: Client, message: Message):
    chat_id = message.chat.id
    if not engine.is_active(chat_id):
        await message.reply_text("❌ Nothing is currently playing.")
        return
    current = await queue_engine.get_current(chat_id)
    old_title = current.get("title", "current track") if current else "current track"
    next_track = await engine.skip(chat_id)
    if next_track:
        vol = await redis_db.get_volume(chat_id)
        await message.reply_text(
            f"⏭ Skipped **{old_title}**\n\n"
            + now_playing_text(next_track, volume=vol),
            reply_markup=now_playing_kb(chat_id),
        )
    else:
        await message.reply_text(
            f"⏭ Skipped **{old_title}**.\n\n"
            "📭 Queue is now empty. Add more songs with /play."
        )


# ── /stop ─────────────────────────────────────────────────────────────────────

async def cmd_stop(client: Client, message: Message):
    chat_id = message.chat.id
    if not engine.is_active(chat_id):
        await message.reply_text("❌ Nothing is currently playing.")
        return
    count = await queue_engine.queue_length(chat_id)
    await engine.stop(chat_id)
    await message.reply_text(
        f"⏹ **Stopped.**\n"
        f"Cleared `{count}` track(s) from queue and left the voice chat."
    )


# ── /seek ─────────────────────────────────────────────────────────────────────

async def cmd_seek(client: Client, message: Message):
    chat_id = message.chat.id
    if not engine.is_active(chat_id):
        await message.reply_text("❌ Nothing is currently playing.")
        return
    args = message.command[1:]
    if not args or not args[0].isdigit():
        await message.reply_text("⏩ **Usage:** `/seek [seconds]`\nExample: `/seek 90`")
        return
    secs = int(args[0])
    current = await queue_engine.get_current(chat_id)
    duration = current.get("duration", 0) if current else 0
    if duration and secs >= duration:
        await message.reply_text(f"❌ Seek position exceeds track duration ({duration}s).")
        return
    ok = await engine.seek(chat_id, secs)
    if ok:
        mins, s = divmod(secs, 60)
        await message.reply_text(f"⏩ Seeked to **{mins:02d}:{s:02d}**.")
    else:
        await message.reply_text("❌ Seek failed. Make sure the track supports seeking.")


# ── /loop ─────────────────────────────────────────────────────────────────────

async def cmd_loop(client: Client, message: Message):
    chat_id = message.chat.id
    current_loop = await redis_db.get_loop(chat_id)
    new_state = not current_loop
    await redis_db.set_loop(chat_id, new_state)
    await mongodb.update_chat_setting(chat_id, "loop", new_state)
    icon = "✅" if new_state else "❌"
    await message.reply_text(f"🔁 Loop mode: **{'On' if new_state else 'Off'}** {icon}")


# ── /shuffle ──────────────────────────────────────────────────────────────────

async def cmd_shuffle(client: Client, message: Message):
    chat_id = message.chat.id
    count = await queue_engine.shuffle_queue(chat_id)
    if count:
        await message.reply_text(f"🔀 Shuffled **{count}** tracks in the queue.")
    else:
        await message.reply_text("📭 Queue is empty — nothing to shuffle.")


# ── /volume ───────────────────────────────────────────────────────────────────

async def cmd_volume(client: Client, message: Message):
    chat_id = message.chat.id
    args = message.command[1:]
    if not args or not args[0].isdigit():
        vol = await redis_db.get_volume(chat_id)
        await message.reply_text(
            f"🔊 Current volume: **{vol}%**\n"
            "Usage: `/volume [0-200]`"
        )
        return
    vol = max(0, min(200, int(args[0])))
    if not engine.is_active(chat_id):
        await redis_db.set_volume(chat_id, vol)
        await message.reply_text(f"🔊 Volume set to **{vol}%** (takes effect on next play).")
        return
    ok = await engine.set_volume(chat_id, vol)
    if ok:
        bar = "█" * (vol // 20) + "░" * (10 - vol // 20)
        await message.reply_text(f"🔊 Volume: `[{bar}]` **{vol}%**")
    else:
        await message.reply_text("❌ Failed to set volume.")


# ── /mute / /unmute ───────────────────────────────────────────────────────────

async def cmd_mute(client: Client, message: Message):
    ok = await engine.mute(message.chat.id)
    await message.reply_text("🔇 **Muted.**" if ok else "❌ Failed to mute.")


async def cmd_unmute(client: Client, message: Message):
    ok = await engine.unmute(message.chat.id)
    await message.reply_text("🔊 **Unmuted.**" if ok else "❌ Failed to unmute.")


# ── /end (alias for stop, leaves VC cleanly) ──────────────────────────────────

async def cmd_end(client: Client, message: Message):
    await cmd_stop(client, message)


# ── Register ───────────────────────────────────────────────────────────────────

def register(app: Client) -> None:
    decs = dict(
        pause=cmd_pause, resume=cmd_resume, skip=cmd_skip,
        stop=cmd_stop, end=cmd_end, seek=cmd_seek, loop=cmd_loop,
        shuffle=cmd_shuffle, volume=cmd_volume, mute=cmd_mute, unmute=cmd_unmute,
    )

    for cmd, handler in decs.items():
        # Admin-only for destructive commands; open for others
        if cmd in ("stop", "end", "skip", "seek"):
            @app.on_message(filters.command(cmd) & filters.group)
            @banned_check
            @maintenance_check
            @admin_only
            async def _wrapped(c, m, _h=handler): await _h(c, m)
        else:
            @app.on_message(filters.command(cmd) & filters.group)
            @banned_check
            @maintenance_check
            @rate_limit(cmd, 5, 10)
            async def _wrapped(c, m, _h=handler): await _h(c, m)
  
