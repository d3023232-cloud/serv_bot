"""Хендлеры добычи дерева и камня."""

from aiogram import Router, types
import aiosqlite
from database.db import DB_PATH
from database import queries
from services import resource_service
import i18n

router = Router()


@router.message(lambda msg: msg.text == "🪵 Добыть дерево")
async def gather_wood_handler(message: types.Message) -> None:
    """Обрабатывает нажатие кнопки добычи дерева с учётом кулдауна."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(db, message.from_user.id)
            success, result = await resource_service.gather_wood(
                db, user["user_id"], user
            )

            if success:
                await message.answer(i18n.GATHER_WOOD_SUCCESS)
            else:
                await message.answer(
                    i18n.GATHER_WOOD_COOLDOWN.format(seconds=result)
                )
    except Exception:
        await message.answer(i18n.ERROR_GENERAL)


@router.message(lambda msg: msg.text == "🪨 Добыть камень")
async def gather_stone_handler(message: types.Message) -> None:
    """Обрабатывает нажатие кнопки добычи камня с учётом кулдауна."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            user = await queries.get_or_create_user(db, message.from_user.id)
            success, result = await resource_service.gather_stone(
                db, user["user_id"], user
            )

            if success:
                await message.answer(i18n.GATHER_STONE_SUCCESS)
            else:
                await message.answer(
                    i18n.GATHER_STONE_COOLDOWN.format(seconds=result)
                )
    except Exception:
        await message.answer(i18n.ERROR_GENERAL)
