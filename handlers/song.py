"""
handlers/song.py - /song, /lyrics, song cards, downloads, lyrics, song info, librosa BPM/key analysis, and share cards.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from typing import Any, Dict, Optional
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message

from animations import (
    autodel,
    bordered_table,
    card_text,
    esc,
    fancy,
    fmt_dur,
    keep_action,
    safe_edit,
    thumb_url,
)
from config import (
    HAVE_LIBROSA,
    MAX_AUDIO_DURATION,
    MAX_FILE_SIZE,
    MAX_VIDEO_DURATION,
    VIDEO_QUALITY,
    log,
)
from db import META, db, gsettings, is_premium, record, remember, touch
from i18n import L, tr
from keyboards import card_markup, info_markup, share_markup
from middlewares import error_hint, group_ok, report_error, report_ok
from services.bpm import analyze_audio, song_info
from services.lyrics import clean_title, fetch_lyrics
from services.youtube import (
    _meta_for,
    fetch_thumb,
    fmt_allowed,
    queued_download,
    run_lookup,
    yt_meta,
)

router = Router(name="song")


async def send_card(
    bot: Bot,
    chat_id: int,
    meta: Dict[str, Any],
    g: Dict[str, Any],
    lang: str = "en",
) -> Message:
    """Send a song card with thumbnail photo and Audio/Video/Lyrics/Info/Share/BPM buttons."""
    vid = meta["id"]
    caption = card_text(meta, lang)
    kb = card_markup(vid, g, lang)
    try:
        m = await bot.send_photo(
            chat_id=chat_id,
            photo=thumb_url(vid),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    except TelegramAPIError:
        m = await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    autodel(m, g)
    return m


async def direct_download(
    bot: Bot,
    msg: Message,
    status: Message,
    vid: str,
    mode: str,
    g: Dict[str, Any],
) -> None:
    """/song <name|link> a|v -> skip the picker and download straight away."""
    user = msg.from_user
    if not user:
        return
    is_audio = mode == "a"
    if not fmt_allowed(g, is_audio):
        await safe_edit(status, tr(L(user.id), "disabled"))
        return
    await run_download(bot, status.chat, user, status, vid, is_audio, g)


async def run_download(
    bot: Bot,
    chat: Any,
    user: Any,
    card: Message,
    vid: str,
    is_audio: bool,
    g: Dict[str, Any],
) -> None:
    """
    Execute audio or 480p video download:
    - Checks Telegram file_id cache first for instant delivery
    - Enforces duration and 50 MB size limits
    - Runs in DL_POOL via queued_download with priority queue, animated frames, and live progress bar
    - Uploads file, caches Telegram file_id, and deletes the status message.
    """
    fmt = "a" if is_audio else str(VIDEO_QUALITY)
    lang = L(user.id)

    meta = META.get(vid)
    if not meta:
        try:
            meta = await run_lookup(yt_meta, vid)
            remember(meta)
        except Exception as e:
            await report_error(bot, e, "download info", vid, user)
            await safe_edit(card, tr(lang, "load_failed"))
            return

    label = tr(lang, "label_audio" if is_audio else "label_video")
    me_obj = await bot.get_me()
    me = me_obj.username or "bot"
    caption = f"🎶 <b>{esc(meta['title'][:150])}</b>\n{label}\n\n🤖 @{esc(me)}"
    key = f"{vid}:{fmt}"
    kind = "a" if is_audio else "v"

    async def send_file(
        media: Any,
        thumb_bytes: Optional[bytes] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Message:
        extra = extra or {}
        thumb_file = (
            BufferedInputFile(thumb_bytes, filename="thumb.jpg") if thumb_bytes else None
        )
        if is_audio:
            return await bot.send_audio(
                chat_id=chat.id,
                audio=media,
                title=meta["title"][:64],
                performer=meta["channel"][:64],
                duration=int(meta["duration"] or 0),
                caption=caption,
                parse_mode=ParseMode.HTML,
                thumbnail=thumb_file,
                request_timeout=300,
            )
        return await bot.send_video(
            chat_id=chat.id,
            video=media,
            duration=int(meta["duration"] or 0),
            caption=caption,
            parse_mode=ParseMode.HTML,
            supports_streaming=True,
            thumbnail=thumb_file,
            request_timeout=300,
            **extra,
        )

    # Check Telegram file_id cache first
    cached = db["cache"].get(key)
    if cached:
        try:
            sent = await send_file(cached)
            autodel(sent, g)
            record(chat, user, meta, kind)
            try:
                await card.delete()
            except TelegramAPIError:
                pass
            return
        except TelegramAPIError:
            db["cache"].pop(key, None)

    default_limit = MAX_AUDIO_DURATION if is_audio else MAX_VIDEO_DURATION
    limit = min(default_limit, int(g.get("dur", 0)) * 60) if g.get("dur") else default_limit
    if meta.get("duration") and int(meta["duration"]) > limit:
        await safe_edit(card, tr(lang, "too_long", n=limit // 60), card_markup(vid, g, lang))
        return

    running = tr(lang, "downloading", label=label, title=esc(meta["title"][:60]))
    await safe_edit(card, running)
    action = ChatAction.UPLOAD_VOICE if is_audio else ChatAction.UPLOAD_VIDEO
    keeper = asyncio.create_task(keep_action(bot, chat.id, action))
    outdir = tempfile.mkdtemp(prefix="musicbot_")
    try:
        thumb_task = asyncio.create_task(fetch_thumb(vid))
        data = await queued_download(
            card=card,
            lang=lang,
            title=meta["title"],
            label=label,
            running_text=running,
            vid=vid,
            fmt=fmt,
            outdir=outdir,
            prio=0 if is_premium(user.id) else 1,
        )
        size = os.path.getsize(data["path"])
        if size > MAX_FILE_SIZE:
            await safe_edit(
                card,
                tr(lang, "too_big", mb=size // (1024 * 1024)),
                card_markup(vid, g, lang),
            )
            return
        await safe_edit(card, tr(lang, "uploading", label=label))
        thumb_bytes = await thumb_task
        extra: Dict[str, Any] = {}
        if not is_audio and data.get("width") and data.get("height"):
            extra = {"width": data["width"], "height": data["height"]}
        fs_file = FSInputFile(data["path"])
        sent = await send_file(fs_file, thumb_bytes, extra)
        media_obj = sent.audio if is_audio else sent.video
        if media_obj:
            db["cache"][key] = media_obj.file_id
            touch()
        autodel(sent, g)
        record(chat, user, meta, kind)
        await report_ok(bot)
        try:
            await card.delete()
        except TelegramAPIError:
            pass
    except Exception as e:
        log.exception("download failed %s", key)
        await report_error(bot, e, f"download {key}", vid, user)
        await safe_edit(
            card,
            tr(lang, "failed", hint=error_hint(e, lang)),
            card_markup(vid, g, lang),
        )
    finally:
        keeper.cancel()
        shutil.rmtree(outdir, ignore_errors=True)


@router.message(Command("song"))
async def cmd_song(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /song <query> [a|v]."""
    user = msg.from_user
    if not user:
        return
    if not command.args:
        await msg.reply(tr(L(user.id), "song_usage"), parse_mode=ParseMode.HTML)
        return
    from handlers.search import handle_query

    await handle_query(bot, msg, command.args.strip(), list_only=False)


@router.callback_query(F.data.startswith("d:"))
async def cb_download(cq: CallbackQuery, bot: Bot) -> None:
    """Handle Audio / Video 480p download button clicks."""
    card = cq.message
    user = cq.from_user
    if not card:
        await cq.answer()
        return
    chat = card.chat
    if not await group_ok(bot, chat, user, cq=cq):
        return
    g = gsettings(chat)
    _, fmt, vid = cq.data.split(":", 2)
    is_audio = fmt == "a"

    if not fmt_allowed(g, is_audio):
        await cq.answer(tr(L(user.id), "disabled"), show_alert=True)
        return
    await cq.answer("⏳")
    await run_download(bot, chat, user, card, vid, is_audio, g)


# ───────────────────────── Lyrics ─────────────────────────
async def send_lyrics(target: Message, user: Any, query: str) -> None:
    """Look up and send song lyrics in up to 3 chunks."""
    lang = L(user.id)
    status = await target.reply(tr(lang, "lyr_search", q=esc(query[:80])), parse_mode=ParseMode.HTML)
    try:
        item = await fetch_lyrics(query)
    except Exception:
        log.exception("lyrics failed")
        await safe_edit(status, tr(lang, "lyr_fail"))
        return
    if not item:
        await safe_edit(status, tr(lang, "lyr_none"))
        return
    head = f"🎤 <b>{esc(item.get('trackName', query))}</b> — {esc(item.get('artistName', ''))}\n\n"
    text = item["plainLyrics"].strip()
    chunks = [text[i : i + 3600] for i in range(0, len(text), 3600)][:3]
    await safe_edit(status, head + esc(chunks[0]))
    for c in chunks[1:]:
        await target.reply(esc(c), parse_mode=ParseMode.HTML)


@router.message(Command("lyrics"))
async def cmd_lyrics(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /lyrics <song>."""
    user = msg.from_user
    if not user:
        return
    if not command.args:
        await msg.reply(tr(L(user.id), "lyr_usage"), parse_mode=ParseMode.HTML)
        return
    if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
        return
    await send_lyrics(msg, user, command.args.strip())


@router.callback_query(F.data.startswith("ly:"))
async def cb_lyrics(cq: CallbackQuery, bot: Bot) -> None:
    """Handle 🎤 Lyrics button on song cards."""
    if not cq.message:
        await cq.answer()
        return
    if not await group_ok(bot, cq.message.chat, cq.from_user, cq=cq):
        return
    await cq.answer()
    vid = cq.data.split(":", 1)[1]
    meta = META.get(vid)
    if not meta:
        try:
            meta = await run_lookup(yt_meta, vid)
            remember(meta)
        except Exception:
            await bot.send_message(cq.message.chat.id, tr(L(cq.from_user.id), "load_failed"))
            return
    query = clean_title(meta["title"])
    await send_lyrics(cq.message, cq.from_user, query)


# ───────────────────────── Song Info & Librosa BPM/Key Analysis ─────────────────────────
def info_view(meta: Dict[str, Any], info: Dict[str, Any]) -> tuple[str, Any]:
    """Build Song Info screen with centered bold description and bordered table."""
    dash = "—"
    if info.get("album"):
        album_html = esc(info["album"]) + (
            f" <i>({esc(info['album_type'])})</i>" if info.get("album_type") else ""
        )
        album_plain = str(info["album"]) + (
            f" ({info['album_type']})" if info.get("album_type") else ""
        )
    else:
        album_html = f"<i>{dash}</i>"
        album_plain = dash

    rows_html = [
        ("Title", f"<b>{esc((info.get('mb_title') or info['title'])[:70])}</b>"),
        ("Artist", esc((info.get("mb_artist") or info["artist"])[:50]) or f"<i>{dash}</i>"),
        ("Album", album_html),
        ("Release year", esc(info["year"]) if info.get("year") else f"<i>{dash}</i>"),
        ("Genre", esc(", ".join(info["genres"])) if info.get("genres") else f"<i>{dash}</i>"),
        ("BPM", f"<b>{esc(info['bpm'])}</b>" if info.get("bpm") else f"<i>{dash}</i>"),
        ("Key", f"<b>{esc(info['key'])}</b>" if info.get("key") else f"<i>{dash}</i>"),
        ("Duration", fmt_dur(meta["duration"])),
        ("Status", "🟢 Online"),
    ]
    rows_table = [
        ("Title", str(info.get("mb_title") or info["title"])[:24]),
        ("Artist", str(info.get("mb_artist") or info["artist"] or dash)[:24]),
        ("Album", album_plain[:24]),
        ("Year", str(info.get("year") or dash)),
        ("Genre", (", ".join(info.get("genres") or []) or dash)[:24]),
        ("BPM", str(info.get("bpm") or dash)),
        ("Key", str(info.get("key") or dash)),
        ("Duration", fmt_dur(meta["duration"])),
        ("Status", "🟢 Online"),
    ]
    src = ["📚 MusicBrainz"] if info.get("mb_title") else ["⚠️ Not found on MusicBrainz"]
    if info.get("bpm_src"):
        src.append(f"🎚 BPM/key: {info['bpm_src']}")
    elif not info.get("bpm"):
        src.append("🎚 BPM/key: not available for this song")

    text = (
        fancy("ℹ️", "Song Info", rows_html, note=" · ".join(src))
        + "\n\n"
        + bordered_table(rows_table, headers=("Attribute", "Value"))
    )
    kb = info_markup(meta["id"], info)
    return text, kb


@router.callback_query(F.data.startswith("in:"))
async def cb_info(cq: CallbackQuery, bot: Bot) -> None:
    """Handle ℹ️ Info button on song card."""
    if not cq.message:
        await cq.answer()
        return
    chat = cq.message.chat
    if not await group_ok(bot, chat, cq.from_user, cq=cq):
        return
    await cq.answer()
    vid = cq.data.split(":", 1)[1]
    try:
        meta = await _meta_for(vid)
    except Exception:
        await bot.send_message(chat.id, tr(L(cq.from_user.id), "load_failed"))
        return
    status = await bot.send_message(
        chat.id,
        fancy("ℹ️", "Song Info", note="🔎 Looking up album, year, genre, BPM and key…"),
        parse_mode=ParseMode.HTML,
    )
    info = await song_info(meta)
    text, kb = info_view(meta, info)
    await safe_edit(status, text, kb)
    autodel(status, gsettings(chat))


@router.callback_query(F.data.startswith("bk:"))
async def cb_bpm(cq: CallbackQuery, bot: Bot) -> None:
    """Handle 🎚 Analyze BPM & key button."""
    if not cq.message:
        await cq.answer()
        return
    chat, user = cq.message.chat, cq.from_user
    if not await group_ok(bot, chat, user, cq=cq):
        return
    if not HAVE_LIBROSA:
        await cq.answer(
            "Local librosa audio analysis is not installed on this server (Deezer/GetSongBPM are used in ℹ️ Info).",
            show_alert=True,
        )
        return
    await cq.answer("🎚")
    lang = L(user.id)
    vid = cq.data.split(":", 1)[1]
    try:
        meta = await _meta_for(vid)
    except Exception:
        await bot.send_message(chat.id, tr(lang, "load_failed"))
        return

    def result_text(res: Dict[str, str]) -> str:
        return fancy(
            "🎚",
            "Analysis result",
            [
                ("Song", esc(meta["title"][:60])),
                ("BPM", f"<b>{esc(res['bpm'])}</b>"),
                ("Key", f"<b>{esc(res['key'])}</b>"),
            ],
            note="Estimated from the audio — can be off by a half/double tempo or the relative key.",
        )

    if vid in db["bpm"]:
        await bot.send_message(chat.id, result_text(db["bpm"][vid]), parse_mode=ParseMode.HTML)
        return
    if meta.get("duration") and int(meta["duration"]) > MAX_VIDEO_DURATION:
        await bot.send_message(
            chat.id,
            fancy("🎚", "Too long", note=f"Analysis works for songs up to {MAX_VIDEO_DURATION // 60} minutes."),
            parse_mode=ParseMode.HTML,
        )
        return

    running = fancy("🎚", "Analyzing…", note="Detecting tempo and key — about 20–40 seconds.")
    status = await bot.send_message(chat.id, running, parse_mode=ParseMode.HTML)
    outdir = tempfile.mkdtemp(prefix="musicbot_bpm_")
    try:
        data = await queued_download(
            card=status,
            lang=lang,
            title=meta["title"],
            label="🎚 Audio Analysis",
            running_text=running,
            vid=vid,
            fmt="a",
            outdir=outdir,
            prio=0 if is_premium(user.id) else 1,
        )
        res = await asyncio.to_thread(analyze_audio, data["path"])
        if len(db["bpm"]) > 2000:
            db["bpm"].pop(next(iter(db["bpm"])), None)
        db["bpm"][vid] = res
        touch()
        await safe_edit(status, result_text(res))
    except Exception as e:
        log.exception("bpm analysis failed")
        await report_error(bot, e, f"bpm {vid}", vid, user)
        await safe_edit(status, fancy("❌", "Analysis failed", note=esc(error_hint(e, lang))))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


# ───────────────────────── Share Card ─────────────────────────
@router.callback_query(F.data.startswith("sh:"))
async def cb_share(cq: CallbackQuery, bot: Bot) -> None:
    """Handle 🔗 Share button on song card."""
    if not cq.message:
        await cq.answer()
        return
    chat = cq.message.chat
    if not await group_ok(bot, chat, cq.from_user, cq=cq):
        return
    await cq.answer()
    vid = cq.data.split(":", 1)[1]
    try:
        meta = await _meta_for(vid)
    except Exception:
        await bot.send_message(chat.id, tr(L(cq.from_user.id), "load_failed"))
        return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=song_{vid}"
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote('🎧 ' + meta['title'][:80])}"
    text = (
        f"🎁 <b>{esc(meta['title'][:90])}</b>\n\n"
        f"🟦 👤 {esc(meta['channel'][:40])}\n🟩 ⏱ {fmt_dur(meta['duration'])}\n\n"
        "<blockquote>Tap <b>Open in bot</b> to listen &amp; download this song instantly.</blockquote>\n"
        f"🔗 <code>{link}</code>"
    )
    kb = share_markup(link, share_url)
    try:
        m = await bot.send_photo(
            chat.id,
            photo=thumb_url(vid),
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    except TelegramAPIError:
        m = await bot.send_message(
            chat.id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    autodel(m, gsettings(chat))
