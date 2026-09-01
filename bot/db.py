"""
Tiny SQLite wrapper shared by the bot and the web server.
Stores the mapping: shortcode -> file info (path, name, size, expiry).
"""
import sqlite3
import time
import secrets
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/opt/filelinkbot/db/files.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    code        TEXT PRIMARY KEY,
    file_path   TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    file_size   INTEGER NOT NULL,
    uploader_id INTEGER NOT NULL,
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER,           -- NULL = never expires
    downloads   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_expires_at ON files(expires_at);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def generate_code(length: int = 8) -> str:
    # URL-safe, unambiguous-ish short code
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_file_entry(file_path: str, file_name: str, file_size: int,
                       uploader_id: int, expires_in_seconds: int | None) -> str:
    """Insert a new file record and return its shortcode."""
    with get_conn() as conn:
        while True:
            code = generate_code()
            existing = conn.execute("SELECT 1 FROM files WHERE code = ?", (code,)).fetchone()
            if not existing:
                break
        now = int(time.time())
        expires_at = now + expires_in_seconds if expires_in_seconds else None
        conn.execute(
            "INSERT INTO files (code, file_path, file_name, file_size, uploader_id, "
            "created_at, expires_at, downloads) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (code, file_path, file_name, file_size, uploader_id, now, expires_at),
        )
        return code


def get_file(code: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None


def increment_downloads(code: str):
    with get_conn() as conn:
        conn.execute("UPDATE files SET downloads = downloads + 1 WHERE code = ?", (code,))


def get_expired_files():
    now = int(time.time())
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM files WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_file_entry(code: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM files WHERE code = ?", (code,))


def get_user_files(uploader_id: int, limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM files WHERE uploader_id = ? ORDER BY created_at DESC LIMIT ?",
            (uploader_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
