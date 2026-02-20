# bot/buttons.py

"""
Inline keyboard generators for the bot.

Callback data patterns:

- Quality buttons:
    quality_<id>
    Example: quality_1080p, quality_720p

- Audio buttons:
    audio_<id>
    Example: audio_eng, audio_hin

- Playlist items:
    plitem_<id>

- Stop / Info buttons:
    stop_<user_id>
    info_<user_id>
"""

from __future__ import annotations

from typing import List, Iterable, Dict, Any, Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# =========================
# Quality Buttons
# =========================

def generate_quality_buttons(
    qualities: Iterable[Union[str, Dict[str, Any]]]
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for selecting quality.

    `qualities` can be:
        - list of strings: ["1080p", "720p", "480p"]
        - list of dicts with:
            {
                "id": "1080p",
                "label": "1080p (Best)",
            }

    Returns:
        InlineKeyboardMarkup with 1–2 buttons per row.
    """
    buttons: List[List[InlineKeyboardButton]] = []

    row: List[InlineKeyboardButton] = []
    for q in qualities:
        if isinstance(q, dict):
            qid = str(q.get("id") or q.get("quality") or q.get("name") or "unknown")
            label = str(q.get("label") or q.get("display") or qid)
        else:
            qid = str(q)
            label = qid

        btn = InlineKeyboardButton(
            text=label,
            callback_data=f"quality_{qid}",
        )
        row.append(btn)

        # 2 per row
        if len(row) >= 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Optional "auto" / "best" button if you want
    # buttons.append([InlineKeyboardButton("AUTO / BEST", callback_data="quality_auto")])

    return InlineKeyboardMarkup(buttons)


# =========================
# Audio Buttons
# =========================

def generate_audio_buttons(
    audios: Iterable[Union[str, Dict[str, Any]]]
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for selecting audio language/track.

    `audios` can be:
        - list of strings: ["Hindi", "English", "Tamil"]
        - list of dicts with:
            {
                "id": "hin",
                "label": "Hindi",
            }

    We convert the id to lowercase and make it safe for callback.

    Callback pattern: audio_<id>
        e.g. audio_hin, audio_eng

    Returns:
        InlineKeyboardMarkup
    """
    buttons: List[List[InlineKeyboardButton]] = []

    row: List[InlineKeyboardButton] = []
    for a in audios:
        if isinstance(a, dict):
            aid = str(a.get("id") or a.get("code") or a.get("lang") or "unknown").lower()
            label = str(a.get("label") or a.get("name") or aid.title())
        else:
            label = str(a)
            # derive id from label (e.g. "Hindi" -> "hindi")
            aid = label.lower().replace(" ", "_")

        btn = InlineKeyboardButton(
            text=label,
            callback_data=f"audio_{aid}",
        )
        row.append(btn)

        if len(row) >= 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # You can also add an "AUTO" option if needed:
    # buttons.append([InlineKeyboardButton("AUTO", callback_data="audio_auto")])

    return InlineKeyboardMarkup(buttons)


# =========================
# Playlist Buttons
# =========================

def generate_playlist_buttons(
    playlists: Iterable[Dict[str, Any]],
    row_width: int = 2,
) -> InlineKeyboardMarkup:
    """
    Generate inline buttons for playlists list or playlist items.

    Expected structure (flexible):
        playlists = [
            {"id": "sports", "name": "Sports"},
            {"id": "news", "name": "News"},
            ...
        ]

    Or for playlist channels/items:
        [
            {"id": "1", "name": "Channel 1"},
            {"id": "2", "name": "Channel 2"},
        ]

    Callback pattern: plitem_<id>
        e.g. plitem_sports, plitem_1

    Returns:
        InlineKeyboardMarkup
    """
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []

    for item in playlists:
        pid = str(item.get("id") or item.get("key") or item.get("name") or "unknown")
        name = str(item.get("name") or item.get("title") or pid)

        btn = InlineKeyboardButton(
            text=name,
            callback_data=f"plitem_{pid}",
        )
        row.append(btn)

        if len(row) >= row_width:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


# =========================
# Stop / Info Buttons
# =========================

def generate_stop_info_buttons(user_id: int) -> InlineKeyboardMarkup:
    """
    Generate [ ⏹ STOP ] [ ℹ️ INFO ] buttons for a specific user's active recording.

    Callback patterns:
        stop_<user_id>
        info_<user_id>
    """
    stop_btn = InlineKeyboardButton(
        text="⏹ STOP",
        callback_data=f"stop_{user_id}",
    )
    info_btn = InlineKeyboardButton(
        text="ℹ️ INFO",
        callback_data=f"info_{user_id}",
    )

    keyboard = [[stop_btn, info_btn]]
    return InlineKeyboardMarkup(keyboard)


# =========================
# (Optional) small helpers
# =========================

def parse_quality_callback(data: str) -> str:
    """
    Parse callback_data like 'quality_1080p' -> '1080p'.
    """
    prefix = "quality_"
    if data.startswith(prefix):
        return data[len(prefix):]
    return data


def parse_audio_callback(data: str) -> str:
    """
    Parse callback_data like 'audio_hin' -> 'hin'.
    """
    prefix = "audio_"
    if data.startswith(prefix):
        return data[len(prefix):]
    return data


def parse_playlist_item_callback(data: str) -> str:
    """
    Parse callback_data like 'plitem_sports' -> 'sports'.
    """
    prefix = "plitem_"
    if data.startswith(prefix):
        return data[len(prefix):]
    return data


def parse_stop_info_callback(data: str) -> str:
    """
    Parse 'stop_<user_id>' or 'info_<user_id>' -> user_id (str).
    You can int() it in handlers.
    """
    if data.startswith("stop_"):
        return data[len("stop_"):]
    if data.startswith("info_"):
        return data[len("info_"):]
    return data