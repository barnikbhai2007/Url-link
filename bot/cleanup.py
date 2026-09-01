"""
Deletes expired files from disk and removes their DB records.
Intended to be run periodically (see systemd timer: filelinkbot-cleanup.timer)
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv("/opt/filelinkbot/.env")

import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    db.init_db()
    expired = db.get_expired_files()
    if not expired:
        logger.info("No expired files.")
        return

    for record in expired:
        path = record["file_path"]
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Deleted file: {path}")
        except OSError:
            logger.exception(f"Failed to delete file: {path}")
        db.delete_file_entry(record["code"])
        logger.info(f"Removed DB record: {record['code']}")

    logger.info(f"Cleanup done. Removed {len(expired)} expired file(s).")


if __name__ == "__main__":
    main()
