"""
Бизнес-логика — тики хижины, починка, расчёт максимума, фоновые уведомления.
"""

import logging
import asyncio
from datetime import datetime, timezone  # FIXED (Задача 2): единое UTC-время
from typing import Optional

import aiosqlite
from aiogram import Bot

from config import (
    DB_PATH,
    TICK_MINUTES,
    CONSUMPTION_PER_TICK_WOOD,
    CONSUMPTION_PER_TICK_STONE,
    DECAY_FAST_PER_TICK,
    REPAIR_WOOD_PER_HP,
    REPAIR_STONE_PER_HP,
    CHECK_INTERVAL,
    NOTIFY_EMPTY_COOLDOWN,
    THRESHOLD_FIFTY,
    RESTORE_STARS_PRICE,
    NOTIFY_LOW_RESOURCES,
    NOTIFY_EMPTY_RESOURCES,
    NOTIFY_CABIN_DESTROYED,
)
from database import (
    get_cabin,
    get_all_cabins,
    get_or_create_user,
    get_notification_state,
    set_notification_state,
    get_fifty_percent_flag,
    set_fifty_percent_flag,
    reset_fifty_percent_flag,
    get_empty_notify_stage,  # FIXED (уведомления): стадия из 3 пустых уведомлений
    set_empty_notify_stage,
    update_cabin_durability,
    update_cabin_storage,
    delete_cabin,
)

logger = logging.getLogger(__name__)


async def apply_cabin_tick(
    db: aiosqlite.Connection, user_id: int, now: Optional[datetime] = None
) -> Optional[dict]:
    """Применяет потребление/гниение хижины за всё прошедшее время."""
    if now is None:
        now = datetime.now(timezone.utc)  # FIXED (Задача 2): UTC вместо локального времени

    cabin = await get_cabin(db, user_id)
    if not cabin or not cabin["is_built"]:
        return cabin

    last_raw = cabin["last_decay_check"]
    if last_raw is None:
        last_check = now
    elif isinstance(last_raw, str):
        # FIXED (Задача 2): старые метки SQLite — naive строки в UTC;
        # проставляем tzinfo=utc, иначе aware/naive вычитание упадёт TypeError.
        last_check = datetime.fromisoformat(last_raw)
        if last_check.tzinfo is None:
            last_check = last_check.replace(tzinfo=timezone.utc)
    else:
        last_check = last_raw
        if last_check.tzinfo is None:  # fallback на случай naive-объекта из БД
            last_check = last_check.replace(tzinfo=timezone.utc)

    minutes_passed = (now - last_check).total_seconds() / 60
    ticks = int(minutes_passed / TICK_MINUTES)

    if ticks <= 0:
        return cabin

    wood = cabin["wood_storage"]
    stone = cabin["stone_storage"]
    durability = cabin["durability"]

    for _ in range(ticks):
        if wood >= CONSUMPTION_PER_TICK_WOOD and stone >= CONSUMPTION_PER_TICK_STONE:
            wood -= CONSUMPTION_PER_TICK_WOOD
            stone -= CONSUMPTION_PER_TICK_STONE
        else:
            durability -= DECAY_FAST_PER_TICK
        durability = max(0.0, durability)

    await update_cabin_durability(db, user_id, round(durability, 1), now)
    await update_cabin_storage(db, user_id, wood, stone)

    cabin["durability"] = round(durability, 1)
    cabin["wood_storage"] = wood
    cabin["stone_storage"] = stone
    return cabin


async def build_cabin(
    db: aiosqlite.Connection, user_id: int, user: dict
) -> tuple[bool, str]:
    """Пытается построить хижину уровня 1, списывая ресурсы из инвентаря."""
    wood_needed = 20
    stone_needed = 10

    if user["wood"] < wood_needed or user["stone"] < stone_needed:
        return False, "not_enough"

    new_wood = user["wood"] - wood_needed
    new_stone = user["stone"] - stone_needed

    from database import update_user_resources, create_cabin
    await update_user_resources(db, user_id, user["coins"], new_wood, new_stone)
    await create_cabin(db, user_id)
    return True, "success"


async def add_to_storage(
    db: aiosqlite.Connection, user_id: int, wood: int, stone: int, user: dict
) -> tuple[bool, str]:
    """Перекладывает ресурсы из инвентаря игрока в шкаф хижины."""
    cabin = await get_cabin(db, user_id)
    if not cabin or not cabin["is_built"]:
        return False, "no_cabin"

    if user["wood"] < wood or user["stone"] < stone:
        return False, "not_enough"

    new_wood_storage = min(cabin["wood_storage"] + wood, cabin["max_wood_storage"])
    new_stone_storage = min(cabin["stone_storage"] + stone, cabin["max_stone_storage"])

    actual_wood = new_wood_storage - cabin["wood_storage"]
    actual_stone = new_stone_storage - cabin["stone_storage"]

    new_user_wood = user["wood"] - actual_wood
    new_user_stone = user["stone"] - actual_stone

    from database import update_user_resources, update_cabin_storage
    await update_user_resources(db, user_id, user["coins"], new_user_wood, new_user_stone)
    await update_cabin_storage(db, user_id, new_wood_storage, new_stone_storage)
    return True, "success"


def calc_max_repair(durability: float, max_dur: float, wood: int, stone: int) -> int:
    """Сколько HP можно восстановить имеющимися ресурсами."""
    need_hp = max_dur - durability
    if need_hp <= 0:
        return 0
    max_by_wood = wood // REPAIR_WOOD_PER_HP
    max_by_stone = stone // REPAIR_STONE_PER_HP
    return min(int(need_hp), max_by_wood, max_by_stone)


async def do_repair(
    db: aiosqlite.Connection, user_id: int, user: dict, hp: int
) -> tuple[bool, str, dict]:
    """Восстанавливает HP хижины, списывая ресурсы."""
    cabin = await get_cabin(db, user_id)
    if not cabin or not cabin["is_built"]:
        return False, "no_cabin", {}

    max_repair = calc_max_repair(
        cabin["durability"], cabin["max_durability"], user["wood"], user["stone"]
    )

    if hp > max_repair:
        need_wood = hp * REPAIR_WOOD_PER_HP
        need_stone = hp * REPAIR_STONE_PER_HP
        lack_wood = max(0, need_wood - user["wood"])
        lack_stone = max(0, need_stone - user["stone"])
        return False, "no_resources", {
            "need_wood": need_wood,
            "need_stone": need_stone,
            "lack_wood": lack_wood,
            "lack_stone": lack_stone,
            "wood": user["wood"],
            "stone": user["stone"],
        }

    cost_wood = hp * REPAIR_WOOD_PER_HP
    cost_stone = hp * REPAIR_STONE_PER_HP
    new_dur = min(cabin["durability"] + hp, cabin["max_durability"])

    from database import update_user_resources, update_cabin_durability
    await update_user_resources(
        db, user_id, user["coins"], user["wood"] - cost_wood, user["stone"] - cost_stone
    )
    await update_cabin_durability(db, user_id, new_dur, datetime.now(timezone.utc))  # FIXED (Задача 2): UTC

    return True, "success", {
        "hp": hp,
        "wood": cost_wood,
        "stone": cost_stone,
        "before": cabin["durability"],
        "after": new_dur,
    }


async def destroy_cabin(db: aiosqlite.Connection, user_id: int) -> None:
    """Удаляет хижину при 0 HP."""
    await delete_cabin(db, user_id)
    await reset_fifty_percent_flag(db, user_id)


async def start_notification_loop(bot: Bot) -> None:
    """Бесконечный цикл проверки шкафов и отправки уведомлений."""
    while True:
        try:
            await check_and_notify(bot)
        except Exception:
            # FIXED (Задача 6): logger.exception вместо logger.error(exc) — с трейсбеком
            logger.exception("Ошибка в цикле уведомлений")
        await asyncio.sleep(CHECK_INTERVAL)


async def check_and_notify(bot: Bot) -> None:
    """Проверяет все хижины и шлёт push."""
    async with aiosqlite.connect(DB_PATH) as db:
        cabins = await get_all_cabins(db)
        now = datetime.now(timezone.utc)  # FIXED (Задача 2): UTC вместо локального времени

        for cabin in cabins:
            user_id = cabin["user_id"]
            cabin = await apply_cabin_tick(db, user_id, now)
            if not cabin:
                continue

            wood = cabin["wood_storage"]
            stone = cabin["stone_storage"]
            max_wood = cabin["max_wood_storage"]
            max_stone = cabin["max_stone_storage"]
            durability = cabin["durability"]

            # FIXED (Задача 3): кулдаун пустых уведомлений считаем заранее,
            # чтобы ветка разрушения (durability <= 0) выполнялась ВСЕГДА —
            # раньше `continue` внутри проверки кулдауна пропускал её до 30 минут.
            empty_cooldown_ok = True
            if wood == 0 or stone == 0:
                last_notify = await get_notification_state(db, user_id)
                # FIXED (Задача 3): last_notify может быть None — трактуем как «кулдаун прошёл»
                if last_notify is not None and (now - last_notify).total_seconds() < NOTIFY_EMPTY_COOLDOWN:
                    empty_cooldown_ok = False

            # Проверка 50% — один раз, сбрасывается при пополнении обоих >= 50%
            fifty_flag = await get_fifty_percent_flag(db, user_id)
            if wood >= max_wood * THRESHOLD_FIFTY and stone >= max_stone * THRESHOLD_FIFTY:
                if fifty_flag:
                    await reset_fifty_percent_flag(db, user_id)
                # FIXED (уведомления): шкаф пополнен (оба ресурса >= 50%) —
                # сбрасываем стадию пустых уведомлений, чтобы следующий цикл
                # разрушения снова получил свои 3 предупреждения.
                if await get_empty_notify_stage(db, user_id) != 0:
                    await set_empty_notify_stage(db, user_id, 0)
            else:
                if not fifty_flag:
                    cursor = await db.execute(
                        "SELECT telegram_id FROM users WHERE user_id = ?", (user_id,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        telegram_id = row[0]
                        try:
                            await bot.send_message(
                                chat_id=telegram_id,
                                text=NOTIFY_LOW_RESOURCES.format(
                                    wood=wood, max_wood=max_wood, stone=stone, max_stone=max_stone
                                ),
                            )
                            await set_fifty_percent_flag(db, user_id, 1)
                            logger.info("50%% уведомление отправлено %s", telegram_id)
                        except Exception:
                            # FIXED (Задача 6): трейсбек вместо голого warning-сообщения
                            logger.exception("Не удалось отправить 50%% уведомление %s", telegram_id)

            # FIXED (уведомления): пустое уведомление теперь НЕ повторяется каждые
            # 30 минут. Максимум 3 уведомления за цикл разрушения — при прочности
            # <90%, <40% и <=10%. Стадия (0..3) хранится в БД; в тексте показывается
            # остаток процентов до полного разрушения хижины. Кулдаун NOTIFY_EMPTY_COOLDOWN
            # оставлен как защита от дублей внутри одного тика.
            if (wood == 0 or stone == 0) and empty_cooldown_ok:
                stage = await get_empty_notify_stage(db, user_id)
                if stage == 0 and durability < 90:
                    new_stage = 1
                elif stage == 1 and durability < 40:
                    new_stage = 2
                elif stage == 2 and durability <= 10:
                    new_stage = 3
                else:
                    new_stage = None  # все 3 уведомления уже отправлены

                if new_stage is not None:
                    cursor = await db.execute(
                        "SELECT telegram_id FROM users WHERE user_id = ?", (user_id,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        telegram_id = row[0]

                        try:
                            await bot.send_message(
                                chat_id=telegram_id,
                                text=NOTIFY_EMPTY_RESOURCES.format(
                                    wood=wood, max_wood=max_wood,
                                    stone=stone, max_stone=max_stone,
                                    durability=int(durability),
                                ),
                            )
                            await set_notification_state(db, user_id, now)
                            await set_empty_notify_stage(db, user_id, new_stage)
                            logger.info(
                                "Пустое уведомление (стадия %d/3) отправлено %s",
                                new_stage, telegram_id,
                            )
                        except Exception:
                            # FIXED (Задача 6): трейсбек вместо голого warning-сообщения
                            logger.exception("Не удалось отправить пустое уведомление %s", telegram_id)

            # Проверка разрушения хижины — всегда, независимо от кулдаунов выше
            # (FIXED (Задача 3): убран ранний continue, блок больше не пропускается)
            if durability <= 0:
                cursor = await db.execute(
                    "SELECT telegram_id FROM users WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                if row:
                    telegram_id = row[0]
                    try:
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        kb = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text=f"🏠 Восстановить за {RESTORE_STARS_PRICE}⭐",
                                        callback_data="restore_cabin",
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        text="❌ Пропустить", callback_data="skip_restore"
                                    )
                                ],
                            ]
                        )
                        await bot.send_message(
                            chat_id=telegram_id,
                            text=NOTIFY_CABIN_DESTROYED.format(price=RESTORE_STARS_PRICE),
                            reply_markup=kb,
                        )
                        logger.info("Уведомление о разрушении отправлено %s", telegram_id)
                    except Exception:
                        # FIXED (Задача 6): трейсбек вместо голого warning-сообщения
                        logger.exception("Не удалось отправить уведомление о разрушении %s", telegram_id)
                await destroy_cabin(db, user_id)
