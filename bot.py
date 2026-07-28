"""
Survival Bot — монолитная версия с мини-игрой 3x3.
Production-ready: type hints, логирование, обработка ошибок, i18n, SQLite, FSM.
"""

import os
import random
import pathlib
import asyncio
import logging
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import aiosqlite

# ═══════════════════════════════════════════════════════════════
# 1. КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATA_DIR: str = os.getenv("DATA_DIR", "")
DB_PATH: str = os.getenv("DB_PATH", "")

if DATA_DIR:
    pathlib.Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    DB_PATH = os.path.join(DATA_DIR, "survival_bot.db")
elif not DB_PATH:
    DB_PATH = "survival_bot.db"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("DB_PATH = %s", DB_PATH)


# ═══════════════════════════════════════════════════════════════
# 2. I18N — ВСЕ ТЕКСТЫ БОТА
# ═══════════════════════════════════════════════════════════════

WELCOME_NEW = (
    "🏕 <b>Добро пожаловать в выживание!</b>\n\n"
    "Ты очнулся в незнакомом лесу. Вокруг только деревья и камни. "
    "Чтобы пережить ночь, тебе нужно построить хижину.\n\n"
    "💰 Стоимость постройки:\n"
    "• <b>20 🪵 дерева</b>\n"
    "• <b>10 🪨 камня</b>\n\n"
    "Начни с добычи ресурсов! Нажми «🪵 Добыть дерево» или «🪨 Добыть камень»."
)

WELCOME_BACK = (
    "👋 <b>С возвращением, выживальщик!</b>\n\n"
    "Лес ждёт. Что будем делать?"
)

BTN_MY_CABIN = "🏠 Моя хижина"
BTN_INVENTORY = "🎒 Инвентарь"
BTN_GATHER_WOOD = "🪵 Добыть дерево"
BTN_GATHER_STONE = "🪨 Добыть камень"

CABIN_NOT_BUILT = (
    "🏠 <b>Хижина</b>\n\n"
    "У тебя ещё нет убежища. Ночью в лесу очень опасно!\n\n"
    "💰 Стоимость постройки:\n"
    "• 20 🪵 дерева\n"
    "• 10 🪨 камня\n\n"
    "Нажми кнопку ниже, когда накопишь ресурсы."
)

CABIN_STATUS = (
    "🏠 <b>Хижина (уровень {level})</b>\n\n"
    "🛡 Прочность: <b>{durability:.1f}%</b> / {max_durability}%\n"
    "🪵 Дерево в шкафу: <b>{wood}</b> / {max_wood}\n"
    "🪨 Камень в шкафу: <b>{stone}</b> / {max_stone}\n\n"
    "⚡ Потребление: 1🪵 + 1🪨 каждые 30 мин\n"
    "🦠 Гниение: 3%/час при ресурсах, 6%/час без ресурсов"
)

INVENTORY_TEXT = (
    "🎒 <b>Инвентарь</b>\n\n"
    "🪵 Дерево: <b>{wood}</b>\n"
    "🪨 Камень: <b>{stone}</b>"
)

# ── Мини-игра: дерево ──
GATHER_WOOD_START = (
    "🪵 <b>Добыча дерева!</b>\n\n"
    "Найди 🪵 среди кустов. Попаданий: <b>0/3</b>\n\n"
    "Будь внимателен — промах = попытка сгорает!"
)
GATHER_WOOD_HIT = (
    "✅ <b>Попадание!</b>\n\n"
    "Найди следующее дерево. Попаданий: <b>{hits}/3</b>"
)
GATHER_WOOD_SUCCESS = (
    "🎉 <b>Отличная работа!</b>\n\n"
    "Ты собрал <b>+{amount} дерева</b>!\n"
    "Возвращайся через 30 секунд."
)
GATHER_WOOD_MISS = (
    "❌ <b>Промах!</b>\n\n"
    "Ты промахнулся и ничего не нашёл.\n"
    "Попытка истрачена. Возвращайся через 30 секунд."
)
GATHER_WOOD_COOLDOWN = (
    "⏳ Дерево восстанавливается.\n\n"
    "Подожди ещё <b>{seconds} сек</b>."
)
GATHER_WOOD_ALREADY = (
    "⚠️ <b>Игра уже идёт!</b>\n\n"
    "Заверши текущую добычу или дождись окончания."
)

# ── Мини-игра: камень ──
GATHER_STONE_START = (
    "🪨 <b>Добыча камня!</b>\n\n"
    "Найди 🪨 среди грунта. Попаданий: <b>0/3</b>\n\n"
    "Будь внимателен — промах = попытка сгорает!"
)
GATHER_STONE_HIT = (
    "✅ <b>Попадание!</b>\n\n"
    "Найди следующий камень. Попаданий: <b>{hits}/3</b>"
)
GATHER_STONE_SUCCESS = (
    "🎉 <b>Отличная работа!</b>\n\n"
    "Ты добыл <b>+{amount} камня</b>!\n"
    "Возвращайся через 1 минуту."
)
GATHER_STONE_MISS = (
    "❌ <b>Промах!</b>\n\n"
    "Ты промахнулся и ничего не нашёл.\n"
    "Попытка истрачена. Возвращайся через 1 минуту."
)
GATHER_STONE_COOLDOWN = (
    "⏳ Камни пока не появились.\n\n"
    "Подожди ещё <b>{seconds} сек</b>."
)
GATHER_STONE_ALREADY = (
    "⚠️ <b>Игра уже идёт!</b>\n\n"
    "Заверши текущую добычу или дождись окончания."
)

CABIN_BUILD_SUCCESS = (
    "🏠 <b>Хижина построена!</b>\n\n"
    "Теперь у тебя есть надёжное убежище. Не забудь пополнять шкаф "
    "ресурсами, иначе она начнёт гнить!"
)
CABIN_BUILD_NO_RESOURCES = (
    "❌ <b>Недостаточно ресурсов!</b>\n\n"
    "Нужно: 20 🪵 и 10 🪨\n"
    "У тебя: {wood} 🪵 и {stone} 🪨"
)

NOTIFY_LOW_RESOURCES = (
    "⚠️ <b>Внимание! Ресурсы в хижине на исходе!</b>\n\n"
    "🪵 Дерево: {wood} / {max_wood}\n"
    "🪨 Камень: {stone} / {max_stone}\n\n"
    "Пополни шкаф, пока хижина не начала разрушаться!"
)

ERROR_GENERAL = "❌ Произошла ошибка. Попробуй позже."


# ═══════════════════════════════════════════════════════════════
# 3. БАЗА ДАННЫХ — ИНИЦИАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════

async def init_db() -> None:
    """Создаёт таблицы SQLite, если они ещё не существуют."""
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


# ═══════════════════════════════════════════════════════════════
# 4. QUERIES — ЧИСТЫЕ SQL-ЗАПРОСЫ
# ═══════════════════════════════════════════════════════════════

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
    cursor = await db.execute("SELECT * FROM cabins WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def create_cabin(db: aiosqlite.Connection, user_id: int) -> None:
    """Создаёт запись о хижине после постройки."""
    await db.execute(
        "INSERT INTO cabins (user_id, is_built) VALUES (?, 1)", (user_id,)
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
    column = "last_wood_gather" if action == "wood" else "last_stone_gather"
    await db.execute(
        f"UPDATE users SET {column} = ? WHERE user_id = ?", (timestamp, user_id)
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


# ═══════════════════════════════════════════════════════════════
# 5. КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════

def main_menu() -> ReplyKeyboardMarkup:
    """Возвращает главную клавиатуру с основными действиями."""
    kb = [
        [
            KeyboardButton(text=BTN_MY_CABIN),
            KeyboardButton(text=BTN_INVENTORY),
        ],
        [
            KeyboardButton(text=BTN_GATHER_WOOD),
            KeyboardButton(text=BTN_GATHER_STONE),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def _build_game_kb(resource: str, target_idx: int) -> InlineKeyboardMarkup:
    """Строит игровое поле 3x3 с одной целью на случайной позиции."""
    emoji_target = "🪵" if resource == "wood" else "🪨"
    emoji_empty = "🌿" if resource == "wood" else "⬜"
    buttons = []
    for idx in range(9):
        text = emoji_target if idx == target_idx else emoji_empty
        buttons.append(
            InlineKeyboardButton(text=text, callback_data=f"game:{resource}:{idx}")
        )
    # Разбиваем на 3 ряда по 3
    keyboard = [buttons[i:i+3] for i in range(0, 9, 3)]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ═══════════════════════════════════════════════════════════════
# 6. СЕРВИСЫ — БИЗНЕС-ЛОГИКА
# ═══════════════════════════════════════════════════════════════

# ── 6.1 Добыча ресурсов — константы ──

WOOD_COOLDOWN = 30    # 30 секунд
STONE_COOLDOWN = 60   # 1 минута
WOOD_YIELD = 2        # за одно попадание
STONE_YIELD = 1       # за одно попадание
GAME_HITS_NEEDED = 3  # попаданий подряд для успеха


# ── 6.2 Хижина ──

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

    cabin = await get_cabin(db, user_id)
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

    await update_user_resources(db, user_id, new_wood, new_stone)
    await create_cabin(db, user_id)
    return True, "success"


async def add_to_storage(
    db: aiosqlite.Connection,
    user_id: int,
    wood: int,
    stone: int,
    user: dict,
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

    await update_user_resources(db, user_id, new_user_wood, new_user_stone)
    await update_cabin_storage(db, user_id, new_wood_storage, new_stone_storage)
    return True, "success"


# ── 6.3 Уведомления ──

CHECK_INTERVAL = 600   # 10 минут
NOTIFY_COOLDOWN = 7200  # 2 часа между повторными уведомлениями
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
        cabins = await get_all_cabins(db)
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

            last_notify = await get_notification_state(db, user_id)
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
                    text=NOTIFY_LOW_RESOURCES.format(
                        wood=wood,
                        max_wood=max_wood,
                        stone=stone,
                        max_stone=max_stone,
                    ),
                )
                await set_notification_state(db, user_id, now)
                logger.info("Уведомление отправлено пользователю %s", telegram_id)
            except Exception as exc:
                logger.warning("Не удалось отправить уведомление %s: %s", telegram_id, exc)


# ═══════════════════════════════════════════════════════════════
# 7. FSM — МАШИНА СОСТОЯНИЙ ДЛЯ МИНИ-ИГРЫ
# ═══════════════════════════════════════════════════════════════

class GatherGame(StatesGroup):
    """Состояние активной мини-игры добычи ресурсов."""
    playing = State()


# ═══════════════════════════════════════════════════════════════
# 8. ХЕНДЛЕРЫ
# ═══════════════════════════════════════════════════════════════

start_router = Router()
inventory_router = Router()
gathering_router = Router()
cabin_router = Router()


# ── /start ──

@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обрабатывает /start: регистрирует нового игрока или приветствует старого."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(
                db, message.from_user.id, message.from_user.username
            )
            cabin = await get_cabin(db, user["user_id"])

            text = WELCOME_BACK if (cabin and cabin["is_built"]) else WELCOME_NEW
            await message.answer(text, reply_markup=main_menu())
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Инвентарь ──

@inventory_router.message(lambda msg: msg.text == BTN_INVENTORY)
async def show_inventory(message: Message) -> None:
    """Показывает текущее количество дерева и камня в инвентаре."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            text = INVENTORY_TEXT.format(wood=user["wood"], stone=user["stone"])
            await message.answer(text)
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Мини-игра: Дерево ──

@gathering_router.message(lambda msg: msg.text == BTN_GATHER_WOOD)
async def gather_wood_handler(message: Message, state: FSMContext) -> None:
    """Запускает мини-игру добычи дерева с проверкой кулдауна."""
    try:
        current_state = await state.get_state()
        if current_state == GatherGame.playing:
            await message.answer(GATHER_WOOD_ALREADY)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)

            # Проверка кулдауна
            now = datetime.now()
            last = user.get("last_wood_gather")
            if last:
                last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
                diff = (now - last_dt).total_seconds()
                if diff < WOOD_COOLDOWN:
                    await message.answer(
                        GATHER_WOOD_COOLDOWN.format(seconds=int(WOOD_COOLDOWN - diff))
                    )
                    return

            # Запуск мини-игры
            target = random.randint(0, 8)
            kb = _build_game_kb("wood", target)
            sent = await message.answer(GATHER_WOOD_START, reply_markup=kb)

            await state.set_state(GatherGame.playing)
            await state.update_data(
                resource="wood",
                hits=0,
                target=target,
                msg_id=sent.message_id,
                chat_id=message.chat.id,
                user_id=user["user_id"],
                wood=user["wood"],
                stone=user["stone"],
            )
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Мини-игра: Камень ──

@gathering_router.message(lambda msg: msg.text == BTN_GATHER_STONE)
async def gather_stone_handler(message: Message, state: FSMContext) -> None:
    """Запускает мини-игру добычи камня с проверкой кулдауна."""
    try:
        current_state = await state.get_state()
        if current_state == GatherGame.playing:
            await message.answer(GATHER_STONE_ALREADY)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)

            # Проверка кулдауна
            now = datetime.now()
            last = user.get("last_stone_gather")
            if last:
                last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
                diff = (now - last_dt).total_seconds()
                if diff < STONE_COOLDOWN:
                    await message.answer(
                        GATHER_STONE_COOLDOWN.format(seconds=int(STONE_COOLDOWN - diff))
                    )
                    return

            # Запуск мини-игры
            target = random.randint(0, 8)
            kb = _build_game_kb("stone", target)
            sent = await message.answer(GATHER_STONE_START, reply_markup=kb)

            await state.set_state(GatherGame.playing)
            await state.update_data(
                resource="stone",
                hits=0,
                target=target,
                msg_id=sent.message_id,
                chat_id=message.chat.id,
                user_id=user["user_id"],
                wood=user["wood"],
                stone=user["stone"],
            )
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Обработка кликов в мини-игре ──

@gathering_router.callback_query(F.data.startswith("game:"))
async def game_callback(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Обрабатывает нажатие кнопки в мини-игре 3x3."""
    try:
        current_state = await state.get_state()
        if current_state != GatherGame.playing:
            await call.answer("Игра уже завершена.", show_alert=True)
            return

        data = await state.get_data()
        parts = call.data.split(":")
        if len(parts) != 3:
            return

        resource = parts[1]
        idx = int(parts[2])

        # Если callback не от текущей игры (wood vs stone)
        if data.get("resource") != resource:
            await call.answer("Это не твоя текущая игра.", show_alert=True)
            return

        target = data["target"]
        hits = data["hits"]
        msg_id = data["msg_id"]
        chat_id = data["chat_id"]
        user_id = data["user_id"]

        if idx == target:
            # ── Попадание ──
            hits += 1
            if hits >= GAME_HITS_NEEDED:
                # Финиш: начисляем ресурсы и записываем кулдаун
                amount = hits * (WOOD_YIELD if resource == "wood" else STONE_YIELD)
                async with aiosqlite.connect(DB_PATH) as db:
                    user = await get_or_create_user(db, call.from_user.id)
                    if resource == "wood":
                        new_wood = user["wood"] + amount
                        await update_user_resources(db, user_id, new_wood, user["stone"])
                        await update_gather_cooldown(db, user_id, "wood", datetime.now())
                        text = GATHER_WOOD_SUCCESS.format(amount=amount)
                    else:
                        new_stone = user["stone"] + amount
                        await update_user_resources(db, user_id, user["wood"], new_stone)
                        await update_gather_cooldown(db, user_id, "stone", datetime.now())
                        text = GATHER_STONE_SUCCESS.format(amount=amount)

                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=None,
                )
                await state.clear()
                logger.info("Пользователь %s успешно завершил добычу %s (+ %s)",
                            call.from_user.id, resource, amount)
            else:
                # Следующий раунд: новая цель, обновляем поле
                new_target = random.randint(0, 8)
                kb = _build_game_kb(resource, new_target)
                hit_text = (
                    GATHER_WOOD_HIT if resource == "wood" else GATHER_STONE_HIT
                ).format(hits=hits)
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=hit_text,
                    reply_markup=kb,
                )
                await state.update_data(hits=hits, target=new_target)
                await call.answer("✅ Попадание!")
        else:
            # ── Промах ──
            async with aiosqlite.connect(DB_PATH) as db:
                if resource == "wood":
                    await update_gather_cooldown(db, user_id, "wood", datetime.now())
                    text = GATHER_WOOD_MISS
                else:
                    await update_gather_cooldown(db, user_id, "stone", datetime.now())
                    text = GATHER_STONE_MISS

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=None,
            )
            await state.clear()
            logger.info("Пользователь %s промахнулся в добыче %s", call.from_user.id, resource)
            await call.answer("❌ Промах!", show_alert=True)

    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


# ── Хижина ──

async def _show_cabin_status(
    db: aiosqlite.Connection,
    telegram_id: int,
    message: Message,
    edit: bool = False,
) -> None:
    """Внутренняя функция отрисовки статуса хижины (новое сообщение или edit)."""
    user = await get_or_create_user(db, telegram_id)
    cabin = await get_cabin(db, user["user_id"])

    if not cabin or not cabin["is_built"]:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏗 Построить хижину", callback_data="build_cabin"
                    )
                ]
            ]
        )
        if edit:
            await message.edit_text(CABIN_NOT_BUILT, reply_markup=kb)
        else:
            await message.answer(CABIN_NOT_BUILT, reply_markup=kb)
        return

    cabin = await apply_cabin_tick(db, user["user_id"])

    text = CABIN_STATUS.format(
        level=cabin["level"],
        durability=cabin["durability"],
        max_durability=cabin["max_durability"],
        wood=cabin["wood_storage"],
        max_wood=cabin["max_wood_storage"],
        stone=cabin["stone_storage"],
        max_stone=cabin["max_stone_storage"],
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ 10 🪵", callback_data="add_wood_10"),
                InlineKeyboardButton(text="➕ 10 🪨", callback_data="add_stone_10"),
            ],
            [
                InlineKeyboardButton(
                    text="🔧 Починить (5🪵+5🪨)", callback_data="repair_cabin"
                )
            ],
        ]
    )

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@cabin_router.message(lambda msg: msg.text == BTN_MY_CABIN)
async def my_cabin(message: Message) -> None:
    """Показывает текущий статус хижины с учётом реального времени гниения."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await _show_cabin_status(db, message.from_user.id, message)
    except Exception:
        await message.answer(ERROR_GENERAL)


@cabin_router.callback_query(F.data == "build_cabin")
async def build_cabin_callback(call: CallbackQuery) -> None:
    """Строит хижину при наличии достаточного количества ресурсов."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            success, _ = await build_cabin(db, user["user_id"], user)

            if success:
                await call.message.edit_text(CABIN_BUILD_SUCCESS)
            else:
                await call.answer(
                    CABIN_BUILD_NO_RESOURCES.format(wood=user["wood"], stone=user["stone"]),
                    show_alert=True,
                )
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "add_wood_10")
async def add_wood_callback(call: CallbackQuery) -> None:
    """Кладёт 10 дерева из инвентаря в шкаф хижины."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            success, _ = await add_to_storage(db, user["user_id"], 10, 0, user)

            if success:
                await call.answer("✅ Дерево добавлено!")
                await _show_cabin_status(db, call.from_user.id, call.message, edit=True)
            else:
                await call.answer("❌ Недостаточно дерева или нет хижины!", show_alert=True)
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "add_stone_10")
async def add_stone_callback(call: CallbackQuery) -> None:
    """Кладёт 10 камня из инвентаря в шкаф хижины."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            success, _ = await add_to_storage(db, user["user_id"], 0, 10, user)

            if success:
                await call.answer("✅ Камень добавлен!")
                await _show_cabin_status(db, call.from_user.id, call.message, edit=True)
            else:
                await call.answer("❌ Недостаточно камня или нет хижины!", show_alert=True)
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "repair_cabin")
async def repair_cabin_callback(call: CallbackQuery) -> None:
    """Заглушка для починки хижины (будет реализовано в следующем этапе)."""
    await call.answer("🔧 Починка будет доступна в следующем обновлении!", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# 9. ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════

async def main() -> None:
    """Главная корутина: подготовка БД и запуск polling."""
    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_routers(
        start_router,
        inventory_router,
        gathering_router,
        cabin_router,
    )

    # Фоновый цикл уведомлений о низких ресурсах
    asyncio.create_task(start_notification_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
