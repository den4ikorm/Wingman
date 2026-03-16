"""
bot/handlers/survey.py
Анкета онбординга v3 — 30 вопросов, 7 блоков
В конце: выбор LifeMode + уровень контроля
"""

import re
import asyncio
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from bot.scheduler_logic import setup_user_jobs
from bot.keyboard_manager import get_main_kb

logger = logging.getLogger(__name__)
router = Router()

TOTAL_STEPS = 30


class Survey(StatesGroup):
    # БЛОК А — База (5)
    name         = State()   # 1
    age          = State()   # 2
    gender       = State()   # 3
    body         = State()   # 4
    city         = State()   # 5

    # БЛОК Б — Тело и активность (7)
    goal         = State()   # 6
    activity     = State()   # 7
    sport_freq   = State()   # 8
    sport_type   = State()   # 9
    schedule     = State()   # 10
    sleep_hours  = State()   # 11
    water        = State()   # 12

    # БЛОК В — Питание (5)
    restrictions = State()   # 13
    dislikes     = State()   # 14
    budget       = State()   # 15
    meal_plan    = State()   # 16
    psychotype   = State()   # 17

    # БЛОК Г — Психология (4)
    stress_level  = State()  # 18
    stress_coping = State()  # 19
    food_meaning  = State()  # 20
    self_attitude = State()  # 21

    # БЛОК Д — Финансы (3)
    fin_income    = State()  # 22
    fin_expenses  = State()  # 23
    fin_goal      = State()  # 24

    # БЛОК Е — Контент (3)
    content_genres = State() # 25
    music_taste    = State() # 26
    book_genres    = State() # 27

    # БЛОК Ж — Образ жизни (2)
    hobby        = State()   # 28
    travel_freq  = State()   # 29

    # ФИНАЛ — LifeMode (1)
    lifemode_choice = State() # 30


# ── HELPERS ────────────────────────────────────────────────────────────────

def kb(*buttons: tuple) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, data in buttons:
        builder.button(text=text, callback_data=data)
    builder.adjust(2)
    return builder.as_markup()


def progress(step: int) -> str:
    """Прогресс-бар: ● ● ● ○ ○ ○"""
    filled = "●" * step
    empty  = "○" * (TOTAL_STEPS - step)
    pct    = int(step / TOTAL_STEPS * 100)
    return f"`{filled}{empty}` {pct}%"


async def ask(message: types.Message, step: int, text: str, markup=None):
    full = f"{progress(step)}\n*Шаг {step} из {TOTAL_STEPS}*\n\n{text}"
    await message.answer(full, reply_markup=markup, parse_mode="Markdown")


async def ask_edit(cb: types.CallbackQuery, step: int, text: str, markup=None):
    full = f"{progress(step)}\n*Шаг {step} из {TOTAL_STEPS}*\n\n{text}"
    await cb.message.edit_text(full, reply_markup=markup, parse_mode="Markdown")
    await cb.answer()


def parse_time_smart(text: str):
    text = text.lower().strip()
    digit_times = re.findall(r'\d{1,2}[:.]?\d{2}', text)
    if len(digit_times) >= 2:
        def fix(t):
            t = t.replace('.', ':')
            if ':' in t:
                h, m = t.split(':')
            else:
                h, m = t[:2], t[2:]
            return f"{int(h):02d}:{int(m):02d}"
        return fix(digit_times[0]), fix(digit_times[1])

    word_map = {
        "ноль": 0, "один": 1, "одного": 1, "два": 2, "двух": 2, "двенадцать": 12,
        "три": 3, "трёх": 3, "четыре": 4, "пять": 5, "шесть": 6,
        "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
        "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
        "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
        "девятнадцать": 19, "двадцать": 20,
    }
    for word, num in sorted(word_map.items(), key=lambda x: -len(x[0])):
        text = text.replace(word, str(num))

    all_nums = re.findall(r'\d+', text)
    if len(all_nums) >= 2:
        h1 = int(all_nums[0])
        h2 = int(all_nums[1])
        if any(w in text for w in ["вечер", "ночи", "ночью", "pm"]) and h2 < 12:
            h2 += 12
        if h1 > 24 or h2 > 24:
            return None, None
        return f"{h1:02d}:00", f"{h2:02d}:00"

    return None, None


# ── СТАРТ ──────────────────────────────────────────────────────────────────

@router.message(F.text.casefold() == "анкета")
@router.message(Command("survey"))
async def start_survey(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(Survey.name)
    await ask(message, 1,
        "🤝 *Блок А — Знакомство* (5 вопросов)\n\n"
        "Как тебя зовут?"
    )


# ── ШАГ 1: ИМЯ ─────────────────────────────────────────────────────────────

@router.message(Survey.name)
async def s_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(Survey.age)
    await ask(m, 2, f"Приятно, {m.text.strip()}! 👋\n\nСколько тебе лет?")


# ── ШАГ 2: ВОЗРАСТ ─────────────────────────────────────────────────────────

@router.message(Survey.age)
async def s_age(m: types.Message, state: FSMContext):
    nums = re.findall(r'\d+', m.text)
    age = nums[0] if nums else m.text.strip()
    await state.update_data(age=age)
    await state.set_state(Survey.gender)
    await ask(m, 3, "Пол?",
        kb(("👨 Мужской", "gender_m"), ("👩 Женский", "gender_f"))
    )


# ── ШАГ 3: ПОЛ ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("gender_"), Survey.gender)
async def s_gender(cb: types.CallbackQuery, state: FSMContext):
    gender = "Мужской" if cb.data == "gender_m" else "Женский"
    await state.update_data(gender=gender)
    await state.set_state(Survey.body)
    await ask_edit(cb, 4,
        "Напиши вес и рост через пробел\n\n"
        "Например: `78 182` или `78кг 182см`"
    )


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
    await state.set_state(Survey.city)
    await ask(m, 5, "В каком городе живёшь?\n\nНапример: `Москва`, `Нефтеюганск`")


# ── ШАГ 6: ЦЕЛЬ ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goal_"), Survey.goal)
async def s_goal(cb: types.CallbackQuery, state: FSMContext):
    goals = {
        "goal_loss": "Похудение", "goal_gain": "Набор массы",
        "goal_health": "Здоровье", "goal_energy": "Больше энергии",
        "goal_detox": "Детокс",
    }
    await state.update_data(goal=goals[cb.data])
    await state.set_state(Survey.activity)
    await ask_edit(cb, 7, "Общий уровень активности?",
        kb(
            ("🪑 Сидячая работа",     "act_low"),
            ("🚶 Лёгкая активность",  "act_light"),
            ("🏃 Спорт 3-5 дней/нед", "act_mid"),
            ("🏋️ Физический труд",    "act_high"),
        )
    )


# ── ШАГ 7: АКТИВНОСТЬ ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("act_"), Survey.activity)
async def s_activity(cb: types.CallbackQuery, state: FSMContext):
    acts = {
        "act_low": "Сидячая работа", "act_light": "Лёгкая активность",
        "act_mid": "Спорт 3-5 дней в неделю", "act_high": "Физический труд",
    }
    await state.update_data(activity=acts[cb.data])
    await state.set_state(Survey.sport_freq)
    await ask_edit(cb, 8, "Как часто занимаешься спортом / тренировками?",
        kb(
            ("🚫 Не занимаюсь",    "sf_never"),
            ("1-2 раза в неделю",  "sf_low"),
            ("3-4 раза в неделю",  "sf_mid"),
            ("5+ раз в неделю",    "sf_high"),
        )
    )


# ── ШАГ 8: ЧАСТОТА СПОРТА ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sf_"), Survey.sport_freq)
async def s_sport_freq(cb: types.CallbackQuery, state: FSMContext):
    sf = {"sf_never": "Не занимаюсь", "sf_low": "1-2 раза/нед",
          "sf_mid": "3-4 раза/нед", "sf_high": "5+ раз/нед"}
    await state.update_data(sport_freq=sf[cb.data])
    await state.set_state(Survey.sport_type)
    await ask_edit(cb, 9, "Какой вид активности предпочитаешь?",
        kb(
            ("🏋️ Силовые / тренажёры", "st_gym"),
            ("🏃 Бег / кардио",         "st_cardio"),
            ("🧘 Йога / растяжка",      "st_yoga"),
            ("⚽ Командные виды",        "st_team"),
            ("🚶 Ходьба / прогулки",    "st_walk"),
            ("🤷 Ничего конкретного",   "st_none"),
        )
    )


# ── ШАГ 9: ВИД СПОРТА ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("st_"), Survey.sport_type)
async def s_sport_type(cb: types.CallbackQuery, state: FSMContext):
    st = {"st_gym": "Силовые", "st_cardio": "Кардио/бег",
          "st_yoga": "Йога", "st_team": "Командные", "st_walk": "Ходьба", "st_none": "Ничего"}
    await state.update_data(sport_type=st[cb.data])
    await state.set_state(Survey.schedule)
    await ask_edit(cb, 10,
        "Во сколько просыпаешься и ложишься?\n\n"
        "Напиши как удобно:\n`07:00 23:00` или `в семь утра, в одиннадцать`\n"
        "_Не знаешь — напиши *не знаю*_"
    )


# ── ШАГ 13: ОГРАНИЧЕНИЯ ────────────────────────────────────────────────────

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
        await ask_edit(cb, 14, "На что именно аллергия? Напиши через запятую")
    else:
        await ask_edit(cb, 14, "Продукты которые не любишь или не ешь?\n\nНапиши или отправь *нет*")


# ── ШАГ 14: НЕЛЮБИМОЕ ──────────────────────────────────────────────────────

@router.message(Survey.dislikes)
async def s_dislikes(m: types.Message, state: FSMContext):
    await state.update_data(dislikes=m.text.strip())
    await state.set_state(Survey.budget)
    await ask(m, 15,
        "Бюджет на питание в день?\n\n"
        "Можно написать: `500`, `около 500 рублей`, `пятьсот`"
    )


# ── ШАГ 15: БЮДЖЕТ ─────────────────────────────────────────────────────────

@router.message(Survey.budget)
async def s_budget(m: types.Message, state: FSMContext):
    nums = re.findall(r'\d+', m.text)
    budget = nums[0] if nums else m.text.strip()
    await state.update_data(budget=budget)
    await state.set_state(Survey.meal_plan)
    await ask(m, 16, "Как удобнее питаться?",
        kb(
            ("🍽 3 раза в день",    "meal_3"),
            ("🥗 Дробно 5-6 раз",   "meal_5"),
            ("⏱ Интервальное 16/8", "meal_interval"),
            ("🤷 Как получится",    "meal_flex"),
        )
    )


# ── ШАГ 16: ГРАФИК ПИТАНИЯ ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("meal_"), Survey.meal_plan)
async def s_meal_plan(cb: types.CallbackQuery, state: FSMContext):
    meals = {
        "meal_3": "3 раза в день", "meal_5": "Дробно 5-6 раз",
        "meal_interval": "Интервальное 16/8", "meal_flex": "Гибкий график",
    }
    await state.update_data(meal_plan=meals[cb.data])
    await state.set_state(Survey.psychotype)
    from core.diet_mode import PSYCHOTYPES
    kb2 = InlineKeyboardBuilder()
    for key, desc in PSYCHOTYPES.items():
        kb2.button(text=desc, callback_data=f"psycho_{key}")
    kb2.adjust(1)
    await cb.message.edit_text(
        f"{progress(17)}\n*Шаг 17 из {TOTAL_STEPS}*\n\n"
        "Как ты обычно ешь?\n_Поможет подобрать режим питания_",
        reply_markup=kb2.as_markup(), parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 17: ПСИХОТИП ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("psycho_"), Survey.psychotype)
async def s_psychotype(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(psychotype=cb.data.split("_", 1)[1])
    await state.set_state(Survey.stress_level)
    await ask_edit(cb, 18,
        "🧠 *Блок Г — Психология*\n\n"
        "Как часто ты испытываешь стресс?",
        kb(
            ("😌 Редко",     "stress_low"),
            ("😐 Иногда",    "stress_mid"),
            ("😟 Часто",     "stress_high"),
            ("🤯 Постоянно", "stress_always"),
        )
    )


# ── ШАГ 10: РАСПИСАНИЕ ─────────────────────────────────────────────────────

@router.message(Survey.schedule)
async def s_schedule(m: types.Message, state: FSMContext):
    text = m.text.strip().lower()
    if any(w in text for w in ["не знаю", "незнаю", "стандарт", "default"]):
        wake, bed = "07:00", "23:00"
    else:
        wake, bed = parse_time_smart(text)
        if not wake:
            wake, bed = "07:00", "23:00"
    await state.update_data(wake_up_time=wake, bedtime=bed)
    await state.set_state(Survey.sleep_hours)
    await ask(m, 11, "Сколько часов ты обычно спишь?",
        kb(
            ("😴 Меньше 6 часов", "sl_low"),
            ("🌙 6-7 часов",      "sl_mid"),
            ("✅ 7-8 часов",      "sl_good"),
            ("💤 Больше 9 часов", "sl_high"),
        )
    )


# ── ШАГ 11: СОН ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sl_"), Survey.sleep_hours)
async def s_sleep(cb: types.CallbackQuery, state: FSMContext):
    sl = {"sl_low": "< 6ч", "sl_mid": "6-7ч", "sl_good": "7-8ч", "sl_high": "9+ч"}
    await state.update_data(sleep_hours=sl[cb.data])
    await state.set_state(Survey.water)
    await ask_edit(cb, 12, "Сколько воды пьёшь в день?",
        kb(
            ("💧 Меньше 1 литра",  "w_low"),
            ("💧💧 1-1.5 литра",   "w_mid"),
            ("💧💧💧 1.5-2 литра", "w_good"),
            ("🌊 Больше 2 литров", "w_high"),
        )
    )


# ── ШАГ 12: ВОДА ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("w_"), Survey.water)
async def s_water(cb: types.CallbackQuery, state: FSMContext):
    w = {"w_low": "< 1л", "w_mid": "1-1.5л", "w_good": "1.5-2л", "w_high": "> 2л"}
    await state.update_data(water_daily=w[cb.data])
    await state.set_state(Survey.restrictions)
    await ask_edit(cb, 13,
        "🍽 *Блок В — Питание*\n\n"
        "Пищевые ограничения?",
        kb(
            ("✅ Нет ограничений", "rest_none"),
            ("🌱 Вегетарианство",  "rest_veg"),
            ("🌿 Веганство",       "rest_vegan"),
            ("☪️ Халяль",          "rest_halal"),
            ("⚠️ Есть аллергии",   "rest_allergy"),
        )
    )


# ── ШАГ 5: ГОРОД ───────────────────────────────────────────────────────────

@router.message(Survey.city)
async def s_city(m: types.Message, state: FSMContext):
    city = m.text.strip()
    tz_map = {
        "москва":3,"санкт-петербург":3,"питер":3,"спб":3,
        "екатеринбург":5,"новосибирск":7,"красноярск":7,
        "иркутск":8,"якутск":9,"хабаровск":10,"владивосток":10,
        "магадан":11,"калининград":2,"самара":4,"уфа":5,
        "пермь":5,"челябинск":5,"омск":6,"томск":7,"тюмень":5,
        "нефтеюганск":5,"казань":3,"нижний новгород":3,
        "ростов":3,"краснодар":3,"воронеж":3,
    }
    utc_offset = tz_map.get(city.lower(), 3)
    await state.update_data(city=city, utc_offset=utc_offset)
    await state.set_state(Survey.goal)
    await ask(m, 6,
        "💪 *Блок Б — Тело и активность*\n\n"
        "Какая главная цель?",
        kb(
            ("🔥 Похудение",      "goal_loss"),
            ("💪 Набор массы",    "goal_gain"),
            ("❤️ Здоровье",       "goal_health"),
            ("⚡ Больше энергии", "goal_energy"),
            ("🧘 Детокс / очищение", "goal_detox"),
        )
    )


# ── ШАГ 18: УРОВЕНЬ СТРЕССА ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("stress_"), Survey.stress_level)
async def s_stress_level(cb: types.CallbackQuery, state: FSMContext):
    sl = {"stress_low":"Редко","stress_mid":"Иногда",
          "stress_high":"Часто","stress_always":"Постоянно"}
    await state.update_data(stress_level=sl[cb.data])
    await state.set_state(Survey.stress_coping)
    await ask_edit(cb, 19,
        "Когда всё идёт не так — что помогает прийти в себя?",
        kb(
            ("🏃 Двигаюсь / гуляю",    "cope_sport"),
            ("🍕 Ем что-нибудь вкусное","cope_food"),
            ("💬 Общаюсь с людьми",     "cope_social"),
            ("🎧 Музыка / фильмы",      "cope_media"),
            ("😴 Сплю или отдыхаю",     "cope_sleep"),
            ("🌀 Само проходит",        "cope_alone"),
        )
    )


# ── ШАГ 19: КАК СПРАВЛЯЕШЬСЯ ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("cope_"), Survey.stress_coping)
async def s_stress_coping(cb: types.CallbackQuery, state: FSMContext):
    cope = {"cope_sport":"Спорт","cope_food":"Еда","cope_social":"Общение",
            "cope_media":"Медиа","cope_sleep":"Сон","cope_alone":"Само проходит"}
    await state.update_data(stress_coping=cope[cb.data])
    await state.set_state(Survey.food_meaning)
    await ask_edit(cb, 20,
        "Еда для тебя — это в первую очередь что?",
        kb(
            ("⚡ Топливо — просто энергия", "fm_fuel"),
            ("🎉 Удовольствие и радость",   "fm_joy"),
            ("🏆 Награда за усилия",        "fm_reward"),
            ("🤗 Утешение когда плохо",     "fm_comfort"),
            ("👥 Способ общаться",          "fm_social"),
        )
    )


# ── ШАГ 20: СМЫСЛ ЕДЫ ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("fm_"), Survey.food_meaning)
async def s_food_meaning(cb: types.CallbackQuery, state: FSMContext):
    fm = {"fm_fuel":"Топливо","fm_joy":"Удовольствие","fm_reward":"Награда",
          "fm_comfort":"Утешение","fm_social":"Общение"}
    await state.update_data(food_meaning=fm[cb.data])
    await state.set_state(Survey.self_attitude)
    await ask_edit(cb, 21,
        "Если сорвался с режима — как относишься к этому?",
        kb(
            ("😤 Злюсь на себя",                 "sa_angry"),
            ("😟 Расстраиваюсь, но иду дальше",  "sa_sad"),
            ("🤷 Нормально, бывает",             "sa_ok"),
            ("😄 Не парюсь",                     "sa_cool"),
        )
    )


# ── ШАГ 21: ОТНОШЕНИЕ К СРЫВУ ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("sa_"), Survey.self_attitude)
async def s_self_attitude(cb: types.CallbackQuery, state: FSMContext):
    sa = {"sa_angry":"Злюсь","sa_sad":"Расстраиваюсь","sa_ok":"Нормально","sa_cool":"Не парюсь"}
    await state.update_data(self_attitude=sa[cb.data])
    await state.set_state(Survey.fin_income)
    await ask_edit(cb, 22,
        "💰 *Блок Д — Финансы*\n\nПримерный доход в месяц?",
        kb(
            ("До 30 000 ₽",       "inc_low"),
            ("30–60 000 ₽",       "inc_mid"),
            ("60–100 000 ₽",      "inc_high"),
            ("Больше 100 000 ₽",  "inc_top"),
            ("Не скажу",          "inc_skip"),
        )
    )


# ── ШАГ 22: ДОХОД ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("inc_"), Survey.fin_income)
async def s_fin_income(cb: types.CallbackQuery, state: FSMContext):
    inc = {"inc_low":"< 30к","inc_mid":"30-60к","inc_high":"60-100к",
           "inc_top":"> 100к","inc_skip":"не указан"}
    await state.update_data(fin_income=inc[cb.data])
    await state.set_state(Survey.fin_expenses)
    await ask_edit(cb, 23,
        "Сколько тратишь в месяц (кроме еды)?",
        kb(
            ("До 15 000 ₽",      "exp_low"),
            ("15–30 000 ₽",      "exp_mid"),
            ("30–60 000 ₽",      "exp_high"),
            ("Больше 60 000 ₽",  "exp_top"),
            ("Не знаю",          "exp_skip"),
        )
    )


# ── ШАГ 23: РАСХОДЫ ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("exp_"), Survey.fin_expenses)
async def s_fin_expenses(cb: types.CallbackQuery, state: FSMContext):
    exp = {"exp_low":"< 15к","exp_mid":"15-30к","exp_high":"30-60к",
           "exp_top":"> 60к","exp_skip":"не знаю"}
    await state.update_data(fin_expenses=exp[cb.data])
    await state.set_state(Survey.fin_goal)
    await ask_edit(cb, 24,
        "Есть финансовая цель на ближайший год?",
        kb(
            ("✈️ Отпуск / путешествие",  "fg_travel"),
            ("🚗 Машина / ремонт",       "fg_car"),
            ("📱 Гаджет / покупка",      "fg_gadget"),
            ("🆘 Подушка безопасности",  "fg_safety"),
            ("🎓 Обучение / курсы",      "fg_edu"),
            ("Нет цели",                "fg_none"),
        )
    )


# ── ШАГ 24: ФИНАНСОВАЯ ЦЕЛЬ ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("fg_"), Survey.fin_goal)
async def s_fin_goal(cb: types.CallbackQuery, state: FSMContext):
    fg = {"fg_travel":"Отпуск","fg_car":"Машина","fg_gadget":"Гаджет",
          "fg_safety":"Подушка","fg_edu":"Обучение","fg_none":"Нет"}
    await state.update_data(fin_goal=fg[cb.data])
    await state.set_state(Survey.content_genres)
    await ask_edit(cb, 25,
        "🎬 *Блок Е — Контент*\n\nЛюбимые жанры кино?",
        kb(
            ("😂 Комедии",         "cg_comedy"),
            ("🎭 Драмы",           "cg_drama"),
            ("🚀 Фантастика",      "cg_scifi"),
            ("🕵️ Детективы",      "cg_detective"),
            ("😱 Триллеры",        "cg_thriller"),
            ("🌍 Документальное",  "cg_doc"),
        )
    )


# ── ШАГ 25: ЖАНРЫ КИНО ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cg_"), Survey.content_genres)
async def s_content_genres(cb: types.CallbackQuery, state: FSMContext):
    cg = {"cg_comedy":"Комедии","cg_drama":"Драмы","cg_scifi":"Фантастика",
          "cg_detective":"Детективы","cg_thriller":"Триллеры","cg_doc":"Документальное"}
    await state.update_data(content_genres=cg.get(cb.data,"любые"))
    await state.set_state(Survey.music_taste)
    await ask_edit(cb, 26,
        "Какую музыку слушаешь?",
        kb(
            ("🎸 Рок / металл",    "mt_rock"),
            ("🎵 Поп / электро",   "mt_pop"),
            ("🎷 Джаз / блюз",     "mt_jazz"),
            ("🎤 Хип-хоп / рэп",   "mt_hiphop"),
            ("🎻 Классика",        "mt_classic"),
            ("🌊 Lo-fi / ambient", "mt_lofi"),
        )
    )


# ── ШАГ 26: МУЗЫКА ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mt_"), Survey.music_taste)
async def s_music_taste(cb: types.CallbackQuery, state: FSMContext):
    mt = {"mt_rock":"Рок","mt_pop":"Поп","mt_jazz":"Джаз",
          "mt_hiphop":"Хип-хоп","mt_classic":"Классика","mt_lofi":"Lo-fi"}
    await state.update_data(music_taste=mt.get(cb.data,"разная"))
    await state.set_state(Survey.book_genres)
    await ask_edit(cb, 27,
        "Читаешь ли книги? Если да — какие?",
        kb(
            ("📚 Нон-фикшн / саморазвитие", "bg_nonfic"),
            ("🚀 Фантастика",               "bg_scifi"),
            ("🕵️ Детективы",               "bg_det"),
            ("💼 Бизнес / психология",      "bg_biz"),
            ("📖 Классика",                 "bg_classic"),
            ("🚫 Не читаю",                 "bg_none"),
        )
    )


# ── ШАГ 27: КНИГИ ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bg_"), Survey.book_genres)
async def s_book_genres(cb: types.CallbackQuery, state: FSMContext):
    bg = {"bg_nonfic":"Нон-фикшн","bg_scifi":"Фантастика","bg_det":"Детективы",
          "bg_biz":"Бизнес","bg_classic":"Классика","bg_none":"Не читаю"}
    await state.update_data(book_genres=bg.get(cb.data,"любые"))
    await state.set_state(Survey.hobby)
    await ask_edit(cb, 28,
        "🌍 *Блок Ж — Образ жизни*\n\n"
        "Расскажи о себе — хобби, работа, чем занимаешься?\n"
        "_Это поможет сделать план ближе к реальности_"
    )


# ── ШАГ 28: ХОББИ ─────────────────────────────────────────────────────────

@router.message(Survey.hobby)
async def s_hobby(m: types.Message, state: FSMContext):
    await state.update_data(hobby=m.text.strip())
    await state.set_state(Survey.travel_freq)
    await ask(m, 29,
        "Как часто путешествуешь?",
        kb(
            ("🚫 Почти никогда",     "tf_never"),
            ("✈️ 1-2 раза в год",    "tf_rare"),
            ("🌍 3-5 раз в год",     "tf_mid"),
            ("🧳 Постоянно в дороге","tf_often"),
        )
    )


# ── ШАГ 29: ПУТЕШЕСТВИЯ ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tf_"), Survey.travel_freq)
async def s_travel_freq(cb: types.CallbackQuery, state: FSMContext):
    tf = {"tf_never":"Редко","tf_rare":"1-2/год","tf_mid":"3-5/год","tf_often":"Часто"}
    await state.update_data(travel_freq=tf.get(cb.data,"редко"))
    await state.set_state(Survey.lifemode_choice)

    kb2 = InlineKeyboardBuilder()
    kb2.button(text="🔥 Сушка — похудеть",           callback_data="lm_cut")
    kb2.button(text="💪 Масса — набрать мышцы",       callback_data="lm_bulk")
    kb2.button(text="❤️ Здоровье — баланс",           callback_data="lm_health")
    kb2.button(text="⚡ Энергия — продуктивность",    callback_data="lm_energy")
    kb2.button(text="🧘 Детокс — очищение",           callback_data="lm_detox")
    kb2.button(text="✈️ Отпуск — накопить и поехать", callback_data="lm_vacation")
    kb2.adjust(1)

    await cb.message.edit_text(
        f"🎉 *Шаг 30 из 30 — Последний!*\n\n"
        "🎯 *Выбери свой режим жизни*\n\n"
        "Это главный параметр — настроит питание, тренировки, "
        "финансы и контент под одну цель:",
        reply_markup=kb2.as_markup(),
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 30: LIFEMODE — ФИНАЛ ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("lm_"), Survey.lifemode_choice)
async def s_lifemode_final(cb: types.CallbackQuery, state: FSMContext):
    mode_map = {"lm_cut":"cut","lm_bulk":"bulk","lm_health":"health",
                "lm_energy":"energy","lm_detox":"detox","lm_vacation":"vacation"}
    mode = mode_map.get(cb.data, "health")

    data = await state.get_data()
    data["lifemode"] = mode
    data["current_vibe"] = "observer"
    data["diet_level"] = 3  # дефолт

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    db.save_profile(data)

    try:
        from core.lifemode_agent import LifeModeAgent, MODES
        lm = LifeModeAgent(user_id)
        lm.set(mode, "moderate")
        mode_cfg = MODES.get(mode, MODES["health"])
        mode_label = mode_cfg["label"]
        mode_hint = mode_cfg["diet_hint"][:80]
    except Exception:
        mode_label = mode
        mode_hint = ""

    setup_user_jobs(user_id,
                    data.get("wake_up_time", "07:00"),
                    data.get("bedtime", "23:00"))

    await state.clear()
    await cb.answer()

    await cb.message.answer(
        f"✅ *Готово, {data.get('name')}!*\n\n"
        f"Режим активирован: *{mode_label}*\n"
        f"_{mode_hint}_\n\n"
        "Генерирую персональный план...\n"
        "⏳ 1-2 минуты.",
        reply_markup=get_main_kb(user_id),
        parse_mode="Markdown"
    )

    await _generate_onboarding(cb.message, user_id, data, db)


async def _generate_onboarding(m: types.Message, user_id: int, data: dict, db: MemoryManager):
    """
    Генерация плана после анкеты.
    - Все Gemini вызовы идут через asyncio.to_thread → event loop не блокируется.
    - Retry-цикл: крутится пока не получим результат (или 5 попыток).
    - После успеха отправляет дашборд как HTML-файл + кнопку «Скачать».
    """
    status_msg = await m.answer("🤔 Анализирую твой профиль...")
    ai = GeminiEngine(data)

    results = {}

    # Шаг 1 — один большой вызов: всё сразу (диета 7 дней + дашборд + покупки)
    try:
        await status_msg.edit_text(
            "`[▓░░]` 1/3\n\n🤖 Gemini генерирует твой план...\n_(может занять 30-60 сек)_",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await m.bot.send_chat_action(user_id, "typing")

    from bot.scheduler_logic import build_dashboard_bytes
    _uid, _data = user_id, data
    results["dashboard_bytes"] = await _safe_call_async(
        lambda uid=_uid, d=_data: build_dashboard_bytes(uid, d)
    )

    # Шаг 2 — диета текстом для отправки в чат (из кэша dashboard)
    try:
        await status_msg.edit_text(
            "`[▓▓░]` 2/3\n\n📋 Формирую чеклист и советы...",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await m.bot.send_chat_action(user_id, "typing")
    # Генерируем текстовую диету для отправки в чат
    results["diet"] = await _safe_call_async(ai.generate_weekly_diet)

    try:
        await status_msg.edit_text(
            "`[▓▓▓]` 3/3\n\n✅ Почти готово, собираю всё вместе...",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await m.bot.send_chat_action(user_id, "typing")

    # Убираем прогресс-бар
    try:
        await status_msg.delete()
    except Exception:
        pass

    # Сохраняем список покупок в БД
    if results.get("shopping"):
        try:
            db.save_shopping_list(results["shopping"])
        except Exception:
            pass

    # ── Отправляем диету ────────────────────────────────────────
    diet = results.get("diet")
    if diet:
        async def _send_chunk(text: str):
            """Конвертирует Markdown → HTML и отправляет. При ошибке — plain text."""
            import re
            # Markdown → HTML конвертация
            html = text
            # **жирный** → <b>жирный</b>
            html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
            # *курсив* → <i>курсив</i>
            html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
            # ### Заголовок → <b>Заголовок</b>
            html = re.sub(r'^#{1,3}\s+(.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
            # `код` → <code>код</code>
            html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
            # --- → разделитель
            html = html.replace('---', '—' * 10)
            try:
                await m.answer(html, parse_mode="HTML")
            except Exception:
                await m.answer(text)  # fallback — plain text

        # Режем на части по 3500 символов по границе дней/разделов
        CHUNK = 3500
        if len(diet) <= CHUNK:
            await _send_chunk(diet)
        else:
            chunks = []
            remaining = diet
            while len(remaining) > CHUNK:
                # Ищем ближайший перенос строки перед границей
                cut = remaining.rfind("\nДень ", 0, CHUNK)
                if cut < 200:
                    cut = remaining.rfind("\n", 0, CHUNK)
                if cut < 100:
                    cut = CHUNK
                chunks.append(remaining[:cut])
                remaining = remaining[cut:]
            chunks.append(remaining)
            for i, chunk in enumerate(chunks):
                await _send_chunk(chunk)
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)
    else:
        await m.answer(
            "Профиль сохранён ✅\nДиету пришлю чуть позже — напиши *составь мне диету*",
            parse_mode="Markdown"
        )

    # ── Отправляем HTML-дашборд как файл ────────────────────────
    dashboard_bytes = results.get("dashboard_bytes")
    if dashboard_bytes:
        from aiogram.types import BufferedInputFile
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="📅 /plan — обновить план", callback_data="noop")
        kb.button(text="🛒 /shopping — покупки",   callback_data="noop")
        await m.answer_document(
            BufferedInputFile(dashboard_bytes, filename="my_day.html"),
            caption="☀️ *Твой персональный дашборд готов!*\nОткрой файл в браузере 👆",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
    else:
        await m.answer("Дашборд пришлю утром — или вызови /plan вручную")

    # ── Итоговое сообщение ───────────────────────────────────────
    shopping_ok  = "✅" if results.get("shopping")        else "⚠️"
    dashboard_ok = "✅" if results.get("dashboard_bytes") else "⚠️"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🍳 Рецепты на сегодня → /recipes", callback_data="noop")
    kb.button(text="🛒 Список покупок → /shopping",    callback_data="noop")
    kb.button(text="📅 Обновить план → /plan",          callback_data="noop")
    kb.adjust(1)

    await m.answer(
        f"🎉 *Всё готово!*\n\n"
        f"{shopping_ok} Список покупок → /shopping\n"
        f"{dashboard_ok} Утренний план → /plan\n"
        f"🍳 Рецепты на сегодня → /recipes\n"
        f"⚖️ Записывай вес → /weight 78.5\n\n"
        "Утром буду присылать план автоматически 🌅\n"
        "Вечером сверимся как прошло 🌙",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


async def _safe_call_async(fn, retries: int = 5):
    """
    Запускает синхронную fn() в отдельном потоке (asyncio.to_thread).
    Не блокирует event loop → Telegram не шлёт повторные апдейты.
    Retry-цикл с экспоненциальной задержкой при ошибках Gemini.
    """
    from core.key_manager import rotate_key
    for attempt in range(retries):
        try:
            result = await asyncio.to_thread(fn)
            return result
        except Exception as e:
            err = str(e).lower()
            logger.warning(f"_safe_call_async attempt {attempt+1}/{retries}: {e}")
            if "429" in err or "quota" in err or "rate" in err:
                rotate_key()
                wait = min(5 * (attempt + 1), 30)
                logger.info(f"Rate limit — ротирую ключ, жду {wait}s")
                await asyncio.sleep(wait)
            elif attempt < retries - 1:
                await asyncio.sleep(3 * (attempt + 1))
            else:
                logger.error(f"Все {retries} попыток провалились: {e}")
                return None
    return None
