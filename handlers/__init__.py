"""
handlers package - Modular aiogram 3 Routers for user, song, search, admin, groups, premium, artist, follow, inline, and recognition features.
"""

from __future__ import annotations

from typing import List
from aiogram import Router

from handlers.user import router as user_router
from handlers.song import router as song_router
from handlers.search import router as search_router
from handlers.admin import router as admin_router
from handlers.groups import router as groups_router
from handlers.premium import router as premium_router
from handlers.artist import router as artist_router
from handlers.follow import router as follow_router
from handlers.inline import router as inline_router
from handlers.recognize import router as recognize_router


def get_routers() -> List[Router]:
    """Return all application routers in registration order (recognize_router last for catch-all message routing)."""
    return [
        user_router,
        song_router,
        search_router,
        admin_router,
        groups_router,
        premium_router,
        artist_router,
        follow_router,
        inline_router,
        recognize_router,
    ]
