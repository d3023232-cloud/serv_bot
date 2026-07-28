"""Хендлер команды /start и регистрации пользователя."""

from aiogram import Router, types
from aiogram.filters import CommandStart
import aiosqlite
from database.db import DB_PATH
from database import queries
from keyboards.main import main_menu
import i18n

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    """Обрабатывает /start: регистрирует нового игрока или приветствует старого."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(
                db, message.from_user.id, message.from_user.username
            )
            cabin = await queries.get_cabin(db, user["user_id"])

            if cabin and cabin["is_built"]:
                text = i18n.WELCOME_BACK
            else:
                text = i18n.WELCOME_NEW

            await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")
    except Exception as exc:
        await message.answer(i18n.ERROR_GENERAL)
        raise
