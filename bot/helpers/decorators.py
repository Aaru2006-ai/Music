"""
Decorator library for Pyrogram command handlers.
Provides: @admin_only, @sudo_only, @rate_limit, @maintenance_check, @banned_check, @chat_allowed
"""

import functools
import logging
from typing import Callable

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message

from bot.config.config import Config
from bot.database import redis_db, mongodb

log = logging.getLogger(__name__)

_ADMIN_STATUS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


# ── Helper: check Telegram admin ─────────────────────────────────────────────

async def _is_telegram_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in _ADMIN_STATUS
    except Exception:
        return False


# ── Decorators ────────────────────────────────────────────────────────────────

def banned_check(func: Callable) -> Callable:
    """Reject commands from globally banned users."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else None
        if user_id and await redis_db.is_in_ban_cache(user_id):
            await message.reply_text("❌ You are globally banned from using this bot.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def maintenance_check(func: Callable) -> Callable:
    """Block all non-sudo users during maintenance mode."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else 0
        if Config.MAINTENANCE and user_id not in Config.SUDO_USERS and user_id != Config.OWNER_ID:
            await message.reply_text(
                "🛠 **Maintenance Mode**\nThe bot is currently under maintenance. Please try again later."
            )
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def rate_limit(command: str, limit: int = 3, window: int = 10):
    """Throttle command to `limit` calls per `window` seconds per user."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(client: Client, message: Message, *args, **kwargs):
            user_id = message.from_user.id if message.from_user else 0
            if user_id and await redis_db.is_rate_limited(user_id, command, limit, window):
                await message.reply_text(
                    f"⏳ Slow down! You can use this command {limit}x every {window}s."
                )
                return
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator


def admin_only(func: Callable) -> Callable:
    """Restrict command to Telegram group admins + sudo users."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else 0
        if user_id in Config.SUDO_USERS or user_id == Config.OWNER_ID:
            return await func(client, message, *args, **kwargs)
        if message.chat.id < 0:  # group/supergroup
            is_admin = await _is_telegram_admin(client, message.chat.id, user_id)
            if is_admin:
                return await func(client, message, *args, **kwargs)
        await message.reply_text("🚫 This command is for group admins only.")
    return wrapper


def sudo_only(func: Callable) -> Callable:
    """Restrict command to sudo users and the owner."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else 0
        if user_id not in Config.SUDO_USERS and user_id != Config.OWNER_ID:
            await message.reply_text("🚫 This command is reserved for sudo users.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def owner_only(func: Callable) -> Callable:
    """Restrict command to the bot owner only."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else 0
        if user_id != Config.OWNER_ID:
            await message.reply_text("🚫 This command is reserved for the bot owner.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def group_only(func: Callable) -> Callable:
    """Ensure the command is only used in groups."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if message.chat.id > 0:
            await message.reply_text("⚠️ This command can only be used in groups.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def combined(*decorators):
    """Apply multiple decorators in order (bottom-up)."""
    def apply(func):
        for dec in reversed(decorators):
            func = dec(func)
        return func
    return apply
                      
