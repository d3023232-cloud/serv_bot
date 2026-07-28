"""Бизнес-логика хижины: гниение, потребление ресурсов, постройка, шкаф."""

import logging
from datetime import datetime
from typing import Optional
import aiosqlite
from database import queries

logger = logging.getLogger(__name__)

TICK_MINUTES = 10
CONSUMPTION_PER_TICK_WOOD = 1
CONSUMPTION_PER_TICK_STONE = 1
DECAY_SLOW_PER_TICK = 0.5   # 3% в час при наличии ресурсов
DECAY_FAST_PER_TICK = 1.0   # 6% в час без ресурсов


async def apply_cabin_tick(
    db: aiosqlite.Connection, user_id: int, now: Optional[datetime] = None
) -> Optional[dict]:
    """Применяет гниение и потребление хижины за всё прошедшее время."""
    if now is None:
        now = datetime.now()

    cabin = await queries.get_cabin(db, user_id)
    if not cabin or not cabin["is_built"]:
        return cabin

    last_raw = cabin["last_decay_check"]
    if last_raw is None:
        last_check = now
    elif isinstance(last_raw, str):
        last_check = datetime.fromisoformat(last_raw)
    else:
        last_check = last_raw

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
            durability -= DECAY_SLOW_PER_TICK
        else:
            durability -= DECAY_FAST_PER_TICK
        durability = max(0.0, durability)

    await queries.update_cabin_durability(db, user_id, round(durability, 1), now)
    await queries.update_cabin_storage(db, user_id, wood, stone)

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

    await queries.update_user_resources(db, user_id, new_wood, new_stone)
    await queries.create_cabin(db, user_id)
    return True, "success"


async def add_to_storage(
    db: aiosqlite.Connection,
    user_id: int,
    wood: int,
    stone: int,
    user: dict,
) -> tuple[bool, str]:
    """Перекладывает ресурсы из инвентаря игрока в шкаф хижины."""
    cabin = await queries.get_cabin(db, user_id)
    if not cabin or not cabin["is_built"]:
        return False, "no_cabin"

    if user["wood"] < wood or user["stone"] < stone:
        return False, "not_enough"

    new_wood_storage = min(
        cabin["wood_storage"] + wood, cabin["max_wood_storage"]
    )
    new_stone_storage = min(
        cabin["stone_storage"] + stone, cabin["max_stone_storage"]
    )

    actual_wood = new_wood_storage - cabin["wood_storage"]
    actual_stone = new_stone_storage - cabin["stone_storage"]

    new_user_wood = user["wood"] - actual_wood
    new_user_stone = user["stone"] - actual_stone

    await queries.update_user_resources(db, user_id, new_user_wood, new_user_stone)
    await queries.update_cabin_storage(db, user_id, new_wood_storage, new_stone_storage)
    return True, "success"
