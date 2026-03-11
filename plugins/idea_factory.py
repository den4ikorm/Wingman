# -*- coding: utf-8 -*-
"""
plugins/idea_factory.py
Idea Factory v2.1 — кнопка "💡 Идея" везде + FSM-флоу

Флоу:
  Кнопка "💡 Идея"
    → [Быстрая идея] [Выбрать модуль] [Пайплайн]
      → Быстрая: бот просит тему → авто-генерация
      → Выбрать: показывает 20 модулей → просит тему → генерация
      → Пайплайн: просит тему → 5 модулей → топ-3

Подключение в bot/main.py:
  from plugins.idea_factory import router as idea_router, get_main_keyboard
  dp.include_router(idea_router)
"""

import re
import logging
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

logger = logging.getLogger(__name__)
router = Router()


# ── REPLY KEYBOARD (постоянная кнопка внизу) ──────────────────────────

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура с кнопкой Идея внизу экрана."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="💡 Идея"),
        KeyboardButton(text="📋 Задачи"),
        KeyboardButton(text="🛒 Покупки"),
    )
    builder.row(
        KeyboardButton(text="⚖️ Вес"),
        KeyboardButton(text="🌙 Итоги дня"),
        KeyboardButton(text="📊 Прогресс"),
    )
    return builder.as_markup(resize_keyboard=True, persistent=True)


# ── FSM ────────────────────────────────────────────────────────────────

class IdeaStates(StatesGroup):
    waiting_topic_auto     = State()  # быстрая идея
    waiting_topic_module   = State()  # выбор модуля — сначала выбрали модуль
    choosing_module        = State()  # ещё не выбрал модуль
    waiting_topic_pipeline = State()  # пайплайн


# ════════════════════════════════════════════════════════════════════════
# 20 СУБМОДУЛЕЙ МЫШЛЕНИЯ
# ════════════════════════════════════════════════════════════════════════

THINKING_MODULES = {
    1:  {"name": "Cross-Domain Fusion",   "tag": "FUSION",  "emoji": "🔀",
         "instruction": "Найди неочевидную связь между ДВУМЯ разными технологическими доменами. Применяй принципы одной области к проблемам другой. Результат: гибридное решение."},
    2:  {"name": "Trend-Wave Predictor",  "tag": "TREND",   "emoji": "📈",
         "instruction": "Экстраполируй текущие IT/бизнес-тренды на 2-3 года вперёд. Опиши продукт для будущего рынка."},
    3:  {"name": "Problem-Solver",        "tag": "PAIN",    "emoji": "🎯",
         "instruction": "Найди реальную боль пользователей. Сформулируй: 'Меня бесит что X, потому что Y'. Предложи MVP который устраняет боль за 1 шаг."},
    4:  {"name": "Sci-Fi Prototype",      "tag": "SCIFI",   "emoji": "🚀",
         "instruction": "Представь технологию из sci-fi. Определи что реализуемо СЕГОДНЯ с Python+API. Спроектируй MVP с 30% фантастики."},
    5:  {"name": "Resource-Constrained",  "tag": "LEAN",    "emoji": "💸",
         "instruction": "MVP за $0: Python + бесплатные API + Termux/Android. 1 разработчик, 1 неделя. Первые 10 пользователей без денег."},
    6:  {"name": "Bionic Design",         "tag": "BIONIC",  "emoji": "🧬",
         "instruction": "Скопируй архитектурное решение из природы в ПО. Нейросети ← мозг. Ant Colony ← маршрутизация."},
    7:  {"name": "Anti-Pattern",          "tag": "ANTI",    "emoji": "🔄",
         "instruction": "Сделай всё НАОБОРОТ. Если все в облаке — локально. Если много функций — одна. Почему инверсия = преимущество?"},
    8:  {"name": "Micro-SaaS",            "tag": "MSAAS",   "emoji": "💡",
         "instruction": "Нишевый продукт: $500-5000 MRR, 1 разработчик. НЕ 'CRM для всех' а 'CRM для татуировщиков'. ЦА + боль + ценообразование."},
    9:  {"name": "Gamification Engine",   "tag": "GAME",    "emoji": "🎮",
         "instruction": "Геймифицируй скучный процесс. XP, уровни, ежедневные квесты. Как механики влияют на поведение?"},
    10: {"name": "Eco-Systemic",          "tag": "ECO",     "emoji": "♻️",
         "instruction": "Циркулярная экономика данных. Отходы одного процесса = ресурс другого. Логи ошибок → обучающий датасет."},
    11: {"name": "Emotional AI",          "tag": "EMO",     "emoji": "🧠",
         "instruction": "ИИ с эмпатией. Система меняет поведение при усталости/стрессе/вдохновении. Как технически через API?"},
    12: {"name": "Legacy Reviver",        "tag": "LEGACY",  "emoji": "🏛️",
         "instruction": "Дай жизнь старой технологии через AI-обёртку. RSS + AI = умный агрегатор. COBOL + LLM = банковский интерфейс."},
    13: {"name": "Chaos Engineering",     "tag": "CHAOS",   "emoji": "⚡",
         "instruction": "Система намеренно ломает себя для проверки устойчивости. Netflix Chaos Monkey. Антихрупкость."},
    14: {"name": "Local-First",           "tag": "LOCAL",   "emoji": "📱",
         "instruction": "Весь AI на устройстве без сети. SQLite + llama.cpp + Termux. Данные не покидают устройство."},
    15: {"name": "Educational Sim",       "tag": "EDU",     "emoji": "🎓",
         "instruction": "Обучение через симуляции. Ошибка = лучший учитель. Бизнес-симулятор в чате. CTF для разработчиков."},
    16: {"name": "Security Guard",        "tag": "SEC",     "emoji": "🛡️",
         "instruction": "Превентивная безопасность ДО атаки. Honeypot, поведенческий анализ, аномалии в трафике."},
    17: {"name": "Zero-Waste Logistics",  "tag": "ZWL",     "emoji": "🚚",
         "instruction": "Оптимизация маршрутов. Travelling Salesman, Vehicle Routing. -20-30% время/расход/простои."},
    18: {"name": "AI-Agent Specialist",   "tag": "AGENTS",  "emoji": "🤖",
         "instruction": "Узкий ИИ-эксперт: юрист/бухгалтер/QA. Знает контекст компании, автономен, отчитывается. LLM + RAG + tools."},
    19: {"name": "Bio-Hacking",           "tag": "BIO",     "emoji": "💪",
         "instruction": "ПО + носимые устройства + биометрика. Пульс, ЧСС, сон. Адаптация среды под физиологию."},
    20: {"name": "Ethical AI",            "tag": "ETHICS",  "emoji": "⚖️",
         "instruction": "Прозрачность и объяснимость решений. Каждое действие объяснено, логировано, оспорено. Accuracy vs интерпретируемость."},
}

IDEA_PROMPT = """ROLE: Архитектор Инноваций
DATE: {date}
СУБМОДУЛЬ: #{module_id:02d} — {module_name} [{module_tag}]

ИНСТРУКЦИЯ:
{instruction}

ТЕМА:
{topic}

СТРУКТУРА ОТВЕТА:
## 💡 Концепт
(2-3 предложения)

## 👥 ЦА и боль

## ⚙️ Реализация
(стек + алгоритм)

## 📅 MVP за 7 дней
1. День 1-2:
2. День 3-5:
3. День 6-7:

## ⚠️ Главный риск + обход

## 💰 Монетизация

## ✅ Реализуемость: ВЫСОКАЯ / СРЕДНЯЯ / НИЗКАЯ

БЕЗ ВОДЫ. Максимум 350 слов."""


def _auto_select(topic: str) -> int:
    t = topic.lower()
    rules = [
        (["боль", "бесит", "проблем", "мешает"], 3),
        (["дёшево", "бесплатно", "mvp", "старт"], 5),
        (["безопасность", "защит", "хакер"], 16),
        (["обучен", "учёба", "курс", "навык"], 15),
        (["локально", "оффлайн", "termux", "edge"], 14),
        (["игра", "геймиф", "очки", "уровень"], 9),
        (["агент", "автоном", "бот", "worker"], 18),
        (["старый", "legacy", "устарел"], 12),
        (["тренд", "будущ", "прогноз"], 2),
        (["эмоц", "настроени", "стресс"], 11),
        (["нишев", "микро", "узкий"], 8),
    ]
    for keywords, mod_id in rules:
        if any(kw in t for kw in keywords):
            return mod_id
    return 1


async def _generate_idea(profile: dict, topic: str, module_id: int) -> str:
    mod = THINKING_MODULES[module_id]
    prompt = IDEA_PROMPT.format(
        date=datetime.now().strftime("%Y-%m-%d"),
        module_id=module_id,
        module_name=mod["name"],
        module_tag=mod["tag"],
        instruction=mod["instruction"],
        topic=topic,
    )
    ai = GeminiEngine(profile)
    return ai._call(prompt, mode="chat")


def _modules_keyboard(topic: str = "") -> InlineKeyboardBuilder:
    """Клавиатура выбора из 20 модулей."""
    builder = InlineKeyboardBuilder()
    for i, mod in THINKING_MODULES.items():
        builder.button(
            text=f"{mod['emoji']} #{i:02d} {mod['name']}",
            callback_data=f"idea_mod_{i}_{topic[:25]}"
        )
    builder.adjust(2)
    return builder


# ── КНОПКА "💡 Идея" ──────────────────────────────────────────────────

@router.message(F.text == "💡 Идея")
@router.message(Command("idea"))
async def idea_entry(message: types.Message, state: FSMContext):
    """Точка входа — показывает три режима."""
    # Если после /idea есть тема — сразу быстрая генерация
    text = message.text or ""
    if text.startswith("/idea "):
        topic = text[6:].strip()
        if topic:
            await state.update_data(topic=topic)
            await _run_auto(message, state, topic)
            return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚡ Быстрая идея",   callback_data="idea_mode_auto"),
        InlineKeyboardButton(text="🎯 Выбрать модуль", callback_data="idea_mode_pick"),
        InlineKeyboardButton(text="🔄 Пайплайн",       callback_data="idea_mode_pipeline"),
    )
    await message.answer(
        "💡 *Idea Factory* — что делаем?\n\n"
        "⚡ *Быстрая* — ввёл тему, бот сам выбирает лучший субмодуль\n"
        "🎯 *Выбрать модуль* — выбираешь из 20 субмодулей мышления\n"
        "🔄 *Пайплайн* — 5 субмодулей параллельно, топ-3 лучших",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ── РЕЖИМ: БЫСТРАЯ ИДЕЯ ───────────────────────────────────────────────

@router.callback_query(F.data == "idea_mode_auto")
async def mode_auto(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "⚡ *Быстрая идея*\n\nНапиши тему или задачу:",
        parse_mode="Markdown"
    )
    await state.set_state(IdeaStates.waiting_topic_auto)
    await cb.answer()


@router.message(IdeaStates.waiting_topic_auto)
async def receive_topic_auto(message: types.Message, state: FSMContext):
    await state.clear()
    await _run_auto(message, state, message.text.strip())


async def _run_auto(message: types.Message, state: FSMContext, topic: str):
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return await message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")

    module_id = _auto_select(topic)
    mod = THINKING_MODULES[module_id]

    await message.answer(
        f"{mod['emoji']} Субмодуль: *#{module_id:02d} {mod['name']}*\nГенерирую...",
        parse_mode="Markdown"
    )
    try:
        idea = await _generate_idea(profile, topic, module_id)
        db.log_insight(f"IDEA_AUTO #{module_id} | {topic}\n{idea[:400]}")
        full = f"{mod['emoji']} *#{module_id:02d} {mod['name']}* `[{mod['tag']}]`\n\n{idea}"
        for chunk in _split(full):
            await message.answer(chunk, parse_mode="Markdown")
        # Кнопки после результата
        await message.answer(
            "Попробовать иначе?",
            reply_markup=_after_idea_kb(topic)
        )
    except Exception as e:
        logger.error(f"idea auto error: {e}")
        await message.answer("Ошибка генерации, попробуй позже.")


# ── РЕЖИМ: ВЫБРАТЬ МОДУЛЬ ─────────────────────────────────────────────

@router.callback_query(F.data == "idea_mode_pick")
async def mode_pick(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "🎯 *Выбери субмодуль мышления:*",
        reply_markup=_modules_keyboard().as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(IdeaStates.choosing_module)
    await cb.answer()


@router.callback_query(F.data.startswith("idea_mod_"), IdeaStates.choosing_module)
async def module_chosen(cb: types.CallbackQuery, state: FSMContext):
    parts = cb.data.split("_", 3)
    module_id = int(parts[2])
    mod = THINKING_MODULES[module_id]
    await state.update_data(module_id=module_id)
    await state.set_state(IdeaStates.waiting_topic_module)
    await cb.message.edit_text(
        f"{mod['emoji']} *#{module_id:02d} {mod['name']}*\n\nНапиши тему:",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.message(IdeaStates.waiting_topic_module)
async def receive_topic_module(message: types.Message, state: FSMContext):
    data = await state.get_data()
    module_id = data.get("module_id", 1)
    topic = message.text.strip()
    await state.clear()

    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return await message.answer("Сначала заполни анкету.", parse_mode="Markdown")

    mod = THINKING_MODULES[module_id]
    await message.answer(f"{mod['emoji']} Генерирую через *{mod['name']}*...", parse_mode="Markdown")

    try:
        idea = await _generate_idea(profile, topic, module_id)
        db.log_insight(f"IDEA_PICK #{module_id} | {topic}\n{idea[:400]}")
        full = f"{mod['emoji']} *#{module_id:02d} {mod['name']}* `[{mod['tag']}]`\n\n{idea}"
        for chunk in _split(full):
            await message.answer(chunk, parse_mode="Markdown")
        await message.answer("Попробовать иначе?", reply_markup=_after_idea_kb(topic))
    except Exception as e:
        logger.error(f"idea pick error: {e}")
        await message.answer("Ошибка генерации.")


# ── РЕЖИМ: ПАЙПЛАЙН ───────────────────────────────────────────────────

@router.callback_query(F.data == "idea_mode_pipeline")
async def mode_pipeline(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "🔄 *Пайплайн* — 5 субмодулей, топ-3\n\nНапиши тему:",
        parse_mode="Markdown"
    )
    await state.set_state(IdeaStates.waiting_topic_pipeline)
    await cb.answer()


@router.message(IdeaStates.waiting_topic_pipeline)
async def receive_topic_pipeline(message: types.Message, state: FSMContext):
    topic = message.text.strip()
    await state.clear()

    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return await message.answer("Сначала заполни анкету.", parse_mode="Markdown")

    pipeline_modules = [3, 8, 1, 14, 9]
    await message.answer(
        f"🔄 Запускаю 5 субмодулей...\n_{topic}_\n\n~1-2 минуты ⏳",
        parse_mode="Markdown"
    )

    results = []
    for mod_id in pipeline_modules:
        mod = THINKING_MODULES[mod_id]
        try:
            await message.answer(f"{mod['emoji']} #{mod_id:02d} {mod['name']}...")
            idea = await _generate_idea(profile, topic, mod_id)
            results.append({"module_id": mod_id, "mod": mod, "idea": idea})
        except Exception as e:
            logger.error(f"pipeline mod {mod_id}: {e}")

    if not results:
        return await message.answer("Не смог сгенерировать идеи.")

    await message.answer(
        f"✅ *Готово! {len(results)} идей для:* _{topic}_",
        parse_mode="Markdown"
    )
    for r in results:
        mod = r["mod"]
        full = f"{mod['emoji']} *#{r['module_id']:02d} {mod['name']}* `[{mod['tag']}]`\n\n{r['idea']}"
        for chunk in _split(full):
            await message.answer(chunk, parse_mode="Markdown")
        db.log_insight(f"PIPELINE #{r['module_id']} | {topic}\n{r['idea'][:300]}")


# ── КНОПКИ ПОСЛЕ РЕЗУЛЬТАТА ───────────────────────────────────────────

def _after_idea_kb(topic: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔀 Другой субмодуль", callback_data=f"idea_reroll_{topic[:30]}"),
        InlineKeyboardButton(text="🔄 Пайплайн",         callback_data="idea_mode_pipeline"),
    )
    return builder.as_markup()


@router.callback_query(F.data.startswith("idea_reroll_"))
async def idea_reroll(cb: types.CallbackQuery, state: FSMContext):
    topic = cb.data.replace("idea_reroll_", "")
    await cb.message.edit_text(
        "🎯 *Выбери субмодуль:*",
        reply_markup=_modules_keyboard(topic).as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(IdeaStates.choosing_module)
    await cb.answer()


@router.callback_query(F.data.startswith("idea_mod_"))
async def module_chosen_reroll(cb: types.CallbackQuery, state: FSMContext):
    """Выбор модуля с темой уже в callback_data (reroll)."""
    current = await state.get_state()
    if current == IdeaStates.choosing_module:
        return  # обрабатывается выше

    parts = cb.data.split("_", 3)
    module_id = int(parts[2])
    topic = parts[3] if len(parts) > 3 else ""
    if not topic:
        await state.update_data(module_id=module_id)
        await state.set_state(IdeaStates.waiting_topic_module)
        mod = THINKING_MODULES[module_id]
        await cb.message.edit_text(f"{mod['emoji']} *{mod['name']}*\n\nНапиши тему:", parse_mode="Markdown")
        await cb.answer()
        return

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return await cb.answer("Нет профиля")

    mod = THINKING_MODULES[module_id]
    await cb.message.answer(f"{mod['emoji']} Генерирую *{mod['name']}*...", parse_mode="Markdown")
    await cb.answer()

    try:
        idea = await _generate_idea(profile, topic, module_id)
        full = f"{mod['emoji']} *#{module_id:02d} {mod['name']}*\n\n{idea}"
        for chunk in _split(full):
            await cb.message.answer(chunk, parse_mode="Markdown")
        await cb.message.answer("Попробовать иначе?", reply_markup=_after_idea_kb(topic))
    except Exception as e:
        logger.error(f"reroll error: {e}")
        await cb.message.answer("Ошибка генерации.")


# ── ВСПОМОГАТЕЛЬНЫЕ КОМАНДЫ ───────────────────────────────────────────

@router.message(Command("idea_list"))
async def cmd_idea_list(message: types.Message):
    lines = ["*20 субмодулей Idea Factory:*\n"]
    for i, mod in THINKING_MODULES.items():
        lines.append(f"{mod['emoji']} `#{i:02d}` *{mod['name']}* `[{mod['tag']}]`")
    lines.append("\n💡 Идея — кнопка внизу экрана")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("idea_pipeline"))
async def cmd_idea_pipeline(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await mode_pipeline_ask(message, state)
        return
    await receive_topic_pipeline_cmd(message, parts[1].strip(), state)


async def mode_pipeline_ask(message: types.Message, state: FSMContext):
    await message.answer("🔄 *Пайплайн* — напиши тему:", parse_mode="Markdown")
    await state.set_state(IdeaStates.waiting_topic_pipeline)


async def receive_topic_pipeline_cmd(message: types.Message, topic: str, state: FSMContext):
    """Запуск пайплайна напрямую с темой из команды."""
    await state.clear()
    fake = types.Message.model_construct(
        text=topic,
        from_user=message.from_user,
        chat=message.chat,
        message_id=message.message_id,
        date=message.date,
        bot=message.bot,
    )
    # Вызываем хендлер напрямую
    await receive_topic_pipeline(message, state)


# ── КНОПКИ REPLY KEYBOARD (дублируем обработку) ──────────────────────

@router.message(F.text == "📋 Задачи")
async def btn_tasks(message: types.Message):
    from bot.handlers.common import cmd_tasks
    await cmd_tasks(message)


@router.message(F.text == "🛒 Покупки")
async def btn_shopping(message: types.Message):
    from bot.handlers.common import cmd_shopping
    await cmd_shopping(message)


@router.message(F.text == "⚖️ Вес")
async def btn_weight(message: types.Message):
    await message.answer("Напиши вес: `/weight 78.5`", parse_mode="Markdown")


@router.message(F.text == "📊 Прогресс")
async def btn_progress(message: types.Message):
    from bot.handlers.common import cmd_progress
    await cmd_progress(message)


@router.message(F.text == "🌙 Итоги дня")
async def btn_evening(message: types.Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✨ Подвести итоги", callback_data="start_evening_review"))
    await message.answer("Готов подвести итоги дня?", reply_markup=builder.as_markup())


# ── УТИЛИТЫ ───────────────────────────────────────────────────────────

def _split(text: str, size: int = 4000) -> list[str]:
    """Разбивает длинный текст на части."""
    if len(text) <= size:
        return [text]
    parts = []
    while text:
        parts.append(text[:size])
        text = text[size:]
    return parts
