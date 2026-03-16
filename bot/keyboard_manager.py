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

    # Вторая строка — постоянная (v4: добавлены Кино и Финансы)
    row2 = [
        KeyboardButton(text="💡 Идея"),
        KeyboardButton(text="🛒 Покупки"),
        KeyboardButton(text="⚙️ Ещё"),
    ]
    row3 = [
        KeyboardButton(text="🎬 Кино"),
        KeyboardButton(text="💰 Финансы"),
        KeyboardButton(text="🎯 LifeMode"),
    ]

    builder = ReplyKeyboardBuilder()
    builder.row(*row1)
    builder.row(*row2)
    builder.row(*row3)
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
    "🎬 Кино", "💰 Финансы", "🎯 LifeMode",
}


@nav_router.message(
    F.text.in_(NAV_TEXTS),
    StateFilter(default_state)
)
async def handle_nav(message: types.Message):
    text = message.text

    # Кнопка "Вес"
    if text in ("⚖️ Вес (!)", "⚖️ Вес"):
        caption, kb = SUBMENUS["💪 Прогресс"]
        alert = ""
        if text == "⚖️ Вес (!)":
            alert = "⚠️ _Вес не вносился 2+ дня_\n\n"
        await message.answer(alert + caption, parse_mode="Markdown", reply_markup=kb)
        return

    # Новые кнопки нижней панели v4 — перенаправляем в нужные handlers
    if text == "🎬 Кино":
        from bot.handlers.content_handler import cmd_movie
        from aiogram.fsm.context import FSMContext
        # Создаём dummy state через dp storage
        await message.answer("🎬 Кино", parse_mode="Markdown")
        try:
            from bot.handlers.content_handler import cmd_movie as _cm
            # Эмулируем команду через send_message
            await message.bot.send_message(message.from_user.id, "/movie")
        except Exception:
            await message.answer("Напиши /movie для рекомендаций кино 🎬")
        return

    if text == "💰 Финансы":
        try:
            await message.bot.send_message(message.from_user.id, "/finance")
        except Exception:
            await message.answer("Напиши /finance для финансов 💰")
        return

    if text == "🎯 LifeMode":
        try:
            await message.bot.send_message(message.from_user.id, "/lifemode")
        except Exception:
            await message.answer("Напиши /lifemode для выбора режима 🎯")
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
    user_id = cb.from_user.id   # FIX B2a: всегда берём из callback, не из cb.message
    action = cb.data

    # Специальные обработчики — прямые вызовы без send_message (FIX B2b)

    if action == "nav_weight":
        await cb.message.answer(
            "⚖️ *Внести вес*\n\nНапиши число — например:\n`/weight 78.5`",
            parse_mode="Markdown",
            reply_markup=after_weight_kb()
        )
        return

    if action == "nav_profile":
        # FIX B2a: передаём user_id явно, не cb.message (from_user у него — бот)
        from bot.handlers.common import _profile_for_user
        await _profile_for_user(user_id, cb.message)
        return

    if action == "nav_streak":
        from bot.handlers.common import _streak_for_user
        await _streak_for_user(user_id, cb.message)
        return

    if action == "nav_travel":
        # FIX B2b: прямой вызов handler, а не send_message('/travel')
        from bot.handlers.travel_handler import cmd_travel
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.base import StorageKey
        state: FSMContext = FSMContext(
            storage=cb.bot.fsm_storage if hasattr(cb.bot, "fsm_storage") else None,
            key=StorageKey(bot_id=cb.bot.id, chat_id=cb.message.chat.id, user_id=user_id)
        )
        try:
            await cmd_travel(cb.message, state)
        except Exception as e:
            logger.warning(f"nav_travel direct call failed ({e}), fallback")
            await cb.message.answer("✈️ Планировщик путешествий — напиши /travel")
        return

    if action == "nav_survey":
        # FIX B-survey: прямой запуск анкеты
        from bot.handlers.survey import start_survey
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.base import StorageKey
        state: FSMContext = FSMContext(
            storage=cb.bot.fsm_storage if hasattr(cb.bot, "fsm_storage") else None,
            key=StorageKey(bot_id=cb.bot.id, chat_id=cb.message.chat.id, user_id=user_id)
        )
        try:
            await start_survey(cb.message, state)
        except Exception:
            await cb.message.answer("📝 Новая анкета — напиши *анкета*", parse_mode="Markdown")
        return

    if action == "nav_diet":
        # FIX B4: отдельный маршрут для недельного меню (не дублирует nav_plan)
        from bot.handlers.common import cmd_diet_week
        await cmd_diet_week(cb.message, user_id)
        return

    if action in ("nav_food_sub", "nav_progress_sub"):
        key = "🍽 Питание" if action == "nav_food_sub" else "💪 Прогресс"
        caption, kb = SUBMENUS[key]
        await cb.message.answer(caption, parse_mode="Markdown", reply_markup=kb)
        return

    if action == "nav_evening" or action == "nav_recs":
        from bot.handlers.evening_handler import send_evening_inline
        try:
            await send_evening_inline(cb.message, user_id)
        except Exception:
            await cb.message.answer("🌙 Вечерний режим — напиши `/evening`", parse_mode="Markdown")
        return

    # Команды, которые можно вызвать через send_message (нет FSM, нет user_id проблемы)
    text_routes = {
        "nav_recipes":    "/recipes",
        "nav_shopping":   "/shopping",
        "nav_fridge":     "/fridge",
        "nav_mode":       "/mode",
        "nav_progress":   "/progress",
        "nav_morning":    "/morning",
        "nav_plan":       "/plan",
        "nav_event":      "/event",
        "nav_weekly":     "/weekly",
        "nav_healer":     "/healer",
        "nav_psychotype": "/psychotype",
        "nav_feedback":   "/feedback",
    }
    cmd = text_routes.get(action)
    if cmd:
        try:
            await cb.bot.send_message(user_id, cmd)
        except Exception:
            await cb.message.answer(f"Напиши `{cmd}`", parse_mode="Markdown")

