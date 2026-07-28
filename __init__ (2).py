"""Хендлер просмотра инвентаря."""

from aiogram import Router, types
import aiosqlite
from database.db import DB_PATH
from database import queries
import i18n

router = Router()


@router.message(lambda msg: msg.text == "🎒 Инвентарь")
async def show_inventory(message: types.Message) -> None:
    """Показывает текущее количество дерева и камня в инвентаре."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(db, message.from_user.id)
            text = i18n.INVENTORY_TEXT.format(wood=user["wood"], stone=user["stone"])
            await message.answer(text, parse_mode="HTML")
    except Exception:
        await message.answer(i18n.ERROR_GENERAL)
