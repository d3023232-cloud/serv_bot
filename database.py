"""
Работа с SQLite — миграции, создание, чтение, обновление записей.
"""

import logging
from datetime import datetime, timezone
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
                sand INTEGER DEFAULT 0,  -- NEW (песок): новый ресурс добычи
                last_sand_gather TIMESTAMP,  -- NEW (песок): кулдаун добычи песка
                last_wood_gather TIMESTAMP,
                last_stone_gather TIMESTAMP,
                registered_at TIMESTAMP  -- FIXED (Задача 2): убран DEFAULT CURRENT_TIMESTAMP, метки ставятся из Python в UTC
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
                last_decay_check TIMESTAMP,  -- FIXED (Задача 2): убран DEFAULT CURRENT_TIMESTAMP, метка ставится из Python в UTC
                is_built INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                user_id INTEGER PRIMARY KEY,
                low_resources_notified_at TIMESTAMP,
                fifty_percent_notified INTEGER DEFAULT 0,
                empty_notify_stage INTEGER DEFAULT 0,
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

        # NEW (песок): новый ресурс — песoк и его кулдаун добычи
        if "sand" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN sand INTEGER DEFAULT 0")
            logger.info("Миграция: добавлена колонка sand в users")
        if "last_sand_gather" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN last_sand_gather TIMESTAMP")
            logger.info("Миграция: добавлена колонка last_sand_gather в users")

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

        # FIXED (уведомления): стадия пустых уведомлений (0..3) — максимум 3 шт.
        # при <90%, <40% и <=10% прочности вместо рассылки каждые 30 мин.
        if "empty_notify_stage" not in columns:
            await db.execute("ALTER TABLE notifications ADD COLUMN empty_notify_stage INTEGER DEFAULT 0")
            logger.info("Миграция: добавлена колонка empty_notify_stage")

        # FIXED (Задача 2): конвертация старых строковых UTC-таймстампов SQLite
        # ("YYYY-MM-DD HH:MM:SS", без таймзоны) в ISO с "+00:00", чтобы
        # datetime.fromisoformat возвращал aware-объекты и сравнение с
        # datetime.now(timezone.utc) не падало и не врало по часовой зоне.
        for table, col in (
            ("cabins", "last_decay_check"),
            ("users", "last_wood_gather"),
            ("users", "last_stone_gather"),
            ("users", "last_sand_gather"),
            ("users", "registered_at"),
            ("notifications", "low_resources_notified_at"),
        ):
            try:
                cur = await db.execute(
                    f"UPDATE {table} SET {col} = replace({col}, ' ', 'T') || '+00:00' "
                    f"WHERE typeof({col}) = 'text' "
                    f"AND length({col}) = 19 "
                    f"AND {col} LIKE '____-__-__ __:__:__'"
                )
                if cur.rowcount:
                    logger.info(
                        "Миграция: %s.%s — сконвертировано UTC-меток без таймзоны: %d",
                        table, col, cur.rowcount,
                    )
            except Exception:
                # FIXED (Задача 6): раньше исключение молча глоталось
                logger.exception("Миграция: ошибка конвертации таймстампов %s.%s", table, col)

        await db.commit()


async def get_or_create_user(
    db: aiosqlite.Connection, telegram_id: int, username: Optional[str] = None
) -> dict:
    cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = await cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    # FIXED (Задача 2): registered_at ставим из Python в UTC вместо убранного
    # DEFAULT CURRENT_TIMESTAMP.
    await db.execute(
        "INSERT INTO users (telegram_id, username, registered_at) VALUES (?, ?, ?)",
        (telegram_id, username, datetime.now(timezone.utc)),
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
    # FIXED (Задача 2): last_decay_check явно ставим в UTC при создании хижины.
    await db.execute(
        "INSERT INTO cabins (user_id, is_built, max_wood_storage, max_stone_storage, last_decay_check) "
        "VALUES (?, 1, 100, 100, ?)",
        (user_id, datetime.now(timezone.utc)),
    )
    await db.commit()


async def delete_cabin(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute("DELETE FROM cabins WHERE user_id = ?", (user_id,))
    await db.commit()


async def update_user_resources(
    db: aiosqlite.Connection, user_id: int, coins: int, wood: int, stone: int,
    sand: Optional[int] = None,
) -> None:
    # NEW (песок): sand опционален — старые вызовы с 5 аргументами не трогает
    # (обновляют только coins/wood/stone); добыча песка передаёт sand явно.
    if sand is None:
        await db.execute(
            "UPDATE users SET coins = ?, wood = ?, stone = ? WHERE user_id = ?",
            (coins, wood, stone, user_id),
        )
    else:
        await db.execute(
            "UPDATE users SET coins = ?, wood = ?, stone = ?, sand = ? WHERE user_id = ?",
            (coins, wood, stone, sand, user_id),
        )
    await db.commit()


async def update_user_coins(db: aiosqlite.Connection, user_id: int, coins: int) -> None:
    await db.execute("UPDATE users SET coins = ? WHERE user_id = ?", (coins, user_id))
    await db.commit()


async def update_gather_cooldown(
    db: aiosqlite.Connection, user_id: int, action: str, timestamp: datetime
) -> None:
    # NEW (песок): карта колонок кулдаунов вместо тернарника (было только wood/stone)
    _cooldown_columns = {
        "sand": "last_sand_gather",
        "wood": "last_wood_gather",
        "stone": "last_stone_gather",
    }
    column = _cooldown_columns[action]
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
            # FIXED (Задача 2): fallback для старых меток без таймзоны — считаем их UTC,
            # иначе aware/naive сравнение упадёт или соврёт.
            dt = datetime.fromisoformat(row[0])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        return row[0]
    return None


async def set_notification_state(
    db: aiosqlite.Connection, user_id: int, timestamp: datetime
) -> None:
    # FIXED (Задача 1): INSERT OR REPLACE затирал всю строку — флаг
    # fifty_percent_notified сбрасывался в 0 при каждом кулдаун-уведомлении.
    # UPSERT обновляет только целевую колонку.
    await db.execute(
        "INSERT INTO notifications (user_id, low_resources_notified_at) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET low_resources_notified_at = excluded.low_resources_notified_at",
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
    # FIXED (Задача 1): INSERT OR REPLACE затирал low_resources_notified_at
    # (обнулялся кулдаун пустых уведомлений → спам). Обновляем только флаг.
    await db.execute(
        "INSERT INTO notifications (user_id, fifty_percent_notified) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET fifty_percent_notified = excluded.fifty_percent_notified",
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


# FIXED (уведомления): стадия пустых уведомлений — счётчик 0..3.
# Уведомление «нет ресурсов» шлётся максимум 3 раза за цикл разрушения:
# при прочности <90%, <40% и <=10% (вместо повторов каждые 30 минут).
async def get_empty_notify_stage(db: aiosqlite.Connection, user_id: int) -> int:
    cursor = await db.execute(
        "SELECT empty_notify_stage FROM notifications WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row and row[0] is not None else 0


async def set_empty_notify_stage(
    db: aiosqlite.Connection, user_id: int, stage: int
) -> None:
    # UPSERT обновляет только колонку стадии, не затирая соседние (Задача 1).
    await db.execute(
        "INSERT INTO notifications (user_id, empty_notify_stage) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET empty_notify_stage = excluded.empty_notify_stage",
        (user_id, stage),
    )
    await db.commit()
