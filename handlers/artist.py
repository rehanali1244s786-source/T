"""
handlers/artist.py - /artist command and artist page callbacks (bio, latest releases, top songs, Follow button).
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from animations import autodel, esc, fancy, meta_line, safe_edit
from config import NUMS, SPON, log
from db import gsettings, remember
from i18n import L, tr
from keyboards import artist_markup
from middlewares import group_ok
from services.musicbrainz import (
    mb_artist_by_id,
    mb_artist_search,
    mb_release_groups,
)
from services.youtube import cached_search

router = Router(name="artist")


async def show_artist(
    status: Message,
    user: Any,
    name: Optional[str] = None,
    mbid: Optional[str] = None,
) -> None:
    """Fetch artist profile, release groups, and top 5 YouTube songs, then edit `status`."""
    lang = L(user.id)
    art = None
    rgs: List[dict] = []
    try:
        art = await (mb_artist_by_id(mbid) if mbid else mb_artist_search(name or ""))
        if art:
            rgs = await mb_release_groups(art["id"])
    except Exception as e:
        log.warning("artist lookup failed: %s", e)

    qname = art["name"] if art else (name or "")
    try:
        songs = await cached_search(f"{qname} songs")
    except Exception:
        songs = []

    if not art and not songs:
        await safe_edit(status, tr(lang, "no_results"))
        return

    rows: List[Tuple[str, str]] = []
    if art:
        rows.append(
            (
                "Artist",
                f"<b>{esc(art['name'])}</b>"
                + (f" <i>({esc(art['dis'])})</i>" if art["dis"] else ""),
            )
        )
        if art["type"]:
            rows.append(("Type", esc(art["type"])))
        if art["country"]:
            rows.append(("Country", esc(art["country"])))
        if art["begin"]:
            rows.append(("Active since", esc(art["begin"][:4])))
        if art["genres"]:
            rows.append(("Genres", esc(", ".join(art["genres"]))))
    else:
        rows.append(("Artist", f"<b>{esc(qname)}</b>"))

    note = ""
    latest = sorted((r for r in rgs if r["date"]), key=lambda r: r["date"], reverse=True)[:5]
    if latest:
        note = "💿 <b>Latest releases</b>\n" + "\n".join(
            f"• {esc(r['date'][:4])} · {esc(r['title'][:40])} <i>({esc(r['type'])})</i>"
            for r in latest
        )
    elif not art:
        note = "Artist details were not found on MusicBrainz — showing songs only."

    lines = [fancy("🎤", "Artist", rows, note=note)]
    if songs:
        lines.append("\n🔥 <b>Top songs</b>")
        for i, r in enumerate(songs[:5]):
            remember(r)
            lines.append(f"{NUMS[i]} <b>{esc(r['title'][:55])}</b>\n      {meta_line(r)}")
        lines.append("\n👇 <i>Tap a number to choose</i>")

    kb = artist_markup(songs, art)
    await safe_edit(status, "\n".join(lines) + SPON, kb)


@router.message(Command("artist"))
async def cmd_artist(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /artist <name> command."""
    user = msg.from_user
    if not user:
        return
    if not command.args:
        await msg.reply(
            fancy(
                "🎤",
                "Artist page",
                note="Send an artist name.\n<b>Example:</b> <code>/artist Karan Aujla</code>",
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
        return
    name = command.args.strip()[:60]
    status = await msg.reply(
        fancy("🎤", "Finding artist…", note=esc(name)),
        parse_mode=ParseMode.HTML,
    )
    await show_artist(status, user, name=name)
    autodel(status, gsettings(msg.chat))


@router.callback_query(F.data.startswith("ar:"))
async def cb_artist(cq: CallbackQuery, bot: Bot) -> None:
    """Handle 🎤 Artist page button from Song Info."""
    if not cq.message:
        await cq.answer()
        return
    chat = cq.message.chat
    if not await group_ok(bot, chat, cq.from_user, cq=cq):
        return
    await cq.answer()
    mbid = cq.data.split(":", 1)[1]
    status = await bot.send_message(
        chat.id,
        fancy("🎤", "Finding artist…"),
        parse_mode=ParseMode.HTML,
    )
    await show_artist(status, cq.from_user, mbid=mbid)
    autodel(status, gsettings(chat))
