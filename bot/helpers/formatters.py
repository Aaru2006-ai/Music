"""
Message formatting utilities — now-playing cards, queue display, stats.
All output is Markdown-safe for Pyrogram (parse_mode="Markdown").
"""

import math
from typing import Dict, List, Optional


# ── Progress bar ──────────────────────────────────────────────────────────────

def progress_bar(current: int, total: int, length: int = 12) -> str:
    if total <= 0:
        return "▬" * length
    filled = math.floor((current / total) * length)
    bar = "█" * filled + "─" * (length - filled)
    return f"[{bar}]"


def fmt_seconds(secs: int) -> str:
    if not secs or secs < 0:
        return "00:00"
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── Now-Playing Card ──────────────────────────────────────────────────────────

def now_playing_text(
    track: Dict,
    position: int = 0,
    queue_count: int = 0,
    looping: bool = False,
    volume: int = 100,
) -> str:
    title      = track.get("title", "Unknown")
    uploader   = track.get("uploader", "Unknown Artist")
    duration   = track.get("duration_str", "??:??")
    source     = track.get("source", "YouTube")
    req_name   = track.get("requester_name", "Someone")
    req_id     = track.get("requester_id", 0)
    quality    = track.get("quality", "128 kbps")

    source_icon = {
        "YouTube": "▶️", "Spotify": "🎧", "SoundCloud": "☁️",
        "JioSaavn": "🎵", "Telegram": "📁",
    }.get(source, "🎵")

    loop_badge   = "  🔁 Loop On" if looping else ""
    queue_badge  = f"  📋 {queue_count} in queue" if queue_count else ""

    requester_text = (
        f"[{req_name}](tg://user?id={req_id})" if req_id else req_name
    )

    text = (
        f"╔═══════════════════╗\n"
        f"║  {source_icon} **NOW PLAYING**\n"
        f"╚═══════════════════╝\n\n"
        f"🎵 **{title}**\n"
        f"👤 {uploader}\n\n"
        f"⏱ `{duration}`{loop_badge}{queue_badge}\n"
        f"🔊 Volume: `{volume}%`\n"
        f"📡 Source: {source}\n\n"
        f"👥 Requested by: {requester_text}"
    )
    return text


# ── Queue Display ─────────────────────────────────────────────────────────────

def format_queue(
    current: Optional[Dict],
    tracks: List[Dict],
    page: int,
    total_pages: int,
    chat_title: str = "Queue",
) -> str:
    lines = [f"**📋 Queue — {chat_title}**\n"]

    if current:
        title = current.get("title", "Unknown")[:40]
        dur   = current.get("duration_str", "??:??")
        lines.append(f"▶️ **Now:** {title} `[{dur}]`\n")

    if not tracks:
        lines.append("_Queue is empty._")
    else:
        lines.append(f"**Up next** (page {page}/{total_pages}):\n")
        start = (page - 1) * 10 + 1
        for i, t in enumerate(tracks, start=start):
            title = t.get("title", "Unknown")[:38]
            dur   = t.get("duration_str", "??:??")
            req   = t.get("requester_name", "?")[:12]
            lines.append(f"`{i}.` {title} `[{dur}]` — {req}")

    return "\n".join(lines)


# ── Stats Card ────────────────────────────────────────────────────────────────

def format_stats(stats: Dict, active_streams: int, bot_name: str = "MusicBot") -> str:
    return (
        f"**📊 {bot_name} Statistics**\n\n"
        f"👤 Users: `{stats.get('users', 0):,}`\n"
        f"💬 Chats: `{stats.get('chats', 0):,}`\n"
        f"🎵 Active Streams: `{active_streams}`\n"
        f"🚫 Banned Users: `{stats.get('bans', 0):,}`\n"
        f"📂 Playlists: `{stats.get('playlists', 0):,}`\n"
        f"📜 Playback History: `{stats.get('history_entries', 0):,}`\n"
    )


# ── Leaderboard ───────────────────────────────────────────────────────────────

def format_leaderboard(top_users: List[Dict]) -> str:
    if not top_users:
        return "📊 No data available yet."
    medals = ["🥇", "🥈", "🥉"] + ["🎵"] * 10
    lines  = ["**🏆 Top Listeners Today**\n"]
    for i, entry in enumerate(top_users):
        uid   = entry.get("user_id")
        plays = entry.get("plays", 0)
        lines.append(f"{medals[i]} `{uid}` — {plays} plays")
    return "\n".join(lines)


# ── Help Text ─────────────────────────────────────────────────────────────────

HELP_TEXTS = {
    "music": (
        "**🎵 Music Commands**\n\n"
        "`/play [song/URL]` — Play audio\n"
        "`/vplay [song/URL]` — Play video\n"
        "`/radio [URL]` — Start radio stream\n"
        "`/song [title]` — Search & pick song\n"
        "`/lyrics [title]` — Get song lyrics\n"
        "`/queue` — View current queue\n"
        "`/remove [position]` — Remove track from queue\n"
        "`/clearqueue` — Clear the entire queue\n"
    ),
    "controls": (
        "**🎛 Playback Controls**\n\n"
        "`/pause` — Pause playback\n"
        "`/resume` — Resume playback\n"
        "`/skip` — Skip current track\n"
        "`/stop` — Stop & leave VC\n"
        "`/seek [seconds]` — Seek to position\n"
        "`/loop` — Toggle loop mode\n"
        "`/shuffle` — Shuffle queue\n"
        "`/volume [0-200]` — Set volume\n"
        "`/speed [0.5-2.0]` — Set playback speed\n"
        "`/replay` — Replay current track\n"
    ),
    "admin": (
        "**⚙️ Admin Commands**\n\n"
        "`/settings` — View/edit chat settings\n"
        "`/clean` — Clean bot messages\n"
        "`/restart` — Restart the bot (sudo)\n"
        "`/update` — Update from GitHub (sudo)\n"
        "`/maintenance` — Toggle maintenance mode\n"
        "`/gban [user_id]` — Global ban\n"
        "`/ungban [user_id]` — Remove global ban\n"
        "`/broadcast` — Broadcast message to all chats\n"
        "`/addadmin` — Add sudo user\n"
        "`/removeadmin` — Remove sudo user\n"
    ),
    "stats": (
        "**📊 Stats Commands**\n\n"
        "`/stats` — Bot statistics\n"
        "`/ping` — Check bot latency\n"
        "`/leaderboard` — Top listeners today\n"
        "`/history` — Recent playback history\n"
        "`/uptime` — Bot uptime\n"
    ),
          }
