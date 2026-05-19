"""
Queue engine — per-group, in-memory with MongoDB persistence.
Supports: priority, shuffle, loop, history, pagination, duplicate prevention.
"""

import asyncio
import logging
import random
from collections import defaultdict, deque
from typing import Dict, List, Optional

from bot.database import mongodb

log = logging.getLogger(__name__)

# chat_id → deque of track dicts
_queues: Dict[int, deque] = defaultdict(deque)

# chat_id → currently playing track dict
_current: Dict[int, Optional[dict]] = {}

# chat_id → position pointer (for history)
_history: Dict[int, List[dict]] = defaultdict(list)

_lock = asyncio.Lock()


# ── Queue operations ──────────────────────────────────────────────────────────

async def add_track(chat_id: int, track: dict, priority: bool = False) -> int:
    """
    Add a track to the queue.
    Returns the new queue length.
    """
    async with _lock:
        if priority:
            _queues[chat_id].appendleft(track)
        else:
            _queues[chat_id].append(track)
        pos = len(_queues[chat_id])
        await _persist(chat_id)
        return pos


async def add_tracks(chat_id: int, tracks: List[dict]) -> int:
    async with _lock:
        for t in tracks:
            _queues[chat_id].append(t)
        await _persist(chat_id)
        return len(_queues[chat_id])


async def get_next(chat_id: int) -> Optional[dict]:
    """Pop the next track from the queue and update current."""
    async with _lock:
        q = _queues[chat_id]
        if not q:
            return None
        track = q.popleft()
        if _current.get(chat_id):
            _history[chat_id].append(_current[chat_id])
            if len(_history[chat_id]) > 50:
                _history[chat_id].pop(0)
        _current[chat_id] = track
        await _persist(chat_id)
        return track


async def get_current(chat_id: int) -> Optional[dict]:
    return _current.get(chat_id)


async def set_current(chat_id: int, track: dict) -> None:
    async with _lock:
        _current[chat_id] = track


async def peek_queue(chat_id: int) -> List[dict]:
    """Return queue contents without modifying it."""
    return list(_queues.get(chat_id, deque()))


async def remove_track(chat_id: int, position: int) -> Optional[dict]:
    """Remove track at 1-based position (1 = next up)."""
    async with _lock:
        q = list(_queues[chat_id])
        idx = position - 1
        if idx < 0 or idx >= len(q):
            return None
        removed = q.pop(idx)
        _queues[chat_id] = deque(q)
        await _persist(chat_id)
        return removed


async def clear_queue(chat_id: int) -> int:
    async with _lock:
        count = len(_queues[chat_id])
        _queues[chat_id].clear()
        _current.pop(chat_id, None)
        await mongodb.clear_queue(chat_id)
        return count


async def queue_length(chat_id: int) -> int:
    return len(_queues.get(chat_id, deque()))


async def is_empty(chat_id: int) -> bool:
    return queue_length(chat_id) == 0


# ── Shuffle ────────────────────────────────────────────────────────────────────

async def shuffle_queue(chat_id: int) -> int:
    async with _lock:
        q = list(_queues[chat_id])
        if not q:
            return 0
        random.shuffle(q)
        _queues[chat_id] = deque(q)
        await _persist(chat_id)
        return len(q)


# ── Duplicate check ────────────────────────────────────────────────────────────

async def is_duplicate(chat_id: int, url: str) -> bool:
    q = list(_queues.get(chat_id, deque()))
    cur = _current.get(chat_id)
    urls = {t.get("url") for t in q}
    if cur:
        urls.add(cur.get("url"))
    return url in urls


# ── History ────────────────────────────────────────────────────────────────────

def get_history(chat_id: int) -> List[dict]:
    return list(_history.get(chat_id, []))


def get_previous(chat_id: int) -> Optional[dict]:
    h = _history.get(chat_id, [])
    return h[-1] if h else None


# ── Pagination helper ──────────────────────────────────────────────────────────

def paginate_queue(chat_id: int, page: int = 1, per_page: int = 10):
    """Return (tracks_on_page, total_pages, total_tracks)."""
    tracks = list(_queues.get(chat_id, deque()))
    total = len(tracks)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return tracks[start:end], total_pages, total


# ── Persistence ────────────────────────────────────────────────────────────────

async def _persist(chat_id: int) -> None:
    """Save queue snapshot to MongoDB (fire-and-forget safe)."""
    try:
        tracks = list(_queues[chat_id])
        await mongodb.save_queue(chat_id, tracks)
    except Exception as e:
        log.warning("Queue persist error for chat %d: %s", chat_id, e)


async def restore_queue(chat_id: int) -> int:
    """Load queue from MongoDB on bot restart."""
    try:
        tracks = await mongodb.load_queue(chat_id)
        if tracks:
            async with _lock:
                _queues[chat_id] = deque(tracks)
            log.info("Restored %d tracks for chat %d", len(tracks), chat_id)
            return len(tracks)
    except Exception as e:
        log.error("Queue restore error for chat %d: %s", chat_id, e)
    return 0
                 
