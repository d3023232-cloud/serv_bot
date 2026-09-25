# -*- coding: utf-8 -*-
"""
Мини-игра добычи ресурсов (камень / дерево / песок) на aiogram 3.x.

Механика:
  - старт: команда /mine или кнопка "⛏ Добыча" -> выбор ресурса;
  - поле 3x3, на одной случайной клетке — настоящий ресурс, остальные 8 — обманки;
  - попал по настоящему: +1 к счётчику, поле перегенерируется;
  - попал по обманке: ход заканчивается, игрок оставляет добытое;
  - отдельная кнопка "🏃 Забрать и уйти" под полем;
  - лимиты за ходку: песок 100 / дерево 20 / камень 10 (авто-завершение).

Состояние игры хранится в FSM (MemoryStorage): тип ресурса, счётчик,
лимит и индекс настоящей клетки (0..8).

Заглушка БД — dict USERS + print(); реальное сохранение помечено # TODO: save to DB.
"""

import random
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

BOT_TOKEN = "PUT_YOUR_TOKEN_HERE"  # TODO: заменить на реальный токен / os.environ["BOT_TOKEN"]


# ---------------------------------------------------------------------------
# Конфигурация ресурсов
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceCfg:
    name: str          # название для текстов
    real_emoji: str    # эмодзи настоящего ресурса
    fake_emoji: str    # эмодзи обманок (сливаются по цвету)
    limit: int         # максимум добычи за одну ходку


RESOURCES: dict[str, ResourceCfg] = {
    "stone": ResourceCfg(name="Камень", real_emoji="🪨", fake_emoji="🌑", limit=10),
    "wood":  ResourceCfg(name="Дерево", real_emoji="🪵", fake_emoji="🟫", limit=20),
    "sand":  ResourceCfg(name="Песок",  real_emoji="🏖️", fake_emoji="🟨", limit=100),
}

BTN_MINE = "⛏ Добыча"

# Заглушка хранилища игроков (вместо SQLite/Redis).
USERS: dict[int, dict[str, int]] = {}  # user_id -> {"stone": n, "wood": n, "sand": n}


def get_user(user_id: int) -> dict[str, int]:
    return USERS.setdefault(user_id, {"stone": 0, "wood": 0, "sand": 0})


def add_resource(user_id: int, rtype: str, amount: int) -> None:
    get_user(user_id)[rtype] += amount
    # TODO: save to DB — здесь UPDATE users SET <rtype> = <rtype> + ? WHERE user_id = ?
    print(f"[DB] user {user_id}: +{amount} {rtype} (всего {get_user(user_id)[rtype]})")


# ---------------------------------------------------------------------------
# FSM-состояния
# ---------------------------------------------------------------------------

class Mining(StatesGroup):
    choosing = State()  # выбран тип ресурса
    playing = State()   # идёт игра на поле 3x3


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------

def main_menu() -> ReplyKeyboardMarkup:
    """Главная клавиатура со стартовой кнопкой добычи."""
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/start"), KeyboardButton(text=BTN_MINE)],
        ],
        resize_keyboard=True,
    )
    return kb


def resource_menu() -> InlineKeyboardMarkup:
    """Выбор ресурса: mine:<type>."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🪨 Камень (до {RESOURCES['stone'].limit})",
                              callback_data="mine:stone")],
        [InlineKeyboardButton(text=f"🪵 Дерево (до {RESOURCES['wood'].limit})",
                              callback_data="mine:wood")],
        [InlineKeyboardButton(text=f"🏖️ Песок (до {RESOURCES['sand'].limit})",
                              callback_data="mine:sand")],
    ])
    return kb


def game_kb(rtype: str) -> InlineKeyboardMarkup:
    """Поле 3x3 + кнопка 'Забрать и уйти'. Индекс настоящей клетки берётся из FSM."""
    cfg = RESOURCES[rtype]
    # Кнопки одинаковой ширины: все клетки — один эмодзи.
    rows = []
    for row in range(3):
        kb_row = []
        for col in range(3):
            idx = row * 3 + col
            kb_row.append(
                InlineKeyboardButton(
                    text=cfg.fake_emoji,  # текст не подсказывает, где настоящий ресурс
                    callback_data=f"mine:{rtype}:{idx}",
                )
            )
        rows.append(kb_row)
    rows.append([InlineKeyboardButton(text="🏃 Забрать и уйти", callback_data="mine:cashout")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Роутер с хендлерами
# ---------------------------------------------------------------------------

router = Router()


def game_text(rtype: str, mined: int) -> str:
    """Текст игрового сообщения (счётчик добытого)."""
    cfg = RESOURCES[rtype]
    return (
        f"{cfg.real_emoji} <b>Добыча: {cfg.name}</b>\n\n"
        f"На поле спрятан настоящий ресурс — остальные клетки обманки.\n"
        f"Жми на нужную: попал — добыча +1 и новое поле;\n"
        f"промах — ход заканчивается, добытое остаётся у тебя.\n\n"
        f"Лимит за ходку: <b>{cfg.limit}</b>\n"
        f"Уже добыто: <b>{mined}</b>"
    )


async def start_game(state: FSMContext, call: CallbackQuery, rtype: str) -> None:
    """Инициализация новой партии: рандомная клетка + сброс счётчика."""
    target = random.randint(0, 8)
    await state.set_state(Mining.playing)
    await state.set_data({
        "rtype": rtype,
        "mined": 0,
        "target": target,
        "limit": RESOURCES[rtype].limit,
    })
    await call.message.edit_text(game_text(rtype, 0), reply_markup=game_kb(rtype))


async def finish_game(state: FSMContext, call: CallbackQuery, reason: str) -> None:
    """Начисление добытого и выход из состояния."""
    data = await state.get_data()
    await state.clear()
    rtype = data.get("rtype")
    mined = int(data.get("mined", 0))
    if not rtype:
        return
    cfg = RESOURCES[rtype]
    if mined > 0:
        add_resource(call.from_user.id, rtype, mined)
        result = (
            f"{reason}\n\n"
            f"Вы добыли <b>{mined}</b> [{cfg.name.lower()}]. "
            f"Они зачислены на ваш счет."
        )
    else:
        result = f"{reason}\n\nВы не добыли ни одного ресурса. На счету пусто."
    try:
        await call.message.edit_text(result)
    except Exception:
        await call.message.answer(result)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "⛏ Игра «Добыча».\nНажмите «Добыча» или команду /mine, чтобы начать.",
        reply_markup=main_menu(),
    )


@router.message(Command("mine"))
@router.message(F.text == BTN_MINE)
async def choose_resource(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Mining.choosing)
    await message.answer("Выберите, что будем добывать:", reply_markup=resource_menu())


@router.callback_query(Mining.choosing, F.data.startswith("mine:"))
async def on_resource_chosen(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")  # mine:<type>
    if len(parts) != 2 or parts[1] not in RESOURCES:
        await call.answer("Неизвестный ресурс.", show_alert=True)
        return
    await start_game(state, call, parts[1])
    await call.answer()


@router.callback_query(Mining.playing, F.data == "mine:cashout")
async def on_cashout(call: CallbackQuery, state: FSMContext) -> None:
    await finish_game(state, call, "🏃 Ты решил забрать добычу и уйти.")
    await call.answer()


@router.callback_query(Mining.playing, F.data.startswith("mine:"))
async def on_cell_click(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":")  # mine:<type>:<cell>
    data = await state.get_data()
    rtype = data.get("rtype")

    # Защита от старых callback_data (кнопки из прошлой партии/другого ресурса):
    # парсим заново и сверяем с текущим состоянием.
    if (
        len(parts) != 3
        or parts[1] not in RESOURCES
        or not parts[2].isdigit()
        or parts[1] != rtype
    ):
        await call.answer("Игра началась заново 🔄", show_alert=True)
        return

    cell = int(parts[2])
    cfg = RESOURCES[rtype]
    mined = int(data.get("mined", 0))

    if cell == data.get("target"):
        # Попал по настоящему ресурсу: +1, перегенерация поля.
        mined += 1
        if mined >= cfg.limit:
            # Лимит за ходку достигнут — авто-завершение.
            await state.update_data(mined=mined)
            await finish_game(
                state, call,
                f"🎯 Лимит исчерпан! Максимум за ходку: {cfg.limit} {cfg.name.lower()}.",
            )
        else:
            new_target = random.randint(0, 8)
            await state.update_data(mined=mined, target=new_target)
            # Перегенерация поля: новая клавиатура + обновлённый счётчик.
            await call.message.edit_text(
                game_text(rtype, mined), reply_markup=game_kb(rtype)
            )
            await call.answer(f"+1 {cfg.name.lower()}! {cfg.real_emoji}")
    else:
        # Промах по обманке: ход заканчивается, добытое остаётся.
        await finish_game(state, call, "💥 Ты накопал на обманку — добыча прекращена.")
        await call.answer("Мимо!", show_alert=True)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
