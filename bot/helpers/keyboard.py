"""
Inline keyboard builder for all bot UI interactions.
"""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ── Now-Playing Controls ───────────────────────────────────────────────────────

def now_playing_kb(chat_id: int, paused: bool = False) -> InlineKeyboardMarkup:
    play_pause = "▶️ Resume" if paused else "⏸ Pause"
    play_pause_cb = f"resume:{chat_id}" if paused else f"pause:{chat_id}"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(play_pause, callback_data=play_pause_cb),
            InlineKeyboardButton("⏭ Skip", callback_data=f"skip:{chat_id}"),
            InlineKeyboardButton("⏹ Stop", callback_data=f"stop:{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔉 Vol -10", callback_data=f"vol_down:{chat_id}"),
            InlineKeyboardButton("🔊 Vol +10", callback_data=f"vol_up:{chat_id}"),
            InlineKeyboardButton("🔁 Loop", callback_data=f"loop:{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔀 Shuffle", callback_data=f"shuffle:{chat_id}"),
            InlineKeyboardButton("📋 Queue", callback_data=f"queue:{chat_id}:1"),
            InlineKeyboardButton("🎵 Lyrics", callback_data=f"lyrics:{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔇 Mute", callback_data=f"mute:{chat_id}"),
            InlineKeyboardButton("🔈 Unmute", callback_data=f"unmute:{chat_id}"),
            InlineKeyboardButton("⬇️ Download", callback_data=f"download:{chat_id}"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close"),
        ],
    ])


# ── Queue Pagination ───────────────────────────────────────────────────────────

def queue_kb(chat_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []

    if page > 1:
        nav.append(
            InlineKeyboardButton(
                "◀️ Prev",
                callback_data=f"queue:{chat_id}:{page - 1}"
            )
        )

    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                "Next ▶️",
                callback_data=f"queue:{chat_id}:{page + 1}"
            )
        )

    rows = []

    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(
            "🗑 Clear Queue",
            callback_data=f"clear_queue:{chat_id}"
        ),
        InlineKeyboardButton(
            "🔀 Shuffle",
            callback_data=f"shuffle:{chat_id}"
        ),
    ])

    rows.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    return InlineKeyboardMarkup(rows)


# ── Search Results ─────────────────────────────────────────────────────────────

def search_results_kb(results: list, chat_id: int) -> InlineKeyboardMarkup:
    buttons = []

    for i, track in enumerate(results[:5]):
        title = track.get("title", "Unknown")[:40]
        dur = track.get("duration_str", "??:??")

        buttons.append([
            InlineKeyboardButton(
                f"{i + 1}. {title} [{dur}]",
                callback_data=f"play_result:{chat_id}:{i}",
            )
        ])

    buttons.append([
        InlineKeyboardButton("❌ Cancel", callback_data="close")
    ])

    return InlineKeyboardMarkup(buttons)


# ── Playlist ───────────────────────────────────────────────────────────────────

def playlist_kb(playlists: list, owner_id: int) -> InlineKeyboardMarkup:
    buttons = []

    for pl in playlists:
        name = pl.get("name", "Unnamed")[:30]

        buttons.append([
            InlineKeyboardButton(
                f"📂 {name}",
                callback_data=f"load_playlist:{owner_id}:{name}"
            ),
            InlineKeyboardButton(
                "🗑",
                callback_data=f"del_playlist:{owner_id}:{name}"
            ),
        ])

    buttons.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    return InlineKeyboardMarkup(buttons)


# ── Settings ───────────────────────────────────────────────────────────────────

def settings_kb(chat_id: int, settings: dict) -> InlineKeyboardMarkup:
    loop_icon = "✅" if settings.get("loop") else "❌"
    shuffle_icon = "✅" if settings.get("shuffle") else "❌"
    auto_icon = "✅" if settings.get("autoplay") else "❌"
    admin_icon = "✅" if settings.get("admin_only") else "❌"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🔁 Loop: {loop_icon}",
                callback_data=f"setting:loop:{chat_id}"
            ),
            InlineKeyboardButton(
                f"🔀 Shuffle: {shuffle_icon}",
                callback_data=f"setting:shuffle:{chat_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                f"▶️ Autoplay: {auto_icon}",
                callback_data=f"setting:autoplay:{chat_id}"
            ),
            InlineKeyboardButton(
                f"🛡 Admin Only: {admin_icon}",
                callback_data=f"setting:admin_only:{chat_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔊 Quality: Audio",
                callback_data=f"setting:quality:{chat_id}"
            ),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close")
        ],
    ])


# ── Help ───────────────────────────────────────────────────────────────────────

def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎵 Music",
                callback_data="help:music"
            ),
            InlineKeyboardButton(
                "⚙️ Admin",
                callback_data="help:admin"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎛 Controls",
                callback_data="help:controls"
            ),
            InlineKeyboardButton(
                "📊 Stats",
                callback_data="help:stats"
            ),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close")
        ],
    ])


# ── Generic ────────────────────────────────────────────────────────────────────

def close_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])


def confirm_kb(action: str, identifier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Confirm",
                callback_data=f"confirm:{action}:{identifier}"
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="close"
            ),
        ]
    ])


HELP_TEXTS = {
    "play": "Use /play to play music.",
    "pause": "Use /pause to pause music.",
    "resume": "Use /resume to resume music.",
    "skip": "Use /skip to skip current track.",
    "stop": "Use /stop to stop playback."
}
