"""
animations.py - Animation frames, delays (0.8s - 1.5s), progress bars, bordered tables, and safe message editors.
"""

from __future__ import annotations

import asyncio
import html
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aiogram import Bot
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, Message

from config import (
    BOT_VERSION,
    CREDIT_USER,
    GDEF,
    MONO_FOOTER,
    RAINBOW,
    SPON,
    SQ,
    log,
)
from db import _bg, db
from i18n import tr

# ───────────────────────── Animation Frame Delays (0.8s – 1.5s) ─────────────────────────
ANIM_DELAY_FAST: float = 0.85
ANIM_DELAY_STD: float = 1.0
ANIM_DELAY_PROGRESS: float = 1.5

# /start loading frames (matching "ITX TALHA PREPARING..." style in video)
START_FRAMES: List[str] = [
    "🕸 <b>DOCK MUSIC BOT PREPARING.</b>",
    "🕸 <b>DOCK MUSIC BOT PREPARING..</b>",
    "🕸 <b>DOCK MUSIC BOT PREPARING...</b>",
]

# Searching animation frames
SEARCH_FRAMES: List[str] = [
    "🔎 <b>Searching.</b>\n<i>{q}</i>",
    "🔎 <b>Searching..</b>\n<i>{q}</i>",
    "🔎 <b>Searching...</b>\n<i>{q}</i>",
]

# Downloading initial animation frames
DOWNLOAD_FRAMES: List[str] = [
    "⏬ <b>Downloading.</b>\n{label}\n<i>{title}</i>",
    "⏬ <b>Downloading..</b>\n{label}\n<i>{title}</i>",
    "⏬ <b>Downloading...</b>\n{label}\n<i>{title}</i>",
]

# Recognition (/find) listening frames
LISTEN_FRAMES: List[str] = [
    "🎧 <b>Listening.</b>\nIdentifying the song, please wait.",
    "🎧 <b>Listening..</b>\nIdentifying the song, please wait.",
    "🎧 <b>Listening...</b>\nIdentifying the song, please wait.",
]


# ───────────────────────── Formatting Helpers ─────────────────────────
def esc(s: Any) -> str:
    """HTML-escape any value safely."""
    return html.escape(str(s or ""))


def fmt_dur(sec: Any) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    sec_i = int(sec or 0)
    h, r = divmod(sec_i, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_views(n: Any) -> str:
    """Format view count as K/M/B."""
    n_i = int(n or 0)
    if n_i >= 1_000_000_000:
        return f"{n_i / 1_000_000_000:.1f}B".replace(".0B", "B")
    if n_i >= 1_000_000:
        return f"{n_i / 1_000_000:.1f}M".replace(".0M", "M")
    if n_i >= 1_000:
        return f"{n_i / 1_000:.1f}K".replace(".0K", "K")
    return str(n_i)


def ago(ts: Any) -> str:
    """Format elapsed time since unix timestamp `ts`."""
    d = int(time.time()) - int(ts or 0)
    if d < 60:
        return "now"
    if d < 3600:
        return f"{d // 60}m"
    if d < 86400:
        return f"{d // 3600}h"
    return f"{d // 86400}d"


def thumb_url(vid: str) -> str:
    """Return YouTube HQ thumbnail URL."""
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def progress_bar(percent: float, width: int = 10) -> str:
    """Build a text progress bar such as [███░░░░░░░] 30%."""
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round((pct / 100.0) * width))
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {int(round(pct))}%"


def bordered_table(
    rows: Sequence[Tuple[str, str]],
    headers: Tuple[str, str] = ("Information", "Details"),
) -> str:
    """
    Build a clean bordered ASCII/Unicode box table inside <pre> with label on the left
    and value on the right (matching the video's Information | Details table).
    """
    clean_rows = [(str(k), str(v)) for k, v in rows]
    w1 = max([len(headers[0])] + [len(k) for k, _ in clean_rows] + [11])
    w2 = max([len(headers[1])] + [len(v) for _, v in clean_rows] + [14])
    w1 = min(w1, 18)
    w2 = min(w2, 26)

    top = f"┌─{'─' * w1}─┬─{'─' * w2}─┐"
    sep = f"├─{'─' * w1}─┼─{'─' * w2}─┤"
    bot = f"└─{'─' * w1}─┴─{'─' * w2}─┘"

    lines = [
        top,
        f"│ {headers[0][:w1]:<{w1}} │ {headers[1][:w2]:<{w2}} │",
        sep,
    ]
    for i, (k, v) in enumerate(clean_rows):
        lines.append(f"│ {k[:w1]:<{w1}} │ {v[:w2]:<{w2}} │")
        if i < len(clean_rows) - 1:
            lines.append(sep)
    lines.append(bot)
    return "<pre>" + esc("\n".join(lines)) + "</pre>"


def fancy(
    icon: str,
    title: str,
    rows: Iterable[Tuple[str, str]] = (),
    note: str = "",
    tail: str = "",
    table_headers: Optional[Tuple[str, str]] = None,
) -> str:
    """
    Colourful card with rainbow bars, coloured squares, centered bold quote description,
    and optional bordered table. Values in `rows` may contain HTML tags.
    """
    rows_list = list(rows)
    out = [RAINBOW, f"{icon} <b>{esc(title)}</b>", RAINBOW, ""]
    if note:
        out += [f"<blockquote><b>{note}</b></blockquote>", ""]
    for i, (label, value) in enumerate(rows_list):
        out.append(f"{SQ[i % 6]} <b>{label}</b> · {value}")
    if table_headers and rows_list:
        plain_rows = [
            (
                label,
                value.replace("<b>", "")
                .replace("</b>", "")
                .replace("<code>", "")
                .replace("</code>", "")
                .replace("<i>", "")
                .replace("</i>", ""),
            )
            for label, value in rows_list
        ]
        out += ["", bordered_table(plain_rows, headers=table_headers)]
    if tail:
        out += ["", tail]
    return "\n".join(out)


def welcome_card_text(user: Any, lang: str) -> str:
    """
    Build the final /start welcome card matching the video ('ITX TALHA BUG BOT' style)
    while preserving the localized greeting, commands, and features.
    """
    name = esc(getattr(user, "first_name", None) or "User")
    mode_str = "Maintenance" if db.get("maintenance") else "Public"
    status_str = "🟢 Online" if not db.get("maintenance") else "🟠 Maintenance"
    table = bordered_table(
        [
            ("Tagline", "Music & Video Downloader"),
            ("Creator", CREDIT_USER),
            ("Version", BOT_VERSION),
            ("Type", "Main Music Bot"),
            ("Mode Bot", mode_str),
            ("Status", status_str),
        ],
        headers=("Information", "Details"),
    )
    base_greeting = tr(lang, "start", name=name)
    return (
        f"🕸 <b>DOCK MUSIC &amp; VIDEO BOT</b>\n\n"
        f"<b>Hello — {name}!</b>\n\n"
        f"<blockquote><b>A high-speed Telegram Music &amp; 480p Video Downloader with Song Recognition, Lyrics, Artist Alerts &amp; Group Manager.</b></blockquote>\n\n"
        f"⚡ <b>Your Ultimate Music Experience!</b>\n"
        f"🚀 <b>Audio (MP3/M4A) &amp; 480p Video (MP4)</b>\n"
        f"💎 <b>Fast, Smooth &amp; Priority Queue</b>\n"
        f"🛡️ <b>AudD Recognition, Lyrics &amp; BPM/Key</b>\n\n"
        f"{table}\n\n"
        f"{ base_greeting }\n\n"
        f"{MONO_FOOTER}{SPON}"
    )


def meta_line(m: Dict[str, Any]) -> str:
    """Single-line metadata summary (channel, duration, views)."""
    bits = [f"👤 {esc(m['channel'][:30])}", f"⏱ {fmt_dur(m['duration'])}"]
    if m.get("views"):
        bits.append(f"👁 {fmt_views(m['views'])}")
    return " · ".join(bits)


def card_text(meta: Dict[str, Any], lang: str = "en") -> str:
    """Build caption/text for a song card."""
    lines = [
        f"🎶 <b>{esc(meta['title'][:90])}</b>",
        "",
        f"🟦 👤 {esc(meta['channel'][:40])}",
        f"🟩 ⏱ {fmt_dur(meta['duration'])}",
    ]
    if meta.get("views"):
        lines.append(f"🟨 👁 {fmt_views(meta['views'])} {tr(lang, 'views')}")
    return "\n".join(lines) + f"\n\n{tr(lang, 'choose')}"


# ───────────────────────── Safe Edit & Animation Runners ─────────────────────────
async def safe_edit(
    msg: Optional[Message],
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> Optional[Message]:
    """
    Safely edit a message's text or caption.
    Ignores 'message is not modified' errors and waits on TelegramRetryAfter.
    """
    if msg is None:
        return None
    for attempt in (1, 2):
        try:
            if msg.photo:
                return await msg.edit_caption(
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                )
            return await msg.edit_text(
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
        except TelegramRetryAfter as e:
            if attempt == 1:
                await asyncio.sleep(min(float(e.retry_after) + 0.5, 10.0))
                continue
        except TelegramBadRequest as e:
            if "not modified" not in str(e).lower():
                log.warning("edit failed: %s", e)
        except TelegramAPIError as e:
            log.warning("edit failed: %s", e)
        break
    return None


async def animate_frames(
    msg: Optional[Message],
    frames: Sequence[str],
    delay: float = ANIM_DELAY_FAST,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Step through `frames` on `msg` with `delay` between 0.8s and 1.5s.
    If `stop_event` is provided, loops frames until `stop_event.is_set()`.
    """
    if msg is None or not frames:
        return
    step_delay = max(0.8, min(1.5, float(delay)))
    try:
        if stop_event is None:
            for frame in frames:
                await safe_edit(msg, frame)
                await asyncio.sleep(step_delay)
        else:
            idx = 0
            while not stop_event.is_set():
                frame = frames[idx % len(frames)]
                await safe_edit(msg, frame)
                idx += 1
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=step_delay)
                except asyncio.TimeoutError:
                    pass
    except (asyncio.CancelledError, TelegramAPIError):
        pass


async def keep_action(bot: Bot, chat_id: int, action: ChatAction) -> None:
    """Continuously send chat action (typing, upload_voice, upload_video) every 4 seconds."""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)
    except (asyncio.CancelledError, TelegramAPIError):
        pass


async def _del_later(msg: Message, secs: int) -> None:
    """Delete a message after `secs` seconds."""
    try:
        await asyncio.sleep(secs)
        await msg.delete()
    except (asyncio.CancelledError, TelegramAPIError):
        pass


def autodel(msg: Optional[Message], g: Dict[str, Any] = GDEF, secs: int = 0) -> None:
    """Schedule automatic deletion of `msg` if configured for the group."""
    delay = secs or int(g.get("del", 0) or 0)
    if msg and delay > 0:
        t = asyncio.create_task(_del_later(msg, delay))
        _bg.add(t)
        t.add_done_callback(_bg.discard)
