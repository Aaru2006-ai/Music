"""
Admin command handlers: /gban, /ungban, /broadcast, /stats,
/maintenance, /addadmin, /removeadmin, /restart, /update, /eval, /shell
"""

import asyncio
import io
import logging
import os
import sys
import textwrap
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config.config import Config
from bot.helpers.decorators import sudo_only, owner_only, banned_check, admin_only
from bot.helpers.formatters import format_stats, format_leaderboard
from bot.streaming import engine
from bot.database import mongodb, redis_db

log = logging.getLogger(__name__)


# ── /gban ─────────────────────────────────────────────────────────────────────

async def cmd_gban(client: Client, message: Message):
    args = message.command[1:]
    target_id = None
    reason    = "No reason provided"

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        reason = " ".join(args) if args else reason
    elif args:
        try:
            target_id = int(args[0])
            reason = " ".join(args[1:]) or reason
        except ValueError:
            await message.reply_text("❌ Usage: `/gban [user_id] [reason]` or reply to a user.")
            return

    if not target_id:
        await message.reply_text("❌ Please provide a user ID or reply to a message.")
        return
    if target_id == Config.OWNER_ID or target_id in Config.SUDO_USERS:
        await message.reply_text("🚫 Cannot ban admins or the owner.")
        return

    await mongodb.ban_user(target_id, reason)
    await redis_db.add_to_ban_cache(target_id)
    await message.reply_text(
        f"🚫 **Globally Banned**\n"
        f"User: `{target_id}`\n"
        f"Reason: {reason}"
    )
    # Notify logs channel
    try:
        await client.send_message(
            Config.LOG_GROUP_ID,
            f"🚫 **GBan**\nUser: `{target_id}`\nBanned by: `{message.from_user.id}`\nReason: {reason}",
        )
    except Exception:
        pass


# ── /ungban ───────────────────────────────────────────────────────────────────

async def cmd_ungban(client: Client, message: Message):
    args = message.command[1:]
    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif args:
        try:
            target_id = int(args[0])
        except ValueError:
            pass

    if not target_id:
        await message.reply_text("❌ Usage: `/ungban [user_id]` or reply to a banned user.")
        return

    removed = await mongodb.unban_user(target_id)
    await redis_db.remove_from_ban_cache(target_id)
    if removed:
        await message.reply_text(f"✅ **Unbanned** user `{target_id}`.")
    else:
        await message.reply_text(f"⚠️ User `{target_id}` was not globally banned.")


# ── /broadcast ────────────────────────────────────────────────────────────────

async def cmd_broadcast(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("📢 Reply to a message to broadcast it to all chats.")
        return

    status_msg = await message.reply_text("📡 Broadcasting...")
    chats = await mongodb.get_all_users()
    ok = fail = 0
    for user in chats:
        try:
            await message.reply_to_message.forward(user["user_id"])
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await status_msg.edit_text(
        f"📢 **Broadcast Complete**\n"
        f"✅ Sent: `{ok}`\n❌ Failed: `{fail}`"
    )


# ── /stats ─────────────────────────────────────────────────────────────────────

async def cmd_stats(client: Client, message: Message):
    stats    = await mongodb.get_stats()
    active   = engine.get_active_count()
    text     = format_stats(stats, active, bot_name=Config.BOT_NAME)
    await message.reply_text(text)


# ── /leaderboard ──────────────────────────────────────────────────────────────

async def cmd_leaderboard(client: Client, message: Message):
    top = await mongodb.get_top_users(10)
    await message.reply_text(format_leaderboard(top))


# ── /maintenance ──────────────────────────────────────────────────────────────

async def cmd_maintenance(client: Client, message: Message):
    Config.MAINTENANCE = not Config.MAINTENANCE
    state = "**ON** 🛠" if Config.MAINTENANCE else "**OFF** ✅"
    await message.reply_text(f"🛠 Maintenance mode: {state}")
    try:
        await client.send_message(
            Config.LOG_GROUP_ID,
            f"🛠 Maintenance: {state} — toggled by `{message.from_user.id}`",
        )
    except Exception:
        pass


# ── /addadmin / /removeadmin ──────────────────────────────────────────────────

async def cmd_addadmin(client: Client, message: Message):
    args = message.command[1:]
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user.id
    elif args:
        try:
            target = int(args[0])
        except ValueError:
            pass
    if not target:
        await message.reply_text("❌ Usage: `/addadmin [user_id]`")
        return
    await mongodb.add_sudo(target)
    if target not in Config.SUDO_USERS:
        Config.SUDO_USERS.append(target)
    await message.reply_text(f"✅ Added `{target}` as a sudo admin.")


async def cmd_removeadmin(client: Client, message: Message):
    args = message.command[1:]
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user.id
    elif args:
        try:
            target = int(args[0])
        except ValueError:
            pass
    if not target:
        await message.reply_text("❌ Usage: `/removeadmin [user_id]`")
        return
    removed = await mongodb.remove_sudo(target)
    if target in Config.SUDO_USERS:
        Config.SUDO_USERS.remove(target)
    if removed:
        await message.reply_text(f"✅ Removed `{target}` from sudo admins.")
    else:
        await message.reply_text(f"⚠️ `{target}` was not a sudo admin.")


# ── /restart ──────────────────────────────────────────────────────────────────

async def cmd_restart(client: Client, message: Message):
    await message.reply_text("🔄 Restarting bot...")
    try:
        await client.send_message(
            Config.LOG_GROUP_ID,
            f"🔄 Bot restarted by `{message.from_user.id}`.",
        )
    except Exception:
        pass
    os.execl(sys.executable, sys.executable, *sys.argv)


# ── /update ───────────────────────────────────────────────────────────────────

async def cmd_update(client: Client, message: Message):
    status = await message.reply_text("🔄 Pulling latest changes from GitHub...")
    proc = await asyncio.create_subprocess_shell(
        "git pull origin main",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = (stdout or b"").decode() or (stderr or b"").decode()
    await status.edit_text(f"```\n{out[:3500]}\n```")
    if proc.returncode == 0:
        await message.reply_text("✅ Update complete! Restarting...")
        await asyncio.sleep(1)
        os.execl(sys.executable, sys.executable, *sys.argv)


# ── /eval (owner only — execute arbitrary Python) ─────────────────────────────

async def cmd_eval(client: Client, message: Message):
    code = " ".join(message.command[1:])
    if message.reply_to_message:
        code = message.reply_to_message.text or code
    code = code.strip().strip("`").strip()

    env = {"client": client, "message": message, "asyncio": asyncio}
    try:
        code_block = f"async def _exec():\n{textwrap.indent(code, '    ')}"
        exec(compile(code_block, "<string>", "exec"), env)
        result = await env["_exec"]()
        output = str(result) if result is not None else "✅ No output."
    except Exception:
        output = traceback.format_exc()

    await message.reply_text(f"```\n{output[:4000]}\n```")


# ── /shell ────────────────────────────────────────────────────────────────────

async def cmd_shell(client: Client, message: Message):
    cmd = " ".join(message.command[1:]).strip()
    if not cmd:
        await message.reply_text("❌ Usage: `/shell [command]`")
        return
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = (stdout or b"").decode() + (stderr or b"").decode()
    await message.reply_text(f"```\n{out[:4000] or 'No output.'}\n```")


# ── /ping ─────────────────────────────────────────────────────────────────────

async def cmd_ping(client: Client, message: Message):
    import time
    start = time.time()
    sent  = await message.reply_text("🏓 Pong!")
    ms    = (time.time() - start) * 1000
    await sent.edit_text(f"🏓 **Pong!** `{ms:.2f}ms`")


# ── Register ───────────────────────────────────────────────────────────────────

def register(app: Client) -> None:

    @app.on_message(filters.command("gban"))
    @banned_check
    @sudo_only
    async def _gban(c, m): await cmd_gban(c, m)

    @app.on_message(filters.command("ungban"))
    @banned_check
    @sudo_only
    async def _ungban(c, m): await cmd_ungban(c, m)

    @app.on_message(filters.command("broadcast"))
    @sudo_only
    async def _broadcast(c, m): await cmd_broadcast(c, m)

    @app.on_message(filters.command("stats"))
    @banned_check
    @sudo_only
    async def _stats(c, m): await cmd_stats(c, m)

    @app.on_message(filters.command("leaderboard"))
    @banned_check
    async def _lb(c, m): await cmd_leaderboard(c, m)

    @app.on_message(filters.command("maintenance"))
    @sudo_only
    async def _maint(c, m): await cmd_maintenance(c, m)

    @app.on_message(filters.command("addadmin"))
    @owner_only
    async def _addadmin(c, m): await cmd_addadmin(c, m)

    @app.on_message(filters.command("removeadmin"))
    @owner_only
    async def _removeadmin(c, m): await cmd_removeadmin(c, m)

    @app.on_message(filters.command("restart"))
    @sudo_only
    async def _restart(c, m): await cmd_restart(c, m)

    @app.on_message(filters.command("update"))
    @sudo_only
    async def _update(c, m): await cmd_update(c, m)

    @app.on_message(filters.command("eval"))
    @owner_only
    async def _eval(c, m): await cmd_eval(c, m)

    @app.on_message(filters.command("shell"))
    @owner_only
    async def _shell(c, m): await cmd_shell(c, m)

    @app.on_message(filters.command("ping"))
    @banned_check
    async def _ping(c, m): await cmd_ping(c, m)
      
