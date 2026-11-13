"""
services/bpm.py - BPM and musical key lookup via GetSongBPM, Deezer (free keyless), and optional librosa analysis.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

from config import GETSONGBPM_KEY, NOTES, log
from db import db
from services.musicbrainz import guess_artist_title, mb_recording
from services.youtube import http_client


async def getsongbpm(title: str, artist: str) -> Optional[Dict[str, str]]:
    """Optional: GetSongBPM lookup (requires GETSONGBPM_KEY)."""
    if not GETSONGBPM_KEY:
        return None
    c = http_client()
    r = await c.get(
        "https://api.getsong.co/search/",
        params={
            "api_key": GETSONGBPM_KEY,
            "type": "both",
            "lookup": f"song:{title} artist:{artist}",
        },
    )
    items = (r.json() or {}).get("search")
    if not isinstance(items, list) or not items:
        return None
    it = items[0]
    if not it.get("tempo") and it.get("id"):
        r2 = await c.get(
            "https://api.getsong.co/song/",
            params={"api_key": GETSONGBPM_KEY, "id": it["id"]},
        )
        it = (r2.json() or {}).get("song") or it
    tempo, key = it.get("tempo"), it.get("key_of")
    if not tempo and not key:
        return None
    return {"bpm": str(tempo or ""), "key": str(key or ""), "bpm_src": "GetSongBPM"}


async def deezer_bpm(title: str, artist: str) -> Optional[Dict[str, str]]:
    """Free, keyless BPM lookup via Deezer API."""
    if not title:
        return None
    c = http_client()
    q = f'artist:"{artist}" track:"{title}"' if artist else f'track:"{title}"'
    r = await c.get("https://api.deezer.com/search", params={"q": q, "limit": 5})
    items = (r.json() or {}).get("data") or []
    if not items and artist:
        r = await c.get("https://api.deezer.com/search", params={"q": f"{artist} {title}", "limit": 5})
        items = (r.json() or {}).get("data") or []
    if not items:
        return None
    a = (artist or "").lower()
    pick = next(
        (
            i
            for i in items
            if a
            and (
                a in (i.get("artist") or {}).get("name", "").lower()
                or (i.get("artist") or {}).get("name", "").lower() in a
            )
        ),
        items[0],
    )
    r2 = await c.get(f"https://api.deezer.com/track/{pick['id']}")
    bpm_raw = (r2.json() or {}).get("bpm")
    try:
        bpm = int(round(float(bpm_raw)))
    except (TypeError, ValueError):
        return None
    if bpm <= 0:
        return None
    return {"bpm": str(bpm), "key": "", "bpm_src": "Deezer"}


def analyze_audio(path: str) -> Dict[str, str]:
    """Local BPM + musical key estimate using librosa (run in thread executor)."""
    import librosa  # type: ignore
    import numpy as np  # type: ignore

    wav = path + ".wav"
    for ss in ("20", "0"):
        subprocess.run(
            ["ffmpeg", "-y", "-ss", ss, "-t", "60", "-i", path, "-ac", "1", "-ar", "22050", wav],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists(wav) and os.path.getsize(wav) > 100_000:
            break
    y, sr = librosa.load(wav, sr=22050, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(round(float(np.atleast_1d(tempo)[0])))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    best, best_key = -2.0, ""
    for i in range(12):
        for prof, mode in ((major, "major"), (minor, "minor")):
            c = float(np.corrcoef(chroma, np.roll(prof, i))[0, 1])
            if c > best:
                best, best_key = c, f"{NOTES[i]} {mode}"
    return {"bpm": str(bpm), "key": best_key, "bpm_src": "audio analysis"}


async def song_info(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Combine MusicBrainz recording metadata with GetSongBPM, Deezer BPM, and cached librosa BPM."""
    artist, title = guess_artist_title(meta)
    info: Dict[str, Any] = {"artist": artist, "title": title}
    try:
        rec = await mb_recording(title, artist)
    except Exception as e:
        log.warning("musicbrainz failed: %s", e)
        rec = None
    if rec:
        info.update(rec)
    try:
        sb = await getsongbpm(title, info.get("mb_artist") or artist)
    except Exception as e:
        log.warning("getsongbpm failed: %s", e)
        sb = None
    if sb:
        info.update(sb)
    if not info.get("bpm"):
        try:
            dz = await deezer_bpm(title, info.get("mb_artist") or artist)
        except Exception as e:
            log.warning("deezer bpm failed: %s", e)
            dz = None
        if dz:
            info.update(dz)
    cached = db["bpm"].get(meta["id"])
    if cached and not info.get("bpm"):
        info.update(cached)
    return info
