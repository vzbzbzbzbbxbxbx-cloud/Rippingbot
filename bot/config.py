# bot/config.py

"""
Global configuration for the Telegram Live Stream Recording Bot.

- Tokens / IDs
- Role limits (owner/admin/normal)
- Trial system
- Themes
- Paths (downloads, logs, database)
- Global concurrency caps
- Optional MongoDB configuration
"""

import os
from pathlib import Path

# ==========
# BOT & ROLES
# ==========

# You *must* set BOT_TOKEN via environment or hardcode it here (not recommended).
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "CHANGE_ME_TELEGRAM_BOT_TOKEN")

# Main owner / super admin (full power, but still max 2 concurrent recordings)
OWNER_ID: int = int(os.getenv("OWNER_ID", "123456789"))

# Additional static admins (comma-separated env, e.g. "111,222,333")
_admin_ids_env = os.getenv("ADMIN_IDS", "")
if _admin_ids_env.strip():
    ADMIN_IDS = [int(x) for x in _admin_ids_env.split(",") if x.strip().isdigit()]
else:
    ADMIN_IDS = []  # you can hardcode like [111111111, 222222222]

# Channel / group where logs and final summaries will be sent
LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "-1001234567890"))

# ==========
# THEMES
# ==========

# Available themes: "hot", "cold", "dark"
THEMES = ("hot", "cold", "dark")

# Default theme for new users
DEFAULT_THEME: str = os.getenv("DEFAULT_THEME", "cold").lower()
if DEFAULT_THEME not in THEMES:
    DEFAULT_THEME = "cold"

# ==========
# LIMITS & TRIALS
# ==========

# Per-role daily limits (in hours) and max concurrent recordings per user
# NOTE: Owner has unlimited hours but still limited concurrent sessions.
LIMITS = {
    "owner": {"hours": None, "max_concurrent": 2},
    "admin": {"hours": 8, "max_concurrent": 2},
    "normal": {"hours": 4, "max_concurrent": 2},
}

# Trial system (for users who hit limit or new users)
TRIALS = {
    "enabled": True,
    "max_trial_per_user": 5,
}

# Daily reset time (24h format)
DAILY_RESET_HOUR: int = 23
DAILY_RESET_MINUTE: int = 59

# Timezone string for daily reset (used by JobQueue)
# Default to your real TZ: Asia/Dhaka
DAILY_RESET_TZ: str = os.getenv("DAILY_RESET_TZ", "Asia/Dhaka")

# ==========
# GLOBAL CONCURRENCY
# ==========

# Hard cap: maximum number of **simultaneous recordings for the entire bot**
# (all users combined). Spec says: "Max 2 recordings at the same time per bot".
GLOBAL_MAX_CONCURRENT_RECORDINGS: int = 2

# ==========
# PATHS & DIRECTORIES (for JSON-based storage and local files)
# ==========

BASE_DIR = Path(__file__).resolve().parent

DOWNLOADS_DIR = BASE_DIR / "downloads"
LOGS_DIR = BASE_DIR / "logs"
DATABASE_DIR = BASE_DIR / "database"
USAGE_DIR = DATABASE_DIR / "usage"

# Ensure basic directories exist at import time
for _p in (DOWNLOADS_DIR, LOGS_DIR, DATABASE_DIR, USAGE_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ==========
# RECORDING / UPLOAD SETTINGS
# ==========

# Max Telegram document size in bytes (depends on bot account;
# we assume 2 GB cap for splitting logic).
TELEGRAM_MAX_FILE_SIZE: int = 2 * 1024 * 1024 * 1024  # 2 GiB

# File extension for final uploaded files
OUTPUT_EXTENSION: str = ".mkv"

# How often (seconds) to update progress messages (download/upload)
PROGRESS_UPDATE_INTERVAL: int = 5

# Safety: minimum duration (seconds) a recording must have to be considered valid
MIN_VALID_DURATION_SECONDS: int = 30

# ==========
# MISC / LOGGING
# ==========

# Log file path (you can use it in main.py logging config)
MAIN_LOG_FILE = LOGS_DIR / "bot.log"

# If True, include FFmpeg command in debug logs (but NOT in user messages)
DEBUG_SHOW_FFMPEG_CMD: bool = True

# Arbitrary bot version string (for /start, diagnostics, etc.)
BOT_VERSION: str = "1.0.0"

# ==========
# MONGO DB (optional, for future: usage/admins/bans/playlists in DB)
# ==========

# Turn this ON when you migrate from JSON files to Mongo.
# e.g. USE_MONGO=true
USE_MONGO: bool = os.getenv("USE_MONGO", "false").lower() in ("1", "true", "yes", "on")

# Standard MongoDB connection string
# e.g. mongodb://user:pass@host:27017
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Database name for this bot
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "streamrec_bot")

# Collection names used by future Mongo-based storage
MONGO_COLLECTIONS = {
    "usage": os.getenv("MONGO_COLL_USAGE", "usage"),
    "admins": os.getenv("MONGO_COLL_ADMINS", "admins"),
    "banned": os.getenv("MONGO_COLL_BANNED", "banned"),
    "playlists": os.getenv("MONGO_COLL_PLAYLISTS", "playlists"),
    "sessions": os.getenv("MONGO_COLL_SESSIONS", "sessions"),
}