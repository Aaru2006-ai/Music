"""
Configuration module — validates all environment variables at startup.
Exits immediately if any required variable is missing.
"""

import os
import sys
from typing import List


class Config:
    # ── Telegram ────────────────────────────────────────────────────────────
    API_ID: int        = int(os.getenv("API_ID", "0"))
    API_HASH: str      = os.getenv("API_HASH", "")
    BOT_TOKEN: str     = os.getenv("BOT_TOKEN", "")
    STRING_SESSION: str = os.getenv("STRING_SESSION", "")

    # ── Database ─────────────────────────────────────────────────────────────
    MONGO_DB_URI: str  = os.getenv("MONGO_DB_URI", "")
    REDIS_URI: str     = os.getenv("REDIS_URI", "")

    # ── Bot Identity ─────────────────────────────────────────────────────────
    LOG_GROUP_ID: int  = int(os.getenv("LOG_GROUP_ID", "0"))
    OWNER_ID: int      = int(os.getenv("OWNER_ID", "0"))
    SUPPORT_CHANNEL: str = os.getenv("SUPPORT_CHANNEL", "")
    SUPPORT_GROUP: str   = os.getenv("SUPPORT_GROUP", "")

    # ── Spotify ──────────────────────────────────────────────────────────────
    SPOTIFY_CLIENT_ID: str     = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")

    # ── Heroku ───────────────────────────────────────────────────────────────
    HEROKU_API_KEY: str  = os.getenv("HEROKU_API_KEY", "")
    HEROKU_APP_NAME: str = os.getenv("HEROKU_APP_NAME", "")

    # ── Limits & Behaviour ───────────────────────────────────────────────────
    DURATION_LIMIT: int          = int(os.getenv("DURATION_LIMIT", "180"))  # minutes
    AUTO_LEAVING_ASSISTANT: bool = os.getenv("AUTO_LEAVING_ASSISTANT", "True").lower() == "true"
    QUEUE_LIMIT: int             = int(os.getenv("QUEUE_LIMIT", "100"))
    STREAM_QUALITY: int          = int(os.getenv("STREAM_QUALITY", "128"))  # kbps
    VIDEO_QUALITY: str           = os.getenv("VIDEO_QUALITY", "720p")

    # ── Internal ─────────────────────────────────────────────────────────────
    BOT_NAME: str    = "MusicBot"
    BOT_VERSION: str = "1.0.0"
    CACHE_TTL: int   = 3600        # seconds

    # Languages
    DEFAULT_LANG: str = os.getenv("DEFAULT_LANG", "en")

    # Maintenance mode — toggled at runtime
    MAINTENANCE: bool = False

    # In-memory sudo users list (populated from DB at startup)
    SUDO_USERS: List[int] = [int(x) for x in os.getenv("SUDO_USERS", "").split() if x]

    @classmethod
    def validate(cls) -> None:
        """Exit the process if any required env var is absent or clearly invalid."""
        errors: List[str] = []

        required_str = {
            "API_HASH": cls.API_HASH,
            "BOT_TOKEN": cls.BOT_TOKEN,
            "STRING_SESSION": cls.STRING_SESSION,
            "MONGO_DB_URI": cls.MONGO_DB_URI,
            "REDIS_URI": cls.REDIS_URI,
        }
        for name, val in required_str.items():
            if not val:
                errors.append(name)

        if cls.API_ID == 0:
            errors.append("API_ID")
        if cls.OWNER_ID == 0:
            errors.append("OWNER_ID")
        if cls.LOG_GROUP_ID == 0:
            errors.append("LOG_GROUP_ID")

        if errors:
            print(
                f"\n[FATAL] Missing or invalid environment variables:\n"
                + "\n".join(f"  ✗  {e}" for e in errors)
                + "\n\nCheck your .env file or Heroku Config Vars.\n"
            )
            sys.exit(1)

        print("[CONFIG] ✓ All required environment variables validated.")

    @classmethod
    def spotify_enabled(cls) -> bool:
        return bool(cls.SPOTIFY_CLIENT_ID and cls.SPOTIFY_CLIENT_SECRET)

    @classmethod
    def heroku_enabled(cls) -> bool:
        return bool(cls.HEROKU_API_KEY and cls.HEROKU_APP_NAME)
      
