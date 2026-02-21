# bot/main.py

import asyncio
import logging
from datetime import time as dt_time, datetime
from typing import Dict, Any, List

from zoneinfo import ZoneInfo
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
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
from .utils.chunk_pipeline import start_chunked_pipeline, request_stop

logger = logging.getLogger(__name__)

# =========================
# In-memory state
# =========================

# Per-user theme ("hot" / "cold" / "dark")
user_themes: Dict[int, str] = {}

# Active recording sessions
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


def summarize_active_recordings() -> List[Dict[str, Any]]:
    """
    Build rec_list for ui.status_display.
    """
    recs: List[Dict[str, Any]] = []
    i = 0
    now = datetime.utcnow()
    for uid, info in active_recordings.items():
        i += 1
        started_at = info.get("start_time")
        if isinstance(started_at, datetime):
            elapsed = (now - started_at).total_seconds()
        else:
            elapsed = 0.0
        recs.append(
            {
                "id": i,
                "name": info.get("filename_base", f"user_{uid}"),
                "quality": "chunked",   # fixed label for our 600MB chunk mode
                "bitrate_mbps": None,
                "elapsed_str": human_duration(elapsed),
                "percent": None,
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

    rec_list = summarize_active_recordings()

    rem_secs = remaining_time(user.id, role)
    role_hours = LIMITS.get(role, {}).get("hours")

    if role_hours is None:
        daily_limit_hours = None
        used_hours = 0.0
    else:
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
# /record and /stop
# =========================

async def record_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /record <link> [filename]

    Example:
        /record http://example.com/stream.m3u8 my_show

    This starts a continuous 600MB-chunked recording:
      - Each chunk (~<=600 MB) is uploaded to Telegram
      - After upload, the file is deleted from disk
      - Recording + upload run in parallel
    """
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    theme = get_theme(user.id)
    role = get_role(user.id)

    args = context.args
    if len(args) < 1:
        await msg.reply_text(
            theme.error("Usage: /record <link> [filename]")
        )
        return

    link = args[0]
    if len(args) >= 2:
        filename_base = args[1].strip()
    else:
        filename_base = f"rec_{user.id}"

    # Limit check: we don't know total duration, so use 0 seconds
    limit_result = check_limits(
        user_id=user.id,
        role=role,
        trial_requested=False,
        duration_seconds=0,
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
            remaining = limit_result.remaining_seconds or 0
            if limit_hours == "∞" or limit_hours is None:
                used_hours = "N/A"
            else:
                total_secs = limit_hours * 3600
                used_secs = max(0, total_secs - remaining)
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

    # Mark concurrency in usage (duration unknown, so 0 here)
    add_usage(
        user_id=user.id,
        role=role,
        duration_seconds=0,
        trial=False,
    )

    # Track active recording
    active_recordings[user.id] = {
        "link": link,
        "filename_base": filename_base,
        "start_time": datetime.utcnow(),
        "chat_id": msg.chat_id,
        "theme_name": get_theme_name(user.id),
    }

    # Inform user
    info_text = theme.recording_start(
        link=link,
        quality="chunked",
        audio="auto",
    )
    await msg.reply_text(info_text)

    out_dir = Path("bot/downloads") / str(user.id)

    async def progress_cb(chunk_info, stage: str):
        # Here you could edit a status message, or log to a channel.
        # For now, just log to stderr.
        if stage == "start":
            logger.info(
                "User %s chunk %s started (%s)",
                chunk_info.user_id,
                chunk_info.part_index,
                chunk_info.path,
            )
        else:
            logger.info(
                "User %s chunk %s uploaded & deleted",
                chunk_info.user_id,
                chunk_info.part_index,
            )

    async def run_pipeline_and_cleanup():
        try:
            await start_chunked_pipeline(
                user_id=user.id,
                chat_id=msg.chat_id,
                bot=context.bot,
                link=link,
                base_name=filename_base,
                out_dir=out_dir,
                progress_cb=progress_cb,
                max_parts=None,
            )
        finally:
            # Cleanup
            remove_concurrent(user.id)
            rec = active_recordings.pop(user.id, None)

            tname = (rec or {}).get("theme_name", get_theme_name(user.id))
            t = ui.get_theme(tname)
            end_text = t.info(f"Recording session for {filename_base} finished.")

            # Notify user
            try:
                await context.bot.send_message(chat_id=msg.chat_id, text=end_text)
            except Exception as e:
                logger.warning("Failed to send end message: %s", e)

            # Notify log channel (optional)
            try:
                await context.bot.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=f"[SESSION_END] user={user.id} base={filename_base}",
                )
            except Exception:
                pass

    # Fire and forget
    context.application.create_task(run_pipeline_and_cleanup())


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /stop – request stop for current user's recording.
    """
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    theme = get_theme(user.id)
    if user.id not in active_recordings:
        await msg.reply_text(theme.info("No active recording to stop."))
        return

    request_stop(user.id)
    await msg.reply_text(theme.info("Stop requested. Recording will finish after current chunk."))


# =========================
# App setup / entry
# =========================

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not BOT_TOKEN or BOT_TOKEN == "CHANGE_ME_TELEGRAM_BOT_TOKEN":
        raise RuntimeError("BOT_TOKEN is not set. Configure it in environment or config.py")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Core commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("record", record_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("hot", hot_command))
    application.add_handler(CommandHandler("cold", cold_command))
    application.add_handler(CommandHandler("dark", dark_command))

    # JobQueue: daily reset
    tz = ZoneInfo(DAILY_RESET_TZ)
    reset_time = dt_time(
        hour=DAILY_RESET_HOUR,
        minute=DAILY_RESET_MINUTE,
        tzinfo=tz,
    )
    application.job_queue.run_daily(daily_reset_job, time=reset_time)

    logger.info("Starting bot (version %s)...", BOT_VERSION)
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
