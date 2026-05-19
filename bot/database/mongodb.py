"""
MongoDB async database layer using Motor.
Provides CRUD helpers for every collection used by the bot.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from bot.config.config import Config

log = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


# ── Connection ───────────────────────────────────────────────────────────────

async def connect() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(Config.MONGO_DB_URI, serverSelectionTimeoutMS=5000)
    _db = _client["musicbot"]
    await _ensure_indexes()
    log.info("MongoDB connected successfully.")


async def disconnect() -> None:
    if _client:
        _client.close()
        log.info("MongoDB disconnected.")


def db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB not connected. Call connect() first.")
    return _db


async def _ensure_indexes() -> None:
    d = db()
    await d.users.create_index("user_id", unique=True)
    await d.chats.create_index("chat_id", unique=True)
    await d.queue.create_index([("chat_id", 1), ("position", 1)])
    await d.playlists.create_index([("owner_id", 1), ("name", 1)])
    await d.bans.create_index("user_id", unique=True)
    await d.playback_history.create_index([("chat_id", 1), ("played_at", -1)])
    await d.analytics.create_index([("date", 1)])
    log.debug("MongoDB indexes ensured.")


# ── Users ────────────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> Optional[Dict]:
    return await db().users.find_one({"user_id": user_id}, {"_id": 0})


async def upsert_user(user_id: int, data: Dict) -> None:
    data.setdefault("joined_at", _now())
    data["user_id"] = user_id
    await db().users.update_one(
        {"user_id": user_id},
        {"$set": data, "$setOnInsert": {"joined_at": _now()}},
        upsert=True,
    )


async def get_all_users() -> List[Dict]:
    return await db().users.find({}, {"_id": 0}).to_list(length=None)


async def user_count() -> int:
    return await db().users.count_documents({})


# ── Chats ────────────────────────────────────────────────────────────────────

async def get_chat(chat_id: int) -> Optional[Dict]:
    return await db().chats.find_one({"chat_id": chat_id}, {"_id": 0})


async def upsert_chat(chat_id: int, data: Dict) -> None:
    data["chat_id"] = chat_id
    await db().chats.update_one(
        {"chat_id": chat_id},
        {"$set": data, "$setOnInsert": {"joined_at": _now()}},
        upsert=True,
    )


async def get_chat_settings(chat_id: int) -> Dict:
    doc = await db().chats.find_one({"chat_id": chat_id}, {"_id": 0})
    defaults = {
        "chat_id": chat_id,
        "loop": False,
        "shuffle": False,
        "volume": 100,
        "quality": Config.STREAM_QUALITY,
        "lang": Config.DEFAULT_LANG,
        "admin_only": False,
        "autoplay": True,
    }
    if doc:
        defaults.update(doc)
    return defaults


async def update_chat_setting(chat_id: int, key: str, value: Any) -> None:
    await db().chats.update_one(
        {"chat_id": chat_id},
        {"$set": {key: value}},
        upsert=True,
    )


async def chat_count() -> int:
    return await db().chats.count_documents({})


# ── Queue (persistent) ───────────────────────────────────────────────────────

async def save_queue(chat_id: int, tracks: List[Dict]) -> None:
    await db().queue.delete_many({"chat_id": chat_id})
    if tracks:
        for i, t in enumerate(tracks):
            t["chat_id"] = chat_id
            t["position"] = i
        await db().queue.insert_many(tracks)


async def load_queue(chat_id: int) -> List[Dict]:
    cursor = db().queue.find(
        {"chat_id": chat_id}, {"_id": 0}
    ).sort("position", 1)
    return await cursor.to_list(length=None)


async def clear_queue(chat_id: int) -> None:
    await db().queue.delete_many({"chat_id": chat_id})


# ── Playback History ─────────────────────────────────────────────────────────

async def add_to_history(chat_id: int, track: Dict) -> None:
    track["chat_id"] = chat_id
    track["played_at"] = _now()
    await db().playback_history.insert_one(track)


async def get_history(chat_id: int, limit: int = 20) -> List[Dict]:
    cursor = (
        db()
        .playback_history.find({"chat_id": chat_id}, {"_id": 0})
        .sort("played_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=None)


# ── Playlists ─────────────────────────────────────────────────────────────────

async def create_playlist(owner_id: int, name: str, tracks: List[Dict], public: bool = False) -> str:
    doc = {
        "owner_id": owner_id,
        "name": name,
        "tracks": tracks,
        "public": public,
        "created_at": _now(),
        "play_count": 0,
    }
    result = await db().playlists.insert_one(doc)
    return str(result.inserted_id)


async def get_playlist(owner_id: int, name: str) -> Optional[Dict]:
    return await db().playlists.find_one(
        {"owner_id": owner_id, "name": name}, {"_id": 0}
    )


async def get_user_playlists(owner_id: int) -> List[Dict]:
    return await db().playlists.find(
        {"owner_id": owner_id}, {"_id": 0, "tracks": 0}
    ).to_list(length=None)


async def delete_playlist(owner_id: int, name: str) -> bool:
    result = await db().playlists.delete_one({"owner_id": owner_id, "name": name})
    return result.deleted_count > 0


# ── Bans ─────────────────────────────────────────────────────────────────────

async def ban_user(user_id: int, reason: str = "No reason") -> None:
    await db().bans.update_one(
        {"user_id": user_id},
        {"$set": {"reason": reason, "banned_at": _now()}},
        upsert=True,
    )


async def unban_user(user_id: int) -> bool:
    result = await db().bans.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def is_banned(user_id: int) -> bool:
    return await db().bans.find_one({"user_id": user_id}) is not None


async def get_all_bans() -> List[Dict]:
    return await db().bans.find({}, {"_id": 0}).to_list(length=None)


# ── Admins / Sudo ─────────────────────────────────────────────────────────────

async def add_sudo(user_id: int) -> None:
    await db().admins.update_one(
        {"user_id": user_id},
        {"$set": {"added_at": _now()}},
        upsert=True,
    )


async def remove_sudo(user_id: int) -> bool:
    result = await db().admins.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def get_sudo_users() -> List[int]:
    docs = await db().admins.find({}, {"user_id": 1, "_id": 0}).to_list(length=None)
    return [d["user_id"] for d in docs]


# ── Analytics ─────────────────────────────────────────────────────────────────

async def increment_play(user_id: int, chat_id: int, track_title: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db().analytics.update_one(
        {"date": today},
        {
            "$inc": {
                "total_plays": 1,
                f"user_plays.{user_id}": 1,
            },
            "$set": {"last_track": track_title, "last_chat": chat_id},
        },
        upsert=True,
    )


async def get_stats() -> Dict:
    return {
        "users": await user_count(),
        "chats": await chat_count(),
        "bans": await db().bans.count_documents({}),
        "playlists": await db().playlists.count_documents({}),
        "history_entries": await db().playback_history.count_documents({}),
    }


async def get_top_users(limit: int = 10) -> List[Dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db().analytics.find_one({"date": today})
    if not doc or "user_plays" not in doc:
        return []
    plays = doc["user_plays"]
    sorted_plays = sorted(plays.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"user_id": int(uid), "plays": count} for uid, count in sorted_plays]


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)
  
