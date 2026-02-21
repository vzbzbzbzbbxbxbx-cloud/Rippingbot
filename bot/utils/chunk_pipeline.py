# bot/utils/chunk_pipeline.py
#
# 600 MB chunked recording + Telegram upload pipeline.
#
# - Records in ~MAX_PART_BYTES chunks using ffmpeg (-fs)
# - After each chunk finishes:
#     • uploads it to Telegram as a document
#     • deletes the local file
#     • recorder immediately continues with next chunk
# - Disk stays small: at most a few chunks at once.
#
# IMPORTANT: Use only with streams/content you have the rights to record.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Callable, Any

from telegram import Bot

# =========================
# Settings
# =========================

# Max file size per chunk: 600 MB
MAX_PART_BYTES = 600 * 1024 * 1024

# Per-user stop flags
_stop_flags: Dict[int, asyncio.Event] = {}


@dataclass
class ChunkInfo:
    """
    Metadata for a single recorded chunk.
    """
    user_id: int
    chat_id: int
    base_name: str
    part_index: int
    path: Path
    size_bytes: int


# =========================
# Public control API
# =========================

def request_stop(user_id: int) -> None:
    """
    Request the pipeline for a given user to stop after the current chunk.
    Called from /stop handler.
    """
    ev = _stop_flags.get(user_id)
    if ev is not None:
        ev.set()


def _get_stop_event(user_id: int) -> asyncio.Event:
    """
    Get or create the asyncio.Event used to signal stopping for a user.
    """
    ev = _stop_flags.get(user_id)
    if ev is None:
        ev = asyncio.Event()
        _stop_flags[user_id] = ev
    return ev


# =========================
# FFmpeg chunk runner
# =========================

async def _run_ffmpeg_chunk(
    link: str,
    out_file: Path,
    max_bytes: int = MAX_PART_BYTES,
) -> bool:
    """
    Run ffmpeg once to produce a single chunk capped by file size.

    Returns True if the chunk was created and has non-zero size.
    """
    # ffmpeg command: copy stream into Matroska, limited by size
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", link,
        "-c", "copy",
        "-fs", str(max_bytes),  # approximate max file size in bytes
        str(out_file),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    code = await proc.wait()

    if code != 0:
        return False

    if not out_file.exists():
        return False

    if out_file.stat().st_size <= 0:
        return False

    return True


# =========================
# Upload logic
# =========================

async def _upload_chunk_to_telegram(
    bot: Bot,
    info: ChunkInfo,
    progress_cb: Optional[Callable[[ChunkInfo, str], Any]] = None,
) -> None:
    """
    Upload a finished chunk as a Telegram document, then delete it.

    progress_cb(info, stage) is called with:
      - stage="start" before upload
      - stage="end" after upload+delete
    """
    if progress_cb:
        res = progress_cb(info, "start")
        if asyncio.iscoroutine(res):
            await res

    try:
        with info.path.open("rb") as f:
            await bot.send_document(
                chat_id=info.chat_id,
                document=f,
                caption=f"{info.base_name} (part {info.part_index})",
            )
    finally:
        # Delete local file to keep disk usage low
        try:
            info.path.unlink(missing_ok=True)
        except Exception:
            pass

    if progress_cb:
        res = progress_cb(info, "end")
        if asyncio.iscoroutine(res):
            await res


# =========================
# Recorder & Uploader loops
# =========================

async def _recorder_loop(
    user_id: int,
    chat_id: int,
    bot: Bot,
    link: str,
    base_name: str,
    out_dir: Path,
    queue: asyncio.Queue,
    progress_cb: Optional[Callable[[ChunkInfo, str], Any]] = None,
    max_parts: Optional[int] = None,
) -> None:
    """
    Loop that continuously records chunks and enqueues them for upload.
    Stops when:
      - stop event is set for user_id, or
      - ffmpeg fails, or
      - max_parts is reached (if provided).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stop_event = _get_stop_event(user_id)
    part_idx = 1

    while not stop_event.is_set():
        if max_parts is not None and part_idx > max_parts:
            break

        out_file = out_dir / f"{base_name}_part{part_idx:03d}.mkv"

        ok = await _run_ffmpeg_chunk(link, out_file, MAX_PART_BYTES)
        if not ok:
            # ffmpeg failed or stream ended
            break

        size = out_file.stat().st_size
        info = ChunkInfo(
            user_id=user_id,
            chat_id=chat_id,
            base_name=base_name,
            part_index=part_idx,
            path=out_file,
            size_bytes=size,
        )

        # Hand over this chunk to uploader
        await queue.put(info)
        part_idx += 1

    # Signal uploader loop to finish (None marker)
    await queue.put(None)  # type: ignore[arg-type]


async def _uploader_loop(
    bot: Bot,
    queue: asyncio.Queue,
    progress_cb: Optional[Callable[[ChunkInfo, str], Any]] = None,
) -> None:
    """
    Loop that takes chunks from queue, uploads them, and deletes them.
    """
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        info: ChunkInfo = item
        try:
            await _upload_chunk_to_telegram(bot, info, progress_cb)
        finally:
            queue.task_done()


# =========================
# Public pipeline starter
# =========================

async def start_chunked_pipeline(
    user_id: int,
    chat_id: int,
    bot: Bot,
    link: str,
    base_name: str,
    out_dir: Path,
    progress_cb: Optional[Callable[[ChunkInfo, str], Any]] = None,
    max_parts: Optional[int] = None,
) -> None:
    """
    Start the full pipeline for a user:

      recorder_loop -> produces chunks -> queue
      uploader_loop -> uploads chunks -> deletes them

    This function returns when:
      - stop is requested via request_stop(user_id), or
      - ffmpeg fails/stream ends, or
      - max_parts is reached (if set).
    """
    # Reset/ensure stop flag
    stop_event = _get_stop_event(user_id)
    stop_event.clear()

    # Small bounded queue to keep disk usage under control
    queue: asyncio.Queue = asyncio.Queue(maxsize=3)

    await asyncio.gather(
        _recorder_loop(
            user_id=user_id,
            chat_id=chat_id,
            bot=bot,
            link=link,
            base_name=base_name,
            out_dir=out_dir,
            queue=queue,
            progress_cb=progress_cb,
            max_parts=max_parts,
        ),
        _uploader_loop(
            bot=bot,
            queue=queue,
            progress_cb=progress_cb,
        ),
    )

    # Cleanup stop flag
    _stop_flags.pop(user_id, None)