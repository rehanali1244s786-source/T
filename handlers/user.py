"""
handlers/user.py - /start, /help, /id, /menu, /lang, /stats and interactive "ITX TALHA BUG BOT" style menu callbacks.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Tuple

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from animations import (
    ANIM_DELAY_FAST,
    START_FRAMES,
    animate_frames,
    bordered_table,
    esc,
    fancy,
    safe_edit,
    welcome_card_text,
)
from config import (
    BOT_VERSION,
    MENU_BANNER_URL,
    MONO_FOOTER,
    is_admin,
)
from db import (
    ERR,
    _users,
    db,
    follow_limit,
    gsettings,
    prem_label,
    recog_limit,
    recog_used,
    ref_count,
    touch,
    user_follows,
    user_total,
)
from handlers.premium import premium_view
from handlers.song import direct_download, send_card
from i18n import LANG_NAMES, L, help_text, tr
from keyboards import (
    lang_markup,
    menu_categories_markup,
    start_markup,
    submenu_back_markup,
)
from middlewares import group_ok
from services.youtube import _meta_for

router = Router(name="user")


def build_menu_overview_text(mode: str = "all") -> str:
    """
    Build the 'Command Library —— Menu' view matching the video's layout:
    - Centered bold description in blockquote
    - Bordered Category | Count table
    - Expandable/collapsible blockquote command lists
    - Monospace footer
    """
    title = "Command Library —— Menu" if mode == "all" else "Action Center —— Menu"
    desc = (
        "This is the command library menu. Click the menu below to see the list of commands available in this bot."
        if mode == "all"
        else "Quick interactive actions for downloading music, 480p video, recognizing audio, and managing alerts."
    )
    table = bordered_table(
        [
            ("Music & Video", "4"),
            ("Recognition", "2"),
            ("Artist & Alerts", "3"),
            ("Premium & VIP", "4"),
            ("System & User", "5"),
            ("Group & Admin", "7"),
        ],
        headers=("Category", "Count"),
    )
    expandable = (
        "<blockquote expandable>"
        "📲 <b>Click Here</b>\n\n"
        "🎵 <b>Music &amp; Video - Menu</b>\n"
        "• <code>/song &lt;name&gt; a</code> — Download MP3/M4A Audio\n"
        "• <code>/song &lt;name&gt; v</code> — Download 480p Video\n"
        "• <code>/search &lt;name&gt;</code> — Numbered search results\n"
        "• <code>/lyrics &lt;name&gt;</code> — Fetch full song lyrics\n\n"
        "🎧 <b>Recognition - Menu</b>\n"
        "• <code>/find</code> — Reply to voice/audio/video to identify song\n"
        "• Voice/Audio in PM — Auto-identify via AudD\n\n"
        "🎤 <b>Artist &amp; Alerts - Menu</b>\n"
        "• <code>/artist &lt;name&gt;</code> — Bio, albums &amp; top tracks\n"
        "• <code>/follow &lt;artist&gt;</code> — Subscribe to release alerts\n"
        "• <code>/following</code> — Manage followed artists\n\n"
        "⭐ <b>Premium &amp; VIP - Menu</b>\n"
        "• <code>/premium</code> — JazzCash / Easypaisa VIP upgrade\n"
        "• <code>/invite</code> — Referral link for extra recognitions\n"
        "• <code>/brand &lt;text&gt;</code> — Custom group footer\n\n"
        "⚙️ <b>System &amp; User - Menu</b>\n"
        "• <code>/start</code> · <code>/menu</code> · <code>/help</code> · <code>/stats</code> · <code>/lang</code> · <code>/id</code>\n\n"
        "🛡️ <b>Group &amp; Admin - Menu</b>\n"
        "• <code>/admin</code> · <code>/groups</code> · <code>/ban</code> · <code>/unban</code> · <code>/warn</code> · <code>/approve</code> · <code>/unapprove</code>"
        "</blockquote>"
    )
    return (
        f"🕸 <b>{title}</b>\n\n"
        f"<blockquote><b>{desc}</b></blockquote>\n\n"
        f"{table}\n\n"
        f"{expandable}\n\n"
        f"Click the menu above or buttons below to see the command list\n\n"
        f"{MONO_FOOTER}"
    )


def build_my_info_text(user: Any) -> str:
    """Build the 'my - info' bordered table card for the user."""
    uid = user.id
    lang_code = L(uid)
    rows = [
        ("Name", (user.full_name or "User")[:24]),
        ("User ID", str(uid)),
        ("Plan", prem_label(uid)),
        ("Downloads", str(user_total(uid))),
        ("Recognitions", f"{recog_used(uid)}/{'∞' if is_admin(uid) else recog_limit(uid)} today"),
        ("Referrals", str(ref_count(uid))),
        ("Following", f"{len(user_follows(uid))}/{follow_limit(uid)} artists"),
        ("Language", LANG_NAMES.get(lang_code, "English")),
        ("Status", "🟢 Online"),
    ]
    return (
        f"❓ <b>User Profile —— My Info</b>\n\n"
        f"<blockquote><b>Your live account status, limits, and download statistics.</b></blockquote>\n\n"
        f"{bordered_table(rows, headers=('Field', 'Value'))}\n\n"
        f"{MONO_FOOTER}"
    )


def build_category_page(cat: str) -> Tuple[str, str]:
    """Return (text, back_page) for a specific menu category page."""
    pages: Dict[str, Tuple[str, str, list]] = {
        "features": (
            "💡 Bot Features Overview",
            "High-speed YouTube Audio & 480p Video Downloader with full metadata and group controls.",
            [
                ("Audio", "320k/192k M4A & MP3"),
                ("Video", "Always crisp 480p MP4"),
                ("Recognition", "AudD voice/audio/video ID"),
                ("Metadata", "MusicBrainz + Deezer BPM"),
                ("Lyrics", "Full synced/plain lrclib"),
                ("Alerts", "New release watcher"),
                ("Status", "🟢 Online"),
            ],
        ),
        "cat_music": (
            "🎵 Music & Video Commands",
            "Download songs or 480p videos directly or choose from interactive search cards.",
            [
                ("/song <n> a", "Direct Audio (MP3/M4A)"),
                ("/song <n> v", "Direct Video (480p MP4)"),
                ("/song <n>", "Interactive picker list"),
                ("/search <n>", "Numbered results + MP3/MP4"),
                ("/lyrics <n>", "Full song lyrics"),
                ("@bot <n>", "Inline search in any chat"),
            ],
        ),
        "cat_video": (
            "🎬 480p Video Downloader",
            "Every video request is automatically optimized at 480p MP4 for fast streaming under 50 MB.",
            [
                ("Command", "/song <name> v"),
                ("YouTube URL", "Paste link + tap Video 480p"),
                ("Resolution", "480p MP4 (streaming ready)"),
                ("Max Length", "15 min default (configurable)"),
                ("Max Size", "50 MB Telegram limit"),
            ],
        ),
        "cat_recog": (
            "🎧 Song Recognition (AudD)",
            "Identify any song from a voice note, audio file, or video clip in seconds.",
            [
                ("Private Chat", "Send voice/audio/video clip"),
                ("In Groups", "Reply to clip with /find"),
                ("Free Limit", f"{recog_limit(0)} recognitions/day"),
                ("Bonus", "Invite friends with /invite"),
            ],
        ),
        "cat_artist": (
            "🎤 Artist Pages & Release Alerts",
            "Explore artist discographies on MusicBrainz and get notified when new music drops.",
            [
                ("/artist <n>", "Bio, latest albums & top 5"),
                ("/follow <n>", "Get new release alerts"),
                ("/following", "List & unfollow artists"),
            ],
        ),
        "cat_prem": (
            "⭐ Premium & VIP Perks",
            "Upgrade via JazzCash or Easypaisa for priority queue, higher limits, and group branding.",
            [
                ("/premium", "View price & pay methods"),
                ("/invite", "Earn bonus recognitions"),
                ("/brand <txt>", "Set custom group footer"),
                ("Priority", "Skip ahead in download queue"),
            ],
        ),
        "cat_sys": (
            "⚙️ System & User Commands",
            "General commands for navigation, language selection, and statistics.",
            [
                ("/start", "Welcome card & banner"),
                ("/menu", "Interactive command library"),
                ("/help", "Full usage guide"),
                ("/stats", "Bot & personal statistics"),
                ("/lang", "English / اردو / हिन्दी"),
                ("/id", "Your Telegram & Chat ID"),
            ],
        ),
        "cat_admin": (
            "🛡️ Group & Admin Commands",
            "Complete group moderation, per-group settings, force-join channels, and broadcasts.",
            [
                ("/admin", "Force-join & Premium panel"),
                ("/groups", "Group manager & broadcast"),
                ("/ban [global]", "Ban user in group/globally"),
                ("/unban", "Unban user & clear warns"),
                ("/warn", "Warn user (3 warns = ban)"),
                ("/approve", "Allow user to add bot"),
                ("/unapprove", "Revoke group-add approval"),
            ],
        ),
    }
    title, desc, rows = pages.get(cat, pages["features"])
    back = "home" if cat == "features" else "all"
    text = (
        f"🕸 <b>{esc(title)}</b>\n\n"
        f"<blockquote><b>{esc(desc)}</b></blockquote>\n\n"
        f"{bordered_table(rows, headers=('Command / Item', 'Description'))}\n\n"
        f"{MONO_FOOTER}"
    )
    return text, back


async def _send_banner_or_text(
    bot: Bot,
    msg: Message,
    text: str,
    markup: Any,
    status_msg: Message | None = None,
) -> None:
    """Send banner image with caption if MENU_BANNER_URL is configured and valid, else edit/send text."""
    if MENU_BANNER_URL:
        try:
            await msg.answer_photo(
                photo=MENU_BANNER_URL,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            if status_msg:
                try:
                    await status_msg.delete()
                except TelegramAPIError:
                    pass
            return
        except TelegramAPIError:
            pass
    if status_msg:
        await safe_edit(status_msg, text, markup)
    else:
        await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)


@router.message(Command("start"))
async def cmd_start(msg: Message, command: CommandObject, bot: Bot) -> None:
    """
    Handle /start:
    - Deep links: `a_<vid>`, `v_<vid>`, `song_<vid>`, `premium`, `ref_<uid>`
    - Normal /start: typing action + animated preparing frames, then banner photo + welcome card.
    """
    user = msg.from_user
    if not user:
        return
    lang = L(user.id)
    arg = (command.args or "").strip()

    # Deep link from inline mode: /start a_<id> or v_<id>
    if arg and re.fullmatch(r"[av]_[\w-]{11}", arg):
        if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
            return
        g = gsettings(msg.chat)
        status = await msg.reply(tr(lang, "fetching"), parse_mode=ParseMode.HTML)
        await direct_download(bot, msg, status, arg[2:], arg[0], g)
        return

    # Share-card deep link: /start song_<id>
    if arg and re.fullmatch(r"song_[\w-]{11}", arg):
        if not await group_ok(bot, msg.chat, user, cooldown=True, msg=msg):
            return
        try:
            meta = await _meta_for(arg[5:])
        except Exception:
            await msg.reply(tr(lang, "bad_link"), parse_mode=ParseMode.HTML)
            return
        await send_card(bot, msg.chat.id, meta, gsettings(msg.chat), lang)
        return

    # Premium deep link: /start premium
    if arg == "premium":
        me = await bot.get_me()
        text, kb = premium_view(user.id, private=(msg.chat.type == "private"), bot_username=me.username or "bot")
        await msg.reply(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # Animated loading sequence before showing the welcome banner card
    try:
        await bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.TYPING)
    except TelegramAPIError:
        pass

    status = await msg.reply(START_FRAMES[0], parse_mode=ParseMode.HTML)
    await animate_frames(status, START_FRAMES[1:], delay=ANIM_DELAY_FAST)

    text = welcome_card_text(user, lang)
    kb = start_markup(user.id)
    await _send_banner_or_text(bot, msg, text, kb, status_msg=status)


@router.message(Command("menu"))
async def cmd_menu(msg: Message, bot: Bot) -> None:
    """Handle /menu command: display the Command Library menu with banner and category buttons."""
    user = msg.from_user
    if not user:
        return
    text = build_menu_overview_text("all")
    kb = menu_categories_markup(user.id, mode="all")
    await _send_banner_or_text(bot, msg, text, kb)


@router.callback_query(F.data.startswith("mn:"))
async def cb_menu(cq: CallbackQuery, bot: Bot) -> None:
    """Handle interactive menu navigation callbacks (`mn:home`, `mn:all`, `mn:action`, `mn:myinfo`, etc.)."""
    user = cq.from_user
    msg = cq.message
    if not msg:
        await cq.answer()
        return
    page = cq.data.split(":", 1)[1]
    lang = L(user.id)
    await cq.answer()

    if page == "home":
        await safe_edit(msg, welcome_card_text(user, lang), start_markup(user.id))
    elif page == "all":
        await safe_edit(msg, build_menu_overview_text("all"), menu_categories_markup(user.id, mode="all"))
    elif page == "action":
        await safe_edit(msg, build_menu_overview_text("action"), menu_categories_markup(user.id, mode="action"))
    elif page == "myinfo":
        await safe_edit(msg, build_my_info_text(user), submenu_back_markup("home"))
    elif page == "lang":
        await safe_edit(msg, tr(lang, "lang_pick"), lang_markup(lang))
    else:
        text, back_page = build_category_page(page)
        await safe_edit(msg, text, submenu_back_markup(back_page))


@router.message(Command("help"))
async def cmd_help(msg: Message, bot: Bot) -> None:
    """Handle /help command."""
    user = msg.from_user
    if not user:
        return
    me = await bot.get_me()
    await msg.reply(
        help_text(L(user.id), me.username),
        parse_mode=ParseMode.HTML,
        reply_markup=submenu_back_markup("home"),
    )


@router.callback_query(F.data == "help")
async def cb_help(cq: CallbackQuery, bot: Bot) -> None:
    """Handle '📖 How to use' button."""
    await cq.answer()
    me = await bot.get_me()
    if cq.message:
        await bot.send_message(
            cq.message.chat.id,
            help_text(L(cq.from_user.id), me.username),
            parse_mode=ParseMode.HTML,
            reply_markup=submenu_back_markup("home"),
        )


@router.message(Command("id"))
async def cmd_id(msg: Message) -> None:
    """Handle /id command."""
    uid = msg.from_user.id if msg.from_user else 0
    await msg.reply(
        f"👤 Your ID: <code>{uid}</code>\n💬 Chat ID: <code>{msg.chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("lang"))
async def cmd_lang(msg: Message) -> None:
    """Handle /lang command."""
    uid = msg.from_user.id if msg.from_user else 0
    lang = L(uid)
    await msg.reply(
        tr(lang, "lang_pick"),
        parse_mode=ParseMode.HTML,
        reply_markup=lang_markup(lang),
    )


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(cq: CallbackQuery) -> None:
    """Handle language change button."""
    code = cq.data.split(":", 1)[1]
    if code not in LANG_NAMES:
        await cq.answer()
        return
    db["ulang"][str(cq.from_user.id)] = code
    touch()
    await cq.answer("✅")
    if cq.message:
        await safe_edit(
            cq.message,
            tr(code, "lang_set", name=LANG_NAMES[code]),
            submenu_back_markup("home"),
        )


@router.message(Command("stats"))
async def cmd_stats(msg: Message) -> None:
    """
    Handle /stats command:
    Shows centered bold description + bordered table with Online green dot + top songs + admin metrics.
    """
    user = msg.from_user
    if not user:
        return
    lang = L(user.id)
    total = sum(s["n"] for s in db["gstats"].values())
    tot = db["tot"]
    today = db["daily"].get(time.strftime("%Y-%m-%d"), 0)

    songs: Dict[str, Dict[str, Any]] = {}
    for s in db["gstats"].values():
        for vid, x in s["songs"].items():
            e = songs.setdefault(vid, {"t": x["t"], "n": 0})
            e["n"] += x["n"]
    top = sorted(songs.values(), key=lambda x: -x["n"])[:5]

    rows = [
        (tr(lang, "st_users"), str(len(_users))),
        (tr(lang, "st_total"), str(total)),
        (tr(lang, "st_today"), str(today)),
        (tr(lang, "st_audio"), str(tot.get("a", 0))),
        (tr(lang, "st_video"), str(tot.get("v", 0))),
        (tr(lang, "st_you"), str(user_total(user.id))),
        ("Premium", prem_label(user.id)),
        ("Status", "🟢 Online"),
    ]

    lines = [
        tr(lang, "st_title"),
        "<blockquote><b>Live bot statistics, download counters, and top requested tracks.</b></blockquote>",
        "",
        bordered_table(rows, headers=("Metric", "Value")),
        "",
        f"👥 {tr(lang, 'st_users')}: <b>{len(_users)}</b> · ⬇️ {tr(lang, 'st_total')}: <b>{total}</b> · 📅 {tr(lang, 'st_today')}: <b>{today}</b>",
        f"🎵 {tr(lang, 'st_audio')}: <b>{tot.get('a', 0)}</b>  ·  🎬 {tr(lang, 'st_video')}: <b>{tot.get('v', 0)}</b>",
        f"👤 {tr(lang, 'st_you')}: <b>{user_total(user.id)}</b>  ·  ⭐ Premium: <b>{prem_label(user.id)}</b>",
        "",
        tr(lang, "st_top"),
    ]
    lines += [f"{i + 1}. {esc(x['t'])} — {x['n']}" for i, x in enumerate(top)] or [
        f"<i>{tr(lang, 'st_none')}</i>"
    ]

    if is_admin(user.id):
        week = sum(
            v
            for k, v in db["daily"].items()
            if k >= time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400))
        )
        admin_rows = [
            ("Groups", str(len(db["groups"]))),
            ("Last 7 days", str(week)),
            ("Banned (global)", str(len(db["banned_global"]))),
            ("Failure streak", str(ERR["streak"])),
            ("Status", "🟢 Online"),
        ]
        lines += [
            "",
            "🛠 <b>Admin Overview</b>",
            bordered_table(admin_rows, headers=("Admin Metric", "Value")),
        ]

    await msg.reply(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=submenu_back_markup("home"),
    )
