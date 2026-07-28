"""Главное меню бота (ReplyKeyboardMarkup)."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu() -> ReplyKeyboardMarkup:
    """Возвращает главную клавиатуру с основными действиями."""
    kb = [
        [
            KeyboardButton(text="🏠 Моя хижина"),
            KeyboardButton(text="🎒 Инвентарь"),
        ],
        [
            KeyboardButton(text="🪵 Добыть дерево"),
            KeyboardButton(text="🪨 Добыть камень"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
