"""
bot/handlers/survey.py
Анкета онбординга — 13 шагов + умный парсинг времени
"""

import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from bot.scheduler_logic import setup_user_jobs
from plugins.idea_factory import get_main_keyboard

router = Router()


class Survey(StatesGroup):
    name         = State()
    age          = State()
    gender       = State()
    body         = State()
    goal         = State()
    activity     = State()
    restrictions = State()
    dislikes     = State()
    budget       = State()
    meal_plan    = State()
    schedule     = State()
    timezone     = State()
    hobby        = State()


# ── HELPERS ────────────────────────────────────────────────────────────────

def kb(*buttons: tuple) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    builder.adjust(2)
    return builder.as_markup()


async def ask(message: types.Message, text: str, markup=None):
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")


def parse_time_smart(text: str):
    """
    Умный парсер времени — понимает:
    - "07:00 23:00"
    - "в семь утра и в одиннадцать вечера"
    - "7 и 23"
    - "просыпаюсь в 7 ложусь в 11"
    Возвращает (wake, bed) или (None, None)
    """
    text = text.lower().strip()

    # Цифровой формат — приоритет
    digit_times = re.findall(r'\d{1,2}[:.]\d{2}', text)
    if len(digit_times) >= 2:
        def fix(t):
            h, m = re.split(r'[.:]', t)
            return f"{int(h):02d}:{int(m):02d}"
        return fix(digit_times[0]), fix(digit_times[1])

    # Слова в числа
    word_map = {
        "ноль": 0, "один": 1, "одного": 1, "два": 2, "двух": 2, "двенадцать": 12,
        "три": 3, "трёх": 3, "четыре": 4, "пять": 5, "шесть": 6,
        "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
        "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
        "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
        "девятнадцать": 19, "двадцать": 20, "двадцати": 20,
    }
    for word, num in sorted(word_map.items(), key=lambda x: -len(x[0])):
        text = text.replace(word, str(num))

    # Ищем все числа
    all_nums = re.findall(r'\d+', text)
    if len(all_nums) >= 2:
        h1 = int(all_nums[0])
        h2 = int(all_nums[1])

        is_evening_2 = any(w in text for w in ["вечер", "ночи", "ночью", "pm"])
        if is_evening_2 and h2 < 12:
            h2 += 12
        if h1 > 24 or h2 > 24:
            return None, None

        return f"{h1:02d}:00", f"{h2:02d}:00"

    return None, None


# ── СТАРТ ──────────────────────────────────────────────────────────────────

@router.message(F.text.casefold() == "анкета")
@router.message(Command("survey"))
async def start_survey(message: types.Message, state: FSMContext):
    await state.set_state(Survey.name)
    await ask(message,
        "Привет! Давай познакомимся 🥗\n\n"
        "*Шаг 1 из 13*\nКак тебя зовут?"
    )


# ── ШАГ 1: ИМЯ ─────────────────────────────────────────────────────────────

@router.message(Survey.name)
async def s_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(Survey.age)
    await ask(m, f"Приятно познакомиться, {m.text.strip()}! 👋\n\n*Шаг 2 из 13*\nСколько тебе лет?")


# ── ШАГ 2: ВОЗРАСТ ─────────────────────────────────────────────────────────

@router.message(Survey.age)
async def s_age(m: types.Message, state: FSMContext):
    # Пробуем извлечь число из текста
    nums = re.findall(r'\d+', m.text)
    age = nums[0] if nums else m.text.strip()
    await state.update_data(age=age)
    await state.set_state(Survey.gender)
    await ask(m, "*Шаг 3 из 13*\nПол?",
        kb(("👨 Мужской", "gender_m"), ("👩 Женский", "gender_f"))
    )


# ── ШАГ 3: ПОЛ ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("gender_"), Survey.gender)
async def s_gender(cb: types.CallbackQuery, state: FSMContext):
    gender = "Мужской" if cb.data == "gender_m" else "Женский"
    await state.update_data(gender=gender)
    await state.set_state(Survey.body)
    await cb.message.edit_text(
        "*Шаг 4 из 13*\nНапиши вес и рост через пробел\n\n"
        "Например: `78 182` или `78кг 182см`",
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 4: ВЕС + РОСТ ─────────────────────────────────────────────────────

@router.message(Survey.body)
async def s_body(m: types.Message, state: FSMContext):
    nums = re.findall(r'\d+', m.text)
    if len(nums) >= 2:
        await state.update_data(weight=nums[0], height=nums[1])
    elif len(nums) == 1:
        await state.update_data(weight=nums[0], height="не указан")
    else:
        await state.update_data(weight="не указан", height="не указан")

    await state.set_state(Survey.goal)
    await ask(m, "*Шаг 5 из 13*\nКакая твоя главная цель?",
        kb(
            ("🔥 Похудение",     "goal_loss"),
            ("💪 Набор массы",   "goal_gain"),
            ("❤️ Здоровье",      "goal_health"),
            ("⚡ Больше энергии", "goal_energy"),
        )
    )


# ── ШАГ 5: ЦЕЛЬ ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goal_"), Survey.goal)
async def s_goal(cb: types.CallbackQuery, state: FSMContext):
    goals = {
        "goal_loss": "Похудение", "goal_gain": "Набор массы",
        "goal_health": "Здоровье", "goal_energy": "Больше энергии",
    }
    await state.update_data(goal=goals[cb.data])
    await state.set_state(Survey.activity)
    await cb.message.edit_text(
        "*Шаг 6 из 13*\nУровень активности?",
        reply_markup=kb(
            ("🪑 Сидячая работа",     "act_low"),
            ("🚶 Лёгкая активность",  "act_light"),
            ("🏃 Спорт 3-5 дней/нед", "act_mid"),
            ("🏋️ Физический труд",    "act_high"),
        ),
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 6: АКТИВНОСТЬ ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("act_"), Survey.activity)
async def s_activity(cb: types.CallbackQuery, state: FSMContext):
    acts = {
        "act_low": "Сидячая работа", "act_light": "Лёгкая активность",
        "act_mid": "Спорт 3-5 дней в неделю", "act_high": "Физический труд",
    }
    await state.update_data(activity=acts[cb.data])
    await state.set_state(Survey.restrictions)
    await cb.message.edit_text(
        "*Шаг 7 из 13*\nПищевые ограничения?",
        reply_markup=kb(
            ("✅ Нет ограничений", "rest_none"),
            ("🌱 Вегетарианство",  "rest_veg"),
            ("🌿 Веганство",       "rest_vegan"),
            ("☪️ Халяль",          "rest_halal"),
            ("⚠️ Есть аллергии",   "rest_allergy"),
        ),
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 7: ОГРАНИЧЕНИЯ ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rest_"), Survey.restrictions)
async def s_restrictions(cb: types.CallbackQuery, state: FSMContext):
    rests = {
        "rest_none": "Нет ограничений", "rest_veg": "Вегетарианство",
        "rest_vegan": "Веганство", "rest_halal": "Халяль",
        "rest_allergy": "Есть аллергии",
    }
    await state.update_data(restrictions=rests[cb.data])
    await state.set_state(Survey.dislikes)
    if cb.data == "rest_allergy":
        await cb.message.edit_text(
            "*Шаг 8 из 13*\nНа что именно аллергия? Напиши через запятую",
            parse_mode="Markdown"
        )
    else:
        await cb.message.edit_text(
            "*Шаг 8 из 13*\nПродукты которые не любишь или не ешь?\n\nНапиши или скажи *нет*",
            parse_mode="Markdown"
        )
    await cb.answer()


# ── ШАГ 8: НЕЛЮБИМОЕ ──────────────────────────────────────────────────────

@router.message(Survey.dislikes)
async def s_dislikes(m: types.Message, state: FSMContext):
    await state.update_data(dislikes=m.text.strip())
    await state.set_state(Survey.budget)
    await ask(m,
        "*Шаг 9 из 13*\nБюджет на питание в день?\n\n"
        "Можно написать: `500`, `около 500 рублей`, `пятьсот`"
    )


# ── ШАГ 9: БЮДЖЕТ ──────────────────────────────────────────────────────────

@router.message(Survey.budget)
async def s_budget(m: types.Message, state: FSMContext):
    # Пробуем извлечь сумму
    nums = re.findall(r'\d+', m.text)
    budget = nums[0] if nums else m.text.strip()
    await state.update_data(budget=budget)
    await state.set_state(Survey.meal_plan)
    await ask(m, "*Шаг 10 из 13*\nКак удобнее питаться?",
        kb(
            ("🍽 3 раза в день",    "meal_3"),
            ("🥗 Дробно 5-6 раз",   "meal_5"),
            ("⏱ Интервальное 16/8", "meal_interval"),
            ("🤷 Как получится",    "meal_flex"),
        )
    )


# ── ШАГ 10: ГРАФИК ПИТАНИЯ ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("meal_"), Survey.meal_plan)
async def s_meal_plan(cb: types.CallbackQuery, state: FSMContext):
    meals = {
        "meal_3": "3 раза в день", "meal_5": "Дробно 5-6 раз",
        "meal_interval": "Интервальное 16/8", "meal_flex": "Гибкий график",
    }
    await state.update_data(meal_plan=meals[cb.data])
    await state.set_state(Survey.schedule)
    await cb.message.edit_text(
        "*Шаг 11 из 13*\nВо сколько просыпаешься и ложишься спать?\n\n"
        "Можно написать как угодно:\n"
        "`07:00 23:00` или `в семь утра, в одиннадцать вечера`\n"
        "Если не знаешь — просто напиши *не знаю* и поставлю 7:00 и 23:00",
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 11: РАСПИСАНИЕ ─────────────────────────────────────────────────────

@router.message(Survey.schedule)
async def s_schedule(m: types.Message, state: FSMContext):
    text = m.text.strip().lower()

    # Если не знает — дефолт
    if any(w in text for w in ["не знаю", "незнаю", "не знаешь", "стандарт", "обычно", "default"]):
        wake, bed = "07:00", "23:00"
        await m.answer("Поставил стандартное: подъём 07:00, сон 23:00 — можно изменить через /survey позже.")
    else:
        wake, bed = parse_time_smart(text)
        if not wake:
            wake, bed = "07:00", "23:00"
            await m.answer(
                "Не смог разобрать время, поставил 07:00 и 23:00.\n"
                "Можно изменить через /survey позже."
            )

    await state.update_data(wake_up_time=wake, bedtime=bed)
    await state.set_state(Survey.timezone)
    await ask(m,
        "*Шаг 12 из 13*\n\nВ каком городе живёшь?\n"
        "Например: `Москва`, `Хабаровск`, `Новосибирск`"
    )


# ── ШАГ 12: ГОРОД ──────────────────────────────────────────────────────────

@router.message(Survey.timezone)
async def s_timezone(m: types.Message, state: FSMContext):
    city = m.text.strip()
    tz_map = {
        "москва": 3, "санкт-петербург": 3, "питер": 3, "спб": 3,
        "екатеринбург": 5, "новосибирск": 7, "красноярск": 7,
        "иркутск": 8, "якутск": 9, "хабаровск": 10, "владивосток": 10,
        "магадан": 11, "камчатка": 12, "петропавловск": 12,
        "калининград": 2, "самара": 4, "уфа": 5, "пермь": 5,
        "челябинск": 5, "омск": 6, "томск": 7, "кемерово": 7,
        "барнаул": 7, "чита": 9, "благовещенск": 9, "сахалин": 11,
        "казань": 3, "нижний новгород": 3, "ростов": 3, "краснодар": 3,
        "воронеж": 3, "волгоград": 3, "саратов": 3, "тюмень": 5,
    }
    utc_offset = tz_map.get(city.lower(), 3)
    await state.update_data(city=city, utc_offset=utc_offset)
    await state.set_state(Survey.hobby)
    await ask(m,
        "*Последний шаг — 13 из 13!* 🎉\n\n"
        "Расскажи о себе — хобби, работа, образ жизни?\n"
        "_(Это поможет сделать план ближе к реальности)_"
    )


# ── ШАГ 13: ХОББИ + ФИНАЛ ──────────────────────────────────────────────────

@router.message(Survey.hobby)
async def s_final(m: types.Message, state: FSMContext):
    data = await state.get_data()
    data["hobby"] = m.text.strip()
    data["current_vibe"] = "observer"

    user_id = m.from_user.id
    db = MemoryManager(user_id)
    db.save_profile(data)
    setup_user_jobs(user_id, data["wake_up_time"], data["bedtime"])

    await state.clear()

    await m.answer(
        f"✅ Отлично, {data.get('name')}! Профиль сохранён.\n\n"
        "Генерирую твой первый дашборд и диету на неделю... ⏳\n"
        "Это займёт 15-20 секунд.",
        reply_markup=get_main_keyboard()
    )

    # Генерируем дашборд сразу
    from bot.scheduler_logic import send_morning_dashboard
    try:
        await send_morning_dashboard(user_id)
    except Exception as e:
        pass

    # Генерируем диету и список покупок
    ai = GeminiEngine(data)
    try:
        diet_text = ai.generate_weekly_diet()
        # Сохраняем структурированный список покупок в БД
        items = ai.generate_shopping_list_structured(diet_text)
        if items:
            db.save_shopping_list(items)

        # Отправляем диету текстом (разбиваем если слишком длинная)
        if len(diet_text) > 4000:
            mid = diet_text.find("\n*День 4")
            await m.answer(diet_text[:mid] if mid > 0 else diet_text[:4000], parse_mode="Markdown")
            await m.answer(diet_text[mid:] if mid > 0 else diet_text[4000:], parse_mode="Markdown")
        else:
            await m.answer(diet_text, parse_mode="Markdown")

        await m.answer(
            "🛒 Список покупок сохранён — посмотри через /shopping\n\n"
            "Утром буду присылать план автоматически 🌅\n"
            "Вечером сверимся как прошло 🌙\n\n"
            "/plan — новый план  /tasks — задачи  /weight — вес  /shopping — список покупок"
        )
    except Exception as e:
        await m.answer(
            "Профиль сохранён ✅\n"
            "Напиши *составь мне диету* и я всё сделаю.",
            parse_mode="Markdown"
        )
