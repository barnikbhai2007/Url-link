# FileLinkBot

A Telegram bot that turns any uploaded file (up to 2GB) into a short, sharable
download link. Runs entirely on your own VPS.

## How it works

```
User sends file to bot
        |
        v
telegram-bot-api (local server, systemd) --> handles files up to 2GB
        |
        v
bot/main.py saves file to /opt/filelinkbot/storage, asks expiry, stores in SQLite
        |
        v
web/server.py serves it at http://YOUR_IP:8000/f/<shortcode>
```

Three long-running services (all managed by systemd, auto-restart on crash/reboot):
- `telegram-bot-api` — Telegram's official local API server, required for >20MB files
- `filelinkbot-bot` — the bot itself
- `filelinkbot-web` — the download server
- plus a `filelinkbot-cleanup.timer` that deletes expired files every 30 min

## Prerequisites

1. Ubuntu/Debian VPS with a regular sudo user (not root)
2. A Telegram bot token from [@BotFather](https://t.me/BotFather) (`/newbot`)
3. `api_id` and `api_hash` from https://my.telegram.org -> "API development tools"

## Deploying via GitHub

This repo is safe to push to GitHub (public or private) as-is — `.gitignore`
excludes `.env`, the SQLite DB, and the storage folder, so no secrets or user
files get committed.

```bash
# From your local machine / wherever you unzip this:
cd filelinkbot
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/filelinkbot.git
git push -u origin main
```

Then on the VPS:

```bash
ssh your_user@your_vps_ip
git clone https://github.com/YOUR_USERNAME/filelinkbot.git
cd filelinkbot
```

From here the steps are identical to a direct copy — continue below at step 3.

## Deployment steps

```bash
# 1. Get the code onto your VPS — either clone from GitHub (above) or copy directly:
scp -r filelinkbot your_user@your_vps_ip:~/

# 2. SSH in
ssh your_user@your_vps_ip
cd ~/filelinkbot

# 3. Run the server setup (installs telegram-bot-api, Python deps, etc.)
#    This takes 5-15 minutes because telegram-bot-api is compiled from source.
bash scripts/01_setup_server.sh

# 4. Create your .env file with real secrets
cp .env.example /opt/filelinkbot/.env
nano /opt/filelinkbot/.env
#    Fill in: BOT_TOKEN, API_ID, API_HASH, BASE_URL (http://YOUR_VPS_IP:8000 for now)

# 5. Install and start the systemd services
bash scripts/02_install_services.sh

# 6. Open the web port in your firewall if using ufw
sudo ufw allow 8000/tcp
```

That's it. Message your bot on Telegram, send it a file, tap an expiry option,
and you'll get back a link like `http://your_vps_ip:8000/f/aB3xY9kP`.

## Checking things are working

```bash
# Is the local Telegram API server up?
sudo systemctl status telegram-bot-api

# Bot logs (should show "Bot starting..." then handle updates as you send files)
journalctl -u filelinkbot-bot -f

# Download server logs
journalctl -u filelinkbot-web -f

# Quick health check
curl http://localhost:8000/healthz
```

## Adding a domain + HTTPS later

Once you have a domain pointed at your VPS's IP (an A record):

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

Then set up nginx as a reverse proxy to `localhost:8000` (certbot can do this
interactively), and update `BASE_URL` in `/opt/filelinkbot/.env` to
`https://yourdomain.com`, then restart the bot:

```bash
sudo systemctl restart filelinkbot-bot
```

Existing short links will keep working immediately since BASE_URL only affects
new links generated after the change — old links using the IP will still
resolve as long as the IP:8000 stays reachable, or you can 301-redirect old
ones once nginx is in place.

## Notes on scale & limits

- **Max file size**: set by `MAX_FILE_SIZE_MB` in `.env`, capped at 2000 (2GB)
  by Telegram's local Bot API server itself.
- **Storage**: files live at `/opt/filelinkbot/storage`. With 100GB disk,
  monitor usage (`df -h`) — nothing here auto-deletes except expired links.
- **Concurrent large uploads**: fine for personal/small-group use. For heavy
  public traffic, you'd eventually want to move storage to S3/R2 and put
  nginx in front of uvicorn for connection handling — not needed at your
  current scale.
- **Security**: anyone with a link can download the file — there's no auth.
  Don't rely on this for sensitive documents; shortcodes are guessable in
  theory (8 random chars) though not practically brute-forceable at low
  traffic.

## File structure

```
filelinkbot/
├── bot/
│   ├── main.py          # Telegram bot logic
│   ├── db.py             # SQLite helper (shared with web server)
│   ├── cleanup.py        # Deletes expired files, run by systemd timer
│   └── requirements.txt
├── web/
│   ├── server.py         # FastAPI download server
│   └── requirements.txt
└── scripts/
    ├── 00_env_example.txt
    ├── 01_setup_server.sh
    ├── 02_install_services.sh
    └── systemd/           # service unit files installed by 02_...sh
```
