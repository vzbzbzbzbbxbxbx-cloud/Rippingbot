# bot/ui.py

"""
UI / Theme system.

Three themes:
    - hot  : savage / trolling / funny
    - cold : professional / clean
    - dark : underground / operator vibe

Each theme implements a common interface:

    system_diagnostic(user, active_recordings, disk, network) -> str
    error(text) -> str
    info(text) -> str
    recording_start(link, quality, audio) -> str
    download_progress(filename, percent, speed_mbps) -> str
    upload_progress(filename, percent, speed_mbps) -> str
    status_display(rec_list, role, daily_used_hours, daily_limit_hours) -> str
    generate_bar(percent, total_blocks=10) -> str

`rec_list` is expected to be a list of dicts like:
    {
        "id": 1,
        "name": "streamer or title",
        "quality": "1080p",
        "bitrate_mbps": 8.2,
        "elapsed_str": "01:20:11",
        "percent": 60.0,    # 0-100 or None if unknown
    }

`disk` can be:
    {"total_gb": 500, "free_gb": 420}
`network` can be:
    {"latency_ms": 12, "status": "Optimal"}

Theme-specific copy lines are mostly delegated to messages.get_reply().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import BOT_VERSION
from . import messages


# ============================
# Base Utilities
# ============================

def _user_display(user: Any) -> str:
    """
    Resolve a display string for a Telegram user object or similar.
    Accepts anything that has .username or .id.
    """
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    uid = getattr(user, "id", None)
    if uid is not None:
        return f"ID:{uid}"
    return "UNKNOWN_USER"


def _safe_percent(p: Optional[float]) -> float:
    if p is None:
        return 0.0
    try:
        return max(0.0, min(100.0, float(p)))
    except Exception:
        return 0.0


def _fmt_hours(hours: Optional[float]) -> str:
    if hours is None:
        return "∞"
    return f"{hours:.2f}h"


def _fmt_role(role: str) -> str:
    r = role.lower()
    if r == "owner":
        return "Owner"
    if r == "admin":
        return "Admin"
    return "User"


# ============================
# Base Theme
# ============================

@dataclass
class BaseTheme:
    name: str  # "hot", "cold", "dark"

    # ---- Generic helpers ----

    def generate_bar(self, percent: float, total_blocks: int = 10) -> str:
        """
        Simple unicode progress bar.
        [██████░░░░] 60%
        """
        p = _safe_percent(percent)
        blocks = max(1, total_blocks)
        filled = int(round((p / 100.0) * blocks))
        empty = blocks - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {int(p)}%"

    # ---- High-level UI elements ----

    def system_diagnostic(
        self,
        user: Any,
        active_recordings: int,
        disk: Dict[str, Any],
        network: Dict[str, Any],
    ) -> str:
        """
        Themed system diagnostic for /start.
        Delegates to messages.get_reply(theme, "system_start", ...)
        """
        user_disp = _user_display(user)
        total_gb = disk.get("total_gb")
        free_gb = disk.get("free_gb")
        latency = network.get("latency_ms")
        net_status = network.get("status", "Unknown")

        return messages.get_reply(
            self.name,
            "system_start",
            user=user_disp,
            active=active_recordings,
            total_gb=total_gb,
            free_gb=free_gb,
            latency=latency,
            net_status=net_status,
            version=BOT_VERSION,
        )

    def error(self, text: str) -> str:
        """
        Theme-flavored error wrapper.
        """
        return messages.get_reply(
            self.name,
            "error",
            text=text,
        )

    def info(self, text: str) -> str:
        """
        Theme-flavored info wrapper.
        """
        return messages.get_reply(
            self.name,
            "info",
            text=text,
        )

    def recording_start(self, link: str, quality: str, audio: str) -> str:
        """
        Theme-flavored recording start message.
        """
        return messages.get_reply(
            self.name,
            "record_start",
            link=link,
            quality=quality,
            audio=audio,
        )

    def download_progress(
        self,
        filename: str,
        percent: Optional[float],
        speed_mbps: Optional[float],
    ) -> str:
        """
        Themed download progress string, using progress bar.
        """
        bar = self.generate_bar(percent or 0.0, total_blocks=10)
        speed = f"{speed_mbps:.2f} Mbps" if speed_mbps is not None else "N/A"
        return messages.get_reply(
            self.name,
            "download_progress",
            filename=filename,
            bar=bar,
            percent=int(_safe_percent(percent)),
            speed=speed,
        )

    def upload_progress(
        self,
        filename: str,
        percent: Optional[float],
        speed_mbps: Optional[float],
    ) -> str:
        """
        Themed upload progress string, using progress bar.
        """
        bar = self.generate_bar(percent or 0.0, total_blocks=10)
        speed = f"{speed_mbps:.2f} Mbps" if speed_mbps is not None else "N/A"
        return messages.get_reply(
            self.name,
            "upload_progress",
            filename=filename,
            bar=bar,
            percent=int(_safe_percent(percent)),
            speed=speed,
        )

    def status_display(
        self,
        rec_list: List[Dict[str, Any]],
        role: str,
        daily_used_hours: float,
        daily_limit_hours: Optional[float],
    ) -> str:
        """
        CLI-style table + daily limit info.
        """
        lines: List[str] = []

        # Header line
        top = messages.get_reply(
            self.name,
            "status_header",
            active=len(rec_list),
            role=_fmt_role(role),
        )
        lines.append(top)

        if rec_list:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("ID  STREAM            QLTY   BITRATE    ELAPSED     PROGRESS")
            lines.append("─────────────────────────────────────")

            for r in rec_list:
                rid = r.get("id")
                name = str(r.get("name", ""))[:14]
                quality = r.get("quality", "N/A")
                br = r.get("bitrate_mbps")
                br_str = f"{br:.1f} Mbps" if br is not None else "N/A"
                elapsed = r.get("elapsed_str", "--:--:--")
                percent = r.get("percent")
                bar = self.generate_bar(percent or 0.0, total_blocks=10)

                lines.append(
                    f"{rid:02d}  {name:<14}  {quality:<6} {br_str:<9} {elapsed:<10} {bar}"
                )

            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        else:
            lines.append("No active recordings.")

        # Daily limit section
        used = daily_used_hours
        limit = daily_limit_hours
        remaining = None
        if limit is None:
            remaining_str = "∞"
        else:
            remaining = max(0.0, limit - used)
            remaining_str = f"{remaining:.2f}h"

        lines.append(
            messages.get_reply(
                self.name,
                "status_limit",
                role=_fmt_role(role),
                used=f"{used:.2f}h",
                limit=_fmt_hours(limit),
                remaining=remaining_str,
            )
        )

        return "\n".join(lines)


# ============================
# Individual Themes
# ============================

class HotTheme(BaseTheme):
    """
    Savage / trolling / funny.
    Mostly relies on messages.get_reply() for flavor,
    but we could override some behavior if needed.
    """
    def __init__(self) -> None:
        super().__init__(name="hot")


class ColdTheme(BaseTheme):
    """
    Professional / clean / friendly.
    """
    def __init__(self) -> None:
        super().__init__(name="cold")


class DarkTheme(BaseTheme):
    """
    Underground / operator vibe / slightly edgy but safe.
    """
    def __init__(self) -> None:
        super().__init__(name="dark")


# ============================
# Theme Registry / Access
# ============================

_THEME_INSTANCES: Dict[str, BaseTheme] = {
    "hot": HotTheme(),
    "cold": ColdTheme(),
    "dark": DarkTheme(),
}


def get_theme(theme_name: str) -> BaseTheme:
    """
    Get a theme instance by name. Falls back to 'cold' if unknown.
    """
    key = (theme_name or "").lower()
    return _THEME_INSTANCES.get(key, _THEME_INSTANCES["cold"])