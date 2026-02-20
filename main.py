# bot/main.py

import asyncio
import logging
from datetime import time as dt_time
from typing import Dict, Any, Optional, List

from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from .config import (
    BOT_TOKEN,
    OWNER_ID,
    ADMIN_IDS,
    LOG_CHANNEL_ID,
    DEFAULT_THEME,
    DAILY_RESET_HOUR,
    DAILY_RESET_MINUTE,
    DAILY_RESET_TZ,
    LIMITS,
    BOT_VERSION,
)
from . import ui, messages
from .limits import (
    check_limits,
    add_usage,
    remove_concurrent,
    remaining_time,
    reset_daily_usage,
)
from .buttons import (
    generate_quality_buttons,
    generate_audio_buttons,
    generate_stop_info_buttons,
    parse_quality_callback,
    parse_audio_callback,
    parse_stop_info_callback,
)
from .utils.probe import probe_stream
from .utils.ffmpeg_runner import start_recording, stop_recording
from .utils.uploader import upload_parts_to_mega


logger = logging.getLogger(__name__)

# =========================
# In-memory state
# =========================

# Per-user theme ("hot" / "cold" / "dark")
user_themes: Dict[int, str] = {}

# Active recording sessions (high-level tracking; ffmpeg_runner has its own registry)
# user_id -> session info dict
active_recordings: Dict[int, Dict[str, Any]] = {}


# =========================
# Utility helpers
# =========================

def get_role(user_id: int) -> str:
    if user_id == OWNER_ID:
        return "owner"
    if user_id in ADMIN_IDS:
        return "admin"
    return "normal"


def get_theme_name(user_id: int) -> str:
    return user_themes.get(user_id, DEFAULT_THEME)


def get_theme(user_id: int) -> ui.BaseTheme:
    return ui.get_theme(get_theme_name(user_id))


def parse_duration_str(s: str) -> Optional[int]:
    """
    Parse a duration parameter:
    - "3600"          -> 3600
    - "01:00:00"      -> 3600
    - "00:00:00" or "0" -> None (unlimited)
    Returns seconds or None for unlimited.
    """
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) != 3:
            return None
        try:
            h, m, sec = map(int, parts)
        except ValueError:
            return None
        total = h * 3600 + m * 60 + sec
    else:
        if not s.isdigit():
            return None
        total = int(s)

    if total <= 0:
        return None
    return total


def human_duration(seconds: float) -> str:
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def build_disk_info() -> Dict[str, Any]:
    """
    Dummy/simple disk info; you can replace with shutil.disk_usage if you want.
    """
    # For now, we just pretend. You can import shutil and compute real numbers.
    return {
        "total_gb": 500,
        "free_gb": 420,
    }


def build_net_info() -> Dict[str, Any]:
    """
    Dummy/simple network info; could be extended with real ping tests.
    """
    return {
        "latency_ms": 12,
        "status": "Optimal",
    }


def summarize_active_recordings(user_id: int) -> List[Dict[str, Any]]:
    """
    Build rec_list for ui.status_display.
    """
    recs = []
    i = 0
    for uid, info in active_recordings.items():
        i += 1
        elapsed = info.get("elapsed", 0.0)
        percent = info.get("percent", None)
        recs.append(
            {
                "id": i,
                "name": info.get("filename_base", f"user_{uid}"),
                "quality": info.get("quality_label", "N/A"),
                "bitrate_mbps": info.get("bitrate_mbps", None),
                "elapsed_str": human_duration(elapsed),
                "percent": percent,
            }
        )
    return recs


# =========================
# Limits / Daily reset job
# =========================

async def daily_reset_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Running daily reset job for usage limits.")
    reset_daily_usage()


# =========================
# Command handlers
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    # Ensure theme in memory
    if user.id not in user_themes:
        user_themes[user.id] = DEFAULT_THEME

    theme = get_theme(user.id)
    disk = build_disk_info()
    net = build_net_info()

    active = len(active_recordings)
    text = theme.system_diagnostic(
        user=user,
        active_recordings=active,
        disk=disk,
        network=net,
    )

    await update.effective_message.reply_text(text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    theme = get_theme(user.id)
    role = get_role(user.id)

    rec_list = summarize_active_recordings(user.id)

    rem_secs = remaining_time(user.id, role)
    role_hours = LIMITS.get(role, {}).get("hours")

    if role_hours is None:
        daily_limit_hours = None
        used_hours = 0.0
    else:
        # remaining_time gives remaining; limit - remaining = used
        if rem_secs is None:
            daily_limit_hours = float(role_hours)
            used_hours = 0.0
        else:
            daily_limit_hours = float(role_hours)
            total_secs = daily_limit_hours * 3600
            used_secs = max(0.0, total_secs - rem_secs)
            used_hours = used_secs / 3600.0

    text = theme.status_display(
        rec_list=rec_list,
        role=role,
        daily_used_hours=used_hours,
        daily_limit_hours=daily_limit_hours,
    )

    await update.effective_message.reply_text(text)


async def theme_command(update: Update, context: ContextTypes.DEFAULT_TYPE, theme_name: str) -> None:
    user = update.effective_user
    if not user:
        return

    if theme_name not in ("hot", "cold", "dark"):
        await update.effective_message.reply_text("Invalid theme.")
        return

    user_themes[user.id] = theme_name
    theme = get_theme(user.id)

    confirm_text = messages.get_reply(
        theme_name,
        "info",
        text=f"Theme switched to {theme_name.upper()} ✅",
    )
    await update.effective_message.reply_text(confirm_text)


async def hot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await theme_command(update, context, "hot")


async def cold_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await theme_command(update, context, "cold")


async def dark_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await theme_command(update, context, "dark")


# =========================
# /record flow (step 1: parse + probe)
# =========================

async def record_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /record <link> <duration_or_timestamp> [filename]

    Example:
        /record http://example.com/stream.m3u8 3600 my_show
        /record http://example.com/stream.m3u8 01:00:00 my_show
        /record http://example.com/stream.m3u8 00:00:00 my_show  (unlimited)
    """
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    theme = get_theme(user.id)
    role = get_role(user.id)

    args = context.args
    if len(args) < 2:
        await msg.reply_text(
            theme.error("Usage: /record <link> <duration_or_timestamp> [filename]")
        )
        return

    link = args[0]
    duration_str = args[1]
    filename = None
    if len(args) >= 3:
        filename = args[2].strip()

    if not filename:
        # Simple fallback base name
        filename = f"rec_{user.id}"

    duration_seconds = parse_duration_str(duration_str)
    # None => unlimited; for limit check we'll treat as 0 pre-estimate
    intended_duration = duration_seconds or 0

    # Check limits & concurrency
    limit_result = check_limits(
        user_id=user.id,
        role=role,
        trial_requested=False,
        duration_seconds=intended_duration,
    )

    if not limit_result.allowed:
        code = limit_result.code or "unknown"
        if code == "concurrent_exceeded":
            text = messages.get_reply(
                get_theme_name(user.id),
                "limit_exceeded",
                limit_hours=LIMITS.get(role, {}).get("hours", "∞"),
                used_hours="N/A",
            )
            # override with savage line:
            text = "Apne Aukat mai raha karo 😒\n\n" + text
            await msg.reply_text(text)
            return
        elif code == "global_concurrent_exceeded":
            await msg.reply_text(
                theme.error("Bot is already at max concurrent recordings. Try later.")
            )
            return
        elif code == "daily_limit":
            limit_hours = LIMITS.get(role, {}).get("hours", "∞")
            used_secs_remaining = limit_result.remaining_seconds or 0
            if limit_hours == "∞" or limit_hours is None:
                used_hours = "N/A"
            else:
                total_secs = limit_hours * 3600
                used_secs = max(0, total_secs - used_secs_remaining)
                used_hours = f"{used_secs / 3600:.2f}"
            text = messages.get_reply(
                get_theme_name(user.id),
                "limit_exceeded",
                limit_hours=limit_hours,
                used_hours=used_hours,
            )
            await msg.reply_text(text)
            return
        else:
            await msg.reply_text(
                theme.error(f"Recording not allowed (code={code}).")
            )
            return

    # If we reach here, allowed (owner always allowed by hours check)
    await msg.reply_text(theme.info("Probing stream for qualities & audio tracks..."))

    probe = await probe_stream(link)

    # Build qualities list for buttons
    if probe.qualities:
        qualities_list = [
            {"id": q.id, "label": q.label, "stream_index": q.stream_index}
            for q in probe.qualities
        ]
    else:
        qualities_list = [{"id": "auto", "label": "AUTO", "stream_index": None}]

    # Build audio list
    if probe.audios:
        audio_list = [
            {"id": a.id, "label": a.label, "stream_index": a.stream_index}
            for a in probe.audios
        ]
    else:
        audio_list = [{"id": "und", "label": "Default", "stream_index": None}]

    # Store pending recording params in user_data
    context.user_data["pending_record"] = {
        "link": link,
        "duration_seconds": duration_seconds,
        "filename_base": filename,
        "qualities": qualities_list,
        "audios": audio_list,
        "role": role,
    }

    kb = generate_quality_buttons(qualities_list)
    await msg.reply_text("Select quality:", reply_markup=kb)


# =========================
# Callback handlers for quality/audio selection
# =========================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Single entry for all callback queries:
      - quality_*
      - audio_*
      - stop_*
      - info_*
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""
    user = query.from_user
    theme = get_theme(user.id)

    # Quality selection
    if data.startswith("quality_"):
        qid = parse_quality_callback(data)
        pending = context.user_data.get("pending_record")
        if not pending:
            await query.edit_message_text(theme.error("No pending recording session."))
            return

        qualities = pending.get("qualities", [])
        selected_q = None
        for q in qualities:
            if str(q.get("id")) == str(qid):
                selected_q = q
                break

        if not selected_q:
            await query.edit_message_text(theme.error("Selected quality not found."))
            return

        pending["selected_quality"] = selected_q
        context.user_data["pending_record"] = pending

        # Ask for audio
        audios = pending.get("audios", [])
        kb = generate_audio_buttons(audios)
        await query.edit_message_text("Select audio track:", reply_markup=kb)
        return

    # Audio selection
    if data.startswith("audio_"):
        aid = parse_audio_callback(data)
        pending = context.user_data.get("pending_record")
        if not pending:
            await query.edit_message_text(theme.error("No pending recording session."))
            return

        audios = pending.get("audios", [])
        selected_a = None
        for a in audios:
            if str(a.get("id")) == str(aid):
                selected_a = a
                break

        if not selected_a:
            await query.edit_message_text(theme.error("Selected audio not found."))
            return

        pending["selected_audio"] = selected_a
        context.user_data["pending_record"] = pending

        # Now start recording
        await start_recording_from_pending(query, context, pending)
        # Remove pending after starting
        context.user_data.pop("pending_record", None)
        return

    # Stop / Info
    if data.startswith("stop_"):
        target_uid_str = parse_stop_info_callback(data)
        try:
            target_uid = int(target_uid_str)
        except ValueError:
            target_uid = user.id

        # Only owner, admins or same user can stop
        user_role = get_role(user.id)
        if user.id != target_uid and user_role not in ("owner", "admin"):
            await query.edit_message_text(theme.error("You are not allowed to stop this session."))
            return

        await stop_recording(target_uid)
        await query.edit_message_text(theme.info("Stop requested. Recording will terminate shortly."))
        return

    if data.startswith("info_"):
        target_uid_str = parse_stop_info_callback(data)
        try:
            target_uid = int(target_uid_str)
        except ValueError:
            target_uid = user.id

        rec = active_recordings.get(target_uid)
        if not rec:
            await query.edit_message_text(theme.info("No active recording for this user."))
            return

        elapsed = rec.get("elapsed", 0.0)
        bitrate = rec.get("bitrate_mbps", 0.0)
        filename_base = rec.get("filename_base", "unknown")
        link = rec.get("link", "n/a")

        text = (
            f"🎥 Recording info\n"
            f"User: {target_uid}\n"
            f"Base name: {filename_base}\n"
            f"Source: {link}\n"
            f"Elapsed: {human_duration(elapsed)}\n"
            f"Bitrate: {bitrate:.2f} Mbps\n"
        )
        await query.edit_message_text(text)
        return


async def start_recording_from_pending(query, context: ContextTypes.DEFAULT_TYPE, pending: Dict[str, Any]) -> None:
    """
    Helper to start recording after quality + audio selection.
    """
    user = query.from_user
    theme = get_theme(user.id)

    link = pending["link"]
    duration_seconds = pending["duration_seconds"]
    filename_base = pending["filename_base"]
    role = pending["role"]
    selected_q = pending.get("selected_quality")
    selected_a = pending.get("selected_audio")

    # Now that user committed, mark usage & concurrency
    intended_duration = duration_seconds or 0
    add_usage(
        user_id=user.id,
        role=role,
        duration_seconds=intended_duration,
        trial=False,
    )

    # Initial active recording info
    active_recordings[user.id] = {
        "link": link,
        "filename_base": filename_base,
        "quality_label": selected_q.get("label") if isinstance(selected_q, dict) else str(selected_q),
        "audio_label": selected_a.get("label") if isinstance(selected_a, dict) else str(selected_a),
        "start_time": None,
        "elapsed": 0.0,
        "bitrate_mbps": 0.0,
        "percent": None,
        "chat_id": query.message.chat_id,
        "message_id": None,  # we'll set after sending
        "theme_name": get_theme_name(user.id),
        "role": role,
    }

    # Send recording start message
    start_text = theme.recording_start(
        link=link,
        quality=active_recordings[user.id]["quality_label"],
        audio=active_recordings[user.id]["audio_label"],
    )
    kb = generate_stop_info_buttons(user.id)
    sent = await query.edit_message_text(start_text, reply_markup=kb)

    # Store message id for progress updates
    active_recordings[user.id]["message_id"] = sent.message_id

    # Prepare callback wrappers
    async def progress_cb(u_id, filename_base, elapsed_sec, bytes_written, bitrate_mbps, percent):
        rec = active_recordings.get(u_id)
        if not rec:
            return
        rec["elapsed"] = elapsed_sec
        rec["bitrate_mbps"] = bitrate_mbps
        rec["percent"] = percent
        active_recordings[u_id] = rec

        # Prepare progress display
        tname = rec.get("theme_name", get_theme_name(u_id))
        t = ui.get_theme(tname)
        # Use download_progress style for recording phase
        text = t.download_progress(
            filename=filename_base,
            percent=percent or 0.0,
            speed_mbps=bitrate_mbps or 0.0,
        )

        chat_id = rec.get("chat_id")
        msg_id = rec.get("message_id")
        if chat_id and msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=generate_stop_info_buttons(u_id),
                )
            except Exception as e:
                logger.warning("Failed to update progress message: %s", e)

    async def done_cb(u_id, filename_base, out_dir, parts, elapsed_sec):
        # Remove concurrency
        remove_concurrent(u_id)
        rec = active_recordings.pop(u_id, None)

        # Upload to MEGA
        from .utils.uploader import upload_parts_to_mega

        async def up_progress_cb(user_id, base_name, part_idx, total_parts, filename, stage, percent):
            # Optionally update message with upload stage
            r = active_recordings.get(user_id) or rec
            if not r:
                return
            chat_id = r.get("chat_id")
            msg_id = r.get("message_id")
            tname = r.get("theme_name", get_theme_name(user_id))
            t = ui.get_theme(tname)

            bar_text = t.upload_progress(
                filename=filename,
                percent=percent,
                speed_mbps=None,
            )
            extra = f"\nPart {part_idx}/{total_parts} | Stage: {stage}"

            if chat_id and msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=bar_text + extra,
                    )
                except Exception as e:
                    logger.warning("Failed to update upload message: %s", e)

        async def up_error_cb(user_id, base_name, message_text):
            r = active_recordings.get(user_id) or rec
            tname = (r or {}).get("theme_name", get_theme_name(user_id))
            t = ui.get_theme(tname)
            text = t.error(f"MEGA upload error: {message_text}")
            chat_id = (r or {}).get("chat_id")
            if chat_id:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=text)
                except Exception as e:
                    logger.warning("Failed to send MEGA error message: %s", e)

        upload_result = await upload_parts_to_mega(
            user_id=u_id,
            base_name=filename_base,
            parts=parts,
            remote_folder=None,
            progress_callback=up_progress_cb,
            error_callback=up_error_cb,
        )

        upload_result = await upload_parts_to_mega(...)