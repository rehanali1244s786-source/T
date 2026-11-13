"""
services/lyrics.py - Lyrics search via lrclib.net and song title cleaning.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

import httpx

LYRICS_API = "https://lrclib.net/api/search"
_JUNK = re.compile(
    r"\(.*?\)|\[.*?\]|official\s*(music\s*)?(video|audio|lyric\s*video)?|lyrics?|lyrical|full\s*(video|song)|hd|4k|\|.*$",
    re.I,
)


def clean_title(t: str) -> str:
    """Strip common YouTube noise tags (Official Video, Lyrics, HD, etc.) from a song title."""
    return re.sub(r"\s{2,}", " ", _JUNK.sub(" ", t)).strip(" -–|") or t


async def fetch_lyrics(query: str) -> Optional[Dict[str, Any]]:
    """Fetch plain lyrics for `query` from lrclib.net."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "MusicBot (Telegram)"}) as c:
        r = await c.get(LYRICS_API, params={"q": query})
        r.raise_for_status()
        for item in r.json():
            if item.get("plainLyrics"):
                return item
    return None
