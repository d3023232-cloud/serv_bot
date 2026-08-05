"""
Конфигурация бота — все цены, кулдауны, тексты, константы.
Меняй здесь всё что нужно без риска сломать логику.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Токен и БД ──
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATA_DIR: str = os.getenv("DATA_DIR", "")
DB_PATH: str = os.getenv("DB_PATH", "")

if DATA_DIR:
    import pathlib
    pathlib.Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    DB_PATH = os.path.join(DATA_DIR, "survival_bot.db")
elif not DB_PATH:
    DB_PATH = "survival_bot.db"

# ── Рынок: цены ──
PRICE_BUY_WOOD = 5  # дерево
PRICE_SELL_WOOD = 3
PRICE_BUY_STONE = 10  # камень
PRICE_SELL_STONE = 6

# ── Добыча ──
WOOD_COOLDOWN = 30
STONE_COOLDOWN = 60
WOOD_YIELD = 2
STONE_YIELD = 1
GAME_HITS_NEEDED = 3

# ── Хижина: тики и гниение ──
TICK_MINUTES = 30
CONSUMPTION_PER_TICK_WOOD = 1
CONSUMPTION_PER_TICK_STONE = 1
DECAY_FAST_PER_TICK = 12.0   # гниение без ресурсов (% за тик)

# ── Починка ──
REPAIR_WOOD_PER_HP = 6
REPAIR_STONE_PER_HP = 3

# ── Восстановление за Stars ──
RESTORE_STARS_PRICE = 14

# ── Уведомления ──
CHECK_INTERVAL = 600           # сек между проверками фонового цикла
NOTIFY_EMPTY_COOLDOWN = 1800   # 30 мин между повторными уведомлениями "нет ресурсов"
THRESHOLD_FIFTY = 0.50

# ── Тексты ──
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
BTN_MARKET = "🛒 Рынок"

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
    "🦠 Гниение: 12%/30 мин при отсутствии ресурсов"
)

INVENTORY_TEXT = (
    "🎒 <b>Инвентарь</b>\n\n"
    "💰 Монеты: <b>{coins}</b>\n"
    "🪵 Дерево: <b>{wood}</b>\n"
    "🪨 Камень: <b>{stone}</b>"
)

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

MARKET_WELCOME = (
    "🛒 <b>Рынок</b>\n\n"
    "Здесь можно торговать ресурсами.\n"
    "Выбери, что хочешь сделать:"
)
MARKET_BUY_HEADER = "🛒 <b>Режим: ПОКУПКА</b>\n\nВыбери товар:"
MARKET_SELL_HEADER = "💰 <b>Режим: ПРОДАЖА</b>\n\nВыбери товар:"

BUY_WOOD_TEXT = "🪵 Купить дерево — 5💰"
BUY_STONE_TEXT = "🪨 Купить камень — 10💰"
SELL_WOOD_TEXT = "🪵 Продать дерево — 3💰"
SELL_STONE_TEXT = "🪨 Продать камень — 6💰"

MARKET_ENTER_AMOUNT = (
    "{mode_emoji} <b>Режим: {mode}</b>\n\n"
    "{emoji} {resource} — <b>{price}💰</b> за шт\n\n"
    "Введи количество, которое хочешь {action}:"
)
MARKET_INVALID_AMOUNT = (
    "❌ <b>Некорректное количество!</b>\n\n"
    "Введи целое число больше 0."
)
MARKET_CANCELLED = "❌ Операция отменена."

BUY_SUCCESS = (
    "✅ <b>Покупка совершена!</b>\n\n"
    "Ты купил <b>{amount} {resource}</b> за <b>{total}💰</b>.\n"
    "💰 Монеты: {coins_before} → {coins_after}\n"
    "{emoji} {resource_cap}: {res_before} → {res_after}"
)
BUY_NO_MONEY = (
    "❌ <b>Недостаточно монет!</b>\n\n"
    "Нужно: <b>{total}💰</b>\n"
    "У тебя: <b>{coins}💰</b>"
)

SELL_SUCCESS = (
    "✅ <b>Продажа совершена!</b>\n\n"
    "Ты продал <b>{amount} {resource}</b> за <b>{total}💰</b>.\n"
    "💰 Монеты: {coins_before} → {coins_after}\n"
    "{emoji} {resource_cap}: {res_before} → {res_after}"
)
SELL_NO_RESOURCES = (
    "❌ <b>Недостаточно ресурсов!</b>\n\n"
    "Нужно: <b>{amount} {resource}</b>\n"
    "У тебя: <b>{have} {resource}</b>"
)

CABIN_BUILD_SUCCESS = (
    "🏠 <b>Хижина построена!</b>\n\n"
    "Теперь у тебя есть надёжное убежище. Не забудь пополнять шкаф "
    "ресурсами, иначе она начнёт разрушаться!"
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

NOTIFY_EMPTY_RESOURCES = (
    "🚨 <b>КРИТИЧЕСКИЙ УРОВЕНЬ!</b>\n\n"
    "🪵 Дерево: {wood} / {max_wood}\n"
    "🪨 Камень: {stone} / {max_stone}\n\n"
    "Хижина гниёт! Каждые 30 мин −12% прочности. Пополни шкаф срочно!"
)

NOTIFY_CABIN_DESTROYED = (
    "💀 <b>Хижина разрушена!</b>\n\n"
    "Твоё убежище превратилось в руины. Всё, что было в шкафу, потеряно.\n\n"
    "Хочешь восстановить хижину за <b>{price}⭐</b>?"
)

REPAIR_ENTER_HP = (
    "🔧 <b>Починка хижины</b>\n\n"
    "Стоимость: <b>10🪵 + 5🪨 за 1 HP</b>\n"
    "Текущая прочность: <b>{durability}%</b> / {max}%\n"
    "У тебя: {wood}🪵, {stone}🪨\n\n"
    "Введи, сколько HP восстановить (макс {max_repair}):"
)

REPAIR_INVALID = (
    "❌ <b>Некорректное значение!</b>\n\n"
    "Введи целое число от 1 до {max_repair}."
)

REPAIR_NO_RESOURCES = (
    "❌ <b>Недостаточно ресурсов!</b>\n\n"
    "Нужно: <b>{need_wood}🪵 и {need_stone}🪨</b>\n"
    "У тебя: {wood}🪵 и {stone}🪨\n"
    "Не хватает: {lack_wood}🪵 и {lack_stone}🪨"
)

REPAIR_SUCCESS = (
    "✅ <b>Починка завершена!</b>\n\n"
    "Восстановлено: <b>{hp} HP</b>\n"
    "Затрачено: {wood}🪵 и {stone}🪨\n"
    "Прочность: {before}% → {after}%"
)

RESTORE_SUCCESS = (
    "🏠 <b>Хижина восстановлена!</b>\n\n"
    "Прочность: <b>100%</b>\n"
    "Шкаф пуст. Не забудь пополнить ресурсы!"
)

ERROR_GENERAL = "❌ Произошла ошибка. Попробуй позже."
