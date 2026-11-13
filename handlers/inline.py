"""
handlers/inline.py - Inline query mode (@bot song name).
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
)

from animations import esc, fmt_dur, fmt_views, meta_line, thumb_url
from config import CREDIT_HTML, is_admin, log
from db import db, remember
from i18n import L, tr
from keyboards import inline_result_markup
from middlewares import missing_chats, report_error, required_chats
from services.youtube import cached_search

router = Router(name="inline")


@router.inline_query()
async def on_inline(iq: InlineQuery, bot: Bot) -> None:
    """Handle @bot <song name> inline queries."""
    user = iq.from_user
    me = await bot.get_me()
    bot_name = me.username or ""
    lang = L(user.id)
    button = InlineQueryResultsButton(text=tr(lang, "inl_open"), start_parameter="start")
    q = iq.query.strip()

    if (user.id in db["banned_global"] and not is_admin(user.id)) or len(q) < 3:
        await iq.answer([], cache_time=5, button=button)
        return

    if not is_admin(user.id) and await missing_chats(bot, user.id, required_chats(None)):
        await iq.answer(
            [],
            cache_time=5,
            button=InlineQueryResultsButton(text=tr(lang, "join_first"), start_parameter="start"),
        )
        return

    try:
        results = await cached_search(q)
    except Exception as e:
        log.exception("inline search failed")
        await report_error(bot, e, "inline search", "", user)
        await iq.answer([], cache_time=5, button=button)
        return

    out = []
    for r in results:
        remember(r)
        kb = inline_result_markup(bot_name, r["id"], lang)
        views = f" · 👁 {fmt_views(r['views'])}" if r.get("views") else ""
        out.append(
            InlineQueryResultArticle(
                id=r["id"],
                title=r["title"][:80],
                description=f"{r['channel'][:30]} · {fmt_dur(r['duration'])}{views}",
                thumbnail_url=thumb_url(r["id"]),
                input_message_content=InputTextMessageContent(
                    message_text=f"🎶 <b>{esc(r['title'][:90])}</b>\n{meta_line(r)}{CREDIT_HTML}",
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=kb,
            )
        )
    await iq.answer(out, cache_time=300, button=button)
