"""
Download server. Serves files at GET /f/<code>.
Supports HTTP Range requests so downloads can resume and download managers work.

Run with: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
import sys
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

load_dotenv("/opt/filelinkbot/.env")

# bot/db.py is shared between the bot and web server
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
import db  # noqa: E402

app = FastAPI(title="FileLinkBot Downloads")


@app.get("/", response_class=HTMLResponse)
async def index():
    return "<h3>FileLinkBot download server is running.</h3>"


@app.get("/f/{code}")
async def download(code: str, request: Request):
    record = db.get_file(code)
    if not record:
        raise HTTPException(status_code=404, detail="Link not found")

    if record["expires_at"] and record["expires_at"] <= int(time.time()):
        raise HTTPException(status_code=410, detail="This link has expired")

    file_path = record["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File no longer exists")

    db.increment_downloads(code)

    # FileResponse natively supports Range requests (partial content / resume)
    return FileResponse(
        path=file_path,
        filename=record["file_name"],
        media_type="application/octet-stream",
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
