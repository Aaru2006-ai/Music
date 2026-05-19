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

def playlist_kb(playlists: list, owner_id: int) ->
