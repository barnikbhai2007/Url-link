#!/usr/bin/env bash
# ==============================================================================
# 02_install_services.sh
# Run this AFTER 01_setup_server.sh and AFTER you've created /opt/filelinkbot/.env
# It substitutes your Linux username into the service files and installs them.
# ==============================================================================
set -euo pipefail

if [ ! -f /opt/filelinkbot/.env ]; then
    echo "ERROR: /opt/filelinkbot/.env not found."
    echo "Copy scripts/00_env_example.txt to /opt/filelinkbot/.env and fill it in first."
    exit 1
fi

CURRENT_USER="$(whoami)"
echo "Installing services to run as user: $CURRENT_USER"

for svc in telegram-bot-api.service filelinkbot-bot.service filelinkbot-web.service \
           filelinkbot-cleanup.service filelinkbot-cleanup.timer; do
    sed "s/YOUR_LINUX_USERNAME/${CURRENT_USER}/g" "./scripts/systemd/${svc}" \
        | sudo tee "/etc/systemd/system/${svc}" > /dev/null
done

sudo systemctl daemon-reload

sudo systemctl enable --now telegram-bot-api.service
sleep 2
sudo systemctl enable --now filelinkbot-bot.service
sudo systemctl enable --now filelinkbot-web.service
sudo systemctl enable --now filelinkbot-cleanup.timer

echo ""
echo "=== Status ==="
sudo systemctl --no-pager status telegram-bot-api.service | head -5
sudo systemctl --no-pager status filelinkbot-bot.service | head -5
sudo systemctl --no-pager status filelinkbot-web.service | head -5

echo ""
echo "Done. Useful commands:"
echo "  journalctl -u filelinkbot-bot -f      # bot logs"
echo "  journalctl -u filelinkbot-web -f      # download server logs"
echo "  journalctl -u telegram-bot-api -f     # local API server logs"
echo "  sudo ufw allow 8000/tcp                # open the web port if using ufw"
