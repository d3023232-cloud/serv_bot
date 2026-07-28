"""Фоновый сервис push-уведомлений при уровне ресурсов < 30%."""

import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
import aiosqlite
from config import DB_PATH
from database import queries
import i18n

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 600   # 10 минут
NOTIFY_COOLDOWN = 7200 # 2 часа между повторными уведомлениями
THRESHOLD = 0.30


async def start_notification_loop(bot: Bot) -> None:
    """Бесконечный цикл проверки шкафов и отправки уведомлений."""
    while True:
        try:
            await check_and_notify(bot)
        except Exception as exc:
            logger.error("Ошибка в цикле уведомлений: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL)


async def check_and_notify(bot: Bot) -> None:
    """Проверяет все хижины и шлёт push, если ресурсов меньше 30%."""
    async with aiosqlite.connect(DB_PATH) as db:
        cabins = await queries.get_all_cabins(db)
        now = datetime.now()

        for cabin in cabins:
            user_id = cabin["user_id"]
            wood = cabin["wood_storage"]
            stone = cabin["stone_storage"]
            max_wood = cabin["max_wood_storage"]
            max_stone = cabin["max_stone_storage"]

            threshold_wood = max_wood * THRESHOLD
            threshold_stone = max_stone * THRESHOLD

            if wood >= threshold_wood and stone >= threshold_stone:
                continue

            last_notify = await queries.get_notification_state(db, user_id)
            if last_notify:
                if (now - last_notify).total_seconds() < NOTIFY_COOLDOWN:
                    continue

            cursor = await db.execute(
                "SELECT telegram_id FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                continue
            telegram_id = row[0]

            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=i18n.NOTIFY_LOW_RESOURCES.format(
                        wood=wood,
                        max_wood=max_wood,
                        stone=stone,
                        max_stone=max_stone,
                    ),
                    parse_mode="HTML",
                )
                await queries.set_notification_state(db, user_id, now)
                logger.info("Уведомление отправлено пользователю %s", telegram_id)
            except Exception as exc:
                logger.warning("Не удалось отправить уведомление %s: %s", telegram_id, exc)
