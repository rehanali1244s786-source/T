"""
services/audd.py - Song recognition from voice notes, audio, or video clips via AudD API.
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, Optional

import httpx
from aiogram.types import Message

from config import AUDD_TOKEN


def pick_media(m: Optional[Message]) -> Optional[Any]:
    """Extract voice, audio, video, video_note, or audio/video document from a Message."""
    if not m:
        return None
    media = m.voice or m.audio or m.video or m.video_note
    if not media and m.document and (m.document.mime_type or "").startswith(("audio/", "video/")):
        media = m.document
    return media


def make_clip(src: str, dst: str) -> None:
    """Extract a 20-second mono 64k MP3 clip via ffmpeg (blocking, run in thread)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-t", "20", "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", dst],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=90,
    )


async def audd_identify(path: str) -> Dict[str, Any]:
    """Send audio clip at `path` to https://api.audd.io/ for recognition."""
    async with httpx.AsyncClient(timeout=45) as c:
        with open(path, "rb") as f:
            r = await c.post(
                "https://api.audd.io/",
                data={"api_token": AUDD_TOKEN},
                files={"file": ("clip.mp3", f, "audio/mpeg")},
            )
    r.raise_for_status()
    return r.json()
