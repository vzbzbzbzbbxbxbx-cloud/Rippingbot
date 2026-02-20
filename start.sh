#!/usr/bin/env bash
set -euo pipefail

echo "=== Rippingbot starting ==="

: "${BOT_TOKEN:?BOT_TOKEN is not set}"
: "${OWNER_ID:?OWNER_ID is not set}"

mkdir -p bot/downloads bot/logs bot/database/usage bot/database/playlists

if command -v ffmpeg >/dev/null 2>&1; then
  echo "[OK] ffmpeg found"
else
  echo "[WARN] ffmpeg not found"
fi

if command -v mega-login >/dev/null 2>&1; then
  echo "[OK] MEGAcmd found"
else
  echo "[WARN] MEGAcmd not found"
fi

exec python -m bot.main
