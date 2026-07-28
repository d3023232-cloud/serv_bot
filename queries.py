"""Инициализация SQLite-базы и создание таблиц."""

import aiosqlite
from config import DB_PATH


async def init_db() -> None:
    """Создаёт таблицы, если они ещё не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
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
                max_wood_storage INTEGER DEFAULT 50,
                max_stone_storage INTEGER DEFAULT 50,
                last_decay_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_built INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                user_id INTEGER PRIMARY KEY,
                low_resources_notified_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()
