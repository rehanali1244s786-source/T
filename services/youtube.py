"""
services/youtube.py - yt-dlp search, metadata, download with progress hooks, priority queue, and thread pools.
"""

from __future__ import annotations

import asyncio
import glob
import heapq
import itertools
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import yt_dlp
from aiogram.types import Message

from animations import ANIM_DELAY_PROGRESS, DOWNLOAD_FRAMES, esc, progress_bar, safe_edit
from config import (
    COOKIES_FILE,
    MAX_PARALLEL_DOWNLOADS,
    SEARCH_CACHE_MAX,
    SEARCH_CACHE_TTL,
    VIDEO_QUALITY,
)
from db import META, SEARCH_CACHE, remember
from i18n import tr


class PrioSlots:
    """Download slots with a priority line: premium/admin (prio 0) go before everyone else (prio 1); FIFO inside a level."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.running = 0
        self._heap: List[Tuple[Tuple[int, int], asyncio.Future[None]]] = []
        self._seq = itertools.count()

    def ticket(self, prio: int) -> Tuple[int, int]:
        return (prio, next(self._seq))

    def _clean(self) -> None:
        while self._heap and self._heap[0][1].done():
            heapq.heappop(self._heap)

    def position(self, ticket: Tuple[int, int]) -> Optional[int]:
        waiting = sorted(t for t, f in self._heap if not f.done())
        return waiting.index(ticket) + 1 if ticket in waiting else None

    async def acquire(self, ticket: Tuple[int, int]) -> None:
        self._clean()
        if self.running < self.n and not self._heap:
            self.running += 1
            return
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._heap, (ticket, fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.release()
            raise

    def release(self) -> None:
        self._clean()
        while self._heap:
            _, fut = heapq.heappop(self._heap)
            if not fut.done():
                fut.set_result(None)
                return
        self.running -= 1


SLOTS = PrioSlots(MAX_PARALLEL_DOWNLOADS)
LOOKUP_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="lookup")
DL_POOL = ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOWNLOADS, thread_name_prefix="dl")
_tls = threading.local()
_INFLIGHT: Dict[str, asyncio.Future[List[Dict[str, Any]]]] = {}
_http: Optional[httpx.AsyncClient] = None


def http_client() -> httpx.AsyncClient:
    """Shared async HTTP client for thumbnails, Deezer, and GetSongBPM."""
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=10,
            limits=httpx.Limits(max_keepalive_connections=20),
        )
    return _http


async def fetch_thumb(vid: str) -> Optional[bytes]:
    """Download medium-quality YouTube thumbnail bytes."""
    try:
        r = await http_client().get(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg")
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


async def run_lookup(fn: Callable[..., Any], *args: Any) -> Any:
    """Run a quick blocking yt-dlp lookup in LOOKUP_POOL so it never waits behind downloads."""
    return await asyncio.get_running_loop().run_in_executor(LOOKUP_POOL, fn, *args)


def _base_opts() -> Dict[str, Any]:
    """Common yt-dlp options with cookies and node runtime support."""
    o: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 3,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 8,
        "http_chunk_size": 10 * 1024 * 1024,
        "noprogress": True,
        "no_color": True,
        "check_formats": False,
        "throttledratelimit": 100 * 1024,
    }
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        o["cookiefile"] = COOKIES_FILE
    if shutil.which("node"):
        o["js_runtimes"] = {"node": {}}
    return o


def _session(name: str, extra: Dict[str, Any]) -> yt_dlp.YoutubeDL:
    """Reuse one yt-dlp instance per thread in LOOKUP_POOL."""
    y = getattr(_tls, name, None)
    if y is None:
        y = yt_dlp.YoutubeDL(_base_opts() | extra)
        setattr(_tls, name, y)
    return y


def yt_search(query: str) -> List[Dict[str, Any]]:
    """Blocking search for top 5 YouTube results."""
    y = _session("search", {"extract_flat": "in_playlist", "skip_download": True})
    info = y.extract_info(f"ytsearch5:{query}", download=False)
    out: List[Dict[str, Any]] = []
    for e in (info or {}).get("entries") or []:
        if e and e.get("id") and len(e["id"]) == 11:
            out.append(
                {
                    "id": e["id"],
                    "title": e.get("title") or "Unknown",
                    "channel": e.get("channel") or e.get("uploader") or "Unknown",
                    "duration": e.get("duration") or 0,
                    "views": e.get("view_count") or 0,
                }
            )
    return out


def yt_meta(vid: str) -> Dict[str, Any]:
    """Blocking metadata lookup for a single YouTube video ID."""
    y = _session("meta", {"skip_download": True})
    e = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    return {
        "id": vid,
        "title": (e or {}).get("title") or "Unknown",
        "channel": (e or {}).get("channel") or (e or {}).get("uploader") or "Unknown",
        "duration": (e or {}).get("duration") or 0,
        "views": (e or {}).get("view_count") or 0,
    }


def yt_download(
    vid: str,
    fmt: str,
    outdir: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Dict[str, Any]:
    """
    Blocking download of audio ('a') or 480p video ('480') into `outdir`.
    Calls `progress_cb(percent)` from yt-dlp's progress_hooks when provided.
    """
    opts = _base_opts() | {"outtmpl": os.path.join(outdir, "%(id)s.%(ext)s")}
    if progress_cb is not None:
        opts["noprogress"] = False

        def _hook(d: Dict[str, Any]) -> None:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                if total > 0:
                    try:
                        progress_cb(min(100.0, (downloaded * 100.0) / total))
                    except Exception:
                        pass

        opts["progress_hooks"] = [_hook]

    if fmt == "a":
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        h = VIDEO_QUALITY
        opts["format"] = (
            f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}][ext=mp4]/"
            f"bv*[height<={h}]+ba/b[height<={h}]/b"
        )
        opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True)

    path = (((info or {}).get("requested_downloads") or [{}])[0]).get("filepath")
    if not path or not os.path.exists(path):
        files = glob.glob(os.path.join(outdir, f"{vid}.*"))
        if not files:
            raise FileNotFoundError("Download produced no file")
        path = files[0]

    if fmt == "a" and not path.lower().endswith((".m4a", ".mp3")):
        mp3 = os.path.join(outdir, f"{vid}.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vn", "-b:a", "192k", mp3],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        path = mp3
    return {
        "path": path,
        "width": (info or {}).get("width"),
        "height": (info or {}).get("height"),
    }


def split_mode(text: str) -> Tuple[str, Optional[str]]:
    """'Tum Hi Ho a' -> ('Tum Hi Ho', 'a'); 'x v' -> ('x', 'v'); otherwise (text, None)."""
    parts = text.rsplit(None, 1)
    if len(parts) == 2 and parts[1].lower() in ("a", "v"):
        return parts[0].strip(), parts[1].lower()
    return text, None


def fmt_allowed(g: Dict[str, Any], is_audio: bool) -> bool:
    """Return True if audio or video format is allowed in group `g`."""
    return g.get("fmt", "both") in ("both", "audio" if is_audio else "video")


def search_key(text: str) -> str:
    """Normalize search query key for caching."""
    return " ".join(text.lower().split())


def cached_results(text: str) -> Optional[List[Dict[str, Any]]]:
    """Return cached search results if fresh within SEARCH_CACHE_TTL (30 min)."""
    hit = SEARCH_CACHE.get(search_key(text))
    if hit and time.time() - hit[0] < SEARCH_CACHE_TTL:
        return hit[1]
    return None


async def cached_search(text: str) -> List[Dict[str, Any]]:
    """Perform YouTube search with 30-minute cache and in-flight request deduplication."""
    key = search_key(text)
    hit = cached_results(text)
    if hit is not None:
        return hit
    task = _INFLIGHT.get(key)
    if task is None:
        task = asyncio.ensure_future(run_lookup(yt_search, text))
        _INFLIGHT[key] = task
        task.add_done_callback(lambda _t, k=key: _INFLIGHT.pop(k, None))
    results = await asyncio.shield(task)
    if results:
        if len(SEARCH_CACHE) >= SEARCH_CACHE_MAX:
            for k, _ in sorted(SEARCH_CACHE.items(), key=lambda kv: kv[1][0])[: SEARCH_CACHE_MAX // 5]:
                SEARCH_CACHE.pop(k, None)
        SEARCH_CACHE[key] = (time.time(), results)
    return results


async def _meta_for(vid: str) -> Dict[str, Any]:
    """Get metadata for `vid` from cache or YouTube lookup."""
    meta = META.get(vid)
    if not meta:
        meta = await run_lookup(yt_meta, vid)
        remember(meta)
    return meta


async def queued_download(
    card: Optional[Message],
    lang: str,
    title: str,
    label: str,
    running_text: str,
    vid: str,
    fmt: str,
    outdir: str,
    prio: int = 1,
) -> Dict[str, Any]:
    """
    Run a blocking yt_download under SLOTS concurrency limit with:
    1) Queue position updates ("You're #N in line") while waiting for a slot
    2) Animated downloading status frames + live text progress bar [███░░░░░░░] 30%
       fed by yt-dlp progress hooks (updated at most once every 1.5 seconds).
    """
    ticket = SLOTS.ticket(prio)
    shown: Dict[str, Any] = {"pos": None}

    async def watch_queue() -> None:
        while True:
            pos = SLOTS.position(ticket)
            if pos is not None and pos != shown["pos"]:
                shown["pos"] = pos
                await safe_edit(card, tr(lang, "queue", n=pos, title=esc(title[:60])))
            await asyncio.sleep(1.5)

    watcher = asyncio.create_task(watch_queue())
    try:
        await SLOTS.acquire(ticket)
    except BaseException:
        watcher.cancel()
        raise

    progress_state: Dict[str, float] = {"pct": -1.0, "last_edit": 0.0}
    stop_anim = asyncio.Event()

    def on_progress(pct: float) -> None:
        progress_state["pct"] = pct

    async def watch_progress() -> None:
        frame_idx = 0
        while not stop_anim.is_set():
            pct = progress_state["pct"]
            if pct >= 0:
                bar = progress_bar(pct)
                txt = (
                    f"{running_text}\n\n"
                    f"<code>{bar}</code>"
                )
                await safe_edit(card, txt)
            else:
                frame = DOWNLOAD_FRAMES[frame_idx % len(DOWNLOAD_FRAMES)].format(
                    label=label, title=esc(title[:60])
                )
                await safe_edit(card, frame)
                frame_idx += 1
            try:
                await asyncio.wait_for(stop_anim.wait(), timeout=ANIM_DELAY_PROGRESS)
            except asyncio.TimeoutError:
                pass

    prog_task: Optional[asyncio.Task[None]] = None
    try:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        if shown["pos"] is not None:
            await safe_edit(card, running_text)
        prog_task = asyncio.create_task(watch_progress())
        return await asyncio.get_running_loop().run_in_executor(
            DL_POOL, yt_download, vid, fmt, outdir, on_progress
        )
    finally:
        stop_anim.set()
        if prog_task is not None:
            prog_task.cancel()
            try:
                await prog_task
            except asyncio.CancelledError:
                pass
        SLOTS.release()
