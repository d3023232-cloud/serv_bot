"""Чистые SQL-запросы к SQLite. Не содержат бизнес-логики."""

from datetime import datetime
from typing import Optional
import aiosqlite


async def get_or_create_user(
    db: aiosqlite.Connection, telegram_id: int, username: Optional[str] = None
) -> dict:
    """Возвращает пользователя по telegram_id или создаёт нового."""
    cursor = await db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    await db.execute(
        "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
        (telegram_id, username),
    )
    await db.commit()

    cursor = await db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def get_cabin(db: aiosqlite.Connection, user_id: int) -> Optional[dict]:
    """Возвращает данные хижины пользователя или None."""
    cursor = await db.execute(
        "SELECT * FROM cabins WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def create_cabin(db: aiosqlite.Connection, user_id: int) -> None:
    """Создаёт запись о хижине после постройки."""
    await db.execute(
        "INSERT INTO cabins (user_id, is_built) VALUES (?, 1)",
        (user_id,),
    )
    await db.commit()


async def update_user_resources(
    db: aiosqlite.Connection, user_id: int, wood: int, stone: int
) -> None:
    """Обновляет количество ресурсов в инвентаре пользователя."""
    await db.execute(
        "UPDATE users SET wood = ?, stone = ? WHERE user_id = ?",
        (wood, stone, user_id),
    )
    await db.commit()


async def update_gather_cooldown(
    db: aiosqlite.Connection, user_id: int, action: str, timestamp: datetime
) -> None:
    """Записывает время последней добычи (wood или stone)."""
    if action == "wood":
        await db.execute(
            "UPDATE users SET last_wood_gather = ? WHERE user_id = ?",
            (timestamp, user_id),
        )
    else:
        await db.execute(
            "UPDATE users SET last_stone_gather = ? WHERE user_id = ?",
            (timestamp, user_id),
        )
    await db.commit()


async def update_cabin_storage(
    db: aiosqlite.Connection, user_id: int, wood: int, stone: int
) -> None:
    """Обновляет содержимое шкафа хижины."""
    await db.execute(
        "UPDATE cabins SET wood_storage = ?, stone_storage = ? WHERE user_id = ?",
        (wood, stone, user_id),
    )
    await db.commit()


async def update_cabin_durability(
    db: aiosqlite.Connection,
    user_id: int,
    durability: float,
    last_check: datetime,
) -> None:
    """Обновляет прочность хижины и время последней проверки."""
    await db.execute(
        "UPDATE cabins SET durability = ?, last_decay_check = ? WHERE user_id = ?",
        (durability, last_check, user_id),
    )
    await db.commit()


async def get_all_cabins(db: aiosqlite.Connection) -> list[dict]:
    """Возвращает список всех построенных хижин для фоновых проверок."""
    cursor = await db.execute("SELECT * FROM cabins WHERE is_built = 1")
    rows = await cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


async def get_notification_state(
    db: aiosqlite.Connection, user_id: int
) -> Optional[datetime]:
    """Возвращает время последнего уведомления о низких ресурсах."""
    cursor = await db.execute(
        "SELECT low_resources_notified_at FROM notifications WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if row and row[0]:
        if isinstance(row[0], str):
            return datetime.fromisoformat(row[0])
        return row[0]
    return None


async def set_notification_state(
    db: aiosqlite.Connection, user_id: int, timestamp: datetime
) -> None:
    """Сохраняет время отправки уведомления."""
    await db.execute(
        "INSERT OR REPLACE INTO notifications (user_id, low_resources_notified_at) VALUES (?, ?)",
        (user_id, timestamp),
    )
    await db.commit()
