"""
FileLinkBot - Telegram bot that turns uploaded files into downloadable short links.

Flow:
1. User sends any file (document, video, audio, photo, voice, etc.)
2. Bot downloads it via the LOCAL Bot API server (supports up to 2GB, not the
   20MB cap of the public api.telegram.org)
3. Bot moves the file into permanent storage and asks the user to pick an
   expiry option via inline buttons
4. On choice, bot creates a DB record and replies with the short link
"""
import logging
import os
import shutil
import uuid

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import db

load_dotenv("/opt/filelinkbot/.env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
LOCAL_API_PORT = os.environ.get("LOCAL_API_PORT", "8081")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/opt/filelinkbot/storage")
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "2000"))

# Local Bot API server base URL (must match how you launch telegram-bot-api)
LOCAL_API_BASE = f"http://localhost:{LOCAL_API_PORT}/bot"

# Expiry options shown to the user: (label, seconds or None for never)
EXPIRY_OPTIONS = [
    ("Never", None),
    ("1 day", 86400),
    ("7 days", 7 * 86400),
    ("30 days", 30 * 86400),
]

# Temporary holding area for a file while we wait for the user's expiry choice
# pending[user_id] = {"path": ..., "name": ..., "size": ...}
pending: dict[int, dict] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me any file (up to 2GB) and I'll give you a direct download link "
        "you can share anywhere.\n\nUse /mine to see your recent uploads."
    )


async def mine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    files = db.get_user_files(user_id)
    if not files:
        await update.message.reply_text("You haven't uploaded anything yet.")
        return
    lines = []
    for f in files:
        exp = "never" if not f["expires_at"] else f"expires <t:{f['expires_at']}>"
        lines.append(f"• {f['file_name']} — {BASE_URL}/f/{f['code']} ({exp}, {f['downloads']} downloads)")
    await update.message.reply_text("\n".join(lines))


def _pick_incoming_file(message):
    """Return (telegram_file_obj_awaitable_getter, filename, size) for whichever
    attachment type is present on this message."""
    if message.document:
        f = message.document
        return f, f.file_name or "file", f.file_size
    if message.video:
        f = message.video
        return f, f.file_name or f"video_{f.file_unique_id}.mp4", f.file_size
    if message.audio:
        f = message.audio
        return f, f.file_name or f"audio_{f.file_unique_id}.mp3", f.file_size
    if message.voice:
        f = message.voice
        return f, f"voice_{f.file_unique_id}.ogg", f.file_size
    if message.photo:
        f = message.photo[-1]  # largest resolution
        return f, f"photo_{f.file_unique_id}.jpg", f.file_size
    if message.video_note:
        f = message.video_note
        return f, f"video_note_{f.file_unique_id}.mp4", f.file_size
    return None, None, None


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id

    tg_file_obj, filename, size = _pick_incoming_file(message)
    if tg_file_obj is None:
        await message.reply_text("Please send a file, video, audio, voice note, or photo.")
        return

    if size and size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(f"File is too large. Max size is {MAX_FILE_SIZE_MB}MB.")
        return

    status_msg = await message.reply_text("Downloading your file…")

    try:
        tg_file = await tg_file_obj.get_file()  # uses local Bot API server under the hood
        # tg_file.file_path is a LOCAL filesystem path when using the local API server
        # (rather than a URL, which is what the public API returns).
        source_path = tg_file.file_path

        os.makedirs(STORAGE_DIR, exist_ok=True)
        ext = os.path.splitext(filename)[1]
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(STORAGE_DIR, stored_name)

        if os.path.exists(source_path):
            # Local API server already saved it to disk — just move it into our storage
            shutil.move(source_path, dest_path)
        else:
            # Fallback: download over HTTP (shouldn't normally happen with local API server)
            await tg_file.download_to_drive(dest_path)

        actual_size = os.path.getsize(dest_path)
        pending[user_id] = {"path": dest_path, "name": filename, "size": actual_size}

        buttons = [
            [InlineKeyboardButton(label, callback_data=f"exp:{seconds}")]
            for label, seconds in EXPIRY_OPTIONS
        ]
        await status_msg.edit_text(
            f"Got it: {filename} ({actual_size / 1024 / 1024:.1f} MB)\n\n"
            "How long should the download link stay active?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception:
        logger.exception("Failed to handle incoming file")
        await status_msg.edit_text("Something went wrong saving your file. Please try again.")


async def handle_expiry_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    info = pending.pop(user_id, None)
    if not info:
        await query.edit_message_text("This upload session expired, please resend the file.")
        return

    seconds_str = query.data.split(":", 1)[1]
    expires_in = None if seconds_str == "None" else int(seconds_str)

    code = db.create_file_entry(
        file_path=info["path"],
        file_name=info["name"],
        file_size=info["size"],
        uploader_id=user_id,
        expires_in_seconds=expires_in,
    )
    link = f"{BASE_URL}/f/{code}"
    await query.edit_message_text(f"Your download link:\n{link}")


def main():
    db.init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .base_url(LOCAL_API_BASE)  # <-- routes through the local Bot API server
        .local_mode(True)          # <-- tells PTB file paths are local, not URLs
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mine", mine))
    app.add_handler(
        MessageHandler(
            filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.VOICE
            | filters.PHOTO
            | filters.VIDEO_NOTE,
            handle_file,
        )
    )
    app.add_handler(CallbackQueryHandler(handle_expiry_choice, pattern=r"^exp:"))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
