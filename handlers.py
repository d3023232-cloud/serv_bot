"""
Все хендлеры — команды, кнопки, FSM-состояния, клавиатуры.
"""

import random
import logging
from datetime import datetime

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
    BTN_GATHER_WOOD,
    BTN_GATHER_STONE,
    BTN_MARKET,
    CABIN_NOT_BUILT,
    CABIN_STATUS,
    INVENTORY_TEXT,
    GATHER_WOOD_START,
    GATHER_WOOD_HIT,
    GATHER_WOOD_SUCCESS,
    GATHER_WOOD_MISS,
    GATHER_WOOD_COOLDOWN,
    GATHER_WOOD_ALREADY,
    GATHER_STONE_START,
    GATHER_STONE_HIT,
    GATHER_STONE_SUCCESS,
    GATHER_STONE_MISS,
    GATHER_STONE_COOLDOWN,
    GATHER_STONE_ALREADY,
    MARKET_WELCOME,
    MARKET_BUY_HEADER,
    MARKET_SELL_HEADER,
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
    WOOD_COOLDOWN,
    STONE_COOLDOWN,
    WOOD_YIELD,
    STONE_YIELD,
    GAME_HITS_NEEDED,
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

# ── FSM ──
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
        [KeyboardButton(text=BTN_GATHER_WOOD), KeyboardButton(text=BTN_GATHER_STONE)],
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


def _build_game_kb(resource: str, target_idx: int) -> InlineKeyboardMarkup:
    emoji_target = "🪵" if resource == "wood" else "🪨"
    emoji_empty = "🌿" if resource == "wood" else "⬜"
    buttons = []
    for idx in range(9):
        text = emoji_target if idx == target_idx else emoji_empty
        buttons.append(
            InlineKeyboardButton(text=text, callback_data=f"game:{resource}:{idx}")
        )
    keyboard = [buttons[i:i+3] for i in range(0, 9, 3)]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ── Роутеры ──
start_router = Router()
inventory_router = Router()
gathering_router = Router()
cabin_router = Router()
market_router = Router()


# ── /start ──
@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id, message.from_user.username)
            cabin = await get_cabin(db, user["user_id"])
            text = WELCOME_BACK if (cabin and cabin["is_built"]) else WELCOME_NEW
            await message.answer(text, reply_markup=main_menu())
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Инвентарь ──
@inventory_router.message(lambda msg: msg.text == BTN_INVENTORY)
async def show_inventory(message: Message) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            text = INVENTORY_TEXT.format(
                coins=user.get("coins", 0), wood=user["wood"], stone=user["stone"]
            )
            await message.answer(text)
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Мини-игра: Дерево ──
@gathering_router.message(lambda msg: msg.text == BTN_GATHER_WOOD)
async def gather_wood_handler(message: Message, state: FSMContext) -> None:
    try:
        if await state.get_state() == GatherGame.playing:
            await message.answer(GATHER_WOOD_ALREADY)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            now = datetime.now()
            last = user.get("last_wood_gather")
            if last:
                last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
                diff = (now - last_dt).total_seconds()
                if diff < WOOD_COOLDOWN:
                    await message.answer(GATHER_WOOD_COOLDOWN.format(seconds=int(WOOD_COOLDOWN - diff)))
                    return

            target = random.randint(0, 8)
            kb = _build_game_kb("wood", target)
            sent = await message.answer(GATHER_WOOD_START, reply_markup=kb)
            await state.set_state(GatherGame.playing)
            await state.update_data(
                resource="wood", hits=0, target=target,
                msg_id=sent.message_id, chat_id=message.chat.id,
                user_id=user["user_id"], wood=user["wood"], stone=user["stone"],
            )
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Мини-игра: Камень ──
@gathering_router.message(lambda msg: msg.text == BTN_GATHER_STONE)
async def gather_stone_handler(message: Message, state: FSMContext) -> None:
    try:
        if await state.get_state() == GatherGame.playing:
            await message.answer(GATHER_STONE_ALREADY)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            user = await get_or_create_user(db, message.from_user.id)
            now = datetime.now()
            last = user.get("last_stone_gather")
            if last:
                last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
                diff = (now - last_dt).total_seconds()
                if diff < STONE_COOLDOWN:
                    await message.answer(GATHER_STONE_COOLDOWN.format(seconds=int(STONE_COOLDOWN - diff)))
                    return

            target = random.randint(0, 8)
            kb = _build_game_kb("stone", target)
            sent = await message.answer(GATHER_STONE_START, reply_markup=kb)
            await state.set_state(GatherGame.playing)
            await state.update_data(
                resource="stone", hits=0, target=target,
                msg_id=sent.message_id, chat_id=message.chat.id,
                user_id=user["user_id"], wood=user["wood"], stone=user["stone"],
            )
    except Exception:
        await message.answer(ERROR_GENERAL)


# ── Обработка кликов в мини-игре ──
@gathering_router.callback_query(F.data.startswith("game:"))
async def game_callback(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    try:
        if await state.get_state() != GatherGame.playing:
            await call.answer("Игра уже завершена.", show_alert=True)
            return

        data = await state.get_data()
        parts = call.data.split(":")
        if len(parts) != 3:
            return

        resource = parts[1]
        idx = int(parts[2])

        if data.get("resource") != resource:
            await call.answer("Это не твоя текущая игра.", show_alert=True)
            return

        target = data["target"]
        hits = data["hits"]
        msg_id = data["msg_id"]
        chat_id = data["chat_id"]
        user_id = data["user_id"]

        if idx == target:
            hits += 1
            if hits >= GAME_HITS_NEEDED:
                amount = hits * (WOOD_YIELD if resource == "wood" else STONE_YIELD)
                async with aiosqlite.connect(DB_PATH) as db:
                    user = await get_or_create_user(db, call.from_user.id)
                    if resource == "wood":
                        new_wood = user["wood"] + amount
                        await update_user_resources(db, user_id, user["coins"], new_wood, user["stone"])
                        await update_gather_cooldown(db, user_id, "wood", datetime.now())
                        text = GATHER_WOOD_SUCCESS.format(amount=amount)
                    else:
                        new_stone = user["stone"] + amount
                        await update_user_resources(db, user_id, user["coins"], user["wood"], new_stone)
                        await update_gather_cooldown(db, user_id, "stone", datetime.now())
                        text = GATHER_STONE_SUCCESS.format(amount=amount)

                await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=None)
                await state.clear()
            else:
                new_target = random.randint(0, 8)
                kb = _build_game_kb(resource, new_target)
                hit_text = (GATHER_WOOD_HIT if resource == "wood" else GATHER_STONE_HIT).format(hits=hits)
                await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=hit_text, reply_markup=kb)
                await state.update_data(hits=hits, target=new_target)
                await call.answer("✅ Попадание!")
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                if resource == "wood":
                    await update_gather_cooldown(db, user_id, "wood", datetime.now())
                    text = GATHER_WOOD_MISS
                else:
                    await update_gather_cooldown(db, user_id, "stone", datetime.now())
                    text = GATHER_STONE_MISS

            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=None)
            await state.clear()
            await call.answer("❌ Промах!", show_alert=True)
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


# ═══════════════════════════════════════════════════════════════
# РЫНОК
# ═══════════════════════════════════════════════════════════════

@market_router.message(lambda msg: msg.text == BTN_MARKET)
async def market_entry(message: Message) -> None:
    try:
        await message.answer(MARKET_WELCOME, reply_markup=market_menu())
    except Exception:
        await message.answer(ERROR_GENERAL)


@market_router.callback_query(F.data == "market:buy")
async def market_buy(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text(MARKET_BUY_HEADER, reply_markup=buy_menu())
        await call.answer()
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data == "market:sell")
async def market_sell(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text(MARKET_SELL_HEADER, reply_markup=sell_menu())
        await call.answer()
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data == "market:back")
async def market_back(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        await call.message.edit_text(MARKET_WELCOME, reply_markup=market_menu())
        await call.answer()
    except Exception:
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data.startswith("buy:"))
async def buy_select(call: CallbackQuery, state: FSMContext) -> None:
    try:
        resource = call.data.split(":")[1]
        price = PRICE_BUY_WOOD if resource == "wood" else PRICE_BUY_STONE
        emoji = "🪵" if resource == "wood" else "🪨"
        res_name = "дерево" if resource == "wood" else "камень"

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
        await call.answer(ERROR_GENERAL, show_alert=True)


@market_router.callback_query(F.data == "market:cancel")
async def market_cancel(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        await call.message.edit_text(MARKET_WELCOME, reply_markup=market_menu())
        await call.answer("Отменено")
    except Exception:
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
        emoji = "🪵" if resource == "wood" else "🪨"
        res_name = "дерево" if resource == "wood" else "камень"
        res_name_cap = "Дерево" if resource == "wood" else "Камень"

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
                await update_user_resources(db, user["user_id"], new_coins, new_wood, new_stone)

                text = BUY_SUCCESS.format(
                    amount=amount, resource=res_name, total=total,
                    coins_before=coins, coins_after=new_coins, emoji=emoji,
                    resource_cap=res_name_cap,
                    res_before=user["wood"] if resource == "wood" else user["stone"],
                    res_after=new_wood if resource == "wood" else new_stone,
                )
                await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=buy_menu())

            else:
                have = user["wood"] if resource == "wood" else user["stone"]
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
async def my_cabin(message: Message) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await _show_cabin_status(db, message.from_user.id, message)
    except Exception:
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
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "repair_cancel")
async def repair_cancel_callback(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            await _show_cabin_status(db, call.from_user.id, call.message, edit=True)
        await call.answer("Отменено")
    except Exception:
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
        await call.answer(ERROR_GENERAL, show_alert=True)


@cabin_router.callback_query(F.data == "skip_restore")
async def skip_restore_callback(call: CallbackQuery) -> None:
    try:
        await call.message.delete()
        await call.answer("Хижина потеряна. Чтобы построить новую, нужно 20🪵 и 10🪨.")
    except Exception:
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
            await update_cabin_durability(db, user["user_id"], 100.0, datetime.now())
            await update_cabin_storage(db, user["user_id"], 0, 0)

        await message.answer(RESTORE_SUCCESS, reply_markup=main_menu())
    except Exception:
        await message.answer(ERROR_GENERAL)
