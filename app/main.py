from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import settings
from app.database.database import init_db
from app.handlers import (
    admin,
    clone,
    common,
    credits,
    generate,
    history,
    referral,
    settings as settings_handlers,
    start,
    voices,
)
from app.middlewares import DatabaseMiddleware
from app.middlewares_gate import ChannelGateMiddleware
from app.services.voice_api import voice_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    db_middleware = DatabaseMiddleware()
    dp.update.middleware(db_middleware)
    # Must come after DatabaseMiddleware (needs db_user) and before every
    # router below, so a non-member never reaches any real handler. No-op if
    # REQUIRED_CHANNEL_ID isn't configured.
    dp.update.middleware(ChannelGateMiddleware(bot=bot))

    # Order matters: admin router first so its filters short-circuit for
    # admin-only callback data before generic routers see them.
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(generate.router)
    dp.include_router(voices.router)
    dp.include_router(clone.router)
    dp.include_router(credits.router)
    dp.include_router(referral.router)
    dp.include_router(history.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(common.router)  # generic nav (main_menu/back/cancel/help) last

    try:
        me = await bot.get_me()
        logger.info("Starting %s as @%s", settings.brand_name, me.username)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Restart / show the main menu"),
                BotCommand(command="menu", description="Show the main menu"),
                BotCommand(command="generate", description="Generate speech with your voice"),
                BotCommand(command="library", description="Browse the voice library"),
                BotCommand(command="male", description="Browse male voices"),
                BotCommand(command="female", description="Browse female voices"),
                BotCommand(command="clone", description="Clone your own voice"),
                BotCommand(command="myvoices", description="Manage your cloned voices"),
                BotCommand(command="history", description="View your generation history"),
                BotCommand(command="balance", description="Check your token balance"),
                BotCommand(command="invite", description="Invite friends, earn tokens"),
                BotCommand(command="settings", description="Change language, speed, volume"),
                BotCommand(command="cancel", description="Cancel the current action"),
                BotCommand(command="help", description="How this bot works"),
            ]
        )
        await dp.start_polling(bot)
    finally:
        await voice_service.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
