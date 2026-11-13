"""
handlers/premium.py - /premium, JazzCash & Easypaisa payment flows, payment proof submission, and /givepremium & /removepremium.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from animations import bordered_table, esc, fancy, safe_edit
from config import ADMIN_IDS, METHODS, is_admin
from db import (
    days_left,
    db,
    fmt_date,
    get_ud,
    grant_premium,
    prem_exp,
    premium_perks,
    touch,
)
from keyboards import (
    cancel_pay_markup,
    payment_method_markup,
    premium_markup,
    proof_review_markup,
)
from middlewares import tell

router = Router(name="premium")


def premium_view(
    uid: int,
    private: bool = True,
    bot_username: str = "bot",
) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Build /premium overview card with bordered table and payment method buttons."""
    p = db["pay"]
    if is_admin(uid):
        status = "👑 Admin — everything unlocked"
        status_plain = "Admin (Unlocked)"
    elif prem_exp(uid) > time.time():
        status = f"✅ Active until <b>{fmt_date(prem_exp(uid))}</b> ({days_left(uid)} days left)"
        status_plain = f"Active ({days_left(uid)}d left)"
    else:
        status = "Free plan"
        status_plain = "Free plan"
    price = (
        f"<b>{esc(p['cur'])} {p['price']:,}</b> / {p['days']} days"
        if p["price"]
        else "<i>not set yet</i>"
    )
    price_plain = f"{p['cur']} {p['price']:,} / {p['days']}d" if p["price"] else "Not set yet"
    table = bordered_table(
        [
            ("Your Status", status_plain),
            ("Price", price_plain),
            ("JazzCash", "Available ✅" if p["jc"]["num"] else "Not set"),
            ("Easypaisa", "Available ✅" if p["ep"]["num"] else "Not set"),
            ("Bot Status", "🟢 Online"),
        ],
        headers=("Premium Info", "Details"),
    )
    text = (
        fancy("⭐", "Premium", [("Status", status), ("Price", price)], note=premium_perks())
        + "\n\n"
        + table
    )
    if p["price"] and any(p[m]["num"] for m in METHODS):
        text += "\n\n👇 <b>Choose a payment method</b>"
    else:
        text += "\n\n<i>Premium sales are not open yet. Please contact the admin.</i>"
    kb = premium_markup(private=private, bot_username=bot_username)
    return text, kb


def method_view(uid: int, m: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Build JazzCash or Easypaisa payment instructions screen."""
    p = db["pay"]
    name, dot = METHODS[m]
    acc = p[m]
    text = fancy(
        dot,
        f"Pay with {name}",
        [
            ("Amount", f"<b>{esc(p['cur'])} {p['price']:,}</b>"),
            ("Number", f"<code>{esc(acc['num'])}</code>"),
            ("Account name", esc(acc["name"]) or "<i>—</i>"),
            ("Your ID", f"<code>{uid}</code>"),
        ],
        note=(
            f"1️⃣ Open <b>{name}</b> → <b>Send Money</b>\n"
            "2️⃣ Send the exact amount to the number above\n"
            "3️⃣ Tap <b>✅ I've Paid</b> and send the <b>Transaction ID</b> or a <b>screenshot</b>"
        ),
    )
    return text, payment_method_markup(m)


@router.message(Command("premium"))
async def cmd_premium(msg: Message, bot: Bot) -> None:
    """Handle /premium command."""
    user = msg.from_user
    if not user:
        return
    me = await bot.get_me()
    text, kb = premium_view(
        user.id,
        private=(msg.chat.type == "private"),
        bot_username=me.username or "bot",
    )
    await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(cq: CallbackQuery, bot: Bot) -> None:
    """Handle `pay:*` callbacks (user payment selection & admin proof approval/rejection)."""
    user = cq.from_user
    ud = get_ud(user.id)
    p = db["pay"]
    parts = cq.data.split(":")
    act = parts[1]

    # Admin decisions on a payment proof
    if act in ("ok", "no"):
        if not is_admin(user.id):
            await cq.answer("⛔ Admins only", show_alert=True)
            return
        uid = int(parts[2])
        pend = db["pending"].pop(str(uid), None)
        if pend is None:
            await cq.answer("Already handled", show_alert=True)
            return
        touch()
        await cq.answer()
        if act == "ok":
            exp = grant_premium(uid, p["days"])
            await tell(
                bot,
                uid,
                fancy(
                    "🎉",
                    "Premium activated!",
                    [
                        ("Valid until", f"<b>{fmt_date(exp)}</b>"),
                        ("Days", f"<b>{p['days']}</b>"),
                    ],
                    note=premium_perks(),
                ),
            )
            if cq.message:
                await safe_edit(
                    cq.message,
                    f"✅ <b>Approved</b> — <code>{uid}</code> · premium until <b>{fmt_date(exp)}</b>\n👮 by {esc(user.full_name)}",
                )
        else:
            await tell(
                bot,
                uid,
                fancy(
                    "❌",
                    "Payment not verified",
                    note="We couldn't verify your payment. Check the details and try again from /premium, or contact the admin.",
                ),
            )
            if cq.message:
                await safe_edit(
                    cq.message,
                    f"❌ <b>Rejected</b> — <code>{uid}</code>\n👮 by {esc(user.full_name)}",
                )
        return

    if not cq.message or cq.message.chat.type != "private":
        await cq.answer("Please open me in a private chat for payments.", show_alert=True)
        return
    await cq.answer()
    if act == "home":
        ud.pop("await_proof", None)
        me = await bot.get_me()
        text, kb = premium_view(user.id, private=True, bot_username=me.username or "bot")
        await safe_edit(cq.message, text, kb)
    elif act == "m" and len(parts) > 2 and parts[2] in METHODS and p[parts[2]]["num"]:
        ud.pop("await_proof", None)
        text, kb = method_view(user.id, parts[2])
        await safe_edit(cq.message, text, kb)
    elif act == "paid" and len(parts) > 2 and parts[2] in METHODS:
        ud["await_proof"] = parts[2]
        await safe_edit(
            cq.message,
            fancy(
                "📨",
                "Send payment proof",
                note="Now send the <b>Transaction ID</b> as text, or a <b>screenshot</b> of the payment.",
            ),
            cancel_pay_markup(),
        )


async def handle_proof(bot: Bot, msg: Message) -> None:
    """Process Transaction ID or screenshot sent by a user during `await_proof`."""
    user = msg.from_user
    if not user:
        return
    ud = get_ud(user.id)
    m = ud.pop("await_proof", None)
    if not m:
        return
    p = db["pay"]
    if not (msg.text or msg.photo or msg.document):
        ud["await_proof"] = m
        await msg.reply("❌ Please send the Transaction ID as text or a screenshot.")
        return
    db["pending"][str(user.id)] = {
        "m": m,
        "ts": int(time.time()),
        "name": (user.full_name or "User")[:40],
    }
    touch()
    name, dot = METHODS[m]
    kb = proof_review_markup(user.id, p["days"])
    card = fancy(
        "💳",
        "Payment proof",
        [
            ("User", f'<a href="tg://user?id={user.id}">{esc((user.full_name or "User")[:30])}</a>'),
            ("ID", f"<code>{user.id}</code>"),
            ("Method", f"{dot} {name}"),
            ("Amount", f"<b>{esc(p['cur'])} {p['price']:,}</b>"),
        ],
        note="Check your wallet app, then approve or reject.",
    )
    for a in ADMIN_IDS:
        try:
            await bot.copy_message(chat_id=a, from_chat_id=msg.chat.id, message_id=msg.message_id)
        except TelegramAPIError:
            pass
        await tell(bot, a, card, kb)
    await msg.reply(
        fancy(
            "✅",
            "Proof received",
            note="An admin will verify your payment shortly. You'll get a message here.",
        ),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("givepremium"))
async def cmd_givepremium(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /givepremium <chat_id> [days]."""
    user = msg.from_user
    if not user or not is_admin(user.id):
        await msg.reply("⛔ Admins only.")
        return
    args = (command.args or "").split()
    try:
        uid = int(args[0])
        days = int(args[1]) if len(args) > 1 else db["pay"]["days"]
    except (ValueError, IndexError):
        await msg.reply("Usage: /givepremium <chat_id> [days]")
        return
    exp = grant_premium(uid, days if days > 0 else db["pay"]["days"])
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
    await msg.reply(
        f"✅ Premium given to <code>{uid}</code> until <b>{fmt_date(exp)}</b>"
        + ("" if sent else "\n⚠️ Couldn't message the user (they must /start the bot)."),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("removepremium"))
async def cmd_removepremium(msg: Message, command: CommandObject) -> None:
    """Handle /removepremium <chat_id>."""
    user = msg.from_user
    if not user or not is_admin(user.id):
        await msg.reply("⛔ Admins only.")
        return
    args = (command.args or "").split()
    try:
        uid = int(args[0])
    except (ValueError, IndexError):
        await msg.reply("Usage: /removepremium <chat_id>")
        return
    db["premium"].pop(str(uid), None)
    touch()
    await msg.reply(f"✅ Premium removed from <code>{uid}</code>", parse_mode=ParseMode.HTML)
