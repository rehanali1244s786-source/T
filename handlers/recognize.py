"""
handlers/recognize.py - /find song recognition (AudD with animated "Listening..." frames),
unknown command suggestion (difflib), and catch-all message router.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import shutil
import tempfile
import time
from typing import Any, Optional

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from animations import ANIM_DELAY_FAST, LISTEN_FRAMES, animate_frames, esc, safe_edit
from config import (
    ADMIN_CMDS,
    ALERT_COOLDOWN,
    CMD_EXAMPLE,
    GROUP_TYPES,
    MAX_RECOGNIZE_FILE,
    USER_CMDS,
    is_admin,
    log,
)
from db import (
    ERR,
    ensure_group,
    get_ud,
    gsettings,
    recog_count,
    recog_limit,
    recog_used,
    remember,
)
from handlers.admin import admin_add_flow, admin_set_flow
from handlers.groups import bc_confirm_view, groups_list_view
from handlers.premium import handle_proof
from handlers.search import handle_query
from handlers.song import send_card
from i18n import L, tr
from middlewares import group_ok, notify_admins
from services.audd import audd_identify, make_clip, pick_media
from services.youtube import cached_search

router = Router(name="recognize")


async def recognize_media(
    bot: Bot,
    msg: Message,
    source: Optional[Message],
    user: Any,
) -> None:
    """
    Identify a song from a voice note, audio, or video message:
    - Enforces daily recognition limits (free + referrals vs. premium vs. admin)
    - Animates "Listening.", "Listening..", "Listening..." while ffmpeg + AudD run
    - Shows the recognized track and immediately sends its downloadable song card.
    """
    lang = L(user.id)
    media = pick_media(source)
    if not media:
        await msg.reply(tr(lang, "rec_usage"), parse_mode=ParseMode.HTML)
        return
    if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
        return
    if not is_admin(user.id) and recog_used(user.id) >= recog_limit(user.id):
        await msg.reply(
            tr(lang, "rec_limit", n=recog_limit(user.id)) + "\n\n🎁 /invite  ·  ⭐ /premium",
            parse_mode=ParseMode.HTML,
        )
        return
    if (getattr(media, "file_size", 0) or 0) > MAX_RECOGNIZE_FILE:
        await msg.reply(tr(lang, "rec_big"))
        return

    g = gsettings(msg.chat)
    status = await msg.reply(tr(lang, "rec_listening"), parse_mode=ParseMode.HTML)
    stop_anim = asyncio.Event()
    anim_task = asyncio.create_task(
        animate_frames(status, LISTEN_FRAMES, delay=ANIM_DELAY_FAST, stop_event=stop_anim)
    )
    outdir = tempfile.mkdtemp(prefix="musicbot_rec_")
    try:
        f = await bot.get_file(media.file_id)
        src = os.path.join(outdir, "in")
        clip = os.path.join(outdir, "clip.mp3")
        await bot.download_file(f.file_path, destination=src)
        await asyncio.to_thread(make_clip, src, clip)
        data = await audd_identify(clip)
        if data.get("status") != "success":
            raise RuntimeError(f"AudD: {data.get('error')}")
    except Exception as e:
        log.exception("recognition failed")
        stop_anim.set()
        anim_task.cancel()
        if time.time() - ERR["last"].get("recog", 0) > ALERT_COOLDOWN:
            ERR["last"]["recog"] = time.time()
            await notify_admins(
                bot,
                "🚨 <b>Song recognition is failing</b>\n\n"
                f"<code>{esc(str(e)[:300])}</code>\n\n"
                "🛠 Check <b>AUDD_TOKEN</b> in .env (invalid or out of free requests), and that ffmpeg is installed.",
            )
        await safe_edit(status, tr(lang, "rec_fail"))
        return
    finally:
        stop_anim.set()
        anim_task.cancel()
        try:
            await anim_task
        except asyncio.CancelledError:
            pass
        shutil.rmtree(outdir, ignore_errors=True)

    recog_count(user.id)
    res = data.get("result")
    if not res or not res.get("title"):
        await safe_edit(status, tr(lang, "rec_none"))
        return

    album = f"\n💿 {esc(res['album'])}" if res.get("album") else ""
    await safe_edit(
        status,
        tr(
            lang,
            "rec_found",
            title=esc(res["title"][:90]),
            artist=esc(res.get("artist", "")[:60]),
            album=album,
        ),
    )
    try:
        results = await cached_search(f"{res.get('artist', '')} {res['title']}".strip())
    except Exception:
        results = []
    if results:
        remember(results[0])
        await send_card(bot, msg.chat.id, results[0], g, lang)


@router.message(Command("find"))
async def cmd_find(msg: Message, bot: Bot) -> None:
    """Handle /find command (replying to voice/audio/video in groups or private chat)."""
    if not msg.from_user:
        return
    await recognize_media(bot, msg, msg.reply_to_message, msg.from_user)


# ───────────────────────── Unknown Commands -> Suggest Closest Match ─────────────────────────
@router.message(F.text.startswith("/"))
async def unknown_command(msg: Message, bot: Bot) -> None:
    """Suggest the closest real command via difflib when an unknown /command is sent."""
    user = msg.from_user
    if not msg.text or not user:
        return
    cmd, _, target = msg.text.split()[0][1:].partition("@")
    me = await bot.get_me()
    if target and target.lower() != (me.username or "").lower():
        return
    cmd = cmd.lower()
    pool = USER_CMDS + (ADMIN_CMDS if is_admin(user.id) else [])
    private = msg.chat.type == "private"
    lang = L(user.id)
    if cmd in pool:
        return
    match = difflib.get_close_matches(cmd, pool, n=1, cutoff=0.6 if private else 0.75)
    if match:
        sug = match[0]
        await msg.reply(
            tr(
                lang,
                "unk_suggest",
                cmd=esc(cmd[:30]),
                sug=sug,
                ex=esc(CMD_EXAMPLE.get(sug, f"/{sug}")),
            ),
            parse_mode=ParseMode.HTML,
        )
    elif private:
        lst = "\n".join(
            f"• <code>{esc(CMD_EXAMPLE[c])}</code>"
            for c in USER_CMDS
            if c not in ("ban", "unban", "warn")
        )
        await msg.reply(
            tr(lang, "unk_list", cmd=esc(cmd[:30]), lst=lst),
            parse_mode=ParseMode.HTML,
        )


# ───────────────────────── Catch-All Message Router ─────────────────────────
@router.message()
async def on_message(msg: Message, bot: Bot) -> None:
    """
    Route non-command messages:
    1) Admin private input flows (`await_chat`, `await_set`, `await_gsearch`, `await_bc`)
    2) User payment proof submission (`await_proof`)
    3) Voice / audio / video song recognition in private chat
    4) Plain-text song search in private chat or in groups with `txt` enabled.
    """
    user = msg.from_user
    if not user:
        return
    chat = msg.chat
    ud = get_ud(user.id)

    if is_admin(user.id) and chat.type == "private":
        if ud.get("await_chat"):
            await admin_add_flow(bot, msg)
            return
        if ud.get("await_set"):
            await admin_set_flow(bot, msg)
            return
        if ud.get("await_gsearch") and msg.text:
            ud.pop("await_gsearch", None)
            ud["gq"] = msg.text.strip()
            text, kb = groups_list_view(0, ud)
            await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        if ud.get("await_bc"):
            ud.pop("await_bc", None)
            ud["bc"] = {"cid": chat.id, "mid": msg.message_id, "sel": []}
            text, kb = bc_confirm_view(ud)
            await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

    if chat.type == "private" and ud.get("await_proof"):
        await handle_proof(bot, msg)
        return

    if chat.type == "private" and pick_media(msg):
        await recognize_media(bot, msg, msg, user)
        return

    if not msg.text:
        return
    text = msg.text.strip()
    if chat.type == "private":
        await handle_query(bot, msg, text)
    elif chat.type in GROUP_TYPES and ensure_group(chat).get("txt") and len(text) >= 3:
        await handle_query(bot, msg, text)
