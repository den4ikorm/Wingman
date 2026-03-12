# -*- coding: utf-8 -*-
"""
bot/handlers/travel_handler.py
Travel Agent v1

Анкета → определяет опыт пользователя → генерирует план поездки.
Новичок  → классика + безопасность + базовые советы
Опытный  → скрытые места, инсайды, редкие локации
Эксперт  → только то, о чём обычно не знают туристы

Команда: /travel
"""

import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

logger = logging.getLogger(__name__)
router = Router()


class TravelSurvey(StatesGroup):
    destination  = State()   # Куда едешь?
    dates        = State()   # Когда? (дата или "через неделю")
    duration     = State()   # Сколько дней?
    companions   = State()   # Один / с кем?
    budget       = State()   # Бюджет в день (USD/RUB)
    experience   = State()   # Опыт в этом месте?
    goals        = State()   # Цель поездки?
    generating   = State()   # Генерируем план


def _kb(*buttons: str, one_time=True) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=b)] for b in buttons]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               one_time_keyboard=one_time)


# ── СТАРТ ─────────────────────────────────────────────────────────────────────

@router.message(Command("travel"))
async def cmd_travel(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(TravelSurvey.destination)
    await message.answer(
        "✈️ *Travel Assistant*\n\n"
        "Помогу спланировать поездку — от маршрута до скрытых мест.\n\n"
        "Куда едешь? Напиши страну и город:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )


# ── АНКЕТА ────────────────────────────────────────────────────────────────────

@router.message(TravelSurvey.destination)
async def survey_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text.strip())
    await state.set_state(TravelSurvey.dates)
    await message.answer(
        "📅 Когда планируешь ехать?\n"
        "Напиши дату или примерно (_через неделю, в мае..._)",
        parse_mode="Markdown"
    )


@router.message(TravelSurvey.dates)
async def survey_dates(message: types.Message, state: FSMContext):
    await state.update_data(dates=message.text.strip())
    await state.set_state(TravelSurvey.duration)
    await message.answer(
        "⏱ Сколько дней поездка?",
        reply_markup=_kb("3-4 дня", "5-7 дней", "1-2 недели", "Больше месяца")
    )


@router.message(TravelSurvey.duration)
async def survey_duration(message: types.Message, state: FSMContext):
    await state.update_data(duration=message.text.strip())
    await state.set_state(TravelSurvey.companions)
    await message.answer(
        "👥 Едешь один или с кем-то?",
        reply_markup=_kb("Один", "С партнёром", "С друзьями", "С семьёй/детьми")
    )


@router.message(TravelSurvey.companions)
async def survey_companions(message: types.Message, state: FSMContext):
    await state.update_data(companions=message.text.strip())
    await state.set_state(TravelSurvey.budget)
    await message.answer(
        "💰 Примерный бюджет в день на человека?",
        reply_markup=_kb("До 50$", "50-100$", "100-200$", "200$+")
    )


@router.message(TravelSurvey.budget)
async def survey_budget(message: types.Message, state: FSMContext):
    await state.update_data(budget=message.text.strip())
    dest = (await state.get_data()).get("destination", "это место")
    await state.set_state(TravelSurvey.experience)
    await message.answer(
        f"🌍 Как часто бывал в *{dest}*?",
        parse_mode="Markdown",
        reply_markup=_kb(
            "Впервые",
            "Был 1-2 раза",
            "Бываю регулярно",
            "Знаю как свои пять пальцев"
        )
    )


@router.message(TravelSurvey.experience)
async def survey_experience(message: types.Message, state: FSMContext):
    text = message.text.strip()
    # Определяем уровень опыта
    if "впервые" in text.lower() or "первый" in text.lower():
        level = "newcomer"
    elif "1-2" in text or "несколько" in text.lower():
        level = "intermediate"
    elif "регулярно" in text.lower() or "часто" in text.lower():
        level = "experienced"
    else:
        level = "expert"

    await state.update_data(experience=text, experience_level=level)
    await state.set_state(TravelSurvey.goals)
    await message.answer(
        "🎯 Какая главная цель поездки?\nМожно выбрать несколько:",
        reply_markup=_kb(
            "🏖 Пляж и отдых",
            "🏛 Культура и история",
            "🍜 Гастрономия",
            "🎉 Тусовки и развлечения",
            "🥾 Природа и активности",
            "🛍 Шоппинг"
        )
    )


@router.message(TravelSurvey.goals)
async def survey_goals(message: types.Message, state: FSMContext):
    await state.update_data(goals=message.text.strip())
    data = await state.get_data()
    await state.set_state(TravelSurvey.generating)

    # Показываем что генерируем
    exp_level = data.get("experience_level", "newcomer")
    exp_labels = {
        "newcomer":     "новичок — дам классику + важные советы",
        "intermediate": "немного знаком — покажу лучшее",
        "experienced":  "опытный — добавлю скрытые места",
        "expert":       "эксперт — только инсайды которые мало кто знает",
    }
    await message.answer(
        f"✈️ Отлично! Уровень: _{exp_labels.get(exp_level, exp_level)}_\n\n"
        f"🤖 Gemini составляет твой план...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # Генерируем план
    await _generate_travel_plan(message, data)
    await state.clear()


# ── ГЕНЕРАЦИЯ ПЛАНА ──────────────────────────────────────────────────────────

async def _generate_travel_plan(message: types.Message, data: dict):
    """Генерирует план через Gemini с учётом опыта пользователя."""
    import asyncio
    from core.key_manager import KeyManager
    from google import genai

    destination    = data.get("destination", "")
    duration       = data.get("duration", "7 дней")
    companions     = data.get("companions", "один")
    budget         = data.get("budget", "100$")
    goals          = data.get("goals", "отдых")
    exp_level      = data.get("experience_level", "newcomer")
    dates          = data.get("dates", "")

    # Инструкции по опыту
    experience_instructions = {
        "newcomer": """
Пользователь ВПЕРВЫЕ в этом месте. Давай:
- Топ-5 обязательных мест (must-see)
- Практические советы (транспорт, безопасность, еда)
- Типичные ошибки новичков
- Простой маршрут без сложностей""",

        "intermediate": """
Пользователь БЫЛ 1-2 РАЗА. Давай:
- Места которые обычно пропускают туристы
- Лучшие локальные рестораны (не tourist traps)
- Оптимальный маршрут без очередей
- 2-3 скрытых места""",

        "experienced": """
Пользователь БЫВАЕТ РЕГУЛЯРНО. Давай:
- Скрытые локации которые знают только местные
- Лучшее время для популярных мест (рассвет/закат)
- Аутентичные места вдали от туристов
- Сезонные события и фестивали
- Необычный опыт (мастер-классы, экскурсии с местными)""",

        "expert": """
Пользователь ЗНАЕТ МЕСТО ОТЛИЧНО. Давай ТОЛЬКО:
- Места которые с большой вероятностью ещё не знает (очень нишевые)
- Секреты местных жителей
- Необычные активности которых нет в туристических гидах
- Редкие рестораны/кафе без упоминания в TripAdvisor
- Скрытые природные локации, квартальчики, рынки""",
    }

    prompt = f"""Ты опытный travel-гид. Составь план поездки в JSON.

ДЕТАЛИ:
- Направление: {destination}
- Даты: {dates}
- Длительность: {duration}
- Компания: {companions}
- Бюджет/день: {budget}
- Цели: {goals}

УРОВЕНЬ ОПЫТА:
{experience_instructions.get(exp_level, experience_instructions["newcomer"])}

Верни ТОЛЬКО валидный JSON без markdown блоков. Начинай с {{

{{
  "destination": "{destination}",
  "summary": "Краткое описание поездки (2-3 предложения с учётом опыта)",
  "best_time": "Лучшее время суток / недели для этой поездки",
  "hidden_gems": [
    {{"name": "Название места", "desc": "Почему стоит посетить", "tip": "Инсайдерский совет"}}
  ],
  "days": [
    {{
      "day": 1,
      "title": "Название дня",
      "morning":   "Что делать утром (конкретно)",
      "afternoon": "Что делать днём",
      "evening":   "Что делать вечером",
      "eat":       "Где поесть (конкретное заведение если возможно)",
      "tip":       "Совет дня"
    }}
  ],
  "checklist": [
    "Что взять с собой пункт 1",
    "Что взять с собой пункт 2"
  ],
  "phrases": [
    {{"phrase": "Спасибо", "local": "Khob khun krap", "note": "для мужчин"}}
  ],
  "budget_tips": [
    "Совет по экономии 1"
  ],
  "warnings": [
    "Важное предупреждение 1"
  ]
}}

Дней в плане должно быть столько сколько длится поездка ({duration}).
Только JSON. Ничего больше."""

    try:
        km = KeyManager()
        client = genai.Client(api_key=km.get_key())

        loop = asyncio.get_event_loop()
        def _call():
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={"max_output_tokens": 8192}
            )
            return resp.text

        raw = await loop.run_in_executor(None, _call)

        # Парсим JSON
        import re
        clean = raw.strip()
        # Убираем markdown
        clean = re.sub(r'```(?:json)?\s*', '', clean)
        clean = re.sub(r'```\s*$', '', clean)
        # Убираем комментарии
        clean = re.sub(r'/\*.*?\*/', '""', clean, flags=re.DOTALL)
        start = clean.find('{')
        end   = clean.rfind('}')
        if start != -1 and end > start:
            clean = clean[start:end+1]
        # Trailing commas
        clean = re.sub(r',\s*([}\]])', r'\1', clean)

        plan = json.loads(clean)
        await _send_travel_plan(message, plan, data)

    except Exception as e:
        logger.error(f"Travel plan generation error: {e}", exc_info=True)
        await message.answer(
            f"⚠️ Не удалось сгенерировать план для *{destination}*.\n"
            f"Попробуй ещё раз: /travel",
            parse_mode="Markdown"
        )


async def _send_travel_plan(message: types.Message, plan: dict, data: dict):
    """Отправляет план поездки красиво разбитый на части."""

    dest      = plan.get("destination", data.get("destination",""))
    summary   = plan.get("summary", "")
    best_time = plan.get("best_time", "")
    days      = plan.get("days", [])
    gems      = plan.get("hidden_gems", [])
    checklist = plan.get("checklist", [])
    phrases   = plan.get("phrases", [])
    warnings  = plan.get("warnings", [])
    budget_tips = plan.get("budget_tips", [])

    exp_level = data.get("experience_level", "newcomer")
    exp_emoji = {"newcomer":"🌱","intermediate":"⚡","experienced":"🌟","expert":"💎"}

    # 1. Заголовок
    header = (
        f"✈️ *Твой план: {dest}*\n"
        f"{exp_emoji.get(exp_level,'')} _{summary}_\n\n"
    )
    if best_time:
        header += f"⏰ *Лучшее время:* {best_time}\n"
    await message.answer(header, parse_mode="Markdown")

    # 2. Скрытые места (только для experienced+)
    if gems and exp_level in ("experienced", "expert", "intermediate"):
        gems_text = "💎 *Скрытые места:*\n\n"
        for g in gems[:5]:
            gems_text += (
                f"📍 *{g.get('name','')}*\n"
                f"{g.get('desc','')}\n"
                f"💡 _{g.get('tip','')}_\n\n"
            )
        await message.answer(gems_text, parse_mode="Markdown")

    # 3. План по дням
    for day in days[:7]:
        day_text = (
            f"📅 *День {day.get('day','')} — {day.get('title','')}*\n\n"
            f"🌅 *Утро:* {day.get('morning','')}\n"
            f"☀️ *День:* {day.get('afternoon','')}\n"
            f"🌙 *Вечер:* {day.get('evening','')}\n"
            f"🍴 *Поесть:* {day.get('eat','')}\n"
        )
        if day.get('tip'):
            day_text += f"\n💡 _{day.get('tip')}_"
        await message.answer(day_text, parse_mode="Markdown")

    # 4. Чеклист
    if checklist:
        check_text = "🎒 *Чеклист:*\n"
        for item in checklist:
            check_text += f"☐ {item}\n"
        await message.answer(check_text, parse_mode="Markdown")

    # 5. Фразы на местном
    if phrases:
        ph_text = "🗣 *Полезные фразы:*\n\n"
        for p in phrases[:6]:
            ph_text += f"_{p.get('phrase','')}_  →  *{p.get('local','')}*"
            if p.get('note'):
                ph_text += f"  _{p.get('note')}_"
            ph_text += "\n"
        await message.answer(ph_text, parse_mode="Markdown")

    # 6. Советы и предупреждения
    final = ""
    if budget_tips:
        final += "💰 *Как сэкономить:*\n"
        for t in budget_tips[:3]:
            final += f"• {t}\n"
        final += "\n"
    if warnings:
        final += "⚠️ *Важно знать:*\n"
        for w in warnings[:3]:
            final += f"• {w}\n"

    if final:
        await message.answer(final, parse_mode="Markdown")

    await message.answer(
        "✅ *План готов!*\n\n"
        "Хочешь изменить что-то? Просто напиши /travel и пройди анкету снова.\n"
        "Хорошей поездки! 🌍",
        parse_mode="Markdown"
    )
