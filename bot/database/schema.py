"""
MongoDB Schema Reference
========================
Collection definitions, indexes, and example documents for MusicBot.
This file is documentation only — Motor creates collections automatically.
"""

SCHEMA = {

    # ── users ──────────────────────────────────────────────────────────────
    "users": {
        "description": "Registered bot users",
        "indexes": [{"key": "user_id", "unique": True}],
        "example": {
            "user_id":    987654321,
            "first_name": "John",
            "username":   "johndoe",
            "lang":       "en",
            "joined_at":  "2024-01-01T00:00:00Z",
        },
    },

    # ── chats ──────────────────────────────────────────────────────────────
    "chats": {
        "description": "Group chat settings",
        "indexes": [{"key": "chat_id", "unique": True}],
        "example": {
            "chat_id":    -1001234567890,
            "title":      "My Music Group",
            "loop":       False,
            "shuffle":    False,
            "autoplay":   True,
            "admin_only": False,
            "volume":     100,
            "quality":    128,
            "lang":       "en",
            "joined_at":  "2024-01-01T00:00:00Z",
        },
    },

    # ── queue ──────────────────────────────────────────────────────────────
    "queue": {
        "description": "Persistent per-group track queues",
        "indexes": [
            {"key": ["chat_id", "position"], "unique": False},
        ],
        "example": {
            "chat_id":        -1001234567890,
            "position":       0,
            "title":          "Blinding Lights",
            "uploader":       "The Weeknd",
            "url":            "https://youtube.com/watch?v=...",
            "stream_url":     "https://...",
            "duration":       200,
            "duration_str":   "03:20",
            "thumbnail":      "https://...",
            "source":         "YouTube",
            "requester_id":   987654321,
            "requester_name": "John",
        },
    },

    # ── playback_history ───────────────────────────────────────────────────
    "playback_history": {
        "description": "Log of all played tracks per chat",
        "indexes": [{"key": ["chat_id", "played_at"], "unique": False}],
        "ttl_index": {"key": "played_at", "expireAfterSeconds": 2592000},  # 30 days
        "example": {
            "chat_id":        -1001234567890,
            "title":          "Blinding Lights",
            "uploader":       "The Weeknd",
            "requester_id":   987654321,
            "requester_name": "John",
            "played_at":      "2024-01-15T12:30:00Z",
        },
    },

    # ── playlists ──────────────────────────────────────────────────────────
    "playlists": {
        "description": "User-saved playlists",
        "indexes": [{"key": ["owner_id", "name"], "unique": True}],
        "example": {
            "owner_id":   987654321,
            "name":       "Chill Vibes",
            "public":     False,
            "play_count": 5,
            "tracks":     [{"title": "...", "url": "..."}],
            "created_at": "2024-01-01T00:00:00Z",
        },
    },

    # ── bans ───────────────────────────────────────────────────────────────
    "bans": {
        "description": "Globally banned users",
        "indexes": [{"key": "user_id", "unique": True}],
        "example": {
            "user_id":   111111111,
            "reason":    "Spamming",
            "banned_at": "2024-01-10T09:00:00Z",
        },
    },

    # ── admins ─────────────────────────────────────────────────────────────
    "admins": {
        "description": "Sudo/admin users with elevated privileges",
        "indexes": [{"key": "user_id", "unique": True}],
        "example": {
            "user_id":   222222222,
            "added_at":  "2024-01-01T00:00:00Z",
        },
    },

    # ── analytics ──────────────────────────────────────────────────────────
    "analytics": {
        "description": "Daily aggregated usage analytics",
        "indexes": [{"key": "date", "unique": True}],
        "example": {
            "date":        "2024-01-15",
            "total_plays": 142,
            "last_track":  "Blinding Lights",
            "last_chat":   -1001234567890,
            "user_plays":  {"987654321": 8, "111111111": 3},
        },
    },
}
