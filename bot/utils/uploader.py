# bot/utils/uploader.py

"""
Uploader utilities (MEGA backend).

This module is responsible for taking finished recording parts
(e.g. from utils.ffmpeg_runner) and pushing them to MEGA.nz using
MEGAcmd (mega-login, mega-put, mega-export).

Environment variables expected:

    MEGA_EMAIL
    MEGA_PASS
    MEGA_FOLDER   (optional, default: /Root/Recordings)

Public API:

    @dataclass
    class UploadResult:
        user_id: int
        base_name: str
        parts: list[Path]
        total_bytes: int
        remote_folder: str
        remote_folder_link: str | None

    async def upload_parts_to_mega(
        user_id: int,
        base_name: str,
        parts: list[Path],
        remote_folder: str | None = None,
        progress_callback: callable | None = None,
        error_callback: callable | None = None,
    ) -> UploadResult

Callbacks:

    progress_callback(
        user_id: int,
        base_name: str,
        part_index: int,         # 1-based
        total_parts: int,
        filename: str,
        stage: str,              # "start" or "end"
        percent: int,            # 0 or 100 for coarse progress
    )

    error_callback(
        user_id: int,
        base_name: str,
        message: str,
    )
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Any, Tuple


# ==========
# Config
# ==========

MEGA_EMAIL: Optional[str] = os.getenv("MEGA_EMAIL")
MEGA_PASS: Optional[str] = os.getenv("MEGA_PASS")
MEGA_DEFAULT_FOLDER: str = os.getenv("MEGA_FOLDER", "/Root/Recordings")


@dataclass
class UploadResult:
    user_id: int
    base_name: str
    parts: List[Path]
    total_bytes: int
    remote_folder: str
    remote_folder_link: Optional[str] = None  # Exported public link (if created)


# ==========
# Internal helpers
# ==========

async def _maybe_await(cb: Optional[Callable[..., Any]], *args, **kwargs):
    """
    Call callback that may be sync or async.
    """
    if cb is None:
        return
    result = cb(*args, **kwargs)
    if asyncio.iscoroutine(result):
        await result


async def _run_cmd(*cmd: str, timeout: Optional[int] = None) -> int:
    """
    Run a shell command asynchronously and return its exit code (stdout ignored).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        # Command not found
        return 127
    except Exception:
        return 1

    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124

    return proc.returncode


async def _run_cmd_capture(*cmd: str, timeout: Optional[int] = None) -> Tuple[int, str]:
    """
    Run a shell command asynchronously and return (exit_code, stdout_text).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return 127, ""
    except Exception:
        return 1, ""

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, ""

    text = stdout.decode("utf-8", errors="ignore") if stdout else ""
    return proc.returncode, text


async def mega_login() -> bool:
    """
    Ensure we are logged in to MEGA.

    Returns True if login is confirmed, False otherwise.
    """
    # First check if already logged in
    code = await _run_cmd("mega-whoami", timeout=5)
    if code == 0:
        return True

    # Need credentials
    if not MEGA_EMAIL or not MEGA_PASS:
        return False

    # Try login
    code = await _run_cmd("mega-login", MEGA_EMAIL, MEGA_PASS, timeout=20)
    if code != 0:
        return False

    # Confirm
    code = await _run_cmd("mega-whoami", timeout=5)
    return code == 0


async def _mega_mkdir(remote_folder: str) -> None:
    """
    Ensure remote folder exists (best-effort).
    """
    await _run_cmd("mega-mkdir", "-p", remote_folder, timeout=20)


async def _mega_put(local_path: Path, remote_folder: str) -> bool:
    """
    Upload one file to MEGA folder using mega-put.

    Returns True if success.
    """
    # MEGAcmd: mega-put /local/path /Remote/Folder/
    code = await _run_cmd("mega-put", str(local_path), remote_folder, timeout=None)
    return code == 0


async def _mega_export_folder(remote_folder: str) -> Optional[str]:
    """
    Create or fetch a public link for a MEGA folder using MEGAcmd.

    Returns the link as string, or None on failure.

    Command used:
        mega-export -a <folder>

    Output usually contains 'https://mega.nz/...' – we parse that.
    """
    code, out = await _run_cmd_capture("mega-export", "-a", remote_folder, timeout=30)
    if code != 0 or not out:
        return None

    for line in out.splitlines():
        line = line.strip()
        if "https://mega.nz" in line:
            parts = line.split()
            for part in parts:
                if part.startswith("https://mega.nz"):
                    return part
    return None


# ==========
# Public API
# ==========

async def upload_parts_to_mega(
    user_id: int,
    base_name: str,
    parts: List[Path],
    remote_folder: Optional[str] = None,
    progress_callback: Optional[Callable[..., Any]] = None,
    error_callback: Optional[Callable[..., Any]] = None,
) -> UploadResult:
    """
    Upload given parts to MEGA.nz sequentially.

    Parameters
    ----------
    user_id : int
        Telegram user id (for logging / callbacks).
    base_name : str
        Base logical name of the recording (e.g. filename without part index).
    parts : list[Path]
        Paths to local .mkv files (segments) to upload.
    remote_folder : str | None
        Remote MEGA folder where to upload.
        If None, uses MEGA_DEFAULT_FOLDER/base_name.
        Typical pattern:
            /Root/Recordings/{base_name}
    progress_callback : callable | None
        progress_callback(
            user_id,
            base_name,
            part_index,
            total_parts,
            filename,
            stage,      # "start" or "end"
            percent,    # 0 or 100
        )
    error_callback : callable | None
        error_callback(
            user_id,
            base_name,
            message,
        )

    Returns
    -------
    UploadResult

    Notes
    -----
    - This does NOT delete local files; caller decides.
    - This does NOT send Telegram documents; it just manages MEGA upload.
      Telegram sending should be handled elsewhere using these parts.
    """

    # Filter existing parts
    clean_parts = [p for p in parts if p.exists()]
    total_parts = len(clean_parts)
    total_bytes = sum(p.stat().st_size for p in clean_parts)

    # Determine remote folder for this recording
    if remote_folder:
        remote_base = remote_folder
    else:
        # Default: /Root/Recordings/<base_name>
        remote_base = f"{MEGA_DEFAULT_FOLDER.rstrip('/')}/{base_name}"

    # Ensure MEGA login
    logged_in = await mega_login()
    if not logged_in:
        await _maybe_await(
            error_callback,
            user_id,
            base_name,
            "MEGA login failed. Check MEGA_EMAIL/MEGA_PASS or MEGAcmd installation.",
        )
        return UploadResult(
            user_id=user_id,
            base_name=base_name,
            parts=[],
            total_bytes=0,
            remote_folder=remote_base,
            remote_folder_link=None,
        )

    # Ensure remote folder exists
    await _mega_mkdir(remote_base)

    # Upload parts sequentially
    current_index = 0
    for part in clean_parts:
        current_index += 1
        filename = part.name

        # Notify start
        await _maybe_await(
            progress_callback,
            user_id,
            base_name,
            current_index,
            total_parts,
            filename,
            "start",
            0,
        )

        ok = await _mega_put(part, remote_base)
        if not ok:
            await _maybe_await(
                error_callback,
                user_id,
                base_name,
                f"Failed to upload part: {filename}",
            )
            # You can choose to continue or stop here; safer to stop
            break

        # Notify end
        await _maybe_await(
            progress_callback,
            user_id,
            base_name,
            current_index,
            total_parts,
            filename,
            "end",
            100,
        )

    # Compute final stats with what was actually processed
    uploaded_parts = [p for p in clean_parts if p.exists()]  # still local, but logically uploaded
    uploaded_bytes = sum(p.stat().st_size for p in uploaded_parts)

    # Create or fetch a public link for this folder (optional)
    folder_link = await _mega_export_folder(remote_base)

    return UploadResult(
        user_id=user_id,
        base_name=base_name,
        parts=uploaded_parts,
        total_bytes=uploaded_bytes,
        remote_folder=remote_base,
        remote_folder_link=folder_link,
    )