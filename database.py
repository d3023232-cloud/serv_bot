"""
Работа с SQLite — миграции, создание, чтение, обновление записей.
"""

import logging
from datetime import datetime
from typing import Optional
import aiosqlite

from config import DB_PATH

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Создаёт таблицы SQLite, если они ещё не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                coins INTEGER DEFAULT 0,
                wood INTEGER DEFAULT 0,
                stone INTEGER DEFAULT 0,
                last_wood_gather TIMESTAMP,
                last_stone_gather TIMESTAMP,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cabins (
                cabin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                level INTEGER DEFAULT 1,
                durability REAL DEFAULT 100.0,
                max_durability REAL DEFAULT 100.0,
                wood_storage INTEGER DEFAULT 0,
                stone_storage INTEGER DEFAULT 0,
                max_wood_storage INTEGER DEFAULT 100,
                max_stone_storage INTEGER DEFAULT 100,
                last_decay_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_built INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                user_id INTEGER PRIMARY KEY,
                low_resources_notified_at TIMESTAMP,
                fifty_percent_notified INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def migrate_db() -> None:
    """Применяет миграции к существующей базе данных."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "coins" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN coins INTEGER DEFAULT 0")
            logger.info("Миграция: добавлена колонка coins в users")

        cursor = await db.execute("PRAGMA table_info(cabins)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "max_wood_storage" in columns:
            await db.execute("UPDATE cabins SET max_wood_storage = 100 WHERE max_wood_storage < 100")
            await db.execute("UPDATE cabins SET max_stone_storage = 100 WHERE max_stone_storage < 100")
            logger.info("Миграция: обновлена вместимость шкафа до 100")

        cursor = await db.execute("PRAGMA table_info(notifications)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "fifty_percent_notified" not in columns:
            await db.execute("ALTER TABLE notifications ADD COLUMN fifty_percent_notified INTEGER DEFAULT 0")
            logger.info("Миграция: добавлена колонка fifty_percent_notified")

        await db.commit()


async def get_or_create_user(
    db: aiosqlite.Connection, telegram_id: int, username: Optional[str] = None
) -> dict:
    cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = await cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    await db.execute(
        "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
        (telegram_id, username),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = await cursor.fetchone()
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def get_cabin(db: aiosqlite.Connection, user_id: int) -> Optional[dict]:
    cursor = await db.execute("SELECT * FROM cabins WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def create_cabin(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute(
        "INSERT INTO cabins (user_id, is_built, max_wood_storage, max_stone_storage) VALUES (?, 1, 100, 100)",
        (user_id,),
    )
    await db.commit()


async def delete_cabin(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute("DELETE FROM cabins WHERE user_id = ?", (user_id,))
    await db.commit()


async def update_user_resources(
    db: aiosqlite.Connection, user_id: int, coins: int, wood: int, stone: int
) -> None:
    await db.execute(
        "UPDATE users SET coins = ?, wood = ?, stone = ? WHERE user_id = ?",
        (coins, wood, stone, user_id),
    )
    await db.commit()


async def update_user_coins(db: aiosqlite.Connection, user_id: int, coins: int) -> None:
    await db.execute("UPDATE users SET coins = ? WHERE user_id = ?", (coins, user_id))
    await db.commit()


async def update_gather_cooldown(
    db: aiosqlite.Connection, user_id: int, action: str, timestamp: datetime
) -> None:
    column = "last_wood_gather" if action == "wood" else "last_stone_gather"
    await db.execute(
        f"UPDATE users SET {column} = ? WHERE user_id = ?", (timestamp, user_id)
    )
    await db.commit()


async def update_cabin_storage(
    db: aiosqlite.Connection, user_id: int, wood: int, stone: int
) -> None:
    await db.execute(
        "UPDATE cabins SET wood_storage = ?, stone_storage = ? WHERE user_id = ?",
        (wood, stone, user_id),
    )
    await db.commit()


async def update_cabin_durability(
    db: aiosqlite.Connection, user_id: int, durability: float, last_check: datetime
) -> None:
    await db.execute(
        "UPDATE cabins SET durability = ?, last_decay_check = ? WHERE user_id = ?",
        (durability, last_check, user_id),
    )
    await db.commit()


async def get_all_cabins(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute("SELECT * FROM cabins WHERE is_built = 1")
    rows = await cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


async def get_notification_state(db: aiosqlite.Connection, user_id: int) -> Optional[datetime]:
    cursor = await db.execute(
        "SELECT low_resources_notified_at FROM notifications WHERE user_id = ?", (user_id,)
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
    await db.execute(
        "INSERT OR REPLACE INTO notifications (user_id, low_resources_notified_at) VALUES (?, ?)",
        (user_id, timestamp),
    )
    await db.commit()


async def get_fifty_percent_flag(db: aiosqlite.Connection, user_id: int) -> int:
    cursor = await db.execute(
        "SELECT fifty_percent_notified FROM notifications WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def set_fifty_percent_flag(
    db: aiosqlite.Connection, user_id: int, value: int
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO notifications (user_id, fifty_percent_notified) VALUES (?, ?)",
        (user_id, value),
    )
    await db.commit()


async def reset_fifty_percent_flag(
    db: aiosqlite.Connection, user_id: int
) -> None:
    await db.execute(
        "UPDATE notifications SET fifty_percent_notified = 0 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()
