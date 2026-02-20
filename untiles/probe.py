# bot/utils/probe.py

"""
Stream probing utilities.

Uses ffprobe (comes with ffmpeg) to inspect a stream URL
(HLS / M3U8 or any ffmpeg-compatible input) and extract:

- Video qualities (height/width -> e.g. "1080p", "720p")
- Audio tracks (language / name)
- Stream indices (for -map in ffmpeg)

Public API:

    @dataclass
    class QualityInfo:
        id: str           # e.g. "1080p"
        label: str        # e.g. "1080p (H.264)"
        stream_index: int # ffmpeg stream index

    @dataclass
    class AudioTrackInfo:
        id: str           # e.g. "eng", "hin"
        label: str        # e.g. "English", "Hindi"
        stream_index: int # ffmpeg stream index

    @dataclass
    class ProbeResult:
        url: str
        qualities: list[QualityInfo]
        audios: list[AudioTrackInfo]

    async def probe_stream(url: str, timeout: int = 15) -> ProbeResult

Requirements:
- ffprobe must be in PATH (comes with ffmpeg).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class QualityInfo:
    id: str
    label: str
    stream_index: int
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None


@dataclass
class AudioTrackInfo:
    id: str
    label: str
    stream_index: int
    language: Optional[str] = None
    codec: Optional[str] = None


@dataclass
class ProbeResult:
    url: str
    qualities: List[QualityInfo] = field(default_factory=list)
    audios: List[AudioTrackInfo] = field(default_factory=list)


# =========================
# Internal helpers
# =========================

def _lang_id_from_tags(tags: dict) -> str:
    """
    Derive a language id from ffprobe tags (language, language_eng, etc.).
    Fallback to 'und' (undefined).
    """
    if not tags:
        return "und"

    lang = (
        tags.get("language")
        or tags.get("LANGUAGE")
        or tags.get("language_eng")
        or tags.get("lang")
        or tags.get("LANG")
    )
    if not lang:
        return "und"

    lang = str(lang).strip().lower()
    # Normalize some common ones
    if lang in ("eng", "en-us", "en-gb", "english"):
        return "eng"
    if lang in ("hin", "hi", "hindi"):
        return "hin"
    if lang in ("tam", "ta", "tamil"):
        return "tam"
    if lang in ("ben", "bn", "bengali"):
        return "ben"
    if lang in ("urd", "ur", "urdu"):
        return "urd"
    if len(lang) > 5:
        # Too long; keep a short id
        return lang[:5]
    return lang


def _lang_label_from_tags(tags: dict, lang_id: str) -> str:
    """
    Human-friendly label for audio track, based on tags and lang_id.
    """
    if not tags:
        # simple title for unknown
        if lang_id == "und":
            return "Unknown / Default"
        return lang_id.upper()

    title = tags.get("title") or tags.get("TITLE")
    if title:
        return f"{title} ({lang_id.upper()})"

    if lang_id == "eng":
        return "English"
    if lang_id == "hin":
        return "Hindi"
    if lang_id == "tam":
        return "Tamil"
    if lang_id == "ben":
        return "Bengali"
    if lang_id == "urd":
        return "Urdu"

    return lang_id.upper()


def _quality_id_from_wh(w: Optional[int], h: Optional[int]) -> str:
    """
    Generate quality id from width/height, prefer height like '1080p'.
    """
    if h:
        return f"{h}p"
    if w:
        return f"{w}w"
    return "auto"


def _quality_label(w: Optional[int], h: Optional[int], codec: Optional[str]) -> str:
    """
    Human label for video quality, e.g. "1080p (H.264)".
    """
    base = None
    if h and w:
        base = f"{h}p ({w}x{h})"
    elif h:
        base = f"{h}p"
    elif w:
        base = f"{w}w"
    else:
        base = "Auto"

    if codec:
        return f"{base} [{codec}]"
    return base


# =========================
# Main probe function
# =========================

async def probe_stream(url: str, timeout: int = 15) -> ProbeResult:
    """
    Probe the given URL using ffprobe and parse out video qualities
    and audio tracks.

    Returns a ProbeResult. If probe fails, fields may be empty.
    """
    # ffprobe command to get streams in JSON
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-i", url,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ProbeResult(url=url, qualities=[], audios=[])

    except FileNotFoundError:
        # ffprobe missing
        return ProbeResult(url=url, qualities=[], audios=[])
    except Exception:
        return ProbeResult(url=url, qualities=[], audios=[])

    if not stdout:
        # Something went wrong or unsupported URL
        return ProbeResult(url=url, qualities=[], audios=[])

    try:
        info = json.loads(stdout.decode("utf-8", errors="ignore"))
    except Exception:
        return ProbeResult(url=url, qualities=[], audios=[])

    streams = info.get("streams") or []

    qualities: List[QualityInfo] = []
    audios: List[AudioTrackInfo] = []

    # Track seen quality ids and audio ids to avoid duplicates
    seen_q_ids = set()
    seen_a_ids = set()

    for s in streams:
        idx = s.get("index")
        codec_type = s.get("codec_type")

        if codec_type == "video":
            width = s.get("width")
            height = s.get("height")
            codec = s.get("codec_name")

            qid = _quality_id_from_wh(width, height)
            if qid in seen_q_ids:
                continue

            seen_q_ids.add(qid)

            qualities.append(
                QualityInfo(
                    id=qid,
                    label=_quality_label(width, height, codec),
                    stream_index=int(idx),
                    width=width,
                    height=height,
                    codec=codec,
                )
            )

        elif codec_type == "audio":
            tags = s.get("tags") or {}
            codec = s.get("codec_name")

            lang_id = _lang_id_from_tags(tags)
            if lang_id in seen_a_ids:
                # Might have multiple streams with same lang; keep first
                continue

            seen_a_ids.add(lang_id)

            audios.append(
                AudioTrackInfo(
                    id=lang_id,
                    label=_lang_label_from_tags(tags, lang_id),
                    stream_index=int(idx),
                    language=lang_id,
                    codec=codec,
                )
            )

    # Sort qualities by height descending if possible
    def _q_sort_key(q: QualityInfo):
        return q.height or 0

    qualities.sort(key=_q_sort_key, reverse=True)

    # Keep audios in discovery order (or sort by label)
    audios.sort(key=lambda a: a.label or a.id)

    return ProbeResult(
        url=url,
        qualities=qualities,
        audios=audios,
  )
