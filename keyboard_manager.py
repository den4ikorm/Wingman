"""
bot/keyboard_manager.py
════════════════════════════════════════════════════════
Гибридная система кнопок Wingman:

  Нижняя панель (Reply) — адаптивная по времени суток
  Субменю (Inline)       — появляется после нажатия на раздел
  Контекст               — inline под каждым ответом бота

Подключение:
  from bot.keyboard_manager import get_main_kb, get_submenu_kb, nav_router
  dp.include_router(nav_router)   # ПЕРЕД common.router
  reply_markup=get_main_kb(user_id)
════════════════════════════════════════════════════════
"""

from datetime import datetime
import logging

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from core.database import MemoryManager

logger = logging.getLogger(__name__)
nav_router = Router()


# ══════════════════════════════════════════════════════
#  АДАПТИВНЫЕ МЕТКИ (по времени + состоянию профиля)
# ══════════════════════════════════════════════════════

def _hour() -> int:
    return datetime.now().hour


def _weight_alert(user_id: int) -> bool:
    """True если вес не вносился 2+ дня."""
    try:
        db = MemoryManager(user_id)
        weights = db.get_weight_history(limit=1)
        if not weights:
            return True
        from datetime import date
        last = weights[0]
        # last — строка даты или объект date
        if isinstance(last, str):
            last_date = date.fromisoformat(last[:10])
        else:
            last_date = last
        return (date.today() - last_date).days >= 2
    except Exception:
        return False


def _label_today(user_id: int) -> str:
    h = _hour()
    if 5 <= h < 12:
        return "☀️ Доброе утро"
    if 12 <= h < 17:
        return "🌤 День"
    if 17 <= h < 22:
        return "🌙 Добрый вечер"
    return "🌙 Ночь"


def _label_weight(user_id: int) -> str:
    if _weight_alert(user_id):
        return "⚖️ Вес (!)"
    return "⚖️ Вес"


# ══════════════════════════════════════════════════════
#  НИЖНЯЯ ПАНЕЛЬ — Reply-клавиатура
# ══════════════════════════════════════════════════════

def get_main_kb(user_id: int = 0) -> ReplyKeyboardMarkup:
    """
    2 строки × 3 кнопки.
    Верхняя строка меняется по времени суток.
    """
    h = _hour()

    # Первая строка — контекстная
    if 5 <= h < 12:
        row1 = [
            KeyboardButton(text="☀️ Сегодня"),
            KeyboardButton(text="🍽 Питание"),
            KeyboardButton(text=_label_weight(user_id)),
        ]
    elif 17 <= h < 23:
        row1 = [
            KeyboardButton(text="🌙 Вечер"),
            KeyboardButton(text="🍽 Питание"),
            KeyboardButton(text="💪 Прогресс"),
        ]
    else:
        row1 = [
            KeyboardButton(text="🍽 Питание"),
            KeyboardButton(text="💪 Прогресс"),
            KeyboardButton(text=_label_weight(user_id)),
        ]

    # Вторая строка — постоянная
    row2 = [
        KeyboardButton(text="💡 Идея"),
        KeyboardButton(text="🛒 Покупки"),
        KeyboardButton(text="⚙️ Ещё"),
    ]

    builder = ReplyKeyboardBuilder()
    builder.row(*row1)
    builder.row(*row2)
    return builder.as_markup(resize_keyboard=True, persistent=True)


# ══════════════════════════════════════════════════════
#  СУБМЕНЮ — Inline-клавиатуры для каждого раздела
# ══════════════════════════════════════════════════════

def _kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Строит InlineKeyboard из списка (текст, callback_data)."""
    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.row(*[
            InlineKeyboardButton(text=t, callback_data=c)
            for t, c in row
        ])
    return builder.as_markup()


SUBMENUS: dict[str, tuple[str, InlineKeyboardMarkup]] = {

    "🍽 Питание": (
        "🍽 *Питание*\nЧто сделать?",
        _kb(
            [("🥗 Диета на неделю", "nav_diet"), ("🍳 Рецепты", "nav_recipes")],
            [("🛒 Список покупок", "nav_shopping"), ("🧊 Из холодильника", "nav_fridge")],
            [("🎯 Мой режим", "nav_mode")],
        )
    ),

    "💪 Прогресс": (
        "💪 *Прогресс*\nЧто смотрим?",
        _kb(
            [("⚖️ Внести вес", "nav_weight"), ("📊 График", "nav_progress")],
            [("🔥 Стрик", "nav_streak"), ("📋 Профиль", "nav_profile")],
        )
    ),

    "☀️ Сегодня": (
        "☀️ *Сегодня*\nЧто делаем?",
        _kb(
            [("😴 Настроение", "nav_morning"), ("📋 План дня", "nav_plan")],
            [("🎯 Режим питания", "nav_mode"), ("📅 Событие дня", "nav_event")],
        )
    ),

    "🌙 Вечер": (
        "🌙 *Вечер*\nЧем займёмся?",
        _kb(
            [("✅ Итоги дня", "nav_evening"), ("🎬 Кино / Музыка", "nav_recs")],
            [("📖 Итоги недели", "nav_weekly")],
        )
    ),

    # Алиасы для дневного варианта
    "🌤 День": (
        "🌤 *День*\nЧто делаем?",
        _kb(
            [("☀️ Настроение", "nav_morning"), ("📋 План дня", "nav_plan")],
            [("🍽 Питание", "nav_food_sub"), ("💪 Прогресс", "nav_progress_sub")],
        )
    ),

    "🌙 Ночь": (
        "🌙 *Ночь*",
        _kb(
            [("✅ Итоги дня", "nav_evening"), ("🎬 Что посмотреть", "nav_recs")],
        )
    ),

    "⚙️ Ещё": (
        "⚙️ *Дополнительно*",
        _kb(
            [("🛫 Путешествие", "nav_travel"), ("💊 Здоровье", "nav_healer")],
            [("🔔 Психотип", "nav_psychotype"), ("💬 Обратная связь", "nav_feedback")],
            [("📝 Новая анкета", "nav_survey")],
        )
    ),
}


# ══════════════════════════════════════════════════════
#  КОНТЕКСТНЫЕ INLINE-КНОПКИ под ответами бота
# ══════════════════════════════════════════════════════

def after_diet_kb() -> InlineKeyboardMarkup:
    return _kb(
        [("🍳 Рецепты", "nav_recipes"), ("🛒 Покупки", "nav_shopping")],
        [("🎯 Сменить режим", "nav_mode")],
    )


def after_recipes_kb() -> InlineKeyboardMarkup:
    return _kb(
        [("🛒 Список покупок", "nav_shopping"), ("🧊 Из холодильника", "nav_fridge")],
    )


def after_morning_kb() -> InlineKeyboardMarkup:
    return _kb(
        [("📋 Показать план", "nav_plan"), ("🥗 Диета", "nav_diet")],
    )


def after_evening_kb() -> InlineKeyboardMarkup:
    return _kb(
        [("🎬 Рекомендация", "nav_recs"), ("📖 Итоги недели", "nav_weekly")],
    )


def after_weight_kb() -> InlineKeyboardMarkup:
    return _kb(
        [("📊 График", "nav_progress"), ("🔥 Стрик", "nav_streak")],
    )


# ══════════════════════════════════════════════════════
#  РОУТЕР — обработка нажатий Reply-кнопок
# ══════════════════════════════════════════════════════

NAV_TEXTS = set(SUBMENUS.keys()) | {
    "⚖️ Вес (!)", "⚖️ Вес",
    "☀️ Доброе утро", "🌤 День", "🌙 Добрый вечер", "🌙 Ночь",
}


@nav_router.message(
    F.text.in_(NAV_TEXTS),
    StateFilter(default_state)
)
async def handle_nav(message: types.Message):
    text = message.text

    # Алиасы → нормализуем
    # Кнопка "Вес" — сразу показываем субменю прогресса с инструкцией
    if text in ("⚖️ Вес (!)", "⚖️ Вес"):
        caption, kb = SUBMENUS["💪 Прогресс"]
        alert = ""
        if text == "⚖️ Вес (!)":
            alert = "⚠️ _Вес не вносился 2+ дня_\n\n"
        await message.answer(
            alert + caption,
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    aliases = {
        "☀️ Доброе утро": "☀️ Сегодня",
        "🌙 Добрый вечер": "🌙 Вечер",
    }
    key = aliases.get(text, text)

    if key in SUBMENUS:
        caption, kb = SUBMENUS[key]
        await message.answer(caption, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer("Выбери раздел 👇")


# ── Inline-колбэки субменю ────────────────────────────

@nav_router.callback_query(F.data.startswith("nav_"), StateFilter(default_state))
async def handle_nav_cb(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id
    action = cb.data  # nav_diet, nav_recipes, etc.

    # Маппинг action → команда/логика
    routes = {
        "nav_diet":       "/plan",
        "nav_recipes":    "/recipes",
        "nav_shopping":   "/shopping",
        "nav_fridge":     "/fridge",
        "nav_mode":       "/mode",
        "nav_weight":     "/weight",
        "nav_progress":   "/progress",
        "nav_streak":     "/streak",
        "nav_profile":    "/profile",
        "nav_morning":    "/morning",
        "nav_plan":       "/plan",
        "nav_event":      "/event",
        "nav_evening":    "evening",
        "nav_recs":       "evening",
        "nav_weekly":     "/weekly",
        "nav_travel":     "/travel",
        "nav_healer":     "/healer",
        "nav_psychotype": "/psychotype",
        "nav_feedback":   "/feedback",
        "nav_survey":     "анкета",
        "nav_food_sub":   "🍽 Питание",
        "nav_progress_sub": "💪 Прогресс",
    }

    cmd = routes.get(action)
    if not cmd:
        return

    # Специальные обработчики — выполняем сразу
    if action == "nav_weight":
        await cb.message.answer(
            "⚖️ *Внести вес*\n\nНапиши число — например:\n`/weight 78.5`",
            parse_mode="Markdown",
            reply_markup=after_weight_kb()
        )
        return

    if action == "nav_profile":
        from bot.handlers.common import cmd_profile
        await cmd_profile(cb.message)
        return

    if action == "nav_streak":
        from bot.handlers.common import cmd_streak
        await cmd_streak(cb.message)
        return

    if action == "nav_survey":
        from bot.handlers.survey import cmd_start_survey
        # Эмулируем Message с нужным user
        await cb.message.answer("Начинаю новую анкету — напиши /start")
        return

    if cmd.startswith("/") or cmd == "анкета":
        # Отправляем команду как текст чтобы роутер её подхватил
        fake = cb.message.model_copy(update={"text": cmd})
        try:
            from aiogram import Bot
            await cb.bot.send_message(cb.from_user.id, cmd)
        except Exception:
            await cb.message.answer(f"Напиши `{cmd}`", parse_mode="Markdown")
        return

    if cmd in ("🍽 Питание", "💪 Прогресс"):
        # Показываем вложенное субменю
        caption, kb = SUBMENUS[cmd]
        await cb.message.answer(caption, parse_mode="Markdown", reply_markup=kb)
    elif cmd == "evening":
        # Запускаем вечерний модуль
        from bot.handlers.evening_handler import send_evening_inline
        try:
            await send_evening_inline(cb.message, user_id)
        except Exception:
            await cb.message.answer("🌙 Вечерний режим — напиши `/evening`", parse_mode="Markdown")
