# bot/limits.py

"""
Limit & trial system (Ultra Enhanced Edition).

Supports two backends:

1) JSON-files (default)
   - database/usage/{user_id}.json

2) MongoDB (optional)
   - controlled by config.USE_MONGO
   - collection: config.MONGO_COLLECTIONS["usage"]
   - document structure:
        {
          "user_id": <int>,
          "date": "YYYY-MM-DD",
          "used_seconds": <int>,
          "concurrent": <int>,
          "trials_used": <int>
        }

Tracks (per user, per day):
    - date (YYYY-MM-DD)
    - used_seconds
    - concurrent
    - trials_used

Enforces:
    - Per-role daily hour limits
    - Per-role max concurrent recordings
    - Global max concurrent recordings (whole bot)
    - Trial system

Public functions:

    load_user_usage(user_id) -> dict
    save_user_usage(user_id, usage) -> None

    check_limits(user_id, role, trial_requested=False, duration_seconds=0) -> LimitResult
    add_usage(user_id, role, duration_seconds=0, trial=False) -> None
    remove_concurrent(user_id) -> None
    remaining_time(user_id, role) -> int | None
    reset_daily_usage() -> None
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Any

from .config import (
    LIMITS,
    TRIALS,
    USAGE_DIR,
    GLOBAL_MAX_CONCURRENT_RECORDINGS,
    USE_MONGO,
    MONGO_URI,
    MONGO_DB_NAME,
    MONGO_COLLECTIONS,
)

# =====================
# MongoDB (optional)
# =====================

_USE_MONGO_EFFECTIVE = False
_mongo_client = None
_mongo_db = None
_mongo_usage_coll = None

if USE_MONGO:
    try:
        from pymongo import MongoClient, ASCENDING  # type: ignore

        _mongo_client = MongoClient(MONGO_URI, connect=False)
        _mongo_db = _mongo_client[MONGO_DB_NAME]
        _mongo_usage_coll = _mongo_db[MONGO_COLLECTIONS["usage"]]

        # Ensure index on (user_id, date)
        _mongo_usage_coll.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING)],
            unique=True,
        )

        _USE_MONGO_EFFECTIVE = True
    except Exception as e:
        # If Mongo is misconfigured or pymongo missing, fall back to JSON mode
        print(f"[limits] Mongo initialization failed, falling back to JSON mode: {e}")
        _USE_MONGO_EFFECTIVE = False


# =====================
# Data structures
# =====================

@dataclass
class LimitResult:
    """
    Result of a limit check.

    allowed:
        True  -> user can start the recording
        False -> refused, check code to see why

    code:
        "ok"                        -> allowed, no issues
        "daily_limit"               -> hit per-role daily hours cap
        "concurrent_exceeded"       -> user has too many active recordings
        "global_concurrent_exceeded"-> bot-wide concurrent cap reached
        "trial_disabled"            -> trials globally disabled
        "trials_exhausted"          -> user used all trials
        "unknown_role"              -> role not in LIMITS

    trial_granted:
        True if this check is specifically for a trial request and it’s allowed.

    remaining_seconds:
        Remaining seconds for today for this role (None if unlimited or unknown).
    """
    allowed: bool
    code: Optional[str] = None
    trial_granted: bool = False
    remaining_seconds: Optional[int] = None


# =====================
# Helpers (generic)
# =====================

def _usage_file(user_id: int) -> Path:
    return USAGE_DIR / f"{user_id}.json"


def _today_str() -> str:
    return date.today().isoformat()


def _role_limit_hours(role: str) -> Optional[int]:
    """
    Returns max daily hours for this role, or None if unlimited.
    """
    info = LIMITS.get(role)
    if not info:
        return None
    return info.get("hours")


def _role_max_concurrent(role: str) -> Optional[int]:
    info = LIMITS.get(role)
    if not info:
        return None
    return info.get("max_concurrent")


# =====================
# JSON backend
# =====================

def _json_load_user_usage(user_id: int) -> Dict[str, Any]:
    path = _usage_file(user_id)

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    today = _today_str()
    if data.get("date") != today:
        data = {
            "date": today,
            "used_seconds": 0,
            "concurrent": 0,
            "trials_used": 0,
        }
        _json_save_user_usage(user_id, data)
        return data

    data.setdefault("date", today)
    data.setdefault("used_seconds", 0)
    data.setdefault("concurrent", 0)
    data.setdefault("trials_used", 0)

    return data


def _json_save_user_usage(user_id: int, usage: Dict[str, Any]) -> None:
    path = _usage_file(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(usage, f, ensure_ascii=False, indent=2)


def _json_global_concurrent() -> int:
    total = 0
    today = _today_str()
    for file in USAGE_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today:
                total += int(data.get("concurrent", 0))
        except Exception:
            continue
    return total


def _json_reset_daily_usage() -> None:
    today = _today_str()
    for file in USAGE_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        data["date"] = today
        data["used_seconds"] = 0
        data["concurrent"] = 0
        data["trials_used"] = 0

        with file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# =====================
# Mongo backend
# =====================

def _mongo_load_user_usage(user_id: int) -> Dict[str, Any]:
    """
    Mongo version of load_user_usage.
    Ensures a doc for (user_id, today) exists.
    """
    if not _USE_MONGO_EFFECTIVE or _mongo_usage_coll is None:
        # Fallback to JSON backend
        return _json_load_user_usage(user_id)

    today = _today_str()
    doc = _mongo_usage_coll.find_one({"user_id": user_id, "date": today})
    if not doc:
        doc = {
            "user_id": user_id,
            "date": today,
            "used_seconds": 0,
            "concurrent": 0,
            "trials_used": 0,
        }
        _mongo_usage_coll.insert_one(doc)

    # Return plain dict similar to JSON version (no _id)
    return {
        "date": doc.get("date", today),
        "used_seconds": int(doc.get("used_seconds", 0)),
        "concurrent": int(doc.get("concurrent", 0)),
        "trials_used": int(doc.get("trials_used", 0)),
    }


def _mongo_save_user_usage(user_id: int, usage: Dict[str, Any]) -> None:
    if not _USE_MONGO_EFFECTIVE or _mongo_usage_coll is None:
        _json_save_user_usage(user_id, usage)
        return

    today = usage.get("date") or _today_str()
    _mongo_usage_coll.update_one(
        {"user_id": user_id, "date": today},
        {
            "$set": {
                "date": today,
                "used_seconds": int(usage.get("used_seconds", 0)),
                "concurrent": int(usage.get("concurrent", 0)),
                "trials_used": int(usage.get("trials_used", 0)),
            }
        },
        upsert=True,
    )


def _mongo_global_concurrent() -> int:
    if not _USE_MONGO_EFFECTIVE or _mongo_usage_coll is None:
        return _json_global_concurrent()

    today = _today_str()
    total = 0
    try:
        for doc in _mongo_usage_coll.find({"date": today}, {"concurrent": 1}):
            total += int(doc.get("concurrent", 0))
    except Exception:
        # On error, be safe and return 0 (don't block everything)
        return 0
    return total


def _mongo_reset_daily_usage() -> None:
    if not _USE_MONGO_EFFECTIVE or _mongo_usage_coll is None:
        _json_reset_daily_usage()
        return

    today = _today_str()
    try:
        _mongo_usage_coll.update_many(
            {},
            {
                "$set": {
                    "date": today,
                    "used_seconds": 0,
                    "concurrent": 0,
                    "trials_used": 0,
                }
            },
        )
    except Exception:
        # If something goes wrong, don't crash the bot
        pass


# =====================
# Backend selectors
# =====================

def load_user_usage(user_id: int) -> Dict[str, Any]:
    """
    Load usage for a user from the active backend (Mongo or JSON).
    """
    if _USE_MONGO_EFFECTIVE:
        return _mongo_load_user_usage(user_id)
    return _json_load_user_usage(user_id)


def save_user_usage(user_id: int, usage: Dict[str, Any]) -> None:
    """
    Save usage for a user to the active backend.
    """
    if _USE_MONGO_EFFECTIVE:
        _mongo_save_user_usage(user_id, usage)
    else:
        _json_save_user_usage(user_id, usage)


def _get_global_concurrent() -> int:
    """
    Sum concurrent recordings across all users (for bot-wide cap).
    """
    if _USE_MONGO_EFFECTIVE:
        return _mongo_global_concurrent()
    return _json_global_concurrent()


# =====================
# Public API
# =====================

def check_limits(
    user_id: int,
    role: str,
    trial_requested: bool = False,
    duration_seconds: int = 0,
) -> LimitResult:
    """
    Check whether this user is allowed to start a recording.

    Parameters
    ----------
    user_id : int
        Telegram user id.
    role : str
        "owner", "admin", "normal", etc.
    trial_requested : bool, optional
        If True, we interpret this as a user asking to use a trial slot.
    duration_seconds : int, optional
        Intended recording duration (in seconds). Used to anticipate
        whether the user will exceed their daily limit if this recording runs fully.

    Returns
    -------
    LimitResult
    """
    # Unknown role guard
    if role not in LIMITS:
        return LimitResult(
            allowed=False,
            code="unknown_role",
            trial_granted=False,
            remaining_seconds=None,
        )

    usage = load_user_usage(user_id)
    role_hours = _role_limit_hours(role)
    role_max_concurrent = _role_max_concurrent(role)

    is_owner = role == "owner"

    # Check user-specific concurrent
    user_concurrent = int(usage.get("concurrent", 0))
    if role_max_concurrent is not None and user_concurrent >= role_max_concurrent:
        return LimitResult(
            allowed=False,
            code="concurrent_exceeded",
            trial_granted=False,
            remaining_seconds=None,
        )

    # Check global concurrent (whole bot)
    global_concurrent = _get_global_concurrent()
    if GLOBAL_MAX_CONCURRENT_RECORDINGS is not None and \
            global_concurrent >= GLOBAL_MAX_CONCURRENT_RECORDINGS:
        return LimitResult(
            allowed=False,
            code="global_concurrent_exceeded",
            trial_granted=False,
            remaining_seconds=None,
        )

    # Owner: ignore hours/trials completely, only concurrency matters.
    if is_owner:
        return LimitResult(
            allowed=True,
            code="ok",
            trial_granted=False,
            remaining_seconds=None,
        )

    # Non-owner: handle trials
    if trial_requested:
        if not TRIALS.get("enabled", False):
            return LimitResult(
                allowed=False,
                code="trial_disabled",
                trial_granted=False,
                remaining_seconds=None,
            )

        max_trials = int(TRIALS.get("max_trial_per_user", 0) or 0)
        trials_used = int(usage.get("trials_used", 0))

        if trials_used >= max_trials:
            return LimitResult(
                allowed=False,
                code="trials_exhausted",
                trial_granted=False,
                remaining_seconds=None,
            )

        # Trial accepted – actual increment happens in add_usage(..., trial=True)
        return LimitResult(
            allowed=True,
            code="ok",
            trial_granted=True,
            remaining_seconds=None,
        )

    # Non-owner: normal daily limit check (non-trial)
    if role_hours is None:
        # Unlimited hours (rare for non-owner, but supported)
        return LimitResult(
            allowed=True,
            code="ok",
            trial_granted=False,
            remaining_seconds=None,
        )

    max_seconds = int(role_hours * 3600)
    used_seconds = int(usage.get("used_seconds", 0))

    expected_total = used_seconds + max(0, int(duration_seconds))

    if expected_total > max_seconds:
        remaining = max(0, max_seconds - used_seconds)
        return LimitResult(
            allowed=False,
            code="daily_limit",
            trial_granted=False,
            remaining_seconds=remaining,
        )

    remaining = max_seconds - used_seconds
    return LimitResult(
        allowed=True,
        code="ok",
        trial_granted=False,
        remaining_seconds=remaining,
    )


def add_usage(
    user_id: int,
    role: str,
    duration_seconds: int = 0,
    trial: bool = False,
) -> None:
    """
    To be called when a new recording is accepted/started.

    For owner:
        - concurrent += 1
        - used_seconds not touched (unlimited)

    For non-owner:
        If trial=True:
            - trials_used += 1
            - concurrent += 1
        Else:
            - used_seconds += duration_seconds
            - concurrent += 1

    NOTE: if you don't know the exact duration in advance, you can pass the
    intended duration here, or 0 and adjust your logic as you like.
    """
    usage = load_user_usage(user_id)
    is_owner = (role == "owner")

    if is_owner:
        usage["concurrent"] = int(usage.get("concurrent", 0)) + 1
        save_user_usage(user_id, usage)
        return

    if trial:
        usage["trials_used"] = int(usage.get("trials_used", 0)) + 1
    else:
        usage["used_seconds"] = int(usage.get("used_seconds", 0)) + max(0, int(duration_seconds))

    usage["concurrent"] = int(usage.get("concurrent", 0)) + 1

    save_user_usage(user_id, usage)


def remove_concurrent(user_id: int) -> None:
    """
    To be called when a recording stops (successfully or with error).
    Decrements concurrent count, never going below zero.
    """
    usage = load_user_usage(user_id)
    current = int(usage.get("concurrent", 0))
    if current > 0:
        usage["concurrent"] = current - 1
        save_user_usage(user_id, usage)


def remaining_time(user_id: int, role: str) -> Optional[int]:
    """
    Returns remaining daily seconds for this user & role.
    None means unlimited (e.g. owner or role with hours=None).
    """
    role_hours = _role_limit_hours(role)
    if role_hours is None:
        return None

    usage = load_user_usage(user_id)
    max_seconds = int(role_hours * 3600)
    used = int(usage.get("used_seconds", 0))
    return max(0, max_seconds - used)


def reset_daily_usage() -> None:
    """
    Reset daily usage for ALL users. Intended to be scheduled via JobQueue.run_daily.

    On reset:
      - date       -> today
      - used_seconds -> 0
      - concurrent   -> 0
      - trials_used  -> 0
    """
    if _USE_MONGO_EFFECTIVE:
        _mongo_reset_daily_usage()
    else:
        _json_reset_daily_usage()