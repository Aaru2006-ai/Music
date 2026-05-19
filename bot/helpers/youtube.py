"""
Media extraction helpers using yt-dlp.
Supports: YouTube, SoundCloud, direct URLs, Telegram audio files.
Returns a normalised Track dict consumed by the streaming engine.
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional

import yt_dlp

from bot.config.config import Config
from bot.database import redis_db

log = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "../../cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ── yt-dlp options ────────────────────────────────────────────────────────────

_YDL_COMMON = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "source_address": "0.0.0.0",
}

_AUDIO_OPTS = {
    **_YDL_COMMON,
    "format": "bestaudio/best",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": str(Config.STREAM_QUALITY),
    }],
    "outtmpl": os.path.join(CACHE_DIR, "%(id)s.%(ext)s"),
}

_INFO_OPTS = {
    **_YDL_COMMON,
    "skip_download": True,
}

_PLAYLIST_OPTS = {
    **_YDL_COMMON,
    "skip_download": True,
    "extract_flat": True,
    "noplaylist": False,
}


# ── Normalise a raw yt-dlp info dict into our Track schema ────────────────────

def _normalise(info: dict, requester_id: int = 0, requester_name: str = "Unknown") -> Dict:
    return {
        "title":         info.get("title", "Unknown Title")[:100],
        "url":           info.get("webpage_url") or info.get("url", ""),
        "stream_url":    _best_audio_url(info),
        "thumbnail":     info.get("thumbnail") or info.get("thumbnails", [{}])[-1].get("url", ""),
        "duration":      info.get("duration", 0),
        "duration_str":  _fmt_duration(info.get("duration", 0)),
        "uploader":      info.get("uploader", "Unknown Artist"),
        "source":        info.get("extractor_key", "YouTube"),
        "requester_id":  requester_id,
        "requester_name": requester_name,
        "is_video":      False,
        "file_path":     None,
    }


def _best_audio_url(info: dict) -> str:
    """Pick the best direct audio URL from yt-dlp format list."""
    formats = info.get("formats") or []
    audio_fmts = [
        f for f in formats
        if f.get("acodec") != "none" and f.get("vcodec") == "none"
    ]
    if audio_fmts:
        audio_fmts.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        return audio_fmts[0].get("url", "")
    # fallback: best format URL
    return info.get("url", "")


def _fmt_duration(seconds: int) -> str:
    if not seconds:
        return "Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _is_url(text: str) -> bool:
    return re.match(r"https?://", text.strip()) is not None


# ── Search ─────────────────────────────────────────────────────────────────────

async def search_youtube(query: str, limit: int = 5) -> List[Dict]:
    """Search YouTube and return top results without downloading."""
    search_query = f"ytsearch{limit}:{query}"
    loop = asyncio.get_event_loop()

    def _search():
        with yt_dlp.YoutubeDL(_INFO_OPTS) as ydl:
            return ydl.extract_info(search_query, download=False)

    try:
        result = await loop.run_in_executor(None, _search)
        entries = result.get("entries", []) if result else []
        return [_normalise(e) for e in entries if e]
    except Exception as e:
        log.error("YouTube search error: %s", e)
        return []


# ── Extract track info ─────────────────────────────────────────────────────────

async def get_track_info(
    query: str,
    requester_id: int = 0,
    requester_name: str = "Unknown",
) -> Optional[Dict]:
    """
    Resolve a URL or search query → Track dict.
    Checks Redis cache first.
    """
    cached = await redis_db.get_cached_track(query)
    if cached:
        log.debug("Cache hit for: %s", query)
        cached["requester_id"] = requester_id
        cached["requester_name"] = requester_name
        return cached

    url = query if _is_url(query) else f"ytsearch1:{query}"
    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(_INFO_OPTS) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await loop.run_in_executor(None, _extract)
        if not info:
            return None
        # If it was a search, grab first entry
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                return None
            info = entries[0]

        # Duration limit check
        duration_mins = (info.get("duration") or 0) / 60
        if duration_mins > Config.DURATION_LIMIT:
            log.warning("Track too long: %.1f min > %d min limit", duration_mins, Config.DURATION_LIMIT)
            return {"error": "duration_exceeded", "duration": duration_mins}

        track = _normalise(info, requester_id, requester_name)
        await redis_db.cache_track(query, track)
        return track

    except yt_dlp.utils.DownloadError as e:
        log.error("yt-dlp download error: %s", e)
        return None
    except Exception as e:
        log.error("Unexpected extraction error: %s", e, exc_info=True)
        return None


# ── Playlist extraction ────────────────────────────────────────────────────────

async def get_playlist_tracks(url: str, limit: int = 50) -> List[Dict]:
    """Extract tracks from a YouTube playlist URL."""
    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(_PLAYLIST_OPTS) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await loop.run_in_executor(None, _extract)
        entries = (info or {}).get("entries", [])[:limit]
        tracks = []
        for e in entries:
            if not e:
                continue
            tracks.append({
                "title":    e.get("title", "Unknown")[:100],
                "url":      e.get("url") or f"https://youtube.com/watch?v={e.get('id', '')}",
                "duration": e.get("duration", 0),
                "duration_str": _fmt_duration(e.get("duration", 0)),
                "uploader": e.get("uploader", "Unknown"),
                "source":   "YouTube",
                "thumbnail": e.get("thumbnail", ""),
                "stream_url": None,  # resolved on play
            })
        return tracks
    except Exception as e:
        log.error("Playlist extraction error: %s", e)
        return []


# ── Download audio file ────────────────────────────────────────────────────────

async def download_audio(url: str) -> Optional[str]:
    """
    Download audio to cache directory.
    Returns local file path on success.
    """
    loop = asyncio.get_event_loop()

    def _download():
        with yt_dlp.YoutubeDL(_AUDIO_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                return ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            return None

    try:
        return await loop.run_in_executor(None, _download)
    except Exception as e:
        log.error("Audio download error: %s", e)
        return None


# ── Lyrics fetch (via lyrics-extractor / Genius fallback) ────────────────────

async def fetch_lyrics(title: str) -> Optional[str]:
    """Lightweight lyrics search using LyricsGenius-style approach."""
    try:
        import aiohttp
        query = title.replace(" ", "+")
        url = f"https://lyrist.vercel.app/api/{query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("lyrics")
    except Exception as e:
        log.warning("Lyrics fetch error: %s", e)
    return None
  
