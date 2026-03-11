"""
bot/handlers/survey.py
Полная анкета онбординга — 12 шагов
После завершения: Gemini генерирует диету на 7 дней + список покупок
"""

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from bot.scheduler_logic import setup_user_jobs

router = Router()


class Survey(StatesGroup):
    name        = State()
    age         = State()
    gender      = State()
    body        = State()  # вес и рост одним сообщением
    goal        = State()
    activity    = State()
    restrictions = State()
    dislikes    = State()
    budget      = State()
    meal_plan   = State()
    schedule    = State()  # время подъёма и сна
    hobby       = State()


# ── HELPERS ────────────────────────────────────────────────────────────────

def kb(*buttons: tuple) -> types.InlineKeyboardMarkup:
    """Быстрый билдер inline-клавиатуры из кортежей (текст, data)"""
    builder = InlineKeyboardBuilder()
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    builder.adjust(2)
    return builder.as_markup()


async def ask(message: types.Message, text: str, markup=None):
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")


# ── СТАРТ АНКЕТЫ ───────────────────────────────────────────────────────────

@router.message(F.text.casefold() == "анкета")
@router.message(Command("survey"))
async def start_survey(message: types.Message, state: FSMContext):
    await state.set_state(Survey.name)
    await ask(message,
        "Привет! Давай познакомимся — я составлю тебе персональную диету 🥗\n\n"
        "*Шаг 1 из 12*\nКак тебя зовут?"
    )


# ── ШАГ 1: ИМЯ ─────────────────────────────────────────────────────────────

@router.message(Survey.name)
async def s_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(Survey.age)
    await ask(m, f"Приятно познакомиться, {m.text.strip()}! 👋\n\n*Шаг 2 из 12*\nСколько тебе лет?")


# ── ШАГ 2: ВОЗРАСТ ─────────────────────────────────────────────────────────

@router.message(Survey.age)
async def s_age(m: types.Message, state: FSMContext):
    await state.update_data(age=m.text.strip())
    await state.set_state(Survey.gender)
    await ask(m,
        "*Шаг 3 из 12*\nПол?",
        kb(("👨 Мужской", "gender_m"), ("👩 Женский", "gender_f"))
    )


# ── ШАГ 3: ПОЛ ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("gender_"), Survey.gender)
async def s_gender(cb: types.CallbackQuery, state: FSMContext):
    gender = "Мужской" if cb.data == "gender_m" else "Женский"
    await state.update_data(gender=gender)
    await state.set_state(Survey.body)
    await cb.message.edit_text(
        f"*Шаг 4 из 12*\nНапиши свой вес и рост через пробел\n\n"
        f"Например: `78 182`\n_(кг и см)_",
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 4: ВЕС + РОСТ ─────────────────────────────────────────────────────

@router.message(Survey.body)
async def s_body(m: types.Message, state: FSMContext):
    parts = m.text.strip().split()
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        await state.update_data(weight=parts[0], height=parts[1])
    else:
        await state.update_data(weight=m.text.strip(), height="не указан")

    await state.set_state(Survey.goal)
    await ask(m,
        "*Шаг 5 из 12*\nКакая твоя главная цель?",
        kb(
            ("🔥 Похудение",    "goal_loss"),
            ("💪 Набор массы",  "goal_gain"),
            ("❤️ Здоровье",     "goal_health"),
            ("⚡ Больше энергии", "goal_energy"),
        )
    )


# ── ШАГ 5: ЦЕЛЬ ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goal_"), Survey.goal)
async def s_goal(cb: types.CallbackQuery, state: FSMContext):
    goals = {
        "goal_loss":   "Похудение",
        "goal_gain":   "Набор массы",
        "goal_health": "Здоровье",
        "goal_energy": "Больше энергии",
    }
    await state.update_data(goal=goals[cb.data])
    await state.set_state(Survey.activity)
    await cb.message.edit_text(
        "*Шаг 6 из 12*\nКакой у тебя уровень активности?",
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
        "act_low":   "Сидячая работа",
        "act_light": "Лёгкая активность",
        "act_mid":   "Спорт 3-5 дней в неделю",
        "act_high":  "Физический труд",
    }
    await state.update_data(activity=acts[cb.data])
    await state.set_state(Survey.restrictions)
    await cb.message.edit_text(
        "*Шаг 7 из 12*\nЕсть ли пищевые ограничения?",
        reply_markup=kb(
            ("✅ Нет ограничений",    "rest_none"),
            ("🌱 Вегетарианство",     "rest_veg"),
            ("🌿 Веганство",          "rest_vegan"),
            ("☪️ Халяль",             "rest_halal"),
            ("⚠️ Есть аллергии",      "rest_allergy"),
        ),
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 7: ОГРАНИЧЕНИЯ ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rest_"), Survey.restrictions)
async def s_restrictions(cb: types.CallbackQuery, state: FSMContext):
    rests = {
        "rest_none":    "Нет ограничений",
        "rest_veg":     "Вегетарианство",
        "rest_vegan":   "Веганство",
        "rest_halal":   "Халяль",
        "rest_allergy": "Есть аллергии",
    }
    val = rests[cb.data]
    await state.update_data(restrictions=val)
    await state.set_state(Survey.dislikes)

    if cb.data == "rest_allergy":
        await cb.message.edit_text(
            "*Шаг 8 из 12*\nНа что именно аллергия? Напиши через запятую\n\n"
            "Например: `орехи, молоко, глютен`",
            parse_mode="Markdown"
        )
    else:
        await cb.message.edit_text(
            "*Шаг 8 из 12*\nЕсть продукты которые ты не любишь или не ешь?\n\n"
            "Напиши через запятую или напиши *нет*",
            parse_mode="Markdown"
        )
    await cb.answer()


# ── ШАГ 8: НЕЛЮБИМЫЕ ПРОДУКТЫ ─────────────────────────────────────────────

@router.message(Survey.dislikes)
async def s_dislikes(m: types.Message, state: FSMContext):
    await state.update_data(dislikes=m.text.strip())
    await state.set_state(Survey.budget)
    await ask(m,
        "*Шаг 9 из 12*\nКакой примерный бюджет на питание в день?\n\n"
        "Напиши сумму в рублях, например: `500`"
    )


# ── ШАГ 9: БЮДЖЕТ ──────────────────────────────────────────────────────────

@router.message(Survey.budget)
async def s_budget(m: types.Message, state: FSMContext):
    await state.update_data(budget=m.text.strip())
    await state.set_state(Survey.meal_plan)
    await ask(m,
        "*Шаг 10 из 12*\nКак тебе удобнее питаться?",
        kb(
            ("🍽 3 раза в день",       "meal_3"),
            ("🥗 Дробно 5-6 раз",      "meal_5"),
            ("⏱ Интервальное 16/8",    "meal_interval"),
            ("🤷 Как получится",        "meal_flex"),
        )
    )


# ── ШАГ 10: ГРАФИК ПИТАНИЯ ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("meal_"), Survey.meal_plan)
async def s_meal_plan(cb: types.CallbackQuery, state: FSMContext):
    meals = {
        "meal_3":        "3 раза в день",
        "meal_5":        "Дробно 5-6 раз",
        "meal_interval": "Интервальное 16/8",
        "meal_flex":     "Гибкий график",
    }
    await state.update_data(meal_plan=meals[cb.data])
    await state.set_state(Survey.schedule)
    await cb.message.edit_text(
        "*Шаг 11 из 12*\nВо сколько просыпаешься и ложишься спать?\n\n"
        "Напиши через пробел, например: `07:00 23:30`",
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 11: РАСПИСАНИЕ ─────────────────────────────────────────────────────

@router.message(Survey.schedule)
async def s_schedule(m: types.Message, state: FSMContext):
    import re
    times = re.findall(r'\d{1,2}[:\.]\d{2}', m.text)
    if len(times) >= 2:
        wake = times[0].replace(".", ":")
        bed  = times[1].replace(".", ":")
    elif len(times) == 1:
        wake = times[0].replace(".", ":")
        bed  = "23:00"
    else:
        await m.answer("Не понял формат. Напиши время через пробел, например: `07:00 23:30`", parse_mode="Markdown")
        return
    def fix(t):
        h, mn = t.split(":")
        return f"{int(h):02d}:{int(mn):02d}"
    try:
        wake = fix(wake)
        bed  = fix(bed)
    except Exception:
        await m.answer("Не понял формат. Напиши: `07:00 23:30`", parse_mode="Markdown")
        return
    await state.update_data(wake_up_time=wake, bedtime=bed)
    await state.set_state(Survey.hobby)
    await ask(m,
        "*Шаг 12 из 12 — последний!*\n\n"
        "Расскажи немного о себе — хобби, работа, образ жизни?\n"
        "_(Это поможет сделать план ближе к реальности)_"
    )


# ── ШАГ 12: ХОББИ + ФИНАЛ ──────────────────────────────────────────────────

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
        f"✅ Отлично, {data.get('name')}! Профиль готов.\n\n"
        "Генерирую твою персональную диету на 7 дней... 🥗\n"
        "Это займёт 10-15 секунд."
    )

    # Генерируем диету и список покупок
    ai = GeminiEngine(data)

    try:
        diet_text = ai.generate_weekly_diet()
        shopping  = ai.generate_shopping_list(diet_text)

        await m.answer(diet_text, parse_mode="Markdown")
        await m.answer(shopping,  parse_mode="Markdown")
        await m.answer(
            "Утром пришлю план дня с учётом твоего рациона.\n"
            "Вечером сверимся как прошло 🌙\n\n"
            "Если хочешь изменить что-то — напиши /survey заново."
        )
    except Exception as e:
        await m.answer(
            "Профиль сохранён ✅\n"
            "Не смог сгенерировать диету прямо сейчас — попробуй написать "
            "«составь мне диету» и я всё сделаю."
        )
