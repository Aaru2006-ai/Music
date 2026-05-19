"""
Security middleware — anti-flood, anti-spam, command injection prevention,
callback validation, suspicious activity detection.
"""

import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Dict, Deque

from pyrogram import Client
from pyrogram.types import Message, CallbackQuery

from bot.config.config import Config
from bot.database import redis_db

log = logging.getLogger(__name__)

# In-memory flood tracker: user_id → deque of timestamps
_flood_tracker: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=10))

FLOOD_LIMIT   = 5   # messages
FLOOD_WINDOW  = 3   # seconds


# ── Anti-flood ────────────────────────────────────────────────────────────────

def is_flooded(user_id: int) -> bool:
    """
    Returns True if user sent more than FLOOD_LIMIT messages
    in the last FLOOD_WINDOW seconds.
    """
    now   = time.time()
    times = _flood_tracker[user_id]
    times.append(now)
    # Count messages within window
    recent = sum(1 for t in times if now - t < FLOOD_WINDOW)
    return recent > FLOOD_LIMIT


# ── Callback validation ───────────────────────────────────────────────────────

def validate_callback_origin(query: CallbackQuery, expected_chat_id: int = None) -> bool:
    """
    Prevent users from triggering callbacks in chats they don't belong to.
    Pass expected_chat_id extracted from callback_data for verification.
    """
    if expected_chat_id is None:
        return True
    return query.message.chat.id == expected_chat_id


# ── Command sanitisation ──────────────────────────────────────────────────────

def sanitise_query(text: str) -> str:
    """Strip control characters and limit length to prevent injection."""
    sanitised = "".join(
        c for c in text if c.isprintable() and c not in ("\x00", "\r")
    )
    return sanitised[:500]


# ── Rate key generator ────────────────────────────────────────────────────────

def make_rate_key(user_id: int, command: str) -> str:
    return f"ratelimit:{command}:{user_id}"


# ── Admin privilege validation ────────────────────────────────────────────────

def is_sudo(user_id: int) -> bool:
    return user_id == Config.OWNER_ID or user_id in Config.SUDO_USERS


# ── Message content scanner ───────────────────────────────────────────────────

_SUSPICIOUS_PATTERNS = [
    "eval(", "exec(", "__import__", "os.system",
    "subprocess", "open(", "/etc/passwd",
]

def is_suspicious_input(text: str) -> bool:
    lowered = text.lower()
    return any(p in lowered for p in _SUSPICIOUS_PATTERNS)


# ── IP / Webhook signature validation ────────────────────────────────────────

def verify_webhook_signature(payload: bytes, secret: str, signature: str) -> bool:
    """HMAC-SHA256 verification for webhook payloads."""
    import hmac
    computed = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


# ── Global middleware function (attach to Pyrogram via on_message) ─────────────

async def global_security_middleware(client: Client, message: Message) -> bool:
    """
    Returns True if message should be processed, False to drop it.
    Attach via filters in app configuration.
    """
    user = message.from_user
    if not user:
        return True  # channel messages pass through

    user_id = user.id

    # Check global ban (fast Redis check)
    if await redis_db.is_in_ban_cache(user_id):
        log.debug("Dropped message from banned user %d", user_id)
        return False

    # Anti-flood check
    if is_flooded(user_id):
        log.warning("Flood detected from user %d", user_id)
        return False

    # Maintenance check
    if Config.MAINTENANCE and not is_sudo(user_id):
        return False

    return True
          
