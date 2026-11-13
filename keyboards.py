"""
keyboards.py - All inline buttons, CallbackData factories, coloured button styles, and keyboard builders.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic import ConfigDict

from config import (
     FMT_LABEL,
    GDEF,
    GROUPS_PER_PAGE,
    HAVE_LIBROSA,
    INACTIVE_DAYS,
    METHODS,
    NUMS,
    OWNER_URL,
    SORT_LABEL,
    VIDEO_QUALITY,
    is_admin,
)
from db import db
from i18n import LANG_NAMES, tr

# ───────────────────────── Coloured Button Support ─────────────────────────
# Telegram Bot API supports coloured button styles ("success" = green, "danger" = red, "primary" = blue).
# NOTE: If the installed aiogram version does not declare `style` as an explicit field on
# InlineKeyboardButton, StyledInlineKeyboardButton uses `extra="allow"` so Pydantic serializes
# `style` directly in the JSON payload sent to Telegram.
class StyledInlineKeyboardButton(InlineKeyboardButton):
    """InlineKeyboardButton subclass that preserves the Telegram `style` field in JSON serialization."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    style: Optional[str] = None


_RED = re.compile(
    r"remove|cancel|delete|block|\bban\b|clean|clear|reset|back|reject|unfollow|"
    r"all\s*-\s*menu|action\s*-\s*menu|my\s*-\s*info|🗑|❌|🚫|🧹|🥀|🚨|❓",
    re.I,
)
_GREEN = re.compile(
    r"audio|video|mp3|mp4|download|joined|✅|approve|confirm|send|start|open|"
    r"contact\s*owner|learn\s*features|follow|invite|paid|analyze|"
    r"ڈاؤن|آڈیو|ऑडियो|unblock|verify|✈️|💡",
    re.I,
)


def Btn(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[str] = None,
    **kw: Any,
) -> InlineKeyboardButton:
    """
    Build an InlineKeyboardButton with automatic or explicit Telegram colour style:
    - "success" (green) for main actions (Download, Audio, Video, Confirm, I've Joined, Contact Owner)
    - "danger" (red) for navigation/destructive (All Menu, Action Menu, My Info, Cancel, Back, Reject)
    - "primary" (blue) for secondary actions (Info, Lyrics, Share)
    Also ensures link-style buttons include a clear icon cue and never rely solely on emoji for colour.
    """
    if style is None:
        t = text.replace("✅ Unblock", "unblock")
        if _RED.search(t) and "unblock" not in t.lower():
            style = "danger"
        elif _GREEN.search(t):
            style = "success"
        else:
            style = "primary"

    # Add arrow cue on URL buttons if not already present
    if url and "↗" not in text:
        text = f"{text} ↗"

    return StyledInlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        url=url,
        style=style,
        **kw,
    )


# ───────────────────────── CallbackData Factories (< 64 bytes) ─────────────────────────
class LangCB(CallbackData, prefix="lang"):
    code: str


class PickCB(CallbackData, prefix="p"):
    vid: str


class DownloadCB(CallbackData, prefix="d"):
    fmt: str
    vid: str


class LyricsCB(CallbackData, prefix="ly"):
    vid: str


class InfoCB(CallbackData, prefix="in"):
    vid: str


class BpmCB(CallbackData, prefix="bk"):
    vid: str


class ShareCB(CallbackData, prefix="sh"):
    vid: str


class ArtistCB(CallbackData, prefix="ar"):
    mbid: str


class FollowCB(CallbackData, prefix="fl"):
    mbid: str


class UnfollowCB(CallbackData, prefix="uf"):
    mbid: str


class MenuCB(CallbackData, prefix="mn"):
    page: str


# ───────────────────────── Navigation Helpers ─────────────────────────
def nav_row(back_cb: str = "mn:home", include_home: bool = True) -> List[InlineKeyboardButton]:
    """Standard Back and Home navigation row for sub-menus."""
    row = [Btn("🥀 ⬅️ Back", callback_data=back_cb, style="danger")]
    if include_home and back_cb != "mn:home":
        row.append(Btn("🏠 Home", callback_data="mn:home", style="danger"))
    return row


# ───────────────────────── Start & Menu Keyboards (ITX TALHA Style + v3) ─────────────────────────
def start_markup(uid: int) -> InlineKeyboardMarkup:
    """Main welcome keyboard combining ITX TALHA BUG BOT style buttons and Music Bot v3 actions."""
    b = InlineKeyboardBuilder()
    b.row(Btn("💡 Learn Features", callback_data=MenuCB(page="features").pack(), style="success"))
    b.row(
        Btn("📖 all - menu", callback_data=MenuCB(page="all").pack(), style="danger"),
        Btn("🚨 action - menu", callback_data=MenuCB(page="action").pack(), style="danger"),
    )
    b.row(Btn("❓ my - info", callback_data=MenuCB(page="myinfo").pack(), style="danger"))
    b.row(
        Btn("⭐ Premium", callback_data="pay:home", style="primary"),
        Btn("🎁 Invite & Earn", callback_data="inv", style="success"),
    )
    b.row(
        Btn("📖 How to use", callback_data="help", style="primary"),
        Btn("🌐 Language", callback_data=MenuCB(page="lang").pack(), style="primary"),
    )
    if is_admin(uid):
        b.row(
            Btn("🛠 Admin Panel", callback_data="adm:home", style="primary"),
            Btn("👥 Groups", callback_data="grp:list:0", style="primary"),
        )
    b.row(Btn("✈️ Contact Owner", url=OWNER_URL, style="success"))
    return b.as_markup()


def menu_categories_markup(uid: int, mode: str = "all") -> InlineKeyboardMarkup:
    """
    Category selector keyboard for 'all - menu' and 'action - menu' matching the video's
    Command Library layout, with Back and Contact Owner buttons.
    """
    b = InlineKeyboardBuilder()
    if mode == "action":
        b.row(
            Btn("🎵 Quick Audio (/song)", callback_data=MenuCB(page="cat_music").pack(), style="success"),
            Btn("🎬 Quick Video 480p", callback_data=MenuCB(page="cat_video").pack(), style="success"),
        )
        b.row(
            Btn("🎧 Recognize Song (/find)", callback_data=MenuCB(page="cat_recog").pack(), style="primary"),
            Btn("🎤 Artist & Follow", callback_data=MenuCB(page="cat_artist").pack(), style="primary"),
        )
        b.row(
            Btn("⭐ Premium & Perks", callback_data="pay:home", style="primary"),
            Btn("🎁 Invite & Earn", callback_data="inv", style="success"),
        )
    else:
        b.row(
            Btn("🎵 Music & Video - Menu", callback_data=MenuCB(page="cat_music").pack(), style="primary"),
            Btn("🎧 Recognition - Menu", callback_data=MenuCB(page="cat_recog").pack(), style="primary"),
        )
        b.row(
            Btn("🎤 Artist & Alerts - Menu", callback_data=MenuCB(page="cat_artist").pack(), style="primary"),
            Btn("⭐ Premium & VIP - Menu", callback_data=MenuCB(page="cat_prem").pack(), style="primary"),
        )
        b.row(
            Btn("⚙️ System & User - Menu", callback_data=MenuCB(page="cat_sys").pack(), style="primary"),
            Btn("🛡️ Group & Admin - Menu", callback_data=MenuCB(page="cat_admin").pack(), style="primary"),
        )
    if is_admin(uid):
        b.row(
            Btn("🛠 Admin Panel", callback_data="adm:home", style="primary"),
            Btn("👥 Group Manager", callback_data="grp:list:0", style="primary"),
        )
    b.row(Btn("🥀 back menu", callback_data=MenuCB(page="home").pack(), style="danger"))
    b.row(Btn("✈️ Contact Owner", url=OWNER_URL, style="success"))
    return b.as_markup()


def submenu_back_markup(back_page: str = "all") -> InlineKeyboardMarkup:
    """Back + Home + Contact Owner keyboard for category detail screens."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn("🥀 back menu", callback_data=MenuCB(page=back_page).pack(), style="danger"),
        Btn("🏠 Home", callback_data=MenuCB(page="home").pack(), style="danger"),
    )
    b.row(Btn("✈️ Contact Owner", url=OWNER_URL, style="success"))
    return b.as_markup()


# ───────────────────────── Force-Join & Language Keyboards ─────────────────────────
def join_markup(missing: Sequence[Dict[str, Any]], lang: str = "en") -> InlineKeyboardMarkup:
    """Force-join keyboard with channel/group URL buttons and 'I've Joined' button."""
    b = InlineKeyboardBuilder()
    for c in missing:
        if c.get("link"):
            icon = "📢" if c.get("type") == "channel" else "👥"
            b.row(
                Btn(
                    f"{icon} " + tr(lang, "join_btn", title=str(c["title"])[:30]),
                    url=str(c["link"]),
                    style="primary",
                )
            )
    b.row(Btn(tr(lang, "join_done"), callback_data="chk", style="success"))
    return b.as_markup()


def lang_markup(current_lang: str) -> InlineKeyboardMarkup:
    """Language selection keyboard with Back/Home row."""
    b = InlineKeyboardBuilder()
    for code, name in LANG_NAMES.items():
        prefix = "✅ " if code == current_lang else "🌐 "
        style = "success" if code == current_lang else "primary"
        b.row(Btn(prefix + name, callback_data=LangCB(code=code).pack(), style=style))
    b.row(*nav_row("mn:home", include_home=False))
    return b.as_markup()


# ───────────────────────── Search & Song Card Keyboards ─────────────────────────
def search_results_markup(results: Sequence[Dict[str, Any]], g: Dict[str, Any] = GDEF) -> InlineKeyboardMarkup:
    """
    Search results keyboard:
    - One row per result with two direct download buttons: (🎵 MP3, 🎬 MP4) as required by Section 3
    - Plus the numbered picker row (1️⃣..5️⃣) so users can also open the full song card (Lyrics/Info/Share/BPM).
    """
    b = InlineKeyboardBuilder()
    num_row: List[InlineKeyboardButton] = []
    for i, r in enumerate(results[:5]):
        vid = r["id"]
        row_btns: List[InlineKeyboardButton] = []
        if g.get("fmt", "both") in ("both", "audio"):
            row_btns.append(
                Btn(
                    f"{NUMS[i]} 🎵 MP3",
                    callback_data=DownloadCB(fmt="a", vid=vid).pack(),
                    style="success",
                )
            )
        if g.get("fmt", "both") in ("both", "video"):
            row_btns.append(
                Btn(
                    f"{NUMS[i]} 🎬 MP4",
                    callback_data=DownloadCB(fmt=str(VIDEO_QUALITY), vid=vid).pack(),
                    style="success",
                )
            )
        if row_btns:
            b.row(*row_btns)
        num_row.append(Btn(f"ℹ️ {NUMS[i]}", callback_data=PickCB(vid=vid).pack(), style="primary"))
    if num_row:
        b.row(*num_row)
    return b.as_markup()


def card_markup(vid: str, g: Dict[str, Any] = GDEF, lang: str = "en") -> InlineKeyboardMarkup:
    """Song card buttons: Audio, Video 480p, Lyrics, Info, Share, and Analyze BPM & key."""
    b = InlineKeyboardBuilder()
    if g.get("fmt", "both") in ("both", "audio"):
        b.row(Btn(tr(lang, "btn_audio"), callback_data=DownloadCB(fmt="a", vid=vid).pack(), style="success"))
    if g.get("fmt", "both") in ("both", "video"):
        b.row(
            Btn(
                tr(lang, "btn_video"),
                callback_data=DownloadCB(fmt=str(VIDEO_QUALITY), vid=vid).pack(),
                style="success",
            )
        )
    b.row(
        Btn(tr(lang, "btn_lyrics"), callback_data=LyricsCB(vid=vid).pack(), style="primary"),
        Btn("ℹ️ Info", callback_data=InfoCB(vid=vid).pack(), style="primary"),
    )
    b.row(
        Btn("🔗 Share", callback_data=ShareCB(vid=vid).pack(), style="primary"),
        Btn("🎚 Analyze BPM & key", callback_data=BpmCB(vid=vid).pack(), style="success"),
    )
    return b.as_markup()


def info_markup(vid: str, info: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Song info view keyboard."""
    b = InlineKeyboardBuilder()
    if HAVE_LIBROSA and not info.get("bpm"):
        b.row(Btn("🎚 Analyze BPM & key", callback_data=BpmCB(vid=vid).pack(), style="success"))
    if info.get("artist_id"):
        b.row(Btn("🎤 Artist page", callback_data=ArtistCB(mbid=info["artist_id"]).pack(), style="primary"))
    b.row(
        Btn("🔗 Share", callback_data=ShareCB(vid=vid).pack(), style="primary"),
        Btn("🎤 Lyrics", callback_data=LyricsCB(vid=vid).pack(), style="primary"),
    )
    b.row(Btn("🎵 Card", callback_data=PickCB(vid=vid).pack(), style="success"))
    return b.as_markup()


def share_markup(link: str, share_url: str) -> InlineKeyboardMarkup:
    """Share card keyboard with link-style buttons."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn("🎧 Open in bot", url=link, style="success"),
        Btn("📤 Share", url=share_url, style="primary"),
    )
    return b.as_markup()


def inline_result_markup(bot_name: str, vid: str, lang: str) -> InlineKeyboardMarkup:
    """Inline query result buttons."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn(tr(lang, "btn_audio"), url=f"https://t.me/{bot_name}?start=a_{vid}", style="success"),
        Btn(tr(lang, "btn_video"), url=f"https://t.me/{bot_name}?start=v_{vid}", style="success"),
    )
    return b.as_markup()


# ───────────────────────── Artist, Follow & Invite Keyboards ─────────────────────────
def artist_markup(songs: Sequence[Dict[str, Any]], art: Optional[Dict[str, Any]]) -> Optional[InlineKeyboardMarkup]:
    """Artist card keyboard with top song numbers and Follow button."""
    b = InlineKeyboardBuilder()
    has_rows = False
    if songs:
        nums = [Btn(NUMS[i], callback_data=PickCB(vid=r["id"]).pack(), style="primary") for i, r in enumerate(songs[:5])]
        b.row(*nums)
        has_rows = True
    if art and art.get("id"):
        b.row(Btn("🔔 Follow — new release alerts", callback_data=FollowCB(mbid=art["id"]).pack(), style="success"))
        has_rows = True
    b.row(*nav_row("mn:home", include_home=False))
    return b.as_markup() if has_rows else b.as_markup()


def following_markup(mine: Sequence[str]) -> InlineKeyboardMarkup:
    """List of followed artists with Unfollow buttons and Back/Home row."""
    b = InlineKeyboardBuilder()
    for m in mine:
        name = db["artists"].get(m, {}).get("n", "Artist")[:26]
        b.row(Btn(f"🗑 Unfollow · {name}", callback_data=UnfollowCB(mbid=m).pack(), style="danger"))
    b.row(*nav_row("mn:home", include_home=False))
    return b.as_markup()


def release_alert_markup(artist_name: str, release_title: str, mbid: str) -> InlineKeyboardMarkup:
    """New release notification keyboard."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn(
            "🔎 Find & download",
            switch_inline_query_current_chat=f"{artist_name} {release_title}"[:60],
            style="success",
        )
    )
    b.row(Btn("🔕 Unfollow", callback_data=UnfollowCB(mbid=mbid).pack(), style="danger"))
    return b.as_markup()


def invite_markup(link: str) -> InlineKeyboardMarkup:
    """Referral /invite keyboard."""
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('🎧 Download any song or video — free!')}"
    b = InlineKeyboardBuilder()
    b.row(Btn("📤 Share my link", url=share, style="success"))
    b.row(Btn("⭐ Go Premium", callback_data="pay:home", style="primary"))
    b.row(*nav_row("mn:home", include_home=False))
    return b.as_markup()


# ───────────────────────── Premium & Payment Keyboards ─────────────────────────
def premium_markup(private: bool = True, bot_username: str = "bot") -> Optional[InlineKeyboardMarkup]:
    """Premium overview keyboard."""
    b = InlineKeyboardBuilder()
    if not private:
        b.row(Btn("⭐ Open in private chat", url=f"https://t.me/{bot_username}?start=premium", style="success"))
        return b.as_markup()
    p = db["pay"]
    if p["price"] and any(p[m]["num"] for m in METHODS):
        if p["jc"]["num"]:
            b.row(Btn("🔴 Pay with JazzCash", callback_data="pay:m:jc", style="danger"))
        if p["ep"]["num"]:
            b.row(Btn("🟢 Pay with Easypaisa", callback_data="pay:m:ep", style="success"))
    b.row(*nav_row("mn:home", include_home=False))
    return b.as_markup()


def payment_method_markup(m: str) -> InlineKeyboardMarkup:
    """JazzCash / Easypaisa payment instructions keyboard."""
    b = InlineKeyboardBuilder()
    b.row(Btn("✅ I've Paid", callback_data=f"pay:paid:{m}", style="success"))
    b.row(*nav_row("pay:home", include_home=True))
    return b.as_markup()


def cancel_pay_markup() -> InlineKeyboardMarkup:
    """Cancel payment proof submission keyboard."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn("❌ Cancel", callback_data="pay:home", style="danger"),
        Btn("🏠 Home", callback_data="mn:home", style="danger"),
    )
    return b.as_markup()


def proof_review_markup(uid: int, days: int) -> InlineKeyboardMarkup:
    """Admin Approve / Reject buttons on a user's payment proof."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn(f"✅ Approve +{days}d", callback_data=f"pay:ok:{uid}", style="success"),
        Btn("❌ Reject", callback_data=f"pay:no:{uid}", style="danger"),
    )
    return b.as_markup()


# ───────────────────────── Admin & Group Manager Keyboards ─────────────────────────
def admin_home_markup() -> InlineKeyboardMarkup:
    """Main /admin panel keyboard."""
    on = db["enabled"]
    maint = db.get("maintenance", False)
    b = InlineKeyboardBuilder()
    b.row(Btn("➕ Add channel / group", callback_data="adm:add", style="success"))
    b.row(Btn(f"👥 Manage Groups ({len(db['groups'])})", callback_data="grp:list:0", style="primary"))
    b.row(Btn("⭐ Premium & Sponsor", callback_data="adm:prem", style="success"))
    b.row(
        Btn(
            f"🔐 Force-join: {'ON ✅' if on else 'OFF ❌'} (tap to toggle)",
            callback_data="adm:tog",
            style="success" if on else "danger",
        )
    )
    b.row(
        Btn(
            f"🛠 Maintenance: {'ON 🟠' if maint else 'OFF 🟢'}",
            callback_data="adm:maint",
            style="danger" if maint else "primary",
        )
    )
    for c in db["chats"]:
        b.row(Btn(f"🗑 Remove · {str(c['title'])[:28]}", callback_data=f"adm:rm:{c['id']}", style="danger"))
    b.row(
        Btn("🔄 Refresh", callback_data="adm:home", style="primary"),
        Btn("🏠 Home", callback_data="mn:home", style="danger"),
    )
    return b.as_markup()


def admin_cancel_markup(target: str = "adm:home") -> InlineKeyboardMarkup:
    """Cancel prompt for admin text input flows."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn("❌ Cancel", callback_data=target, style="danger"),
        Btn("🏠 Home", callback_data="mn:home", style="danger"),
    )
    return b.as_markup()


def prem_admin_markup() -> InlineKeyboardMarkup:
    """Admin Premium & Sponsor configuration keyboard."""
    sp = db["sponsor"]
    b = InlineKeyboardBuilder()
    b.row(
        Btn("💰 Set price", callback_data="adm:set:price", style="primary"),
        Btn("⏳ Set days", callback_data="adm:set:days", style="primary"),
    )
    b.row(
        Btn("🔴 JazzCash", callback_data="adm:set:jc", style="danger"),
        Btn("🟢 Easypaisa", callback_data="adm:set:ep", style="success"),
    )
    b.row(
        Btn("➕ Give premium", callback_data="adm:set:give", style="success"),
        Btn("➖ Remove premium", callback_data="adm:set:rmprem", style="danger"),
    )
    b.row(Btn("📋 Premium users", callback_data="adm:pl", style="primary"))
    b.row(
        Btn("📣 Set sponsor line", callback_data="adm:set:sponsor", style="primary"),
        Btn(f"📣 {'Turn OFF' if sp['on'] else 'Turn ON'}", callback_data="adm:sp:tog", style="success" if not sp["on"] else "danger"),
    )
    b.row(Btn("🗑 Clear sponsor", callback_data="adm:sp:clr", style="danger"))
    b.row(*nav_row("adm:home", include_home=True))
    return b.as_markup()


def prem_users_back_markup() -> InlineKeyboardMarkup:
    """Back + Home keyboard for the premium users list."""
    b = InlineKeyboardBuilder()
    b.row(*nav_row("adm:prem", include_home=True))
    return b.as_markup()


def groups_list_markup(
    items: Sequence[ Any],
    page: int,
    pages: int,
    sort: str,
    has_query: bool,
    gdl_fn: Any,
    ago_fn: Any,
) -> InlineKeyboardMarkup:
    """Group Manager main paginated list keyboard."""
    b = InlineKeyboardBuilder()
    for gid, g in items[page * GROUPS_PER_PAGE : (page + 1) * GROUPS_PER_PAGE]:
        extra = ""
        if sort == "downloads":
            extra = f" · {gdl_fn(gid)}⬇"
        elif sort == "members":
            extra = f" · {g['members']}👤"
        elif sort == "activity":
            extra = f" · {ago_fn(g['last'])}"
        b.row(
            Btn(
                f"{'🚫' if g['blocked'] else '🟢'} {str(g['title'])[:28]}{extra}",
                callback_data=f"grp:v:{gid}",
                style="danger" if g["blocked"] else "primary",
            )
        )
    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(Btn("⬅️ Prev", callback_data=f"grp:list:{page - 1}", style="primary"))
    if page < pages - 1:
        nav.append(Btn("Next ➡️", callback_data=f"grp:list:{page + 1}", style="primary"))
    if nav:
        b.row(*nav)

    sort_row = [
        Btn(f"↕️ {SORT_LABEL[sort]}", callback_data="grp:sort", style="primary"),
        Btn("🔍 Search", callback_data="grp:sch", style="primary"),
    ]
    if has_query:
        sort_row.append(Btn("❌ Clear", callback_data="grp:clr", style="danger"))
    b.row(*sort_row)
    b.row(
        Btn("🏆 Top groups", callback_data="grp:top", style="primary"),
        Btn("📣 Broadcast", callback_data="grp:bcast", style="success"),
    )
    b.row(
        Btn("🧹 Clean inactive", callback_data="grp:inact", style="danger"),
        Btn(f"🛡 Approval: {'ON' if db['approval'] else 'OFF'}", callback_data="grp:apt", style="primary"),
    )
    b.row(
        Btn("🔄 Refresh", callback_data=f"grp:list:{page}", style="primary"),
        Btn("🛠 Admin", callback_data="adm:home", style="danger"),
        Btn("🏠 Home", callback_data="mn:home", style="danger"),
    )
    return b.as_markup()


def group_detail_markup(gid: str, blocked: bool) -> InlineKeyboardMarkup:
    """Single group management detail keyboard."""
    b = InlineKeyboardBuilder()
    b.row(
        Btn("✅ Unblock" if blocked else "🚫 Block", callback_data=f"grp:blk:{gid}", style="success" if blocked else "danger"),
        Btn("⚙️ Settings", callback_data=f"grp:set:{gid}", style="primary"),
    )
    b.row(
        Btn("📊 Stats", callback_data=f"grp:st:{gid}", style="primary"),
        Btn("🚪 Leave", callback_data=f"grp:leave:{gid}", style="danger"),
    )
    b.row(*nav_row("grp:list:0", include_home=True))
    return b.as_markup()


def group_settings_markup(gid: str, g: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Per-group settings toggles keyboard."""
    on = lambda v: "ON ✅" if v else "OFF"
    b = InlineKeyboardBuilder()
    b.row(Btn(f"🎚 Formats: {FMT_LABEL[g['fmt']]}", callback_data=f"grp:t:{gid}:fmt", style="primary"))
    b.row(Btn(f"📺 Video quality: {VIDEO_QUALITY}p (fixed)", callback_data=f"grp:t:{gid}:fmt", style="primary"))
    b.row(Btn(f"⏱ Max length: {str(g['dur']) + ' min' if g['dur'] else 'default'}", callback_data=f"grp:t:{gid}:dur", style="primary"))
    b.row(Btn(f"🧊 Cooldown: {str(g['cool']) + 's' if g['cool'] else 'off'}", callback_data=f"grp:t:{gid}:cool", style="primary"))
    b.row(Btn(f"👮 Admins-only: {on(g['adm'])}", callback_data=f"grp:t:{gid}:adm", style="primary"))
    b.row(Btn(f"🧹 Auto-delete: {str(g['del']) + 's' if g['del'] else 'off'}", callback_data=f"grp:t:{gid}:del", style="primary"))
    b.row(Btn(f"💬 Text search: {on(g['txt'])}", callback_data=f"grp:t:{gid}:txt", style="primary"))
    b.row(Btn(f"🔗 Force-join here ({len(g['force'])})", callback_data=f"grp:fj:{gid}", style="primary"))
    b.row(*nav_row(f"grp:v:{gid}", include_home=True))
    return b.as_markup()


def group_force_markup(gid: str, g: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Per-group force-join selector keyboard."""
    b = InlineKeyboardBuilder()
    for c in db["chats"]:
        checked = c["id"] in g["force"]
        b.row(
            Btn(
                f"{'☑️' if checked else '⬜'} {str(c['title'])[:30]}",
                callback_data=f"grp:fjt:{gid}:{c['id']}",
                style="success" if checked else "primary",
            )
        )
    b.row(*nav_row(f"grp:set:{gid}", include_home=True))
    return b.as_markup()


def group_back_markup(back_cb: str = "grp:list:0") -> InlineKeyboardMarkup:
    """Back + Home keyboard for group stats/top/cleanup screens."""
    b = InlineKeyboardBuilder()
    b.row(*nav_row(back_cb, include_home=True))
    return b.as_markup()


def group_inactive_markup(n: int) -> InlineKeyboardMarkup:
    """Inactive group cleanup confirmation keyboard."""
    b = InlineKeyboardBuilder()
    if n:
        b.row(Btn(f"🧹 Leave {n} group(s)", callback_data="grp:inacty", style="danger"))
    b.row(*nav_row("grp:list:0", include_home=True))
    return b.as_markup()


def bc_confirm_markup(all_count: int, sel_count: int) -> InlineKeyboardMarkup:
    """Broadcast confirmation keyboard."""
    b = InlineKeyboardBuilder()
    b.row(Btn(f"📤 Send to ALL groups ({all_count})", callback_data="grp:bsa", style="success"))
    b.row(Btn(f"☑️ Select groups ({sel_count} selected)", callback_data="grp:bp:0", style="primary"))
    b.row(
        Btn("❌ Cancel", callback_data="grp:list:0", style="danger"),
        Btn("🏠 Home", callback_data="mn:home", style="danger"),
    )
    return b.as_markup()


def bc_select_markup(
    items: Sequence[Any],
    sel: set,
    page: int,
    pages: int,
) -> InlineKeyboardMarkup:
    """Broadcast group multi-select keyboard."""
    b = InlineKeyboardBuilder()
    for gid, g in items[page * GROUPS_PER_PAGE : (page + 1) * GROUPS_PER_PAGE]:
        in_sel = gid in sel
        b.row(
            Btn(
                f"{'☑️' if in_sel else '⬜'} {str(g['title'])[:32]}",
                callback_data=f"grp:bt:{gid}:{page}",
                style="success" if in_sel else "primary",
            )
        )
    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(Btn("⬅️", callback_data=f"grp:bp:{page - 1}", style="primary"))
    if page < pages - 1:
        nav.append(Btn("➡️", callback_data=f"grp:bp:{page + 1}", style="primary"))
    if nav:
        b.row(*nav)
    b.row(Btn(f"📤 Send to selected ({len(sel)})", callback_data="grp:bss", style="success"))
    b.row(*nav_row("grp:bv", include_home=True))
    return b.as_markup()


def approve_user_markup(uid: int) -> InlineKeyboardMarkup:
    """Inline button sent to admins when an unapproved user tries to add the bot to a group."""
    b = InlineKeyboardBuilder()
    b.row(Btn("✅ Approve this user", callback_data=f"grp:ap:{uid}", style="success"))
    return b.as_markup()
