from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database.base import init_models
from app.handlers import get_root_router
from app.middlewares.db_middleware import DatabaseMiddleware
from app.middlewares.user_middleware import UserMiddleware
from app.services.weekly_reward import run_weekly_reward_loop

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares навешиваем на update целиком — они сработают перед любым
    # конкретным обработчиком (message, business_message, callback_query и т.д.)
    dp.update.outer_middleware(DatabaseMiddleware())
    dp.update.outer_middleware(UserMiddleware())

    dp.include_router(get_root_router())

    await init_models()

    logger.info("qqRP Bot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(run_weekly_reward_loop(bot))
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
