"""Хендлеры хижины: статус, постройка, пополнение шкафа."""

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
from database.db import DB_PATH
from database import queries
from services import cabin_service
import i18n

router = Router()


async def _show_cabin_status(
    db: aiosqlite.Connection,
    telegram_id: int,
    message: types.Message,
    edit: bool = False,
) -> None:
    """Внутренняя функция отрисовки статуса хижины (новое сообщение или edit)."""
    user = await queries.get_or_create_user(db, telegram_id)
    cabin = await queries.get_cabin(db, user["user_id"])

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
        text = i18n.CABIN_NOT_BUILT
        if edit:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    cabin = await cabin_service.apply_cabin_tick(db, user["user_id"])

    text = i18n.CABIN_STATUS.format(
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
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(lambda msg: msg.text == "🏠 Моя хижина")
async def my_cabin(message: types.Message) -> None:
    """Показывает текущий статус хижины с учётом реального времени гниения."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await _show_cabin_status(db, message.from_user.id, message)
    except Exception:
        await message.answer(i18n.ERROR_GENERAL)


@router.callback_query(F.data == "build_cabin")
async def build_cabin_callback(call: types.CallbackQuery) -> None:
    """Строит хижину при наличии достаточного количества ресурсов."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(db, call.from_user.id)
            success, status = await cabin_service.build_cabin(
                db, user["user_id"], user
            )

            if success:
                await call.message.edit_text(
                    i18n.CABIN_BUILD_SUCCESS, parse_mode="HTML"
                )
            else:
                await call.answer(
                    i18n.CABIN_BUILD_NO_RESOURCES.format(
                        wood=user["wood"], stone=user["stone"]
                    ),
                    show_alert=True,
                )
    except Exception:
        await call.answer(i18n.ERROR_GENERAL, show_alert=True)


@router.callback_query(F.data == "add_wood_10")
async def add_wood_callback(call: types.CallbackQuery) -> None:
    """Кладёт 10 дерева из инвентаря в шкаф хижины."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(db, call.from_user.id)
            success, status = await cabin_service.add_to_storage(
                db, user["user_id"], 10, 0, user
            )

            if success:
                await call.answer("✅ Дерево добавлено!")
                await _show_cabin_status(
                    db, call.from_user.id, call.message, edit=True
                )
            else:
                await call.answer(
                    "❌ Недостаточно дерева или нет хижины!", show_alert=True
                )
    except Exception:
        await call.answer(i18n.ERROR_GENERAL, show_alert=True)


@router.callback_query(F.data == "add_stone_10")
async def add_stone_callback(call: types.CallbackQuery) -> None:
    """Кладёт 10 камня из инвентаря в шкаф хижины."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(db, call.from_user.id)
            success, status = await cabin_service.add_to_storage(
                db, user["user_id"], 0, 10, user
            )

            if success:
                await call.answer("✅ Камень добавлен!")
                await _show_cabin_status(
                    db, call.from_user.id, call.message, edit=True
                )
            else:
                await call.answer(
                    "❌ Недостаточно камня или нет хижины!", show_alert=True
                )
    except Exception:
        await call.answer(i18n.ERROR_GENERAL, show_alert=True)


@router.callback_query(F.data == "repair_cabin")
async def repair_cabin_callback(call: types.CallbackQuery) -> None:
    """Заглушка для починки хижины (будет реализовано в следующем этапе)."""
    await call.answer(
        "🔧 Починка будет доступна в следующем обновлении!", show_alert=True
    )
