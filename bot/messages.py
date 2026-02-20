# bot/messages.py

"""
Message templates and theme-based replies.

Themes:
    - hot  : Trolling / savage / funny
    - cold : Professional / clean
    - dark : Underground / operator vibe

Categories (used by various modules):
    - system_start
    - record_start
    - record_stop
    - limit_exceeded
    - trial_start
    - trial_end
    - error
    - info
    - status_header
    - status_limit
    - status              # generic status if needed
    - download_progress
    - upload_progress

Templates are simple .format(**kwargs) strings.
Use get_reply(theme, category, **kwargs) to get the final text.
"""

from __future__ import annotations

import random
from typing import Dict, List


# =========================
# TEMPLATE DATA
# =========================

# NOTE: You can expand this with more variants anytime.
# Just keep placeholders consistent with what ui.py / other modules pass in.

_REPLIES: Dict[str, Dict[str, List[str]]] = {
    "hot": {
        # --- System Start / Diagnostic ---
        "system_start": [
            (
                "🔥 YO! SYSTEM BOOTED 🔥\n"
                "USER: {user} | ACTIVE RECORDINGS: {active}\n"
                "DISK: {free_gb} GB free / {total_gb} GB total\n"
                "NET: {net_status} ({latency}ms)\n"
                "ENGINE: v{version}\n"
                "Ready to wreck some streams 😎"
            ),
            (
                "🚀 LAUNCH COMPLETE\n"
                "USER: {user}\n"
                "ACTIVE SESSIONS: {active}\n"
                "STORAGE: {free_gb}GB / {total_gb}GB\n"
                "LINK: {net_status} [{latency}ms]\n"
                "Version {version} locked & loaded."
            ),
        ],

        # --- Recording Start / Stop ---
        "record_start": [
            (
                "🎬 RECORDING STARTED\n"
                "TARGET: {link}\n"
                "QUALITY: {quality}\n"
                "AUDIO: {audio}\n"
                "If this fails, blame your WiFi, not me 😏"
            ),
            (
                "📡 CAPTURE ONLINE\n"
                "LINK: {link}\n"
                "QLTY: {quality} | AUDIO: {audio}\n"
                "Sit back, your content farm just got an upgrade 🔥"
            ),
        ],
        "record_stop": [
            (
                "🧯 RECORDING STOPPED\n"
                "FILE: {filename}\n"
                "DURATION: {duration}\n"
                "Try not to cry when you rewatch it 🥲"
            ),
            (
                "⏹ SESSION TERMINATED\n"
                "OUTPUT: {filename}\n"
                "LENGTH: {duration}\n"
                "Another one for the vault 📦"
            ),
        ],

        # --- Limits / Trials ---
        "limit_exceeded": [
            (
                "🛑 Daily limit exceeded ({limit_hours}h).\n"
                "Used: {used_hours}h.\n"
                "Apne Aukat mai raha karo 😒"
            ),
            (
                "📉 Your watch-time wallet is EMPTY.\n"
                "Limit: {limit_hours}h | Used: {used_hours}h\n"
                "Either touch some grass or contact owner. 🌿"
            ),
        ],
        "trial_start": [
            (
                "🎟 TRIAL MODE ACTIVATED\n"
                "You just burned trial #{trial_number} out of {trial_max}.\n"
                "Don't waste it on cringe streams 😑"
            ),
            (
                "🧪 Trial granted.\n"
                "Slot {trial_number}/{trial_max} consumed.\n"
                "Make this one worth it, hero."
            ),
        ],
        "trial_end": [
            (
                "⏳ Trial session finished.\n"
                "If you want more, convince the owner. Or send pizza. 🍕"
            ),
            (
                "TRIAL_OVER: That’s all you get for free.\n"
                "Upgrade your life, not just your bitrate."
            ),
        ],

        # --- Errors / Info ---
        "error": [
            "❌ Bruh. {text}",
            "💥 Error: {text}",
            "⚠️ System choked: {text}",
        ],
        "info": [
            "ℹ️ {text}",
            "✅ INFO: {text}",
        ],

        # --- Status (used by ui.status_display) ---
        "status_header": [
            "🟢 SYSTEM: ONLINE     🎥 ACTIVE: {active}  | ROLE: {role}",
            "📊 STATUS PANEL  | ACTIVE SESSIONS: {active} | ROLE: {role}",
        ],
        "status_limit": [
            (
                "🎟 DAILY LIMIT\n"
                "Role: {role}\n"
                "Used Today: {used} / {limit}\n"
                "Remaining: {remaining}\n"
                "Try not to speedrun your limit next time 😏"
            ),
            (
                "⏱ QUOTA\n"
                "Role: {role}\n"
                "Usage: {used} / {limit}\n"
                "Left: {remaining}\n"
                "Math is math. No more freebies if it hits 0."
            ),
        ],
        "status": [
            "📡 STATUS_CHECK | Active: {active} | Role: {role}",
        ],

        # --- Progress (download / upload) ---
        "download_progress": [
            (
                "📥 DOWNLOADING\n"
                "{filename}\n"
                "{bar}\n"
                "Speed: {speed}"
            ),
            (
                "⬇️ Ingesting: {filename}\n"
                "{bar}\n"
                "Pipe speed: {speed}"
            ),
        ],
        "upload_progress": [
            (
                "📤 UPLOADING\n"
                "{filename}\n"
                "{bar}\n"
                "Speed: {speed}"
            ),
            (
                "🚀 Launching to Telegram: {filename}\n"
                "{bar}\n"
                "Uplink: {speed}"
            ),
        ],
    },

    # =========================
    # COLD THEME
    # =========================
    "cold": {
        "system_start": [
            (
                "❄️ SYSTEM_COLD [v{version}]\n"
                "USER: {user}\n"
                "ACTIVE RECORDINGS: {active}\n"
                "DISK: {free_gb} GB free / {total_gb} GB total\n"
                "NETWORK: {net_status} ({latency}ms)\n"
                "Ready for ingest."
            ),
            (
                "SYSTEM_COLD_INIT\n"
                "User: {user}\n"
                "Sessions: {active}\n"
                "Disk Free: {free_gb}GB\n"
                "Net: {net_status} ({latency}ms)\n"
                "Version: {version}"
            ),
        ],
        "record_start": [
            (
                "🎬 Recording initialized.\n"
                "Source: {link}\n"
                "Quality: {quality}\n"
                "Audio: {audio}\n"
                "Mode: Direct copy (no re-encode)."
            ),
            (
                "CAPTURE_STARTED\n"
                "Link: {link}\n"
                "Quality: {quality}\n"
                "Audio: {audio}\n"
                "Pipeline: Stable."
            ),
        ],
        "record_stop": [
            (
                "⏹ Recording stopped.\n"
                "File: {filename}\n"
                "Duration: {duration}\n"
                "Session closed cleanly."
            ),
            (
                "CAPTURE_COMPLETE\n"
                "Output: {filename}\n"
                "Length: {duration}"
            ),
        ],
        "limit_exceeded": [
            (
                "Daily limit exceeded.\n"
                "Limit: {limit_hours}h | Used: {used_hours}h\n"
                "Please contact the owner if you need more."
            ),
            (
                "Usage cap reached for today.\n"
                "Allowed: {limit_hours}h\n"
                "Current: {used_hours}h"
            ),
        ],
        "trial_start": [
            (
                "Trial session granted.\n"
                "This is trial {trial_number}/{trial_max}.\n"
                "Use it wisely."
            ),
            (
                "Trial mode active.\n"
                "Slot: {trial_number}/{trial_max}."
            ),
        ],
        "trial_end": [
            (
                "Trial session completed.\n"
                "We hope it was useful."
            ),
            (
                "Trial has ended.\n"
                "You can request another if available."
            ),
        ],
        "error": [
            "An error occurred: {text}",
            "Operation failed: {text}",
            "Unexpected error: {text}",
        ],
        "info": [
            "{text}",
            "INFO: {text}",
        ],
        "status_header": [
            "🟢 SYSTEM: ONLINE     🎥 ACTIVE: {active}  | ROLE: {role}",
            "STATUS: OK | Active sessions: {active} | Role: {role}",
        ],
        "status_limit": [
            (
                "🎟 DAILY LIMIT\n"
                "Role: {role}\n"
                "Used Today: {used} / {limit}\n"
                "Remaining: {remaining}"
            ),
            (
                "QUOTA\n"
                "Role: {role}\n"
                "Usage: {used} / {limit}\n"
                "Left: {remaining}"
            ),
        ],
        "status": [
            "STATUS_CHECK\nActive: {active}\nRole: {role}",
        ],
        "download_progress": [
            (
                "📥 Downloading {filename}\n"
                "{bar}\n"
                "Speed: {speed}"
            ),
            (
                "Ingest: {filename}\n"
                "{bar}\n"
                "Throughput: {speed}"
            ),
        ],
        "upload_progress": [
            (
                "📤 Uploading {filename}\n"
                "{bar}\n"
                "Speed: {speed}"
            ),
            (
                "Delivery: {filename}\n"
                "{bar}\n"
                "Uplink: {speed}"
            ),
        ],
    },

    # =========================
    # DARK THEME
    # =========================
    "dark": {
        "system_start": [
            (
                "🏴‍☠️ SESSION_ANONYMOUS\n"
                "USER: {user}\n"
                "SVS: DARK_RECON_V{version}\n"
                "ACTIVE OPS: {active}\n"
                "DISK: {free_gb}GB free / {total_gb}GB total\n"
                "NET: {net_status} | PING: {latency}ms\n"
                "Awaiting target manifest..."
            ),
            (
                "BLACKBOX ONLINE\n"
                "Handle: {user}\n"
                "Ops in progress: {active}\n"
                "Storage window: {free_gb}GB free\n"
                "Line status: {net_status} ({latency}ms)\n"
                "Protocol v{version}."
            ),
        ],
        "record_start": [
            (
                "🎥 OP_START\n"
                "Target: {link}\n"
                "Profile: {quality} / {audio}\n"
                "Codec: COPY_ONLY\n"
                "All packets will be archived. No questions asked."
            ),
            (
                "CAPTURE_CHAIN ARMED\n"
                "Stream: {link}\n"
                "Quality: {quality}\n"
                "Audio: {audio}\n"
                "You pull the trigger, I log the footage."
            ),
        ],
        "record_stop": [
            (
                "🕳 OP_TERMINATED\n"
                "Artifact: {filename}\n"
                "Timeline: {duration}\n"
                "Vault updated."
            ),
            (
                "SESSION_CLOSED\n"
                "File: {filename}\n"
                "Duration: {duration}\n"
                "Trail preserved."
            ),
        ],
        "limit_exceeded": [
            (
                "🔒 ACCESS DENIED\n"
                "Your daily window is spent.\n"
                "Limit: {limit_hours}h | Used: {used_hours}h\n"
                "Request override from handler."
            ),
            (
                "QUOTA LOCKED\n"
                "You've hit the daily ceiling.\n"
                "Allowed: {limit_hours}h | Used: {used_hours}h"
            ),
        ],
        "trial_start": [
            (
                "🧪 FIELD_TRIAL ENABLED\n"
                "Token {trial_number}/{trial_max} burned.\n"
                "Use the time. The system never forgets."
            ),
            (
                "TRIAL AUTHORIZED\n"
                "Slot: {trial_number}/{trial_max}\n"
                "Surveillance channel open."
            ),
        ],
        "trial_end": [
            (
                "TRIAL WINDOW CLOSED.\n"
                "If you want more time, you know who to ask."
            ),
            (
                "EXPERIMENT COMPLETE.\n"
                "Footage stored. Access pending orders."
            ),
        ],
        "error": [
            "❌ OP_FAIL: {text}",
            "SYSTEM_GLITCH: {text}",
            "RED FLAG: {text}",
        ],
        "info": [
            "ℹ️ {text}",
            "SYS_NOTE: {text}",
        ],
        "status_header": [
            "🟢 NODE: ONLINE     🎥 ACTIVE OPS: {active}  | ROLE: {role}",
            "RECON_STATUS | Ops: {active} | Role: {role}",
        ],
        "status_limit": [
            (
                "🎟 QUOTA WINDOW\n"
                "Role: {role}\n"
                "Logged Today: {used} / {limit}\n"
                "Buffer Left: {remaining}"
            ),
            (
                "USAGE_REPORT\n"
                "Actor: {role}\n"
                "Time used: {used} / {limit}\n"
                "Margin: {remaining}"
            ),
        ],
        "status": [
            "NODE_STATUS\nOps: {active}\nRole: {role}",
        ],
        "download_progress": [
            (
                "📥 LINK_TAP: {filename}\n"
                "{bar}\n"
                "Line rate: {speed}"
            ),
            (
                "INGEST_PIPE ACTIVE\n"
                "{filename}\n"
                "{bar}\n"
                "Flow: {speed}"
            ),
        ],
        "upload_progress": [
            (
                "📤 ARCHIVE_UPLINK: {filename}\n"
                "{bar}\n"
                "Rate: {speed}"
            ),
            (
                "VAULT_UPDATE\n"
                "{filename}\n"
                "{bar}\n"
                "Uplink: {speed}"
            ),
        ],
    },
}


# Default theme to fall back to if requested theme or category is missing
_FALLBACK_THEME = "cold"


# =========================
# PUBLIC API
# =========================

def get_reply(theme: str, category: str, **kwargs) -> str:
    """
    Get a theme-flavored reply string.

    Parameters
    ----------
    theme : str
        "hot", "cold", or "dark"
    category : str
        One of: system_start, record_start, record_stop, limit_exceeded,
        trial_start, trial_end, error, info, status_header, status_limit,
        status, download_progress, upload_progress
    **kwargs :
        Variables for .format() in the template.

    Returns
    -------
    str : Final formatted message.
    """
    theme = (theme or "").lower().strip()
    if theme not in _REPLIES:
        theme = _FALLBACK_THEME

    theme_dict = _REPLIES.get(theme, {})
    variants = theme_dict.get(category)

    # If category missing in this theme, try fallback theme
    if not variants:
        fallback_dict = _REPLIES.get(_FALLBACK_THEME, {})
        variants = fallback_dict.get(category, None)

    # If still not found, generic behavior
    if not variants:
        # last resort: just echo raw text if provided, or category name
        base = kwargs.get("text", "") or f"[{theme.upper()}:{category}]"
        return str(base)

    template = random.choice(variants)
    try:
        return template.format(**kwargs)
    except Exception:
        # If formatting fails (missing key), just return the template as-is
        return template