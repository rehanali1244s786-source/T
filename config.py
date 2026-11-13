"""
config.py - Environment variables, defaults, and constants for the Telegram Music + Video Bot.
"""

from __future__ import annotations

import base64
import importlib.util
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple


def _load_env(path: str = ".env") -> None:
    """Tiny .env loader (also supports python-dotenv if installed). Real environment variables win."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=Path(__file__).resolve().parent / path, override=False)
        return
    except Exception:
        pass

    p = Path(__file__).resolve().parent / path
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# Logging setup (never log BOT_TOKEN)
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.INFO)
log = logging.getLogger("MusicBot")

# Core environment variables
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: Set[int] = {int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", ""))}
DATA_FILE: Path = Path(
    os.getenv("DATA_FILE", str(Path(__file__).resolve().parent / "musicbot_data.json"))
)
BOT_VERSION: str = os.getenv("BOT_VERSION", "3.0").strip() or "3.0"
MENU_BANNER_URL: str = os.getenv(
    "MENU_BANNER_URL",
    "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=1200&q=80",
).strip()

# Cookies setup (file path, COOKIES_B64, or /data/cookies.txt on Railway volume)
COOKIES_FILE: str | None = os.getenv("COOKIES_FILE", "").strip() or None
try:
    _cb = os.getenv("COOKIES_B64", "").strip()
    if _cb:
        _cp = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
        with open(_cp, "wb") as _f:
            _f.write(base64.b64decode(_cb))
        COOKIES_FILE = _cp
    elif not COOKIES_FILE and os.path.exists("/data/cookies.txt"):
        _cp = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
        shutil.copyfile("/data/cookies.txt", _cp)
        COOKIES_FILE = _cp
except Exception as _e:
    log.warning("cookies setup failed: %s", _e)

# Download & recognition limits
MAX_PARALLEL_DOWNLOADS: int = int(os.getenv("MAX_PARALLEL_DOWNLOADS", "6"))
AUDD_TOKEN: str = os.getenv("AUDD_TOKEN", "").strip()
RECOGNIZE_DAILY_LIMIT: int = int(os.getenv("RECOGNIZE_DAILY_LIMIT", "5"))
PREMIUM_RECOG_LIMIT: int = int(os.getenv("PREMIUM_RECOG_LIMIT", "50"))
MAX_RECOGNIZE_FILE: int = 20 * 1024 * 1024  # 20 MB Telegram bot download limit

# Referrals & artist follow settings
REF_BONUS: int = int(os.getenv("REF_BONUS", "1"))
REF_MAX_BONUS: int = int(os.getenv("REF_MAX_BONUS", "10"))
RELEASE_CHECK_HOURS: float = float(os.getenv("RELEASE_CHECK_HOURS", "6"))
FOLLOW_LIMIT_FREE: int = int(os.getenv("FOLLOW_LIMIT_FREE", "5"))
FOLLOW_LIMIT_PREMIUM: int = int(os.getenv("FOLLOW_LIMIT_PREMIUM", "25"))

# Metadata & branding settings
GETSONGBPM_KEY: str = os.getenv("GETSONGBPM_KEY", "").strip()
MB_USER_AGENT: str = os.getenv(
    "MB_USER_AGENT", "MusicBot/3.0 ( https://t.me/Dockworldwide )"
).strip()
BRANDING_FREE: bool = os.getenv("BRANDING_FREE", "0").strip() == "1"
HAVE_LIBROSA: bool = importlib.util.find_spec("librosa") is not None

# Operational constants
MAX_AUDIO_DURATION: int = 30 * 60
MAX_VIDEO_DURATION: int = 15 * 60
MAX_FILE_SIZE: int = 49 * 1024 * 1024  # ~49 MB safe limit under Telegram's 50 MB cap
VIDEO_QUALITY: int = 480  # video is ALWAYS downloaded at 480p
MEMBER_CACHE_TTL: int = 300
SEARCH_CACHE_TTL: int = 1800
SEARCH_CACHE_MAX: int = 500
INACTIVE_DAYS: int = 30
WARN_LIMIT: int = 3
GROUPS_PER_PAGE: int = 8
ALERT_COOLDOWN: int = 30 * 60
ALERT_STREAK: int = 3

GROUP_TYPES: Tuple[str, str] = ("group", "supergroup")
NUMS: List[str] = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
MEDALS: List[str] = ["🥇", "🥈", "🥉"]
NOTES: List[str] = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
METHODS: Dict[str, Tuple[str, str]] = {"jc": ("JazzCash", "🔴"), "ep": ("Easypaisa", "🟢")}

# Styling & footer markers
RAINBOW: str = "🟥🟧🟨🟩🟦🟪"
SQ: List[str] = ["🟦", "🟩", "🟨", "🟧", "🟪", "🟥"]
FOOT: str = "\u2063"  # invisible marker: "this text already has a footer"
SPON: str = "\u2060"  # invisible marker: "a sponsor line may be added here"
CREDIT_USER: str = "@Dockworldwide"
OWNER_URL: str = "https://t.me/Dockworldwide"
CREDIT_HTML: str = f"\n\n👨‍💻 <i>Developed by</i> <b>Dock</b> — {CREDIT_USER}"
CREDIT_PLAIN: str = f"\n\n👨‍💻 Developed by Dock — {CREDIT_USER}"
MONO_FOOTER: str = "<code>- while (true) { DOCK MUSIC BOT }</code>"

YT_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?.*?v=|shorts/|embed/)|music\.youtube\.com/watch\?.*?v=)([\w-]{11})"
)

# Group defaults
GDEF: Dict[str, object] = {
    "title": "",
    "blocked": False,
    "fmt": "both",       # both | audio | video
    "qual": 720,         # max video quality setting key preserved from v3
    "dur": 0,            # max minutes (0 = default)
    "cool": 0,           # seconds between requests per user
    "adm": False,        # only group admins can use the bot
    "del": 0,            # auto-delete bot messages after N seconds (0 = off)
    "txt": False,        # reply to plain text (no /song needed)
    "force": [],         # extra force-join chat ids for this group
    "added": 0,
    "last": 0,
    "members": 0,
    "brand": "",
    "brand_by": 0,       # custom footer (premium perk) and who set it
}

SORTS: List[str] = ["name", "activity", "downloads", "members"]
SORT_LABEL: Dict[str, str] = {
    "name": "Name",
    "activity": "Activity",
    "downloads": "Downloads",
    "members": "Members",
}
FMT_LABEL: Dict[str, str] = {
    "both": "Audio + Video",
    "audio": "Audio only",
    "video": "Video only",
}
CYCLES: Dict[str, list] = {
    "fmt": ["both", "audio", "video"],
    "qual": [720, 480, 360],
    "dur": [0, 5, 10, 15],
    "cool": [0, 10, 30, 60],
    "del": [0, 30, 120, 600],
}
TOGGLES: Set[str] = {"adm", "txt"}

ADMIN_FIX: Dict[str, str] = {
    "cookies": (
        "YouTube is blocking the server. Your <b>cookies.txt</b> has probably expired — "
        "export fresh cookies from a logged-in browser, replace the file, then restart the bot."
    ),
    "ffmpeg": (
        "<b>ffmpeg</b> is missing or broken on the server. "
        "Install it (e.g. <code>apt install ffmpeg</code>) and restart."
    ),
    "other": (
        "Several downloads in a row failed. Check the server's internet, disk space, "
        "and try <code>pip install -U yt-dlp</code>."
    ),
}

USER_CMDS: List[str] = [
    "start", "help", "id", "menu", "song", "search", "find", "lyrics",
    "artist", "follow", "following", "invite", "premium", "brand",
    "lang", "stats", "ban", "unban", "warn",
]
ADMIN_CMDS: List[str] = [
    "admin", "groups", "approve", "unapprove", "givepremium", "removepremium",
]
CMD_EXAMPLE: Dict[str, str] = {
    "start": "/start",
    "help": "/help",
    "id": "/id",
    "menu": "/menu",
    "lang": "/lang",
    "stats": "/stats",
    "song": "/song Tum Hi Ho a",
    "search": "/search Tum Hi Ho",
    "find": "/find (reply to audio)",
    "lyrics": "/lyrics Tum Hi Ho",
    "ban": "/ban (reply)",
    "unban": "/unban (reply)",
    "warn": "/warn (reply)",
    "admin": "/admin",
    "groups": "/groups",
    "approve": "/approve 12345",
    "unapprove": "/unapprove 12345",
    "artist": "/artist Karan Aujla",
    "follow": "/follow Karan Aujla",
    "following": "/following",
    "invite": "/invite",
    "premium": "/premium",
    "brand": "/brand My group footer",
    "givepremium": "/givepremium 12345 30",
    "removepremium": "/removepremium 12345",
}


def is_admin(uid: int) -> bool:
    """Return True if the Telegram user ID is in ADMIN_IDS."""
    return int(uid) in ADMIN_IDS
