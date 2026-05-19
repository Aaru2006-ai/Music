"""
Spotify API integration via spotipy.
Converts Spotify links → track search queries used by yt-dlp.
"""

import logging
import re
from typing import Dict, List, Optional

from bot.config.config import Config

log = logging.getLogger(__name__)

_spotify = None  # spotipy.Spotify instance (lazy init)

SPOTIFY_URL_RE = re.compile(
    r"https?://open\.spotify\.com/(track|album|playlist|artist)/([A-Za-z0-9]+)"
)


def _init_spotify():
    global _spotify
    if _spotify is not None:
        return True
    if not Config.spotify_enabled():
        return False
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        auth = SpotifyClientCredentials(
            client_id=Config.SPOTIFY_CLIENT_ID,
            client_secret=Config.SPOTIFY_CLIENT_SECRET,
        )
        _spotify = spotipy.Spotify(auth_manager=auth)
        log.info("Spotify client initialised.")
        return True
    except Exception as e:
        log.error("Spotify init error: %s", e)
        return False


def is_spotify_url(url: str) -> bool:
    return bool(SPOTIFY_URL_RE.match(url.strip()))


def parse_spotify_url(url: str) -> Optional[tuple]:
    """Returns (type, id) or None."""
    m = SPOTIFY_URL_RE.match(url.strip())
    if m:
        return m.group(1), m.group(2)
    return None


# ── Single track ──────────────────────────────────────────────────────────────

async def get_spotify_track(track_id: str) -> Optional[Dict]:
    """Return a normalised track dict from a Spotify track ID."""
    if not _init_spotify():
        return None
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        track = await loop.run_in_executor(None, lambda: _spotify.track(track_id))
        return _normalise_track(track)
    except Exception as e:
        log.error("Spotify track fetch error: %s", e)
        return None


def _normalise_track(track: dict) -> Dict:
    artists = ", ".join(a["name"] for a in track.get("artists", []))
    album = track.get("album", {})
    images = album.get("images", [])
    thumbnail = images[0]["url"] if images else ""
    duration_ms = track.get("duration_ms", 0)

    return {
        "title":          track.get("name", "Unknown"),
        "uploader":       artists,
        "duration":       duration_ms // 1000,
        "duration_str":   _fmt_ms(duration_ms),
        "thumbnail":      thumbnail,
        "source":         "Spotify",
        "search_query":   f"{track.get('name', '')} {artists}",
        "url":            track.get("external_urls", {}).get("spotify", ""),
        "stream_url":     None,  # resolved via yt-dlp search
    }


def _fmt_ms(ms: int) -> str:
    seconds = ms // 1000
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── Playlist ──────────────────────────────────────────────────────────────────

async def get_spotify_playlist(playlist_id: str, limit: int = 50) -> List[Dict]:
    if not _init_spotify():
        return []
    try:
        import asyncio
        loop = asyncio.get_event_loop()

        def _fetch():
            results = _spotify.playlist_tracks(playlist_id, limit=limit)
            items = results.get("items", [])
            tracks = []
            for item in items:
                t = item.get("track")
                if t and t.get("id"):
                    tracks.append(_normalise_track(t))
            return tracks

        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        log.error("Spotify playlist fetch error: %s", e)
        return []


# ── Album ────────────────────────────────────────────────────────────────────

async def get_spotify_album(album_id: str) -> List[Dict]:
    if not _init_spotify():
        return []
    try:
        import asyncio
        loop = asyncio.get_event_loop()

        def _fetch():
            album = _spotify.album(album_id)
            tracks = album.get("tracks", {}).get("items", [])
            album_info = {
                "images": album.get("images", []),
            }
            result = []
            for t in tracks:
                t["album"] = album_info
                result.append(_normalise_track(t))
            return result

        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        log.error("Spotify album fetch error: %s", e)
        return []
  
