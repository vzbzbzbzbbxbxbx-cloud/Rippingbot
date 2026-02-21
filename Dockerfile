FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Only what we need: ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps
COPY bot/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy source
COPY . /app

# Ensure folders exist
RUN mkdir -p bot/downloads bot/logs bot/database/usage bot/database/playlists && \
    touch bot/__init__.py bot/utils/__init__.py

CMD ["python", "-m", "bot.main"]
