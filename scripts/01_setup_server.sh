#!/usr/bin/env bash
# ==============================================================================
# 01_setup_server.sh
# Run this once on a fresh Ubuntu/Debian VPS as a user with sudo access.
# It installs everything needed EXCEPT your secrets (bot token, api_id, api_hash)
# which go in the .env file (see 00_env_example.txt).
# ==============================================================================
set -euo pipefail

echo "=== 1. System packages ==="
sudo apt update
sudo apt install -y \
    git curl wget unzip \
    build-essential cmake gperf \
    libssl-dev zlib1g-dev \
    python3 python3-pip python3-venv \
    sqlite3

echo "=== 2. Build telegram-bot-api (Telegram's official Local Bot API Server) ==="
# This is required to handle files >20MB (up to 2000MB / 2GB).
# Building from source takes a while (5-15 min depending on VPS specs).
if [ ! -f /usr/local/bin/telegram-bot-api ]; then
    cd /home
    if [ ! -d telegram-bot-api ]; then
        git clone --recursive https://github.com/tdlib/telegram-bot-api.git
    fi
    cd telegram-bot-api
    rm -rf build
    mkdir build
    cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    cmake --build . --target install -j"$(nproc)"
    sudo cp /home/telegram-bot-api/build/telegram-bot-api /usr/local/bin/
else
    echo "telegram-bot-api already installed, skipping build."
fi

echo "=== 3. Create app directories ==="
sudo mkdir -p /opt/filelinkbot
sudo mkdir -p /opt/filelinkbot/storage      # actual uploaded files live here
sudo mkdir -p /opt/filelinkbot/bot-api-data # telegram-bot-api's working dir
sudo mkdir -p /opt/filelinkbot/db
sudo chown -R "$USER":"$USER" /opt/filelinkbot

echo "=== 4. Copy application files ==="
cp -r ./bot /opt/filelinkbot/
cp -r ./web /opt/filelinkbot/

echo "=== 5. Python virtual environment ==="
cd /opt/filelinkbot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r bot/requirements.txt -r web/requirements.txt
deactivate

echo "=== Done ==="
echo "Next steps:"
echo "1. Copy .env.example to /opt/filelinkbot/.env and fill in your secrets"
echo "2. Run 02_install_services.sh to set up systemd services"
