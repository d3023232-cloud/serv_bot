"""
Все хендлеры — команды, кнопки, FSM-состояния, клавиатуры.
"""

import random
import logging
import sys  # FIXED (Задача 6): для имени хендлера в логах исключений
from datetime import datetime, timezone  # FIXED (Задача 2): единое UTC-время
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
)
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import aiosqlite

from config import (
    DB_PATH,
    WELCOME_NEW,
    WELCOME_BACK,
    BTN_MY_CABIN,
    BTN_INVENTORY,
    BTN_GATHER,  # FIXED (реплей кнопок добычи): одна кнопка вместо двух
    BTN_MARKET,
    CABIN_NOT_BUILT,
    CABIN_STATUS,
    INVENTORY_TEXT,
    # NEW (добыча): тексты меню выбора места добычи и мгновенной добычи
    GATHER_MENU_TEXT,
    # FIXED (мини-игра возвращена): тексты и параметры игры «найди предмет»
    GATHER_GAME_TEXT,
    GATHER_GAME_MISS,
    GATHER_GAME_FAIL,
    GATHER_GRID_SIZE,
    GATHER_MAX_ATTEMPTS,
    GATHER_SAND_SUCCESS,
    GATHER_WOOD_SUCCESS,
    GATHER_STONE_SUCCESS,
    GATHER_COOLDOWN,
    MARKET_WELCOME,
    MARKET_BUY_HEADER,
    MARKET_SELL_HEADER,
    BUY_SAND_TEXT,  # NEW (песок): товар рынка
    BUY_WOOD_TEXT,
    BUY_STONE_TEXT,
    SELL_WOOD_TEXT,
    SELL_STONE_TEXT,
    MARKET_ENTER_AMOUNT,
    MARKET_INVALID_AMOUNT,
    BUY_SUCCESS,
    BUY_NO_MONEY,
    SELL_SUCCESS,
    SELL_NO_RESOURCES,
    CABIN_BUILD_SUCCESS,
    CABIN_BUILD_NO_RESOURCES,
    ERROR_GENERAL,
    REPAIR_ENTER_HP,
    REPAIR_INVALID,
    REPAIR_NO_RESOURCES,
    REPAIR_SUCCESS,
    RESTORE_SUCCESS,
    PRICE_BUY_WOOD,
    PRICE_SELL_WOOD,
    PRICE_BUY_STONE,
    PRICE_SELL_STONE,
    SAND_PRICE,  # NEW (песок): цена покупки на рынке
    WOOD_COOLDOWN,
    STONE_COOLDOWN,
    SAND_COOLDOWN,  # NEW (добыча): кулдауны и максимумы за заход
    MAX_SAND_PER_RUN,
    MAX_WOOD_PER_RUN,
    MAX_STONE_PER_RUN,
    RESTORE_STARS_PRICE,
)
from database import (
    get_or_create_user,
    get_cabin,
    update_user_resources,
    update_gather_cooldown,
    update_cabin_storage,
    update_cabin_durability,
)
from services import (
    apply_cabin_tick,
    build_cabin,
    add_to_storage,
    calc_max_repair,
    do_repair,
)

logger = logging.getLogger(__name__)


def _current_handler_name() -> str:
    """Имя хендлера, в котором произошёл exception (для логов, Задача 6)."""
    frame = sys.exc_info()[2]
    if frame is None:
        return "?"
    while frame.tb_next:
        frame = frame.tb_next
    return frame.tb_frame.f_code.co_name


def _parse_ts(raw) -> Optional[datetime]:
    """Парсит таймстемп из БД в aware UTC datetime.

    FIXED (Задача 2): старые строки SQLite ("YYYY-MM-DD HH:MM:SS") — это UTC без
    таймзоны; приравниваем tzinfo=utc, чтобы корректно сравнивать с
    datetime.now(timezone.utc). Миграция в migrate_db() приводит их к ISO+00:00,
    но fallback оставлен на случай пропуска миграции.
    """
    if raw is None:
        return None
    dt = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

# ── FSM ──
# FIXED (мини-игра возвращена): состояние активной игры «найди предмет».
class GatherGame(StatesGroup):
    playing = State()

class MarketState(StatesGroup):
    entering_amount = State()

class RepairState(StatesGroup):
    entering_hp = State()


# ── Клавиатуры ──
def main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text=BTN_MY_CABIN), KeyboardButton(text=BTN_INVENTORY)],
        # FIXED (реплей кнопок добычи): вместо двух реплей-кнопок дерева/камня —
        # одна «⛏ Добыча», внутри неё инлайн-выбор места добычи.
        [KeyboardButton(text=BTN_GATHER)],
        [KeyboardButton(text=BTN_MARKET)],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def market_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Продать", callback_data="market:sell"),
                InlineKeyboardButton(text="🛒 Купить", callback_data="market:buy"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="market:back")],
        ]
    )


def buy_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BUY_SAND_TEXT, callback_data="buy:sand")],  # NEW (песок)
            [InlineKeyboardButton(text=BUY_WOOD_TEXT, callback_data="buy:wood")],
            [InlineKeyboardButton(text=BUY_STONE_TEXT, callback_data="buy:stone")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="market:back")],
        ]
    )


def sell_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=SELL_WOOD_TEXT, callback_data="sell:wood")],
            [InlineKeyboardButton(text=SELL_STONE_TEXT, callback_data="sell:stone")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="market:back")],
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="market:cancel")],
        ]
    )


# NEW (добыча): справочник параметров мест добычи (иерархия: песок → дерево → камень)
GATHER_RESOURCES = {
    "sand": {
        "emoji": "🏖", "name": "Песок", "place": "Пляж",
        "cooldown": SAND_COOLDOWN, "max_per_run": MAX_SAND_PER_RUN,
        "success_text": GATHER_SAND_SUCCESS,
        "column": "last_sand_gather",
    },
    "wood": {
        "emoji": "🪵", "name": "Дерево", "place": "Лес",
        "cooldown": WOOD_COOLDOWN, "max_per_run": MAX_WOOD_PER_RUN,
        "success_text": GATHER_WOOD_SUCCESS,
        "column": "last_wood_gather",
    },
    "stone": {
        "emoji": "🪨", "name": "Камень", "place": "Каменоломня",
        "cooldown": STONE_COOLDOWN, "max_per_run": MAX_STONE_PER_RUN,
        "success_text": GATHER_STONE_SUCCESS,
        "column": "last_stone_gather",
    },
}


def gather_menu_kb() -> InlineKeyboardMarkup:
    """NEW (добыча): инлайн-выбор места добычи (вместо реплей-кнопок)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🏖 Пляж 🏖 (до {MAX_SAND_PER_RUN}, кд {SAND_COOLDOWN}с)",
                callback_data="gather:sand")],
            [InlineKeyboardButton(
                text=f"🌲 Лес 🪵 (до {MAX_WOOD_PER_RUN}, кд {WOOD_COOLDOWN}с)",
                callback_data="gather:wood")],
            [InlineKeyboardButton(
                text=f"⛰ Каменоломня 🪨 (до {MAX_STONE_PER_RUN}, кд {STONE_COOLDOWN}с)",
                callback_data="gather:stone")],
        ]
    )


# FIXED (мини-игра возвращена): сетка 3x3 с случайной клеткой, где спрятан ресурс.
def gather_game_kb(target_cell: int) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура поля игры «найди предмет» (клетки gather:cell:N)."""
    cells = []
    for row in range(GATHER_GRID_SIZE):
        line = []
        for col in range(GATHER_GRID_SIZE):
            idx = row * GATHER_GRID_SIZE + col
            line.append(InlineKeyboardButton(
                text="▪️", callback_data=f"gather:cell:{idx}:{target_cell}"))
        cells.append(line)
    return InlineKeyboardMarkup(inline_keyboard=cells)


# ── Роутеры ──
start_router = Router()
inventory_router = Router()
gathering_router = Router()
cabin_router = Router()
market_router = Router()


# ── /start ──
@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    try:
        # FIXED (Задача 4): сбрасываем зависшее FSM-состояние при /start
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id, message.from_user.username)
            cabin = await get_cabin(db, user["user_id"])
            text = WELCOME_BACK if (cabin and cabin["is_built"]) else WELCOME_NEW
            await message.answer(text, reply_markup=main_menu())
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)


# ── Инвентарь ──
@inventory_router.message(lambda msg: msg.text == BTN_INVENTORY)
async def show_inventory(message: Message, state: FSMContext) -> None:
    try:
        # FIXED (Задача 4): кнопка главного меню — сбрасываем FSM, иначе
        # следующее сообщение юзера парсилось бы как число рынка/починки
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            text = INVENTORY_TEXT.format(
                coins=user.get("coins", 0),
                sand=user.get("sand", 0),  # NEW (песок)
                wood=user["wood"], stone=user["stone"],
            )
            await message.answer(text)
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)


# ── Добыча (NEW: реплей-кнопка «⛏ Добыча» + инлайн-выбор места добычи) ──
@gathering_router.message(lambda msg: msg.text == BTN_GATHER)
async def gather_menu_handler(message: Message, state: FSMContext) -> None:
    """Показывает текст «Выбери место добычи» и инлайн-кнопки ресурсов."""
    try:
        # FIXED (Задача 4): кнопка главного меню — сбрасываем зависшее FSM
        await state.clear()
        text = GATHER_MENU_TEXT.format(
            sand_max=MAX_SAND_PER_RUN, sand_cd=SAND_COOLDOWN,
            wood_max=MAX_WOOD_PER_RUN, wood_cd=WOOD_COOLDOWN,
            stone_max=MAX_STONE_PER_RUN, stone_cd=STONE_COOLDOWN,
        )
        await message.answer(text, reply_markup=gather_menu_kb())
    except Exception:
        # FIXED (Задача 6): логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)


async def _finish_gather(call: CallbackQuery, bot: Bot, resource: str) -> None:
    """FIXED (мини-игра возвращена): завершение добычи после победы в игре.

    Проверяет кулдаун, выдаёт случайное количество от 1 до максимума заход,
    ставит кулдаун. Вызывается только при успешном нажатии на нужную клетку.
    """
    info = GATHER_RESOURCES[resource]
    async with aiosqlite.connect(DB_PATH) as db:
        user = await get_or_create_user(db, call.from_user.id)
        now = datetime.now(timezone.utc)  # FIXED (Задача 2): единое UTC
        last = _parse_ts(user.get(info["column"]))
        if last:
            diff = (now - last).total_seconds()
            if diff < info["cooldown"]:
                await call.answer(
                    GATHER_COOLDOWN.format(
                        emoji=info["emoji"], resource=info["name"].lower(),
                        seconds=int(info["cooldown"] - diff),
                    ).replace("<b>", "").replace("</b>", ""),
                    show_alert=True,
                )
                return False

        amount = random.randint(1, info["max_per_run"])
        new_coins = user.get("coins", 0)
        new_wood = user["wood"] + (amount if resource == "wood" else 0)
        new_stone = user["stone"] + (amount if resource == "stone" else 0)
        new_sand = user.get("sand", 0) + (amount if resource == "sand" else 0)
        await update_user_resources(db, user["user_id"], new_coins, new_wood, new_stone, new_sand)
        await update_gather_cooldown(db, user["user_id"], resource, now)

    text = info["success_text"].format(amount=amount, cooldown=info["cooldown"])
    await bot.edit_message_text(
        chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=text, reply_markup=None,
    )
    await call.answer(f"✅ +{amount} {info['name'].lower()}!")
    return True


@gathering_router.callback_query(F.data.startswith("gather:"))
async def gather_start_callback(call: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Инлайн-кнопки выбора места добычи → запуск мини-игры «найди предмет»."""
    try:
        parts = call.data.split(":")          # gather:<resource>
        resource = parts[1]
        if resource not in GATHER_RESOURCES:
            await call.answer()
            return
        info = GATHER_RESOURCES[resource]

        # Если юзер уже играет — не даём начать новую игру поверх старой.
        current = await state.get_state()
        if current == GatherGame.playing.state:
            data = await state.get_data()
            if data.get("resource"):
                await call.answer("🎮 У тебя уже идёт игра! Нажми на клетку.", show_alert=True)
                return

        # Проверка кулдауна ДО запуска игры (как и раньше — чтобы не играть впустую).
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            now = datetime.now(timezone.utc)
            last = _parse_ts(user.get(info["column"]))
            if last:
                diff = (now - last).total_seconds()
                if diff < info["cooldown"]:
                    await call.answer(
                        GATHER_COOLDOWN.format(
                            emoji=info["emoji"], resource=info["name"].lower(),
                            seconds=int(info["cooldown"] - diff),
                        ).replace("<b>", "").replace("</b>", ""),
                        show_alert=True,
                    )
                    return

        # FIXED (Задача 5 / мини-игра): кулдаун ставится в МОМЕНТ СТАРТА игры,
        # а не только по её итогам. Иначе юзер мог кликнуть 1–2 клетки, бросить
        # игру и мгновенно начать новую. Первый вариант по ТЗ выбран сознательно:
        # ужесточение баланса ровно на величину существующего кулдауна локации.
        async with aiosqlite.connect(DB_PATH) as db:
            await update_gather_cooldown(db, user["user_id"], resource, now)

        target_cell = random.randint(0, GATHER_GRID_SIZE * GATHER_GRID_SIZE - 1)
        await state.set_state(GatherGame.playing)
        await state.update_data(resource=resource, attempts=GATHER_MAX_ATTEMPTS)

        text = GATHER_GAME_TEXT.format(
            emoji=info["emoji"], place=info["place"], name_lower=info["name"].lower(),
            attempts=GATHER_MAX_ATTEMPTS, max=info["max_per_run"], cd=info["cooldown"],
        )
        await bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=text, reply_markup=gather_game_kb(target_cell),
        )
        await call.answer()
    except Exception:
        # FIXED (Задача 6): логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


# FIXED (мини-игра возвращена): клик по клетке поля 3x3.
# callback_data формата gather:cell:<выбрана>:<целевая>.
@gathering_router.callback_query(GatherGame.playing, F.data.startswith("gather:cell:"))
async def gather_cell_callback(call: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    try:
        _, _, chosen_s, target_s = call.data.split(":")
        chosen, target = int(chosen_s), int(target_s)

        data = await state.get_data()
        resource = data.get("resource")
        if not resource or resource not in GATHER_RESOURCES:
            # Состояние потеряно (например, рестарт бота) — выходим в меню добычи.
            await state.clear()
            await call.answer("Игра сброшена, начни заново.", show_alert=True)
            return
        info = GATHER_RESOURCES[resource]

        if chosen == target:
            # Победа: выдаём ресурс (кулдаун уже поставлен на старте игры,
            # но обновляем метку на момент финала для точности).
            await state.clear()
            await _finish_gather(call, bot, resource)
            return

        attempts = int(data.get("attempts", GATHER_MAX_ATTEMPTS)) - 1
        if attempts <= 0:
            # Поражение: игра окончена, кулдаун со старта остаётся в силе.
            await state.clear()
            async with aiosqlite.connect(DB_PATH) as db:
                user = await get_or_create_user(db, call.from_user.id)
                last = _parse_ts(user.get(info["column"]))
                remain = 0
                if last:
                    remain = max(0, int(info["cooldown"] - (datetime.now(timezone.utc) - last).total_seconds()))
            await bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=GATHER_GAME_FAIL.format(name_lower=info["name"].lower(), seconds=remain),
                reply_markup=None,
            )
            await call.answer("😔 Попытки закончились.")
            return

        await state.update_data(attempts=attempts)
        # Меняем нажатую клетку на ❌ и пересобираем поле (цель та же).
        kb_rows = []
        for row in range(GATHER_GRID_SIZE):
            line = []
            for col in range(GATHER_GRID_SIZE):
                idx = row * GATHER_GRID_SIZE + col
                label = "❌" if idx == chosen else "▪️"
                line.append(InlineKeyboardButton(
                    text=label, callback_data=f"gather:cell:{idx}:{target}"))
            kb_rows.append(line)
        text = GATHER_GAME_TEXT.format(
            emoji=info["emoji"], place=info["place"], name_lower=info["name"].lower(),
            attempts=attempts, max=info["max_per_run"], cd=info["cooldown"],
        ) + "\n\n" + GATHER_GAME_MISS.format(attempts=attempts)
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )
        await bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )
        await call.answer("❌ Пусто")
    except Exception:
        # FIXED (Задача 6): логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


# ═══════════════════════════════════════════════════════════════
# РЫНОК
# ═══════════════════════════════════════════════════════════════

@market_router.message(lambda msg: msg.text == BTN_MARKET)
async def market_entry(message: Message, state: FSMContext) -> None:
    try:
        # FIXED (Задача 4): кнопка главного меню — сбрасываем зависшее FSM,
        # иначе следующее сообщение юзера парсилось бы как число рынка
        await state.clear()
        await message.answer(MARKET_WELCOME, reply_markup=market_menu())
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)


@market_router.callback_query(F.data == "market:buy")
async def market_buy(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text(MARKET_BUY_HEADER, reply_markup=buy_menu())
        await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data == "market:sell")
async def market_sell(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text(MARKET_SELL_HEADER, reply_markup=sell_menu())
        await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data == "market:back")
async def market_back(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        await call.message.edit_text(MARKET_WELCOME, reply_markup=market_menu())
        await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data.startswith("buy:"))
async def buy_select(call: CallbackQuery, state: FSMContext) -> None:
    try:
        resource = call.data.split(":")[1]
        # NEW (песок): карта товаров вместо тернарников (было только wood/stone)
        _buy_info = {
            "sand": (SAND_PRICE, "🏖", "песок"),
            "wood": (PRICE_BUY_WOOD, "🪵", "дерево"),
            "stone": (PRICE_BUY_STONE, "🪨", "камень"),
        }
        if resource not in _buy_info:
            await call.answer()
            return
        price, emoji, res_name = _buy_info[resource]

        text = MARKET_ENTER_AMOUNT.format(
            mode_emoji="🛒", mode="ПОКУПКА", emoji=emoji,
            resource=res_name, price=price, action="купить",
        )
        await call.message.edit_text(text, reply_markup=cancel_kb())
        await state.set_state(MarketState.entering_amount)
        await state.update_data(
            operation="buy", resource=resource, price=price,
            chat_id=call.message.chat.id, msg_id=call.message.message_id,
        )
        await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data.startswith("sell:"))
async def sell_select(call: CallbackQuery, state: FSMContext) -> None:
    try:
        resource = call.data.split(":")[1]
        price = PRICE_SELL_WOOD if resource == "wood" else PRICE_SELL_STONE
        emoji = "🪵" if resource == "wood" else "🪨"
        res_name = "дерево" if resource == "wood" else "камень"

        text = MARKET_ENTER_AMOUNT.format(
            mode_emoji="💰", mode="ПРОДАЖА", emoji=emoji,
            resource=res_name, price=price, action="продать",
        )
        await call.message.edit_text(text, reply_markup=cancel_kb())
        await state.set_state(MarketState.entering_amount)
        await state.update_data(
            operation="sell", resource=resource, price=price,
            chat_id=call.message.chat.id, msg_id=call.message.message_id,
        )
        await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data == "market:cancel")
async def market_cancel(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        await call.message.edit_text(MARKET_WELCOME, reply_markup=market_menu())
        await call.answer("Отменено")
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.message(MarketState.entering_amount)
async def market_process_amount(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        data = await state.get_data()
        operation = data["operation"]
        resource = data["resource"]
        price = data["price"]
        msg_id = data["msg_id"]
        chat_id = data["chat_id"]

        try:
            amount = int(message.text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.delete()
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=MARKET_INVALID_AMOUNT, reply_markup=cancel_kb(),
            )
            return

        total = price * amount
        # NEW (песок): справочник названий/эмодзи для сообщений рынка
        _res_meta = {
            "sand": ("🏖", "песок", "Песок"),
            "wood": ("🪵", "дерево", "Дерево"),
            "stone": ("🪨", "камень", "Камень"),
        }
        emoji, res_name, res_name_cap = _res_meta[resource]

        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            coins = user.get("coins", 0)

            if operation == "buy":
                if coins < total:
                    await message.delete()
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=msg_id,
                        text=BUY_NO_MONEY.format(total=total, coins=coins),
                        reply_markup=buy_menu(),
                    )
                    await state.clear()
                    return

                new_coins = coins - total
                new_wood = user["wood"] + (amount if resource == "wood" else 0)
                new_stone = user["stone"] + (amount if resource == "stone" else 0)
                # NEW (песок): песок тоже можно купить — обновляем и его колонку
                new_sand = user.get("sand", 0) + (amount if resource == "sand" else 0)
                await update_user_resources(db, user["user_id"], new_coins, new_wood, new_stone, new_sand)

                _before = {"sand": user.get("sand", 0), "wood": user["wood"], "stone": user["stone"]}[resource]
                _after = {"sand": new_sand, "wood": new_wood, "stone": new_stone}[resource]
                text = BUY_SUCCESS.format(
                    amount=amount, resource=res_name, total=total,
                    coins_before=coins, coins_after=new_coins, emoji=emoji,
                    resource_cap=res_name_cap,
                    res_before=_before,
                    res_after=_after,
                )
                await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=buy_menu())

            else:
                # NOTE (песок): продажа песка пока не добавлена в меню sell_menu,
                # поэтому сюда попадают только wood/stone; .get("sand", 0) — на будущее.
                have = {"sand": user.get("sand", 0), "wood": user["wood"], "stone": user["stone"]}[resource]
                if have < amount:
                    await message.delete()
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=msg_id,
                        text=SELL_NO_RESOURCES.format(amount=amount, resource=res_name, have=have),
                        reply_markup=sell_menu(),
                    )
                    await state.clear()
                    return

                new_coins = coins + total
                new_wood = user["wood"] - (amount if resource == "wood" else 0)
                new_stone = user["stone"] - (amount if resource == "stone" else 0)
                await update_user_resources(db, user["user_id"], new_coins, new_wood, new_stone)

                text = SELL_SUCCESS.format(
                    amount=amount, resource=res_name, total=total,
                    coins_before=coins, coins_after=new_coins, emoji=emoji,
                    resource_cap=res_name_cap,
                    res_before=have,
                    res_after=new_wood if resource == "wood" else new_stone,
                )
                await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=sell_menu())

        await state.clear()
        await message.delete()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)
        await state.clear()


# ═══════════════════════════════════════════════════════════════
# ХИЖИНА
# ═══════════════════════════════════════════════════════════════

async def _show_cabin_status(
    db: aiosqlite.Connection, telegram_id: int, message: Message, edit: bool = False
) -> None:
    user = await get_or_create_user(db, telegram_id)
    cabin = await get_cabin(db, user["user_id"])

    if not cabin or not cabin["is_built"]:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏗 Построить хижину", callback_data="build_cabin")]
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
                InlineKeyboardButton(text="🔧 Починить", callback_data="repair_cabin"),
            ],
        ]
    )

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@cabin_router.message(lambda msg: msg.text == BTN_MY_CABIN)
async def my_cabin(message: Message, state: FSMContext) -> None:
    try:
        # FIXED (Задача 4): кнопка главного меню — сбрасываем зависшее FSM
        # (MarketState.entering_amount / RepairState.entering_hp)
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            await _show_cabin_status(db, message.from_user.id, message)
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)


@cabin_router.callback_query(F.data == "build_cabin")
async def build_cabin_callback(call: CallbackQuery) -> None:
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
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "add_wood_10")
async def add_wood_callback(call: CallbackQuery) -> None:
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
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "add_stone_10")
async def add_stone_callback(call: CallbackQuery) -> None:
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
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


# ── Починка ──
@cabin_router.callback_query(F.data == "repair_cabin")
async def repair_cabin_callback(call: CallbackQuery, state: FSMContext) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            cabin = await get_cabin(db, user["user_id"])
            if not cabin or not cabin["is_built"]:
                await call.answer("❌ У тебя нет хижины!", show_alert=True)
                return

            cabin = await apply_cabin_tick(db, user["user_id"])
            max_repair = calc_max_repair(
                cabin["durability"], cabin["max_durability"], user["wood"], user["stone"]
            )

            if max_repair <= 0:
                await call.answer("❌ Недостаточно ресурсов для починки!", show_alert=True)
                return

            text = REPAIR_ENTER_HP.format(
                durability=cabin["durability"],
                max=cabin["max_durability"],
                wood=user["wood"],
                stone=user["stone"],
                max_repair=max_repair,
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"🔧 Починить максимум ({max_repair} HP)",
                            callback_data="repair_max",
                        )
                    ],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="repair_cancel")],
                ]
            )

            await call.message.edit_text(text, reply_markup=kb)
            await state.set_state(RepairState.entering_hp)
            await state.update_data(
                user_id=user["user_id"],
                msg_id=call.message.message_id,
                chat_id=call.message.chat.id,
            )
            await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "repair_cancel")
async def repair_cancel_callback(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            await _show_cabin_status(db, call.from_user.id, call.message, edit=True)
        await call.answer("Отменено")
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "repair_max")
async def repair_max_callback(call: CallbackQuery, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            cabin = await get_cabin(db, user["user_id"])
            if not cabin:
                await call.answer("❌ Хижина не найдена!", show_alert=True)
                return

            cabin = await apply_cabin_tick(db, user["user_id"])
            max_repair = calc_max_repair(
                cabin["durability"], cabin["max_durability"], user["wood"], user["stone"]
            )

            if max_repair <= 0:
                await call.answer("❌ Недостаточно ресурсов!", show_alert=True)
                await state.clear()
                return

            ok, status, info = await do_repair(db, user["user_id"], user, max_repair)
            if ok:
                text = REPAIR_SUCCESS.format(**info)
                await call.message.edit_text(text)
            else:
                await call.answer("❌ Ошибка починки!", show_alert=True)
        await state.clear()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)
        await state.clear()


@cabin_router.message(RepairState.entering_hp)
async def repair_process_hp(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        data = await state.get_data()
        msg_id = data["msg_id"]
        chat_id = data["chat_id"]

        try:
            hp = int(message.text.strip())
            if hp <= 0:
                raise ValueError
        except ValueError:
            await message.delete()
            async with aiosqlite.connect(DB_PATH) as db:
                user = await get_or_create_user(db, message.from_user.id)
                cabin = await get_cabin(db, user["user_id"])
                if cabin:
                    cabin = await apply_cabin_tick(db, user["user_id"])
                    max_repair = calc_max_repair(
                        cabin["durability"], cabin["max_durability"], user["wood"], user["stone"]
                    )
                else:
                    max_repair = 0
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=REPAIR_INVALID.format(max_repair=max_repair),
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            ok, status, info = await do_repair(db, user["user_id"], user, hp)

            if not ok:
                if status == "no_resources":
                    text = REPAIR_NO_RESOURCES.format(**info)
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="🔧 Починить максимум", callback_data="repair_max"
                                )
                            ],
                            [InlineKeyboardButton(text="❌ Отмена", callback_data="repair_cancel")],
                        ]
                    )
                    await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=kb)
                else:
                    await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=ERROR_GENERAL)
                await message.delete()
                return

            text = REPAIR_SUCCESS.format(**info)
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text)

        await state.clear()
        await message.delete()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)
        await state.clear()


# ── Восстановление за Stars ──
@cabin_router.callback_query(F.data == "restore_cabin")
async def restore_cabin_callback(call: CallbackQuery) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, call.from_user.id)
            cabin = await get_cabin(db, user["user_id"])
            if cabin and cabin["is_built"]:
                await call.answer("❌ У тебя уже есть хижина!", show_alert=True)
                return

        prices = [LabeledPrice(label="Восстановление хижины", amount=RESTORE_STARS_PRICE)]
        await call.message.answer_invoice(
            title="Восстановление хижины",
            description="Восстановить разрушенную хижину до 100% прочности",
            payload=f"restore_cabin:{call.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=prices,
        )
        await call.answer()
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "skip_restore")
async def skip_restore_callback(call: CallbackQuery) -> None:
    try:
        await call.message.delete()
        await call.answer("Хижина потеряна. Чтобы построить новую, нужно 20🪵 и 10🪨.")
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s callback_data=%s",
            _current_handler_name(),
            call.from_user.id if call.from_user else '?',
            call.data,
        )
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query) -> None:
    await pre_checkout_query.answer(ok=True)


@cabin_router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    try:
        payload = message.successful_payment.invoice_payload
        if not payload.startswith("restore_cabin:"):
            return

        telegram_id = int(payload.split(":")[1])
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, telegram_id)
            from database import create_cabin
            await create_cabin(db, user["user_id"])
            await update_cabin_durability(db, user["user_id"], 100.0, datetime.now(timezone.utc))
            await update_cabin_storage(db, user["user_id"], 0, 0)

        await message.answer(RESTORE_SUCCESS, reply_markup=main_menu())
    except Exception:
        # FIXED (Задача 6): не глотаем исключение молча — логируем с контекстом
        logger.exception(
            "HANDLER ERROR: handler=%s telegram_id=%s",
            _current_handler_name(), message.from_user.id if message.from_user else '?',
        )
        await message.answer(ERROR_GENERAL)
