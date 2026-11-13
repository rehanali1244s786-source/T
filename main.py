"""
main.py - Entry point for the Telegram Music + Video Bot (v3) on aiogram 3.x.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import List, Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import ADMIN_IDS, BOT_TOKEN, log
from db import save_db, saver
from handlers import get_routers
from handlers.follow import release_watcher
from middlewares import CreditRequestMiddleware, GateMiddleware

_bg_tasks: List[asyncio.Task] = []


async def on_startup(bot: Bot) -> None:
    """Start background tasks (`saver`, `release_watcher`) and register bot commands."""
    _bg_tasks.append(asyncio.create_task(saver(), name="db_saver"))
    _bg_tasks.append(asyncio.create_task(release_watcher(bot), name="release_watcher"))
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="menu", description="Interactive command & action menu"),
            BotCommand(command="song", description="/song name a (audio) or v (video 480p)"),
            BotCommand(command="search", description="Search a song: /search song name"),
            BotCommand(command="help", description="How to use"),
            BotCommand(command="find", description="Identify a song (reply to audio/voice)"),
            BotCommand(command="lyrics", description="Song lyrics: /lyrics song name"),
            BotCommand(command="lang", description="Change language (EN / اردو / हिन्दी)"),
            BotCommand(command="artist", description="Artist page: /artist name"),
            BotCommand(command="follow", description="Get alerts for new releases: /follow artist"),
            BotCommand(command="following", description="Artists you follow"),
            BotCommand(command="invite", description="Invite friends, earn more recognitions"),
            BotCommand(command="premium", description="Premium: priority downloads & more"),
            BotCommand(command="brand", description="Group footer (premium): /brand text"),
            BotCommand(command="stats", description="Bot statistics"),
            BotCommand(command="id", description="Show your Telegram ID"),
        ]
    )
    log.info("Bot started...")


async def on_shutdown(bot: Bot) -> None:
    """Cancel background tasks and flush database to disk on shutdown."""
    for t in _bg_tasks:
        t.cancel()
    for t in _bg_tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
    save_db()
    log.info("Database saved. Bot stopped cleanly.")


async def run_bot() -> None:
    """Initialize Bot and Dispatcher, attach middlewares and routers, and start polling."""
    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN environment variable first.")
    if not ADMIN_IDS:
        log.warning(
            "ADMIN_IDS is empty — admin features unavailable. Send /id to the bot to get your ID."
        )
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not found! Video merging / audio conversion may fail.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # Outgoing request middleware that appends "Developed by Dock — @Dockworldwide" / group brand / sponsor
    bot.session.middleware(CreditRequestMiddleware())

    dp = Dispatcher()
    # Outer update middleware that enforces bans, maintenance, blocked groups, and force-join
    dp.update.outer_middleware(GateMiddleware())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    for r in get_routers():
        dp.include_router(r)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def main() -> None:
    """Synchronous entry point."""
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        save_db()


if __name__ == "__main__":
    main()
