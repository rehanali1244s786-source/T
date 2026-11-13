"""
handlers/follow.py - /follow, /following, /invite, release_watcher background loop, and follow/unfollow/invite callbacks.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from animations import esc, fancy, safe_edit
from config import (
    REF_BONUS,
    REF_MAX_BONUS,
    RELEASE_CHECK_HOURS,
    is_admin,
    log,
)
from db import (
    db,
    follow_limit,
    recog_limit,
    ref_count,
    touch,
    user_follows,
)
from keyboards import (
    following_markup,
    invite_markup,
    release_alert_markup,
    submenu_back_markup,
)
from middlewares import group_ok
from services.musicbrainz import (
    mb_artist_by_id,
    mb_artist_search,
    mb_release_groups,
)

router = Router(name="follow")


async def do_follow(uid: int, mbid: str, name: str) -> str:
    """Subscribe `uid` to release alerts for artist `mbid`."""
    mine = user_follows(uid)
    if mbid in mine:
        return "dup"
    if len(mine) >= follow_limit(uid):
        return "limit"
    a = db["artists"].get(mbid)
    if a is None:
        rgs = await mb_release_groups(mbid, fresh=True)
        a = db["artists"][mbid] = {
            "n": name,
            "seen": [r["id"] for r in rgs],
            "subs": [],
            "chk": int(time.time()),
        }
    a["subs"].append(uid)
    touch()
    return "ok"


def follow_result_text(res: str, name: str, uid: int) -> str:
    """Format follow status result card."""
    if res == "ok":
        return fancy(
            "🔔",
            "Following!",
            [("Artist", f"<b>{esc(name)}</b>")],
            note=f"I'll message you when new music is released.\nYou follow {len(user_follows(uid))}/{follow_limit(uid)} artists.",
        )
    if res == "dup":
        return fancy(
            "🔔",
            "Already following",
            [("Artist", f"<b>{esc(name)}</b>")],
            note="See your list with /following",
        )
    return fancy(
        "🔔",
        "Follow limit reached",
        [("Limit", f"<b>{follow_limit(uid)}</b> artists")],
        note="Unfollow someone with /following, or go ⭐ /premium for more.",
    )


@router.message(Command("follow"))
async def cmd_follow(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /follow <artist>."""
    user = msg.from_user
    if not user:
        return
    if not command.args:
        await msg.reply(
            fancy(
                "🔔",
                "Follow an artist",
                note="Get a message when they release something new.\n<b>Example:</b> <code>/follow Karan Aujla</code>",
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
        return
    name = command.args.strip()[:60]
    status = await msg.reply(
        fancy("🔔", "Finding artist…", note=esc(name)),
        parse_mode=ParseMode.HTML,
    )
    try:
        art = await mb_artist_search(name)
        if not art:
            await safe_edit(
                status,
                fancy("😕", "Artist not found", note="Check the spelling and try again."),
            )
            return
        res = await do_follow(user.id, art["id"], art["name"])
    except Exception as e:
        log.warning("follow failed: %s", e)
        await safe_edit(
            status,
            fancy("❌", "Couldn't follow", note="The music database is busy. Try again in a moment."),
        )
        return
    await safe_edit(status, follow_result_text(res, art["name"], user.id))


@router.callback_query(F.data.startswith("fl:"))
async def cb_follow(cq: CallbackQuery, bot: Bot) -> None:
    """Handle 🔔 Follow button on artist card."""
    user = cq.from_user
    mbid = cq.data.split(":", 1)[1]
    try:
        art = await mb_artist_by_id(mbid)
        name = art["name"] if art else "Artist"
        res = await do_follow(user.id, mbid, name)
    except Exception as e:
        log.warning("follow failed: %s", e)
        await cq.answer("Couldn't follow right now. Try again.", show_alert=True)
        return
    await cq.answer(
        {"ok": "🔔 Following!", "dup": "Already following", "limit": "Follow limit reached"}[res],
        show_alert=(res == "limit"),
    )
    if res != "limit" and cq.message:
        await bot.send_message(
            cq.message.chat.id,
            follow_result_text(res, name, user.id),
            parse_mode=ParseMode.HTML,
        )


def following_view(uid: int) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Build /following list view."""
    mine = user_follows(uid)
    if not mine:
        return (
            fancy(
                "🔔",
                "Following",
                note="You don't follow anyone yet.\nUse <code>/follow artist name</code>.",
            ),
            submenu_back_markup("home"),
        )
    rows = [(f"{i + 1}", esc(db["artists"][m]["n"][:40])) for i, m in enumerate(mine)]
    text = fancy(
        "🔔",
        "Following",
        rows,
        note=f"{len(mine)}/{follow_limit(uid)} artists · alerts every ~{int(RELEASE_CHECK_HOURS)}h",
    )
    return text, following_markup(mine)


@router.message(Command("following"))
async def cmd_following(msg: Message) -> None:
    """Handle /following command."""
    user = msg.from_user
    if not user:
        return
    text, kb = following_view(user.id)
    await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("uf:"))
async def cb_unfollow(cq: CallbackQuery) -> None:
    """Handle 🗑 Unfollow button."""
    uid = cq.from_user.id
    mbid = cq.data.split(":", 1)[1]
    a = db["artists"].get(mbid)
    if a and uid in a["subs"]:
        a["subs"].remove(uid)
        if not a["subs"]:
            db["artists"].pop(mbid, None)
        touch()
    await cq.answer("🔕 Unfollowed")
    text, kb = following_view(uid)
    if cq.message:
        await safe_edit(cq.message, text, kb)


# ───────────────────────── Invite & Referrals ─────────────────────────
def invite_view(user: Any, bot_name: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Build /invite referral card."""
    link = f"https://t.me/{bot_name}?start=ref_{user.id}"
    n = ref_count(user.id)
    bonus = min(n * REF_BONUS, REF_MAX_BONUS)
    limit = "Unlimited" if is_admin(user.id) else str(recog_limit(user.id))
    text = fancy(
        "🎁",
        "Invite & Earn",
        [
            ("Friends invited", f"<b>{n}</b>"),
            ("Bonus", f"+{bonus} / {REF_MAX_BONUS} per day"),
            ("Your daily recognitions", f"<b>{limit}</b>"),
        ],
        note=f"Every friend who joins with your link gives you <b>+{REF_BONUS}</b> song recognition(s) per day.",
        tail=f"🔗 <b>Your link</b>\n<code>{link}</code>",
    )
    return text, invite_markup(link)


@router.message(Command("invite"))
async def cmd_invite(msg: Message, bot: Bot) -> None:
    """Handle /invite command."""
    user = msg.from_user
    if not user:
        return
    me = await bot.get_me()
    text, kb = invite_view(user, me.username or "bot")
    await msg.reply(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "inv")
async def cb_invite(cq: CallbackQuery, bot: Bot) -> None:
    """Handle 🎁 Invite & Earn button."""
    await cq.answer()
    me = await bot.get_me()
    text, kb = invite_view(cq.from_user, me.username or "bot")
    if cq.message:
        await bot.send_message(
            cq.message.chat.id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )


# ───────────────────────── Release Watcher Background Task ─────────────────────────
async def release_watcher(bot: Bot) -> None:
    """Background loop: check followed artists every RELEASE_CHECK_HOURS and notify subscribers."""
    await asyncio.sleep(90)
    while True:
        try:
            for mbid, a in list(db["artists"].items()):
                if not a.get("subs"):
                    db["artists"].pop(mbid, None)
                    continue
                try:
                    rgs = await mb_release_groups(mbid, fresh=True)
                except Exception as e:
                    log.warning("release check failed for %s: %s", a.get("n"), e)
                    continue
                seen = set(a.get("seen", []))
                new = [r for r in rgs if r["id"] not in seen]
                if not new:
                    continue
                a["seen"] = list(seen | {r["id"] for r in new})
                a["chk"] = int(time.time())
                touch()
                cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 120 * 86400))
                fresh = [r for r in new if r["date"] and r["date"] >= cutoff[: len(r["date"])]]
                for r in sorted(fresh, key=lambda r: r["date"], reverse=True)[:3]:
                    text = fancy(
                        "🎉",
                        "New release!",
                        [
                            ("Artist", f"<b>{esc(a['n'])}</b>"),
                            ("Title", f"<b>{esc(r['title'][:60])}</b>"),
                            ("Type", esc(r["type"])),
                            ("Date", esc(r["date"])),
                        ],
                        note="Tap below to find it and download.",
                    )
                    kb = release_alert_markup(a["n"], r["title"], mbid)
                    for uid in list(a["subs"]):
                        try:
                            await bot.send_message(
                                uid,
                                text,
                                parse_mode=ParseMode.HTML,
                                reply_markup=kb,
                            )
                        except TelegramForbiddenError:
                            a["subs"].remove(uid)
                            touch()
                        except TelegramAPIError:
                            pass
                        await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("release watcher error")
        await asyncio.sleep(max(1800.0, float(RELEASE_CHECK_HOURS) * 3600.0))
