"""
services/musicbrainz.py - MusicBrainz artist, release-group, and recording lookups with rate-limiting and cache.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import MB_USER_AGENT
from services.lyrics import clean_title

MB_BASE = "https://musicbrainz.org/ws/2"
_mb: Dict[str, Any] = {"lock": None, "last": 0.0, "client": None}
_MBC: Dict[Any, Tuple[float, Any]] = {}
MBC_TTL = 24 * 3600


def mb_client() -> httpx.AsyncClient:
    """Return shared httpx AsyncClient for MusicBrainz API requests."""
    if _mb["client"] is None:
        _mb["client"] = httpx.AsyncClient(
            timeout=12,
            headers={"User-Agent": MB_USER_AGENT, "Accept": "application/json"},
        )
    return _mb["client"]


async def mb_get(path: str, **params: Any) -> Dict[str, Any]:
    """MusicBrainz allows ~1 request/second: every call waits its turn under an async lock."""
    params["fmt"] = "json"
    if _mb["lock"] is None:
        _mb["lock"] = asyncio.Lock()
    for attempt in (1, 2):
        async with _mb["lock"]:
            wait = 1.1 - (time.time() - _mb["last"])
            if wait > 0:
                await asyncio.sleep(wait)
            _mb["last"] = time.time()
        r = await mb_client().get(f"{MB_BASE}/{path}", params=params)
        if r.status_code in (429, 503) and attempt == 1:
            await asyncio.sleep(2.5)
            continue
        r.raise_for_status()
        return r.json()
    return {}


def _mbc_get(key: Any, ttl: float = MBC_TTL) -> Any:
    hit = _MBC.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def _mbc_put(key: Any, val: Any) -> Any:
    if len(_MBC) > 800:
        for k, _ in sorted(_MBC.items(), key=lambda kv: kv[1][0])[:200]:
            _MBC.pop(k, None)
    _MBC[key] = (time.time(), val)
    return val


def lq(s: str) -> str:
    """Sanitize string for Lucene query."""
    return re.sub(r'["\\]', " ", s or "").strip()


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def parse_artist(a: Dict[str, Any]) -> Dict[str, Any]:
    """Extract normalized artist fields from MusicBrainz artist object."""
    ls = a.get("life-span") or {}
    tags = sorted(a.get("genres") or a.get("tags") or [], key=lambda t: -t.get("count", 0))
    return {
        "id": a.get("id", ""),
        "name": a.get("name", ""),
        "dis": a.get("disambiguation", ""),
        "type": a.get("type", ""),
        "country": (a.get("area") or {}).get("name") or a.get("country", "") or "",
        "begin": ls.get("begin") or "",
        "genres": [t["name"].title() for t in tags[:4] if t.get("name")],
    }


async def mb_artist_search(name: str) -> Optional[Dict[str, Any]]:
    """Search MusicBrainz for an artist by name."""
    key = ("as", name.lower())
    hit = _mbc_get(key)
    if hit is not None:
        return hit or None
    d = await mb_get("artist", query=f'artist:"{lq(name)}"', limit=3)
    best = None
    for a in d.get("artists", []):
        if int(a.get("score", 0)) >= 70 and _sim(a.get("name", ""), name) >= 0.55:
            best = a
            break
    return _mbc_put(key, parse_artist(best) if best else {}) or None


async def mb_artist_by_id(mbid: str) -> Optional[Dict[str, Any]]:
    """Fetch MusicBrainz artist details by MBID."""
    key = ("ai", mbid)
    hit = _mbc_get(key)
    if hit is not None:
        return hit or None
    d = await mb_get(f"artist/{mbid}", inc="genres+tags")
    return _mbc_put(key, parse_artist(d) if d.get("id") else {}) or None


async def mb_release_groups(
    mbid: str,
    max_pages: int = 3,
    fresh: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch official albums, singles, and EPs for an artist MBID."""
    key = ("rg", mbid)
    if not fresh:
        hit = _mbc_get(key, 6 * 3600)
        if hit is not None:
            return hit
    out: List[Dict[str, Any]] = []
    off = 0
    while True:
        d = await mb_get("release-group", artist=mbid, limit=100, offset=off, type="album|single|ep")
        for r in d.get("release-groups", []):
            sec = r.get("secondary-types") or []
            if any(s in ("Compilation", "DJ-mix", "Remix", "Live", "Demo") for s in sec):
                continue
            out.append(
                {
                    "id": r.get("id", ""),
                    "title": r.get("title", ""),
                    "type": r.get("primary-type") or "Release",
                    "date": r.get("first-release-date") or "",
                }
            )
        off += 100
        if off >= d.get("release-group-count", 0) or off >= 100 * max_pages:
            break
    return _mbc_put(key, out)


def parse_recording(r: Dict[str, Any]) -> Dict[str, Any]:
    """Extract normalized recording metadata from MusicBrainz recording entry."""
    ac = r.get("artist-credit") or []
    artist = "".join((c.get("name", "") + c.get("joinphrase", "")) for c in ac).strip()
    artist_id = ((ac[0].get("artist") or {}).get("id")) if ac else None
    rels = r.get("releases") or []

    def is_album(x: Dict[str, Any]) -> bool:
        rg = x.get("release-group") or {}
        return rg.get("primary-type") == "Album" and not rg.get("secondary-types")

    pick = (
        next((x for x in rels if is_album(x) and x.get("status") == "Official"), None)
        or next((x for x in rels if is_album(x)), None)
        or (rels[0] if rels else None)
    )
    date = r.get("first-release-date") or (pick or {}).get("date") or ""
    tags = sorted(r.get("tags") or [], key=lambda t: -t.get("count", 0))
    return {
        "mb_title": r.get("title", ""),
        "mb_artist": artist,
        "artist_id": artist_id,
        "album": (pick or {}).get("title", ""),
        "album_type": ((pick or {}).get("release-group") or {}).get("primary-type", ""),
        "year": date[:4],
        "date": date,
        "genres": [t["name"].title() for t in tags[:3] if t.get("name")],
    }


async def mb_recording(title: str, artist: str) -> Optional[Dict[str, Any]]:
    """Look up recording metadata on MusicBrainz."""
    key = ("rec", f"{artist}|{title}".lower())
    hit = _mbc_get(key)
    if hit is not None:
        return hit or None
    q = f'recording:"{lq(title)}"' + (f' AND artist:"{lq(artist)}"' if artist else "")
    d = await mb_get("recording", query=q, limit=5)
    best = None
    for r in d.get("recordings", []):
        if int(r.get("score", 0)) >= 70 and _sim(r.get("title", ""), title) >= 0.6:
            best = r
            break
    if not best:
        return _mbc_put(key, {}) or None
    info = parse_recording(best)
    if not info["genres"] and info.get("artist_id"):
        try:
            a = await mb_artist_by_id(info["artist_id"])
            info["genres"] = (a or {}).get("genres", [])[:3]
        except Exception:
            pass
    return _mbc_put(key, info)


def guess_artist_title(meta: Dict[str, Any]) -> Tuple[str, str]:
    """Guess (artist, title) from YouTube video title and channel name."""
    t = clean_title(meta["title"])
    ch = re.sub(r"\s*-\s*Topic$|VEVO$|\s*Official$", "", meta.get("channel", ""), flags=re.I).strip()
    if " - " in t:
        a, s = t.split(" - ", 1)
        return a.strip(), s.strip() or t
    return ch, t
