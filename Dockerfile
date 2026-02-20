FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        wget \
        gnupg && \
    # MEGAcmd repo (Debian 12)
    wget -qO - https://mega.nz/linux/MEGAsync/Debian_12/Release.key | gpg --dearmor -o /usr/share/keyrings/meganz-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/meganz-archive-keyring.gpg] https://mega.nz/linux/MEGAsync/Debian_12/ ./" > /etc/apt/sources.list.d/meganz.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends megacmd && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bot/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY . /app

RUN mkdir -p bot/downloads bot/logs bot/database/usage bot/database/playlists && \
    touch bot/__init__.py bot/utils/__init__.py

CMD ["python", "-m", "bot.main"]
