"""
db.py - JSON storage with identical keys to musicbot_data.json, atomic save, debounced saver, and state helpers.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Set

from config import (
    BRANDING_FREE,
    DATA_FILE,
    FOLLOW_LIMIT_FREE,
    FOLLOW_LIMIT_PREMIUM,
    GDEF,
    GROUP_TYPES,
    PREMIUM_RECOG_LIMIT,
    RECOGNIZE_DAILY_LIMIT,
    REF_BONUS,
    REF_MAX_BONUS,
    is_admin,
    log,
)

# Persistent JSON database structure (identical keys to v3 musicbot_data.json)
db: Dict[str, Any] = {
    "enabled": True,
    "maintenance": False,
    "chats": [],
    "users": [],
    "cache": {},
    "groups": {},
    "approval": False,
    "approved": [],
    "banned_global": [],
    "banned_groups": {},
    "warns": {},
    "gstats": {},
    "ulang": {},
    "recog": {},
    "tot": {"a": 0, "v": 0},
    "daily": {},
    "premium": {},
    "pending": {},
    "ref": {"by": {}, "n": {}},
    "artists": {},
    "bpm": {},
    "sponsor": {"on": False, "text": ""},
    "pay": {
        "price": 0,
        "days": 30,
        "cur": "PKR",
        "jc": {"num": "", "name": ""},
        "ep": {"num": "", "name": ""},
    },
}

if DATA_FILE.exists():
    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            db.update(loaded)
    except Exception:
        log.exception("Could not read %s, starting fresh", DATA_FILE)

_now = int(time.time())
for _g in db["groups"].values():
    for _k, _v in GDEF.items():
        _g.setdefault(_k, list(_v) if isinstance(_v, list) else _v)
    _g["added"] = _g.get("added") or _now
    _g["last"] = _g.get("last") or _now

_users: Set[int] = {int(u) for u in db.get("users", []) if str(u).lstrip("-").isdigit()}
_dirty: bool = False

# In-memory caches & runtime state
META: Dict[str, Dict[str, Any]] = {}
SEARCH_CACHE: Dict[str, Any] = {}
_member_cache: Dict[ Any, float] = {}
_check_alert: Dict[Any, float] = {}
_gadm_cache: Dict[Any, Any] = {}
_cooldown: Dict[Any, float] = {}
_bg: Set[asyncio.Task] = set()
ERR: Dict[str, Any] = {"streak": 0, "alerted": False, "last": {}}
USER_DATA: Dict[int, Dict[str, Any]] = {}


def get_ud(uid: int) -> Dict[str, Any]:
    """Return per-user mutable state dictionary (replaces PTB context.user_data)."""
    return USER_DATA.setdefault(int(uid), {})


def clear_flags(ud: Dict[str, Any]) -> None:
    """Clear pending input flags for admin/user flows."""
    for k in ("await_chat", "await_gsearch", "await_bc", "await_set"):
        ud.pop(k, None)


def _write_db(payload: str) -> None:
    """Atomically write JSON payload to DATA_FILE."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(DATA_FILE)


def save_db() -> None:
    """Synchronously flush database to disk."""
    try:
        db["users"] = list(_users)
        _write_db(json.dumps(db, ensure_ascii=False))
    except Exception:
        log.exception("save_db failed")


def touch() -> None:
    """Mark data as changed; the background saver writes it every 15s."""
    global _dirty
    _dirty = True


async def saver() -> None:
    """Background loop that periodically flushes dirty database state to disk."""
    global _dirty
    while True:
        await asyncio.sleep(15)
        if _dirty:
            _dirty = False
            try:
                db["users"] = list(_users)
                payload = json.dumps(db, ensure_ascii=False)
                await asyncio.to_thread(_write_db, payload)
            except Exception:
                log.exception("background save failed")


def remember(meta: Dict[str, Any]) -> None:
    """Cache video metadata in memory."""
    if not meta or "id" not in meta:
        return
    if len(META) > 3000:
        META.clear()
    META[meta["id"]] = meta


def ensure_group(chat: Any) -> Dict[str, Any]:
    """Ensure a group chat exists in db['groups'] with all default keys populated."""
    gid = str(chat.id)
    g = db["groups"].get(gid)
    now = int(time.time())
    if g is None:
        g = {"title": getattr(chat, "title", None) or gid, "added": now, "last": now}
        db["groups"][gid] = g
        touch()
    for k, v in GDEF.items():
        if k not in g:
            g[k] = list(v) if isinstance(v, list) else v
    title = getattr(chat, "title", None)
    if title and g["title"] != title:
        g["title"] = title
        touch()
    return g


def gsettings(chat: Any) -> Dict[str, Any]:
    """Return group settings for a group chat or GDEF for private chat."""
    return ensure_group(chat) if getattr(chat, "type", "") in GROUP_TYPES else dict(GDEF)


def record(chat: Any, user: Any, meta: Dict[str, Any], kind: str = "a") -> None:
    """Record a completed download in group stats, daily stats, and totals."""
    gid = str(chat.id) if getattr(chat, "type", "") in GROUP_TYPES else "pm"
    s = db["gstats"].setdefault(gid, {"n": 0, "users": {}, "songs": {}})
    s["n"] += 1
    full_name = getattr(user, "full_name", "") or getattr(user, "first_name", "User")
    u = s["users"].setdefault(str(user.id), {"n": 0, "name": full_name[:30]})
    u["n"] += 1
    u["name"] = full_name[:30]
    song = s["songs"].setdefault(meta["id"], {"t": meta["title"][:60], "n": 0})
    song["n"] += 1
    if len(s["songs"]) > 300:
        for k, _ in sorted(s["songs"].items(), key=lambda kv: kv[1]["n"])[:50]:
            s["songs"].pop(k, None)
    if gid in db["groups"]:
        db["groups"][gid]["last"] = int(time.time())
    db["tot"][kind] = db["tot"].get(kind, 0) + 1
    day = time.strftime("%Y-%m-%d")
    db["daily"][day] = db["daily"].get(day, 0) + 1
    if len(db["daily"]) > 40:
        for k in sorted(db["daily"])[:-35]:
            db["daily"].pop(k, None)
    touch()


def user_total(uid: int) -> int:
    """Return total downloads across all chats for a user."""
    return sum(s["users"].get(str(uid), {}).get("n", 0) for s in db["gstats"].values())


def gdl(gid: str) -> int:
    """Return total downloads for a group ID."""
    return db["gstats"].get(gid, {}).get("n", 0)


# ───────────────────────── Premium & Referral helpers ─────────────────────────
def prem_exp(uid: int) -> int:
    """Return unix expiration timestamp for a user's premium subscription."""
    return int(db["premium"].get(str(uid), 0))


def is_premium(uid: int) -> bool:
    """Return True if the user is an admin or has active premium."""
    return is_admin(uid) or prem_exp(uid) > time.time()


def days_left(uid: int) -> int:
    """Return remaining premium days for a user."""
    return max(0, (prem_exp(uid) - int(time.time()) + 86399) // 86400)


def fmt_date(ts: int) -> str:
    """Format unix timestamp as 'DD Mon YYYY'."""
    return time.strftime("%d %b %Y", time.localtime(int(ts)))


def grant_premium(uid: int, days: int) -> int:
    """Grant or extend premium for `uid` by `days` days."""
    now = int(time.time())
    db["premium"][str(uid)] = max(now, prem_exp(uid)) + int(days) * 86400
    touch()
    return db["premium"][str(uid)]


def ref_count(uid: int) -> int:
    """Return number of referrals completed by `uid`."""
    return int(db["ref"]["n"].get(str(uid), 0))


def recog_limit(uid: int) -> int:
    """Daily recognitions: premium gets PREMIUM_RECOG_LIMIT; free gets base + referral bonus."""
    if is_premium(uid):
        return PREMIUM_RECOG_LIMIT
    return RECOGNIZE_DAILY_LIMIT + min(ref_count(uid) * REF_BONUS, REF_MAX_BONUS)


def prem_label(uid: int) -> str:
    """Return human-readable premium status label."""
    if is_admin(uid):
        return "Admin"
    return f"until {fmt_date(prem_exp(uid))}" if prem_exp(uid) > time.time() else "no"


def premium_perks() -> str:
    """Return HTML bullet list of premium perks."""
    return (
        "⚡ <b>Priority downloads</b> — skip the queue\n"
        f"🎧 <b>{PREMIUM_RECOG_LIMIT}</b> song recognitions per day\n"
        "🚫 <b>No sponsor</b> messages\n"
        "🏷 <b>Custom footer</b> for your groups (/brand)\n"
        f"🔔 Follow up to <b>{FOLLOW_LIMIT_PREMIUM}</b> artists"
    )


def recog_used(uid: int) -> int:
    """Return how many song recognitions `uid` has used today."""
    e = db["recog"].get(str(uid))
    return int(e["n"]) if e and e.get("d") == time.strftime("%Y-%m-%d") else 0


def recog_count(uid: int) -> None:
    """Increment today's song recognition count for `uid`."""
    day = time.strftime("%Y-%m-%d")
    e = db["recog"].get(str(uid))
    if not e or e.get("d") != day:
        e = db["recog"][str(uid)] = {"d": day, "n": 0}
    e["n"] += 1
    touch()


def user_follows(uid: int) -> List[str]:
    """Return list of MusicBrainz artist IDs followed by `uid`."""
    return [m for m, a in db["artists"].items() if uid in a.get("subs", [])]


def follow_limit(uid: int) -> int:
    """Return maximum artists `uid` may follow."""
    return FOLLOW_LIMIT_PREMIUM if is_premium(uid) else FOLLOW_LIMIT_FREE


def brand_active(g: Dict[str, Any]) -> bool:
    """Return True if custom group branding is active for group `g`."""
    return bool(g.get("brand")) and (BRANDING_FREE or is_premium(int(g.get("brand_by", 0))))
