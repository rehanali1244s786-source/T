"""
handlers/groups.py - Group manager (/groups), moderation (/ban, /unban, /warn, /approve, /unapprove),
group branding (/brand), broadcast, inactive cleanup, and ChatMember handler (on_my_member).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, Message

from animations import ago, bordered_table, esc, fancy, safe_edit
from config import (
    BRANDING_FREE,
    CYCLES,
    GROUPS_PER_PAGE,
    GROUP_TYPES,
    INACTIVE_DAYS,
    MEDALS,
    SORTS,
    SORT_LABEL,
    TOGGLES,
    WARN_LIMIT,
    is_admin,
)
from db import (
    brand_active,
    clear_flags,
    db,
    ensure_group,
    gdl,
    get_ud,
    is_premium,
    save_db,
    touch,
)
from keyboards import (
    admin_cancel_markup,
    approve_user_markup,
    bc_confirm_markup,
    bc_select_markup,
    group_back_markup,
    group_detail_markup,
    group_force_markup,
    group_inactive_markup,
    group_settings_markup,
    groups_list_markup,
)
from middlewares import deny, is_group_admin, notify_admins

router = Router(name="groups")


def filtered_groups(ud: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Filter and sort groups according to admin's search query and sort mode."""
    items = list(db["groups"].items())
    qs = ud.get("gq")
    if qs:
        items = [kv for kv in items if qs.lower() in str(kv[1].get("title", "")).lower()]
    sort = ud.get("gsort", "name")
    if sort == "name":
        items.sort(key=lambda kv: str(kv[1].get("title", "")).lower())
    elif sort == "activity":
        items.sort(key=lambda kv: -int(kv[1].get("last", 0)))
    elif sort == "downloads":
        items.sort(key=lambda kv: -gdl(kv[0]))
    else:
        items.sort(key=lambda kv: -int(kv[1].get("members", 0)))
    return items


def groups_list_view(page: int, ud: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    """Build Group Manager paginated overview."""
    items = filtered_groups(ud)
    total = len(items)
    pages = max(1, (total + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    sort = ud.get("gsort", "name")
    blocked = sum(1 for _, g in items if g.get("blocked"))
    table = bordered_table(
        [
            ("Total Groups", str(len(db["groups"]))),
            ("Blocked", str(blocked)),
            ("Approval Mode", "ON" if db["approval"] else "OFF"),
            ("Sort By", SORT_LABEL[sort]),
            ("Page", f"{page + 1}/{pages}"),
            ("Status", "🟢 Online"),
        ],
        headers=("Group Metric", "Value"),
    )
    text = (
        "👥 <b>Group Manager</b>\n\n"
        "<blockquote><b>Manage group permissions, formats, cooldowns, statistics, and broadcasts.</b></blockquote>\n\n"
        f"{table}\n\n"
        f"Groups: <b>{len(db['groups'])}</b>   🚫 Blocked: <b>{blocked}</b>   "
        f"🛡 Approval: <b>{'ON' if db['approval'] else 'OFF'}</b>\n"
        f"↕️ Sort: <b>{SORT_LABEL[sort]}</b>   📄 Page {page + 1}/{pages}\n"
    )
    if ud.get("gq"):
        text += f"🔍 Search: <b>{esc(ud['gq'])}</b> ({total} found)\n"
    text += "\n👇 <i>Tap a group to manage it</i>" if total else "\n<i>No groups to show.</i>"
    text += "\n\n<i>Commands: /ban /unban /warn (reply) · /approve /unapprove &lt;id&gt;</i>"

    kb = groups_list_markup(
        items=items,
        page=page,
        pages=pages,
        sort=sort,
        has_query=bool(ud.get("gq")),
        gdl_fn=gdl,
        ago_fn=ago,
    )
    return text, kb


async def detail_view(bot: Bot, gid: str) -> Optional[Tuple[str, InlineKeyboardMarkup]]:
    """Build single-group detail screen with live member count and bordered table."""
    g = db["groups"].get(gid)
    if not g:
        return None
    try:
        g["members"] = await bot.get_chat_member_count(int(gid))
        touch()
    except TelegramAPIError:
        pass
    banned = len(db["banned_groups"].get(gid, []))
    rows = [
        ("Chat ID", str(gid)),
        ("Members", str(g.get("members") or "?")),
        ("Status", "🚫 Blocked" if g.get("blocked") else "🟢 Active"),
        ("Downloads", str(gdl(gid))),
        ("Last Active", f"{ago(g.get('last'))} ago"),
        ("Banned Users", str(banned)),
    ]
    text = (
        f"👥 <b>{esc(g['title'])}</b>\n\n"
        f"<blockquote><b>Group overview and moderation controls.</b></blockquote>\n\n"
        f"{bordered_table(rows, headers=('Property', 'Value'))}\n\n"
        f"🆔 <code>{gid}</code>\n"
        f"👤 Members: <b>{g['members'] or '?'}</b>\n"
        f"📶 Status: <b>{'🚫 Blocked' if g['blocked'] else '🟢 Active'}</b>\n"
        f"⬇️ Downloads: <b>{gdl(gid)}</b>\n"
        f"🕒 Last active: <b>{ago(g['last'])} ago</b>\n"
        f"⛔ Banned users: <b>{banned}</b>"
    )
    return text, group_detail_markup(gid, bool(g.get("blocked")))


def settings_view(gid: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Build per-group settings toggle screen."""
    g = db["groups"][gid]
    text = f"⚙️ <b>Settings — {esc(g['title'])}</b>\n\n<i>Tap an option to change it.</i>"
    return text, group_settings_markup(gid, g)


def force_view(gid: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Build per-group force-join selector screen."""
    g = db["groups"][gid]
    if not db["chats"]:
        text = "🔗 <b>Force-join here</b>\n\n<i>No channels/groups added yet. Add them in /admin first.</i>"
        return text, group_back_markup(f"grp:set:{gid}")
    text = (
        f"🔗 <b>Force-join in {esc(g['title'])}</b>\n\n"
        "Selected chats are required <b>in this group</b>, even if global force-join is off."
    )
    return text, group_force_markup(gid, g)


def stats_view(gid: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Build per-group download statistics screen."""
    g = db["groups"][gid]
    s = db["gstats"].get(gid, {"n": 0, "users": {}, "songs": {}})
    tu = sorted(s["users"].values(), key=lambda u: -u["n"])[:3]
    ts = sorted(s["songs"].values(), key=lambda x: -x["n"])[:3]
    lines = [
        f"📊 <b>Stats — {esc(g['title'])}</b>\n",
        f"⬇️ Total downloads: <b>{s['n']}</b>\n",
        "👤 <b>Top users</b>",
    ]
    lines += [f"{MEDALS[i]} {esc(u['name'])} — {u['n']}" for i, u in enumerate(tu)] or [
        "<i>No data yet</i>"
    ]
    lines.append("\n🎵 <b>Top songs</b>")
    lines += [f"{MEDALS[i]} {esc(x['t'])} — {x['n']}" for i, x in enumerate(ts)] or [
        "<i>No data yet</i>"
    ]
    return "\n".join(lines), group_back_markup(f"grp:v:{gid}")


def top_view() -> Tuple[str, InlineKeyboardMarkup]:
    """Build leaderboard of top groups and most requested songs."""
    rows = sorted(((gid, g) for gid, g in db["groups"].items()), key=lambda kv: -gdl(kv[0]))[:10]
    total = sum(s["n"] for s in db["gstats"].values())
    lines = ["🏆 <b>Top groups</b>\n", f"⬇️ Total downloads (all chats): <b>{total}</b>\n"]
    for i, (gid, g) in enumerate(rows):
        lines.append(
            f"{MEDALS[i] if i < 3 else str(i + 1) + '.'} {esc(g['title'][:34])} — {gdl(gid)}"
        )
    if not rows:
        lines.append("<i>No groups yet.</i>")
    songs: Dict[str, Dict[str, Any]] = {}
    for s in db["gstats"].values():
        for vid, x in s["songs"].items():
            e = songs.setdefault(vid, {"t": x["t"], "n": 0})
            e["n"] += x["n"]
    lines.append("\n🎵 <b>Most requested songs</b>")
    top = sorted(songs.values(), key=lambda x: -x["n"])[:5]
    lines += [f"{i + 1}. {esc(x['t'])} — {x['n']}" for i, x in enumerate(top)] or [
        "<i>No data yet</i>"
    ]
    return "\n".join(lines), group_back_markup("grp:list:0")


def bc_confirm_view(ud: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    """Build broadcast target confirmation screen."""
    n = len([1 for g in db["groups"].values() if not g.get("blocked")])
    sel = len(ud["bc"]["sel"])
    text = (
        "📣 <b>Broadcast ready</b>\n\n"
        "Your message will be copied exactly as you sent it.\n"
        "Choose who gets it 👇"
    )
    return text, bc_confirm_markup(n, sel)


def bc_select_view(ud: Dict[str, Any], page: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Build broadcast group multi-select screen."""
    items = sorted(db["groups"].items(), key=lambda kv: str(kv[1].get("title", "")).lower())
    pages = max(1, (len(items) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    sel = set(ud["bc"]["sel"])
    kb = bc_select_markup(items, sel, page, pages)
    return f"☑️ <b>Select groups</b>\nPage {page + 1}/{pages}", kb


async def run_broadcast(bot: Bot, ids: List[str], bc: Dict[str, Any]) -> Tuple[int, int]:
    """Copy broadcast message `bc` to all target group IDs in `ids`."""
    ok = fail = 0
    for gid in ids:
        for attempt in (1, 2):
            try:
                await bot.copy_message(
                    chat_id=int(gid),
                    from_chat_id=bc["cid"],
                    message_id=bc["mid"],
                )
                ok += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(float(e.retry_after) + 1.0)
                if attempt == 1:
                    continue
                fail += 1
            except TelegramForbiddenError:
                fail += 1
                db["groups"].pop(gid, None)
            except TelegramAPIError:
                fail += 1
            break
        await asyncio.sleep(0.05)
    save_db()
    return ok, fail


@router.message(Command("groups"))
async def cmd_groups(msg: Message, command: CommandObject) -> None:
    """Handle /groups [search] command."""
    user = msg.from_user
    if not user or not is_admin(user.id):
        await msg.reply("⛔ Admins only.")
        return
    if msg.chat.type != "private":
        await msg.reply("👥 Please use /groups in private chat with me.")
        return
    ud = get_ud(user.id)
    clear_flags(ud)
    if command.args:
        ud["gq"] = command.args.strip()
    text, kb = groups_list_view(0, ud)
    await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("grp:"))
async def cb_groups(cq: CallbackQuery, bot: Bot) -> None:
    """Handle all `grp:*` Group Manager callbacks."""
    user = cq.from_user
    if not is_admin(user.id):
        await cq.answer("⛔ Admins only", show_alert=True)
        return
    msg = cq.message
    if not msg:
        await cq.answer()
        return
    ud = get_ud(user.id)
    parts = cq.data.split(":")
    act = parts[1]
    if act not in ("sch", "bcast"):
        ud.pop("await_gsearch", None)
        ud.pop("await_bc", None)

    async def show(view: Optional[Tuple[str, Optional[InlineKeyboardMarkup]]]) -> None:
        if view:
            await safe_edit(msg, view[0], view[1])

    async def to_list() -> None:
        await show(groups_list_view(0, ud))

    if act == "list":
        await cq.answer()
        await show(groups_list_view(int(parts[2]), ud))
    elif act == "sort":
        await cq.answer()
        ud["gsort"] = SORTS[(SORTS.index(ud.get("gsort", "name")) + 1) % len(SORTS)]
        await to_list()
    elif act == "sch":
        await cq.answer()
        ud["await_gsearch"] = True
        await show(
            (
                "🔍 <b>Search groups</b>\n\nSend part of the group name.",
                admin_cancel_markup("grp:list:0"),
            )
        )
    elif act == "clr":
        await cq.answer()
        ud.pop("gq", None)
        await to_list()
    elif act == "top":
        await cq.answer()
        await show(top_view())
    elif act == "apt":
        db["approval"] = not db["approval"]
        save_db()
        await cq.answer("🛡 Approval ON" if db["approval"] else "🛡 Approval OFF")
        await to_list()
    elif act == "ap":
        uid = int(parts[2])
        if uid not in db["approved"]:
            db["approved"].append(uid)
            save_db()
        await cq.answer("✅ User approved")
        orig_html = getattr(msg, "html_text", None) or msg.text or ""
        await safe_edit(msg, f"{orig_html}\n\n✅ <b>User approved.</b>", None)

    # Inactive cleanup
    elif act == "inact":
        await cq.answer()
        cutoff = time.time() - INACTIVE_DAYS * 86400
        n = sum(1 for g in db["groups"].values() if g["last"] < cutoff)
        await show(
            (
                f"🧹 <b>Clean inactive groups</b>\n\nGroups with no activity for <b>{INACTIVE_DAYS} days</b>: <b>{n}</b>",
                group_inactive_markup(n),
            )
        )
    elif act == "inacty":
        cutoff = time.time() - INACTIVE_DAYS * 86400
        ids = [gid for gid, g in db["groups"].items() if g["last"] < cutoff]
        await cq.answer("🧹 Cleaning…")
        for gid in ids:
            try:
                await bot.leave_chat(int(gid))
            except TelegramAPIError:
                pass
            db["groups"].pop(gid, None)
            await asyncio.sleep(0.05)
        save_db()
        await show(
            (
                f"✅ Left <b>{len(ids)}</b> inactive group(s).",
                group_back_markup("grp:list:0"),
            )
        )

    # Broadcast
    elif act == "bcast":
        await cq.answer()
        ud["await_bc"] = True
        ud.pop("bc", None)
        await show(
            (
                "📣 <b>Broadcast</b>\n\nSend the message you want to broadcast (text, photo, video…).",
                admin_cancel_markup("grp:list:0"),
            )
        )
    elif act in ("bp", "bt", "bv", "bsa", "bss"):
        if "bc" not in ud:
            await cq.answer("Start a broadcast first", show_alert=True)
            return
        if act == "bt":
            sel = ud["bc"]["sel"]
            gid = parts[2]
            sel.remove(gid) if gid in sel else sel.append(gid)
            await cq.answer()
            await show(bc_select_view(ud, int(parts[3])))
        elif act == "bp":
            await cq.answer()
            await show(bc_select_view(ud, int(parts[2])))
        elif act == "bv":
            await cq.answer()
            await show(bc_confirm_view(ud))
        else:
            ids = (
                [gid for gid, g in db["groups"].items() if not g.get("blocked")]
                if act == "bsa"
                else [gid for gid in ud["bc"]["sel"] if gid in db["groups"]]
            )
            if not ids:
                await cq.answer("No groups selected", show_alert=True)
                return
            await cq.answer()
            await show((f"📤 <b>Sending to {len(ids)} group(s)…</b>", None))
            ok, fail = await run_broadcast(bot, ids, ud.pop("bc"))
            await show(
                (
                    f"✅ <b>Broadcast done</b>\n\nSent: <b>{ok}</b>\nFailed: <b>{fail}</b>",
                    group_back_markup("grp:list:0"),
                )
            )

    # Per-group actions
    elif act in ("v", "blk", "leave", "set", "t", "fj", "fjt", "st"):
        gid = parts[2]
        g = db["groups"].get(gid)
        if not g:
            await cq.answer("Group no longer exists", show_alert=True)
            await to_list()
            return
        if act == "v":
            await cq.answer()
            await show(await detail_view(bot, gid))
        elif act == "blk":
            g["blocked"] = not g["blocked"]
            save_db()
            await cq.answer("🚫 Blocked" if g["blocked"] else "✅ Unblocked")
            await show(await detail_view(bot, gid))
        elif act == "leave":
            db["groups"].pop(gid, None)
            save_db()
            try:
                await bot.leave_chat(int(gid))
                await cq.answer("🚪 Left the group", show_alert=True)
            except TelegramAPIError:
                await cq.answer("⚠️ Couldn't leave (already removed?)", show_alert=True)
            await to_list()
        elif act == "set":
            await cq.answer()
            await show(settings_view(gid))
        elif act == "t":
            key = parts[3]
            if key in CYCLES:
                vals = CYCLES[key]
                g[key] = vals[(vals.index(g[key]) + 1) % len(vals)] if g[key] in vals else vals[0]
            elif key in TOGGLES:
                g[key] = not g[key]
            save_db()
            await cq.answer("✅ Saved")
            await show(settings_view(gid))
        elif act == "fj":
            await cq.answer()
            await show(force_view(gid))
        elif act == "fjt":
            cid = int(parts[3])
            g["force"].remove(cid) if cid in g["force"] else g["force"].append(cid)
            save_db()
            await cq.answer("✅ Saved")
            await show(force_view(gid))
        elif act == "st":
            await cq.answer()
            await show(stats_view(gid))
    else:
        await cq.answer()


# ───────────────────────── Bot added / removed + approval ─────────────────────────
@router.my_chat_member()
async def on_my_member(ev: ChatMemberUpdated, bot: Bot) -> None:
    """Handle bot being added to or removed from a group chat."""
    chat, by = ev.chat, ev.from_user
    if chat.type not in GROUP_TYPES:
        return
    new, old = ev.new_chat_member.status, ev.old_chat_member.status
    who = f'<a href="tg://user?id={by.id}">{esc(by.full_name)}</a> (<code>{by.id}</code>)'

    if new in ("left", "kicked"):
        g = db["groups"].pop(str(chat.id), None)
        if g:
            save_db()
            await notify_admins(
                bot,
                f"➖ <b>Removed from group</b>\n{esc(g['title'])}\nBy: {who}",
            )
        return

    if old in ("left", "kicked"):
        allowed = (not db["approval"]) or is_admin(by.id) or by.id in db["approved"]
        if not allowed:
            try:
                await bot.send_message(
                    chat.id,
                    "🚫 I can only be added by approved users. Leaving…",
                    parse_mode=ParseMode.HTML,
                )
                await bot.leave_chat(chat.id)
            except TelegramAPIError:
                pass
            await notify_admins(
                bot,
                f"🛡 <b>Blocked an add attempt</b>\n{esc(chat.title)} (<code>{chat.id}</code>)\nBy: {who}",
                approve_user_markup(by.id),
            )
            return
        ensure_group(chat)
        save_db()
        await notify_admins(
            bot,
            f"➕ <b>Added to group</b>\n{esc(chat.title)} (<code>{chat.id}</code>)\nBy: {who}",
        )
    else:
        ensure_group(chat)


# ───────────────────────── Moderation Commands ─────────────────────────
def target_from(msg: Message, args: List[str]) -> Tuple[Optional[int], Optional[str]]:
    """Extract target (user_id, full_name) from a replied-to message or command arguments."""
    r = msg.reply_to_message
    if r and r.from_user and not r.from_user.is_bot:
        return r.from_user.id, r.from_user.full_name
    for a in args:
        if a.lstrip("-").isdigit():
            return int(a), a
    return None, None


async def can_moderate(bot: Bot, chat: Any, user: Any) -> bool:
    """Return True if `user` is a bot admin or an admin of `chat`."""
    return is_admin(user.id) or (
        chat.type in GROUP_TYPES and await is_group_admin(bot, chat.id, user.id)
    )


@router.message(Command("ban"))
async def cmd_ban(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /ban [global] (reply|id)."""
    user = msg.from_user
    if not user:
        return
    args = (command.args or "").split()
    tid, name = target_from(msg, args)
    if tid is None:
        await msg.reply("Reply to a user (or pass their ID): /ban [global]")
        return
    glob = msg.chat.type == "private" or any(a.lower() == "global" for a in args)
    if glob and not is_admin(user.id):
        await msg.reply("⛔ Only bot admins can ban globally.")
        return
    if not glob and not await can_moderate(bot, msg.chat, user):
        await msg.reply("⛔ Only group admins can do that.")
        return
    if is_admin(tid):
        await msg.reply("❌ I can't ban a bot admin.")
        return
    lst = db["banned_global"] if glob else db["banned_groups"].setdefault(str(msg.chat.id), [])
    if tid not in lst:
        lst.append(tid)
    save_db()
    await msg.reply(
        f"🚫 <b>{esc(name)}</b> banned {'globally' if glob else 'in this group'}.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("unban"))
async def cmd_unban(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /unban [global] (reply|id)."""
    user = msg.from_user
    if not user:
        return
    args = (command.args or "").split()
    tid, name = target_from(msg, args)
    if tid is None:
        await msg.reply("Reply to a user (or pass their ID): /unban [global]")
        return
    glob = msg.chat.type == "private" or any(a.lower() == "global" for a in args)
    if glob and not is_admin(user.id):
        await msg.reply("⛔ Only bot admins can unban globally.")
        return
    if not glob and not await can_moderate(bot, msg.chat, user):
        await msg.reply("⛔ Only group admins can do that.")
        return
    lst = db["banned_global"] if glob else db["banned_groups"].setdefault(str(msg.chat.id), [])
    if tid in lst:
        lst.remove(tid)
    db["warns"].get(str(msg.chat.id), {}).pop(str(tid), None)
    save_db()
    await msg.reply(f"✅ <b>{esc(name)}</b> unbanned.", parse_mode=ParseMode.HTML)


@router.message(Command("warn"))
async def cmd_warn(msg: Message, bot: Bot) -> None:
    """Handle /warn (reply) — 3 warnings = automatic group ban."""
    user = msg.from_user
    if not user:
        return
    if msg.chat.type not in GROUP_TYPES:
        await msg.reply("⚠️ Use /warn in a group, replying to the user.")
        return
    if not await can_moderate(bot, msg.chat, user):
        await msg.reply("⛔ Only group admins can do that.")
        return
    tid, name = target_from(msg, [])
    if tid is None:
        await msg.reply("Reply to the user's message with /warn")
        return
    if is_admin(tid) or await is_group_admin(bot, msg.chat.id, tid):
        await msg.reply("❌ I can't warn an admin.")
        return
    gid = str(msg.chat.id)
    w = db["warns"].setdefault(gid, {})
    n = w.get(str(tid), 0) + 1
    if n >= WARN_LIMIT:
        w.pop(str(tid), None)
        lst = db["banned_groups"].setdefault(gid, [])
        if tid not in lst:
            lst.append(tid)
        save_db()
        await msg.reply(
            f"🚫 <b>{esc(name)}</b> reached {WARN_LIMIT} warnings and is banned here.",
            parse_mode=ParseMode.HTML,
        )
    else:
        w[str(tid)] = n
        save_db()
        await msg.reply(
            f"⚠️ <b>{esc(name)}</b> warned ({n}/{WARN_LIMIT}).",
            parse_mode=ParseMode.HTML,
        )


async def _do_approve(msg: Message, command: CommandObject, add: bool = True) -> None:
    user = msg.from_user
    if not user or not is_admin(user.id):
        await msg.reply("⛔ Admins only.")
        return
    args = (command.args or "").split()
    tid, _ = target_from(msg, args)
    if tid is None:
        await msg.reply(f"Usage: /{'approve' if add else 'unapprove'} <user_id>")
        return
    if add and tid not in db["approved"]:
        db["approved"].append(tid)
    if not add and tid in db["approved"]:
        db["approved"].remove(tid)
    save_db()
    await msg.reply(
        f"{'✅ Approved' if add else '🗑 Removed'}: <code>{tid}</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("approve"))
async def cmd_approve(msg: Message, command: CommandObject) -> None:
    """Handle /approve <user_id>."""
    await _do_approve(msg, command, add=True)


@router.message(Command("unapprove"))
async def cmd_unapprove(msg: Message, command: CommandObject) -> None:
    """Handle /unapprove <user_id>."""
    await _do_approve(msg, command, add=False)


# ───────────────────────── Per-Group Branding (/brand) ─────────────────────────
@router.message(Command("brand"))
async def cmd_brand(msg: Message, command: CommandObject, bot: Bot) -> None:
    """Handle /brand <text|off> to customize a group's footer."""
    user = msg.from_user
    if not user:
        return
    if msg.chat.type not in GROUP_TYPES:
        await msg.reply(
            fancy(
                "🏷",
                "Group footer",
                note="Use <code>/brand your text</code> <b>inside a group</b> to replace the bot's footer there.",
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    if not (is_admin(user.id) or await is_group_admin(bot, msg.chat.id, user.id)):
        await deny("🔒 Only group admins can change the footer.", msg)
        return
    g = ensure_group(msg.chat)
    text = (command.args or "").replace("\n", " ").strip()
    if not text:
        cur = esc(g["brand"]) if brand_active(g) else "<i>default (Developed by Dock)</i>"
        await msg.reply(
            fancy(
                "🏷",
                "Group footer",
                [("Current", cur)],
                note=(
                    "<code>/brand Your text here</code> — set footer (max 80 chars)\n"
                    "<code>/brand off</code> — back to default\n"
                    "⭐ Premium perk."
                ),
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    if text.lower() in ("off", "reset", "default", "remove"):
        g["brand"], g["brand_by"] = "", 0
        touch()
        await msg.reply(
            fancy("🏷", "Footer reset", note="Back to the default footer."),
            parse_mode=ParseMode.HTML,
        )
        return
    if not (BRANDING_FREE or is_premium(user.id)):
        await msg.reply(
            fancy(
                "⭐",
                "Premium perk",
                note="Custom group footers are for premium members.\nSee /premium",
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    g["brand"], g["brand_by"] = text[:80], user.id
    touch()
    await msg.reply(
        fancy(
            "🏷",
            "Footer saved",
            [("Footer", f"✨ <i>{esc(g['brand'])}</i>")],
            note="It shows on this group's bot messages while your premium is active.",
        ),
        parse_mode=ParseMode.HTML,
    )
