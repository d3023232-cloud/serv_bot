"""
Точка входа — запускает бота, подключает роутеры, запускает фоновый цикл уведомлений.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db, migrate_db
from services import start_notification_loop
from handlers import (
    start_router,
    inventory_router,
    gathering_router,
    cabin_router,
    market_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_token_or_exit(token: str) -> None:
    """Понятная ошибка вместо краша aiogram с нечитаемым трейсбеком."""
    if not token:
        raise SystemExit(
            "Ошибка: переменная окружения BOT_TOKEN не задана. "
            "Укажите токен бота в настройках хостинга (получить можно у @BotFather)."
        )
    if ":" not in token or not token.split(":", 1)[0].isdigit():
        raise SystemExit(
            f"Ошибка: BOT_TOKEN имеет неверный формат: {token!r}. "
            "Ожидается значение вида '123456789:ABCdefGHI...'. "
            "Скопируйте токен целиком из @BotFather и вставьте без кавычек и лишнего текста."
        )


async def main() -> None:
    _validate_token_or_exit(BOT_TOKEN)

    await init_db()
    await migrate_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_routers(
        start_router,
        inventory_router,
        gathering_router,
        cabin_router,
        market_router,
    )

    asyncio.create_task(start_notification_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
