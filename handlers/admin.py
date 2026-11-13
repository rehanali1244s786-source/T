"""
handlers/admin.py - /admin panel (force-join chats, maintenance toggle, premium & sponsor config) and admin input flows.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from animations import bordered_table, esc, fancy, safe_edit
from config import is_admin
from db import (
    _users,
    clear_flags,
    db,
    fmt_date,
    get_ud,
    grant_premium,
    prem_exp,
    premium_perks,
    save_db,
    touch,
)
from keyboards import (
    admin_cancel_markup,
    admin_home_markup,
    prem_admin_markup,
    prem_users_back_markup,
)
from middlewares import tell

router = Router(name="admin")

SET_PROMPT: Dict[str, str] = {
    "price": "💰 Send the new <b>price</b> (number only).\nExample: <code>300</code>",
    "days": "⏳ Send the <b>premium duration in days</b>.\nExample: <code>30</code>",
    "jc": (
        "🔴 Send the <b>JazzCash number and account name</b>.\n"
        "Example: <code>03001234567 Ali Khan</code>\n"
        "Send <code>-</code> to remove."
    ),
    "ep": (
        "🟢 Send the <b>Easypaisa number and account name</b>.\n"
        "Example: <code>03001234567 Ali Khan</code>\n"
        "Send <code>-</code> to remove."
    ),
    "sponsor": (
        "📣 Send the <b>sponsor line</b> (max 200 characters).\n"
        "It appears under bot messages for non-premium users."
    ),
    "give": (
        "➕ Send the <b>user chat ID</b> and optionally the days.\n"
        "Example: <code>123456789 30</code>\n"
        "(No days = default duration.)"
    ),
    "rmprem": "➖ Send the <b>user chat ID</b> to remove premium.",
}


def admin_view() -> Tuple[str, InlineKeyboardMarkup]:
    """Build /admin main view with centered bold description and bordered table."""
    on = db["enabled"]
    maint = db.get("maintenance", False)
    table_rows = [
        ("Status", "🟠 Maintenance" if maint else "🟢 Online"),
        ("Force-join", "ON ✅" if on else "OFF ❌"),
        ("Users", str(len(_users))),
        ("Groups", str(len(db["groups"]))),
        ("Cached files", str(len(db["cache"]))),
        ("Required chats", str(len(db["chats"]))),
    ]
    lines = [
        "🛠 <b>Admin Panel</b>\n",
        "<blockquote><b>Manage force-join channels, groups, premium settings, and bot status.</b></blockquote>\n",
        bordered_table(table_rows, headers=("System Key", "Value")),
        "",
        f"🔐 Force-join: <b>{'ON ✅' if on else 'OFF ❌'}</b>",
        f"👥 Users: <b>{len(_users)}</b>   💾 Cached files: <b>{len(db['cache'])}</b>\n",
        f"📋 <b>Required chats ({len(db['chats'])}):</b>",
    ]
    if db["chats"]:
        for i, c in enumerate(db["chats"], 1):
            icon = "📢" if c.get("type") == "channel" else "👥"
            lines.append(f"{i}. {icon} {esc(c['title'])}")
    else:
        lines.append("<i>None added yet.</i>")
    return "\n".join(lines), admin_home_markup()


def prem_admin_view() -> Tuple[str, InlineKeyboardMarkup]:
    """Build Admin Premium & Sponsor configuration screen with bordered table."""
    p, sp = db["pay"], db["sponsor"]
    now = time.time()
    active = sum(1 for v in db["premium"].values() if v > now)

    def acc(m: str) -> str:
        a = p[m]
        return f"<code>{esc(a['num'])}</code> {esc(a['name'])}" if a["num"] else "<i>not set</i>"

    def acc_plain(m: str) -> str:
        a = p[m]
        return f"{a['num']} {a['name']}".strip() if a["num"] else "not set"

    rows = [
        ("Price", f"<b>{esc(p['cur'])} {p['price']:,}</b> / {p['days']} days" if p["price"] else "<i>not set</i>"),
        ("JazzCash", acc("jc")),
        ("Easypaisa", acc("ep")),
        ("Premium users", f"<b>{active}</b>"),
        ("Pending proofs", f"<b>{len(db['pending'])}</b>"),
        ("Sponsor", (("ON ✅ " if sp["on"] else "OFF ❌ ") + esc(sp["text"][:60])) if sp["text"] else "<i>none</i>"),
        ("Status", "🟢 Online"),
    ]
    table_rows = [
        ("Price", f"{p['cur']} {p['price']:,} / {p['days']}d" if p["price"] else "not set"),
        ("JazzCash", acc_plain("jc")[:24]),
        ("Easypaisa", acc_plain("ep")[:24]),
        ("Premium users", str(active)),
        ("Pending proofs", str(len(db["pending"]))),
        ("Sponsor", ("ON" if sp["on"] else "OFF") if sp["text"] else "none"),
        ("Status", "🟢 Online"),
    ]
    text = (
        fancy(
            "⭐",
            "Premium & Sponsor",
            rows,
            note="Grant premium by user chat ID with ➕ below, or /givepremium ID [days].",
        )
        + "\n\n"
        + bordered_table(table_rows, headers=("Setting", "Value"))
    )
    return text, prem_admin_markup()


@router.message(Command("admin"))
async def cmd_admin(msg: Message) -> None:
    """Handle /admin command."""
    user = msg.from_user
    if not user or not is_admin(user.id):
        await msg.reply("⛔ Admins only.")
        return
    if msg.chat.type != "private":
        await msg.reply("🛠 Please use /admin in private chat with me.")
        return
    clear_flags(get_ud(user.id))
    text, kb = admin_view()
    await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:"))
async def cb_admin(cq: CallbackQuery) -> None:
    """Handle `adm:*` callbacks."""
    user = cq.from_user
    if not is_admin(user.id):
        await cq.answer("⛔ Admins only", show_alert=True)
        return
    await cq.answer()
    parts = cq.data.split(":")
    action = parts[1]
    ud = get_ud(user.id)
    clear_flags(ud)

    if action in ("prem", "set", "sp", "pl"):
        await cb_admin_prem(cq, parts)
        return

    if action == "add":
        ud["await_chat"] = True
        if cq.message:
            await safe_edit(
                cq.message,
                "➕ <b>Add channel / group</b>\n\n"
                "Send me one of these:\n"
                "• <code>@username</code> of the channel/group\n"
                "• The chat ID (e.g. <code>-1001234567890</code>)\n"
                "• Or <b>forward</b> any message from the channel\n\n"
                "⚠️ Make sure I'm added there as <b>admin</b> first.",
                admin_cancel_markup("adm:home"),
            )
        return
    if action == "tog":
        db["enabled"] = not db["enabled"]
        save_db()
    elif action == "maint":
        db["maintenance"] = not db.get("maintenance", False)
        save_db()
    elif action == "rm":
        cid = int(parts[2])
        db["chats"] = [c for c in db["chats"] if c["id"] != cid]
        for g in db["groups"].values():
            if cid in g["force"]:
                g["force"].remove(cid)
        save_db()
    text, kb = admin_view()
    if cq.message:
        await safe_edit(cq.message, text, kb)


async def cb_admin_prem(cq: CallbackQuery, parts: List[str]) -> None:
    """Handle `adm:prem`, `adm:set:*`, `adm:sp:*`, and `adm:pl` callbacks."""
    ud = get_ud(cq.from_user.id)
    action = parts[1]
    if action == "set" and len(parts) > 2 and parts[2] in SET_PROMPT:
        ud["await_set"] = parts[2]
        if cq.message:
            await safe_edit(cq.message, SET_PROMPT[parts[2]], admin_cancel_markup("adm:prem"))
        return
    if action == "sp" and len(parts) > 2:
        if parts[2] == "tog":
            db["sponsor"]["on"] = not db["sponsor"]["on"]
        elif parts[2] == "clr":
            db["sponsor"] = {"on": False, "text": ""}
        touch()
    if action == "pl":
        now = time.time()
        items = sorted(((int(v), k) for k, v in db["premium"].items() if v > now), reverse=True)[:30]
        lines = [f"<code>{k}</code> — {(v - int(now)) // 86400}d left" for v, k in items] or [
            "<i>No premium users yet.</i>"
        ]
        if cq.message:
            await safe_edit(
                cq.message,
                fancy("📋", "Premium users", note="\n".join(lines)),
                prem_users_back_markup(),
            )
        return
    text, kb = prem_admin_view()
    if cq.message:
        await safe_edit(cq.message, text, kb)


def parse_ref(text: str) -> Optional[Any]:
    """Parse a channel/group reference (@username, t.me/ link, or integer chat ID)."""
    t = text.strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if "+" in t or "joinchat" in t:
        return None
    m = re.search(r"(?:t\.me/|@)([A-Za-z][A-Za-z0-9_]{3,})", t) or re.fullmatch(
        r"([A-Za-z][A-Za-z0-9_]{3,})", t
    )
    return f"@{m.group(1)}" if m else None


async def admin_add_flow(bot: Bot, msg: Message) -> None:
    """Process channel/group reference sent by an admin during `await_chat` flow."""
    fo = getattr(msg, "forward_origin", None)
    f_chat = getattr(fo, "chat", None) if fo is not None else getattr(msg, "forward_from_chat", None)
    ref = f_chat.id if f_chat is not None else (parse_ref(msg.text) if msg.text else None)
    if ref is None:
        await msg.reply("❌ Invalid. Send @username, chat ID, or forward a message from the channel.")
        return
    try:
        chat = await bot.get_chat(ref)
    except TelegramAPIError:
        await msg.reply("❌ I can't find that chat. Add me as admin there, then try again.")
        return
    try:
        me_user = await bot.get_me()
        me = await bot.get_chat_member(chat.id, me_user.id)
    except TelegramAPIError:
        me = None
    if not me or me.status not in ("administrator", "creator"):
        await msg.reply("❌ I'm not an admin there. Make me admin, then send it again.")
        return

    link = f"https://t.me/{chat.username}" if chat.username else getattr(chat, "invite_link", None)
    if not link:
        try:
            link = await bot.export_chat_invite_link(chat.id)
        except TelegramAPIError:
            link = None

    entry = {
        "id": chat.id,
        "title": chat.title or str(chat.id),
        "link": link,
        "type": "channel" if chat.type == "channel" else "group",
    }
    db["chats"] = [c for c in db["chats"] if c["id"] != chat.id] + [entry]
    save_db()
    if msg.from_user:
        get_ud(msg.from_user.id).pop("await_chat", None)

    warn = "" if link else "\n⚠️ No invite link available — give me the 'Invite users' permission."
    text, kb = admin_view()
    await msg.reply(
        f"✅ <b>Added:</b> {esc(entry['title'])}{warn}\n\n{text}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def admin_set_flow(bot: Bot, msg: Message) -> None:
    """Process admin input for `await_set` (price, days, jc, ep, sponsor, give, rmprem)."""
    if not msg.from_user:
        return
    ud = get_ud(msg.from_user.id)
    p = db["pay"]
    field = ud.pop("await_set", None)
    text = (msg.text or "").strip()
    if not text:
        ud["await_set"] = field
        await msg.reply("❌ Please send text.")
        return
    note = ""
    try:
        if field == "price":
            p["price"] = max(0, int(text.replace(",", "")))
        elif field == "days":
            p["days"] = max(1, int(text))
        elif field in ("jc", "ep"):
            if text == "-":
                p[field] = {"num": "", "name": ""}
            else:
                num, _, nm = text.partition(" ")
                p[field] = {"num": num.strip()[:20], "name": nm.strip()[:40]}
        elif field == "sponsor":
            db["sponsor"] = {"on": True, "text": text[:200]}
        elif field == "give":
            bits = text.split()
            uid = int(bits[0])
            days = int(bits[1]) if len(bits) > 1 else p["days"]
            exp = grant_premium(uid, days if days > 0 else p["days"])
            sent = await tell(
                bot,
                uid,
                fancy(
                    "🎉",
                    "Premium activated!",
                    [("Valid until", f"<b>{fmt_date(exp)}</b>")],
                    note=premium_perks(),
                ),
            )
            note = (
                f"✅ Premium given to <code>{uid}</code> until <b>{fmt_date(exp)}</b>"
                + ("" if sent else "\n⚠️ Couldn't message the user (they must /start the bot).")
                + "\n\n"
            )
        elif field == "rmprem":
            uid = int(text.split()[0])
            db["premium"].pop(str(uid), None)
            note = f"✅ Premium removed from <code>{uid}</code>\n\n"
        else:
            return
    except (ValueError, IndexError):
        ud["await_set"] = field
        await msg.reply("❌ Invalid value. Try again.")
        return
    touch()
    view, kb = prem_admin_view()
    await msg.reply(
        note + "✅ Saved\n\n" + view if not note else note + view,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
