"""
middlewares.py - Gate middleware (bans, maintenance, force-join, group rules) and Outgoing Credit middleware.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import (
    EditMessageCaption,
    EditMessageText,
    SendAudio,
    SendDocument,
    SendMessage,
    SendPhoto,
    SendVideo,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from animations import autodel, esc, fancy, safe_edit
from config import (
    ADMIN_FIX,
    ADMIN_IDS,
    ALERT_COOLDOWN,
    ALERT_STREAK,
    CREDIT_HTML,
    CREDIT_PLAIN,
    CREDIT_USER,
    FOOT,
    GDEF,
    GROUP_TYPES,
    MEMBER_CACHE_TTL,
    SPON,
    is_admin,
    log,
)
from db import (
    ERR,
    _check_alert,
    _cooldown,
    _gadm_cache,
    _member_cache,
    _users,
    brand_active,
    db,
    ensure_group,
    is_premium,
    recog_limit,
    ref_count,
    touch,
)
from i18n import L, tr
from keyboards import join_markup


# ───────────────────────── Admin & Group Rule Helpers ─────────────────────────
async def notify_admins(
    bot: Bot,
    text: str,
    markup: Optional[Any] = None,
) -> None:
    """Send a notification message to all ADMIN_IDS."""
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except TelegramAPIError:
            pass


async def tell(
    bot: Bot,
    uid: int,
    text: str,
    markup: Optional[Any] = None,
) -> bool:
    """Send a direct message to `uid`; return True on success."""
    try:
        await bot.send_message(
            uid,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        return True
    except TelegramAPIError:
        return False


async def is_group_admin(bot: Bot, cid: int, uid: int) -> bool:
    """Check if `uid` is an administrator or creator in group `cid` (cached for 60s)."""
    hit = _gadm_cache.get((cid, uid))
    if hit and time.time() - hit[0] < 60:
        return bool(hit[1])
    try:
        m = await bot.get_chat_member(cid, uid)
        ok = m.status in ("administrator", "creator")
    except TelegramAPIError:
        ok = False
    _gadm_cache[(cid, uid)] = (time.time(), ok)
    return ok


async def deny(
    text: str,
    msg: Optional[Message] = None,
    cq: Optional[CallbackQuery] = None,
) -> None:
    """Reply with a temporary denial message or callback alert."""
    if cq:
        try:
            await cq.answer(text, show_alert=True)
        except TelegramAPIError:
            pass
    elif msg:
        try:
            m = await msg.reply(text)
            autodel(m, GDEF, 8)
        except TelegramAPIError:
            pass


async def group_ok(
    bot: Bot,
    chat: Any,
    user: Any,
    *,
    cooldown: bool = False,
    msg: Optional[Message] = None,
    cq: Optional[CallbackQuery] = None,
) -> bool:
    """Enforce per-group rules: admins-only mode and per-user cooldown. Bot admins bypass everything."""
    if getattr(chat, "type", "") not in GROUP_TYPES or is_admin(user.id):
        return True
    g = ensure_group(chat)
    if g["adm"] and not await is_group_admin(bot, chat.id, user.id):
        await deny("🔒 Only group admins can use the bot here.", msg, cq)
        return False
    if cooldown and g["cool"]:
        k = (chat.id, user.id)
        wait = g["cool"] - (time.time() - _cooldown.get(k, 0))
        if wait > 0:
            await deny(f"⏳ Please wait {int(wait) + 1}s before the next request.", msg, cq)
            return False
        _cooldown[k] = time.time()
    return True


# ───────────────────────── Error classification & admin alerts ─────────────────────────
def error_kind(e: Exception) -> str:
    """Classify download/lookup exception into 'cookies', 'ffmpeg', 'video', or 'other'."""
    m = str(e).lower()
    if "sign in" in m or "bot" in m or "cookies" in m or "login" in m:
        return "cookies"
    if "ffmpeg" in m or "ffprobe" in m:
        return "ffmpeg"
    if "private" in m or "unavailable" in m or "removed" in m or "not available" in m:
        return "video"
    return "other"


def error_hint(e: Exception, lang: str = "en") -> str:
    """Return localized user-friendly hint for an exception."""
    return tr(
        lang,
        {
            "cookies": "hint_cookies",
            "ffmpeg": "hint_ffmpeg",
            "video": "hint_unavail",
        }.get(error_kind(e), "hint_retry"),
    )


async def report_error(
    bot: Bot,
    e: Exception,
    where: str,
    vid: str = "",
    user: Optional[Any] = None,
) -> None:
    """Alert bot admins when downloads break for server-side reasons (not for a single unavailable video)."""
    kind = error_kind(e)
    if kind == "video":
        return
    ERR["streak"] += 1
    if kind == "other" and ERR["streak"] < ALERT_STREAK:
        return
    now = time.time()
    if now - ERR["last"].get(kind, 0) < ALERT_COOLDOWN:
        return
    ERR["last"][kind] = now
    ERR["alerted"] = True
    who = f"{esc(user.full_name)} (<code>{user.id}</code>)" if user else "—"
    await notify_admins(
        bot,
        f"🚨 <b>Bot alert — downloads failing</b>\n\n"
        f"📍 Where: <code>{esc(where)}</code>\n"
        f"🎬 Video: <code>{esc(vid) or '—'}</code>\n"
        f"👤 User: {who}\n"
        f"🔁 Failures in a row: <b>{ERR['streak']}</b>\n\n"
        f"🧾 <code>{esc(str(e)[:350])}</code>\n\n"
        f"🛠 {ADMIN_FIX.get(kind, ADMIN_FIX['other'])}",
    )


async def report_ok(bot: Bot) -> None:
    """Reset failure streak and alert admins when downloads recover."""
    ERR["streak"] = 0
    if ERR["alerted"]:
        ERR["alerted"] = False
        ERR["last"].clear()
        await notify_admins(bot, "✅ <b>Bot recovered</b> — downloads are working again.")


# ───────────────────────── Referrals & Force-Join Helpers ─────────────────────────
async def register_referral(bot: Bot, user: Any, ref_uid: int) -> None:
    """Credit `ref_uid` when a new user starts the bot via `?start=ref_<ref_uid>`."""
    r = db["ref"]
    if ref_uid == user.id or ref_uid not in _users or str(user.id) in r["by"]:
        return
    r["by"][str(user.id)] = ref_uid
    r["n"][str(ref_uid)] = r["n"].get(str(ref_uid), 0) + 1
    touch()
    await tell(
        bot,
        ref_uid,
        fancy(
            "🎉",
            "A friend joined!",
            [
                ("Friend", esc((user.full_name or "User")[:30])),
                ("Invited so far", f"<b>{ref_count(ref_uid)}</b>"),
                ("Your daily recognitions", f"<b>{recog_limit(ref_uid)}</b>"),
            ],
            note="Thanks for sharing! Keep inviting with /invite to unlock more.",
        ),
    )


def required_chats(g: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return list of force-join chats required globally and/or in group `g`."""
    req = list(db["chats"]) if db["enabled"] else []
    if g:
        ids = {c["id"] for c in req}
        req += [c for c in db["chats"] if c["id"] in g.get("force", []) and c["id"] not in ids]
    return req


async def missing_chats(bot: Bot, user_id: int, required: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check which required chats `user_id` has not joined yet; alert admins if bot lacks admin rights."""
    async def one(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        key = (user_id, c["id"])
        if time.time() - _member_cache.get(key, 0) < MEMBER_CACHE_TTL:
            return None
        try:
            m = await bot.get_chat_member(c["id"], user_id)
        except TelegramAPIError as e:
            if time.time() - _check_alert.get(c["id"], 0) > 3600:
                _check_alert[c["id"]] = time.time()
                await notify_admins(
                    bot,
                    f"⚠️ <b>Force-join problem</b>\n\nI can't check members of <b>{esc(c['title'])}</b> "
                    f"(<code>{c['id']}</code>), so users are being let through.\n"
                    f"👉 Make me an <b>admin</b> in that channel/group.\n\n<code>{esc(str(e)[:150])}</code>",
                )
            return None
        ok = m.status in ("member", "administrator", "creator") or (
            m.status == "restricted" and getattr(m, "is_member", False)
        )
        if ok:
            _member_cache[key] = time.time()
            return None
        return c

    res = await asyncio.gather(*(one(c) for c in required))
    return [c for c in res if c]


# ───────────────────────── Gate Middleware (Outer Update Middleware) ─────────────────────────
class GateMiddleware(BaseMiddleware):
    """
    Central gate executed before any handler:
    - Registers new users and referral deep links (`/start ref_<id>`)
    - Tracks group activity and blocks updates from blocked groups
    - Enforces maintenance mode (for non-admins)
    - Enforces global and per-group bans
    - Enforces force-join channels/groups and handles the `chk` ("I've Joined") callback
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        bot: Bot = data["bot"]
        msg: Optional[Message] = event.message
        cq: Optional[CallbackQuery] = event.callback_query
        if not (msg or cq):
            return await handler(event, data)

        user = msg.from_user if msg else (cq.from_user if cq else None)
        chat = msg.chat if msg else (cq.message.chat if (cq and cq.message) else None)
        if not user or user.is_bot or not chat:
            return None

        # Register first-time user & check referral deep link
        if user.id not in _users:
            _users.add(user.id)
            touch()
            m_ref = re.match(r"/start(?:@\w+)?\s+ref_(\d+)", msg.text or "") if msg else None
            if m_ref:
                await register_referral(bot, user, int(m_ref.group(1)))

        admin = is_admin(user.id)
        g: Optional[Dict[str, Any]] = None
        if chat.type in GROUP_TYPES:
            g = ensure_group(chat)
            now = int(time.time())
            if now - int(g.get("last", 0)) > 60:
                g["last"] = now
                touch()
            if g.get("blocked") and not admin:
                return None

        lang = L(user.id)

        # Maintenance mode check
        if db.get("maintenance") and not admin:
            if cq:
                await cq.answer(tr(lang, "maintenance"), show_alert=True)
            elif chat.type == "private" and msg:
                await msg.reply(tr(lang, "maintenance"), parse_mode=ParseMode.HTML)
            return None

        # Global & group ban check
        if not admin:
            gid = str(chat.id)
            if user.id in db["banned_global"] or user.id in db["banned_groups"].get(gid, []):
                if cq:
                    await cq.answer(tr(lang, "banned"), show_alert=True)
                elif chat.type == "private" and msg:
                    await msg.reply(tr(lang, "banned"), parse_mode=ParseMode.HTML)
                return None

        required = required_chats(g)

        # Handle "✅ I've Joined" verification button
        if cq and cq.data == "chk":
            for k in [k for k in _member_cache if k[0] == user.id]:
                _member_cache.pop(k, None)
            missing = await missing_chats(bot, user.id, required)
            if missing:
                await cq.answer(tr(lang, "join_not_yet"), show_alert=True)
                if cq.message:
                    await safe_edit(cq.message, tr(lang, "join_text"), join_markup(missing, lang))
            else:
                await cq.answer(tr(lang, "join_verified"))
                if cq.message:
                    await safe_edit(cq.message, tr(lang, "join_ok"))
            return None

        if admin or not required:
            return await handler(event, data)

        is_cmd = bool(msg and msg.text and msg.text.startswith("/"))
        is_text_query = bool(msg and msg.text and (chat.type == "private" or (g and g.get("txt"))))
        if msg and chat.type == "private" and (msg.voice or msg.audio or msg.video or msg.video_note):
            is_text_query = True
        if not (cq or is_cmd or is_text_query):
            return await handler(event, data)

        missing = await missing_chats(bot, user.id, required)
        if not missing:
            return await handler(event, data)

        if cq:
            await cq.answer(tr(lang, "join_first"))
            if cq.message:
                await bot.send_message(
                    cq.message.chat.id,
                    tr(lang, "join_text"),
                    parse_mode=ParseMode.HTML,
                    reply_markup=join_markup(missing, lang),
                )
        elif msg:
            await msg.reply(
                tr(lang, "join_text"),
                parse_mode=ParseMode.HTML,
                reply_markup=join_markup(missing, lang),
            )
        return None


# ───────────────────────── Outgoing Credit & Sponsor Middleware ─────────────────────────
def _footer(chat_id: Any, html_mode: bool, want_sponsor: bool) -> str:
    """Build the credit/brand/sponsor footer for a message sent to `chat_id`."""
    g = db["groups"].get(str(chat_id)) if chat_id is not None else None
    if g and brand_active(g):
        return f"\n\n{FOOT}✨ <i>{esc(g['brand'])}</i>" if html_mode else f"\n\n{FOOT}✨ {g['brand']}"
    out = ""
    sp = db["sponsor"]
    private_premium = isinstance(chat_id, int) and chat_id > 0 and is_premium(chat_id)
    if want_sponsor and sp.get("on") and sp.get("text") and not private_premium:
        out += f"\n\n{FOOT}📣 <i>{esc(sp['text'])}</i>" if html_mode else f"\n\n{FOOT}📣 {sp['text']}"
    credit = CREDIT_HTML if html_mode else CREDIT_PLAIN
    return out + (credit if out else credit.replace("\n\n", f"\n\n{FOOT}", 1))


def _apply_credit_to_text(
    txt: Optional[str],
    parse_mode: Any,
    chat_id: Any,
    sponsor_ok: bool,
) -> Optional[str]:
    """Append the credit/sponsor footer to `txt` if not already present."""
    if not isinstance(txt, str) or not txt:
        return txt
    had_spon = SPON in txt
    cleaned = txt.replace(SPON, "")
    if FOOT in cleaned or CREDIT_USER in cleaned:
        return cleaned
    pm_str = str(getattr(parse_mode, "value", parse_mode) or "").upper()
    html_mode = pm_str == "HTML"
    return cleaned + _footer(chat_id, html_mode, sponsor_ok or had_spon)


class CreditRequestMiddleware(BaseRequestMiddleware):
    """
    Aiogram session middleware that automatically appends 'Developed by Dock — @Dockworldwide'
    (or the group's custom `/brand` footer) plus optional sponsor text to every outgoing bot
    message and caption, replicating `install_credit()` from the original bot.
    """

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        try:
            if isinstance(method, SendMessage):
                method.text = _apply_credit_to_text(
                    method.text, method.parse_mode, method.chat_id, sponsor_ok=False
                ) or method.text
            elif isinstance(method, EditMessageText):
                method.text = _apply_credit_to_text(
                    method.text, method.parse_mode, method.chat_id, sponsor_ok=False
                ) or method.text
            elif isinstance(method, EditMessageCaption):
                if method.caption:
                    method.caption = _apply_credit_to_text(
                        method.caption, method.parse_mode, method.chat_id, sponsor_ok=False
                    )
            elif isinstance(method, (SendPhoto, SendVideo, SendAudio)):
                if method.caption:
                    method.caption = _apply_credit_to_text(
                        method.caption, method.parse_mode, method.chat_id, sponsor_ok=True
                    )
            elif isinstance(method, SendDocument):
                if method.caption:
                    method.caption = _apply_credit_to_text(
                        method.caption, method.parse_mode, method.chat_id, sponsor_ok=False
                    )
        except Exception as e:
            log.warning("credit middleware error: %s", e)

        return await make_request(bot, method)
