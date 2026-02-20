# Rippingbot

# 🎥 Telegram Live Stream Recorder Bot

A clean, reliable Telegram bot for recording HLS / M3U8 live streams with multi-quality selection and automatic MEGA upload.

---

## ✨ Overview

This bot helps you:

- 📺 Record HLS / M3U8 streams
- 🎚️ Choose video quality (1080p / 720p / etc.)
- 🎧 Choose audio track (multi-audio support)
- ⚡ Record without re-encoding (`-c copy`)
- ☁️ Upload recordings to MEGA automatically
- 🔒 Keep uploads private (only shared if you share the link)
- 🧠 Enforce role-based limits + concurrency rules
- 🎨 Use 3 UI themes (Hot / Cold / Dark)

---

## ✅ Key Features

### 🎬 Recording
- ✅ HLS support (master + media playlists)
- ✅ No re-encode (stream copy)
- ✅ Duration-based or unlimited recording
- ✅ Live progress updates
- ✅ Multi-audio track mapping

### ☁️ Upload (MEGA)
- 📁 Creates **one folder per recording**:

- /Root/Recordings/<record_name>/

- 📤 Uploads all split parts into that folder
- 🔗 Can generate a MEGA folder link after upload (optional)
- 🔐 Files remain private unless you share the link

### 🧑‍💼 Roles & Limits
| Role   | Daily Limit | Max Concurrent |
|--------|------------|----------------|
| 👑 Owner  | Unlimited  | 2              |
| 🛡️ Admin  | 8 hours    | 2              |
| 👤 User   | 4 hours    | 2              |

- 🕛 Daily reset (configurable)
- 🎟️ Trial support
- 🧩 Global concurrency cap

### 🧰 Extras
- 📃 Playlist support
- 📊 /status live dashboard
- 🧠 JSON or MongoDB backend
- ⚠️ CPU load monitoring (owner notifications)
- 🧾 Logging to a Telegram channel

---

## 🗂️ Project Structure

bot/ ├── main.py ├── config.py ├── limits.py ├── ui.py ├── messages.py ├── buttons.py ├── management.py ├── utils/ │   ├── ffmpeg_runner.py │   ├── uploader.py │   ├── probe.py ├── downloads/ ├── logs/ └── database/ └── usage/

---

## 🧩 Requirements

### 🖥️ System Dependencies
- ✅ Python 3.10+
- ✅ FFmpeg (with ffprobe)
- ✅ MEGAcmd (`mega-login`, `mega-put`, `mega-export`)

### 📦 Python Dependencies

python-telegram-bot==20.7 psutil==5.9.8 pymongo==4.7.1

Install:

```bash
pip install -r bot/requirements.txt

🔐 Environment Variables
Set these before running:

BOT_TOKEN=your_telegram_bot_token
OWNER_ID=your_telegram_user_id
LOG_CHANNEL_ID=-100xxxxxxxxxx

MEGA_EMAIL=your_mega_email
MEGA_PASS=your_mega_password
MEGA_FOLDER=/Root/Recordings

USE_MONGO=false
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=streamrec_bot

⚠️ Never commit secrets to GitHub.

▶️ Run Locally
python -m bot.main

🐳 Run With Docker
Build:
docker build -t streamrec-bot .

Run:
docker run -d \
  -e BOT_TOKEN=your_token \
  -e OWNER_ID=your_id \
  -e MEGA_EMAIL=your_email \
  -e MEGA_PASS=your_password \
  streamrec-bot

✅ Start
/start
🎥 Record
/record <m3u8_link> <duration> <filename>
📃 Playlist
/playlist add sports https://example.com/stream.m3u8
/playlist select sports
🛡️ Admin Commands
/add <user_id>
/rm <user_id>
/ban <user_id>
/unban <user_id>
📊 Status
/status

🔒 Security Notes
✅ MEGA uploads are private by default
🔗 Folder links expose content only if you share them
🔐 Keep MEGA credentials safe (use env vars)
🧱 Use a private repo if you want maximum safety

⚠️ Disclaimer
This project is for educational and personal use.
You are responsible for complying with local laws and streaming platform policies.

👨‍💻 Developer
Developer TG - @DoraemonBro
