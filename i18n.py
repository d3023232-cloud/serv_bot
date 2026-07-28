"""Бизнес-логика добычи ресурсов с кулдаунами."""

from datetime import datetime
import aiosqlite
from database import queries

WOOD_COOLDOWN = 120   # 2 минуты
STONE_COOLDOWN = 180  # 3 минуты
WOOD_YIELD = 5
STONE_YIELD = 3


async def gather_wood(
    db: aiosqlite.Connection, user_id: int, user: dict
) -> tuple[bool, int]:
    """Добыча дерева. Возвращает (успех, количество_или_оставшиеся_секунды)."""
    now = datetime.now()
    last = user.get("last_wood_gather")

    if last:
        last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
        diff = (now - last_dt).total_seconds()
        if diff < WOOD_COOLDOWN:
            return False, int(WOOD_COOLDOWN - diff)

    new_wood = user["wood"] + WOOD_YIELD
    await queries.update_user_resources(db, user_id, new_wood, user["stone"])
    await queries.update_gather_cooldown(db, user_id, "wood", now)
    return True, WOOD_YIELD


async def gather_stone(
    db: aiosqlite.Connection, user_id: int, user: dict
) -> tuple[bool, int]:
    """Добыча камня. Возвращает (успех, количество_или_оставшиеся_секунды)."""
    now = datetime.now()
    last = user.get("last_stone_gather")

    if last:
        last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
        diff = (now - last_dt).total_seconds()
        if diff < STONE_COOLDOWN:
            return False, int(STONE_COOLDOWN - diff)

    new_stone = user["stone"] + STONE_YIELD
    await queries.update_user_resources(db, user_id, user["wood"], new_stone)
    await queries.update_gather_cooldown(db, user_id, "stone", now)
    return True, STONE_YIELD
