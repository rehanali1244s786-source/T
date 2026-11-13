"""
handlers/search.py - /search command, query handling with animated "Searching..." frames, and song picker callback.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from animations import (
    ANIM_DELAY_FAST,
    SEARCH_FRAMES,
    animate_frames,
    autodel,
    esc,
    meta_line,
    safe_edit,
)
from config import GDEF, NUMS, SPON, YT_RE, log
from db import META, gsettings, remember
from handlers.song import direct_download, send_card
from i18n import L, tr
from keyboards import search_results_markup
from middlewares import error_hint, group_ok, report_error
from services.youtube import (
    cached_results,
    cached_search,
    run_lookup,
    split_mode,
    yt_meta,
)

router = Router(name="search")


def results_body(
    results: List[Dict[str, Any]],
    text: str,
    lang: str,
    g: Dict[str, Any] = GDEF,
) -> Tuple[str, InlineKeyboardMarkup]:
    """Build numbered search results text and MP3/MP4 + picker inline keyboard."""
    lines = [tr(lang, "results_title", q=esc(text[:60]))]
    for i, r in enumerate(results[:5]):
        remember(r)
        lines.append(f"{NUMS[i]} <b>{esc(r['title'][:55])}</b>\n      {meta_line(r)}")
    lines.append(tr(lang, "tap") + SPON)
    return "\n".join(lines), search_results_markup(results[:5], g)


async def handle_query(
    bot: Bot,
    msg: Message,
    text: str,
    list_only: bool = False,
) -> None:
    """
    Process a song query or YouTube URL:
    - `list_only=True` (/search): always show the numbered results list with MP3/MP4 buttons
    - `list_only=False` (/song or text search): supports trailing `a` or `v` for immediate download,
      and animates "Searching.", "Searching..", "Searching..." in place until results arrive.
    """
    user = msg.from_user
    if not user:
        return
    if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
        return
    g = gsettings(msg.chat)
    lang = L(user.id)
    mode: Optional[str] = None
    if not list_only:
        text, mode = split_mode(text)

    # Check if the query is a direct YouTube link
    m = YT_RE.search(text)
    if m:
        vid = m.group(1)
        meta = META.get(vid)
        status: Optional[Message] = None
        if meta is None:
            status = await msg.reply(tr(lang, "fetching"), parse_mode=ParseMode.HTML)
            try:
                meta = await run_lookup(yt_meta, vid)
                remember(meta)
            except Exception as e:
                log.exception("meta failed for %s", vid)
                await report_error(bot, e, "link info", vid, user)
                await safe_edit(status, tr(lang, "bad_link"))
                return
        if mode:
            if status is None:
                status = await msg.reply(tr(lang, "fetching"), parse_mode=ParseMode.HTML)
            await direct_download(bot, msg, status, vid, mode, g)
            return
        await send_card(bot, msg.chat.id, meta, g, lang)
        if status:
            try:
                await status.delete()
            except TelegramAPIError:
                pass
        return

    # Fast path: cached search -> answer immediately
    results = cached_results(text)
    status = None
    if results is None:
        search_task = asyncio.ensure_future(cached_search(text))
        stop_anim = asyncio.Event()
        anim_task: Optional[asyncio.Task[None]] = None
        try:
            q_escaped = esc(text[:80])
            frames = [f.format(q=q_escaped) for f in SEARCH_FRAMES]
            status = await msg.reply(frames[0], parse_mode=ParseMode.HTML)
            anim_task = asyncio.create_task(
                animate_frames(status, frames[1:], delay=ANIM_DELAY_FAST, stop_event=stop_anim)
            )
        except TelegramAPIError:
            status = None
        try:
            results = await search_task
        except Exception as e:
            log.exception("search failed for %r", text)
            stop_anim.set()
            if anim_task:
                anim_task.cancel()
            await report_error(bot, e, "search", "", user)
            if status:
                await safe_edit(status, tr(lang, "search_failed", hint=error_hint(e, lang)))
            else:
                await msg.reply(
                    tr(lang, "search_failed", hint=error_hint(e, lang)),
                    parse_mode=ParseMode.HTML,
                )
            return
        finally:
            stop_anim.set()
            if anim_task:
                anim_task.cancel()
                try:
                    await anim_task
                except asyncio.CancelledError:
                    pass

    if not results:
        if status:
            await safe_edit(status, tr(lang, "no_results"))
        else:
            await msg.reply(tr(lang, "no_results"), parse_mode=ParseMode.HTML)
        return

    if mode:
        remember(results[0])
        if status is None:
            status = await msg.reply(tr(lang, "fetching"), parse_mode=ParseMode.HTML)
        await direct_download(bot, msg, status, results[0]["id"], mode, g)
        return

    body, kb = results_body(results, text, lang, g)
    if status:
        await safe_edit(status, body, kb)
        autodel(status, g)
    else:
        sent = await msg.reply(
            body,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        autodel(sent, g)


@router.message(Command("search"))
async def cmd_search(msg: Message, command: CommandObject, bot: Bot) -> None:
    """/search <name> -> numbered list of results (title, channel, duration, views) with MP3/MP4 buttons."""
    user = msg.from_user
    if not user:
        return
    if not command.args:
        await msg.reply(tr(L(user.id), "search_usage"), parse_mode=ParseMode.HTML)
        return
    await handle_query(bot, msg, command.args.strip(), list_only=True)


@router.callback_query(F.data.startswith("p:"))
async def cb_pick(cq: CallbackQuery, bot: Bot) -> None:
    """Handle picking a numbered song result to open its full song card."""
    if not cq.message:
        await cq.answer()
        return
    chat = cq.message.chat
    if not await group_ok(bot, chat, cq.from_user, cq=cq):
        return
    await cq.answer()
    lang = L(cq.from_user.id)
    vid = cq.data.split(":", 1)[1]
    try:
        meta = META.get(vid) or await run_lookup(yt_meta, vid)
        remember(meta)
    except Exception as e:
        await report_error(bot, e, "pick info", vid, cq.from_user)
        await safe_edit(cq.message, tr(lang, "load_failed"))
        return
    await asyncio.gather(
        send_card(bot, chat.id, meta, gsettings(chat), lang),
        cq.message.delete(),
        return_exceptions=True,
    )
