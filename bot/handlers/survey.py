"""
bot/handlers/survey.py
Анкета онбординга v2 — 13 шагов без Gemini
Gemini вызывается ОДИН РАЗ в самом конце одним блоком.
Прогресс-бар + статусные сообщения пока думает.
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
from plugins.idea_factory import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()

TOTAL_STEPS = 15


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
    psychotype   = State()
    diet_level   = State()


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
    await state.set_state(Survey.name)
    await ask(message, 1, "Давай познакомимся 🤝\n\nКак тебя зовут?")


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
    await state.set_state(Survey.goal)
    await ask(m, 5, "Какая твоя главная цель?",
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
    await ask_edit(cb, 6, "Уровень активности?",
        kb(
            ("🪑 Сидячая работа",     "act_low"),
            ("🚶 Лёгкая активность",  "act_light"),
            ("🏃 Спорт 3-5 дней/нед", "act_mid"),
            ("🏋️ Физический труд",    "act_high"),
        )
    )


# ── ШАГ 6: АКТИВНОСТЬ ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("act_"), Survey.activity)
async def s_activity(cb: types.CallbackQuery, state: FSMContext):
    acts = {
        "act_low": "Сидячая работа", "act_light": "Лёгкая активность",
        "act_mid": "Спорт 3-5 дней в неделю", "act_high": "Физический труд",
    }
    await state.update_data(activity=acts[cb.data])
    await state.set_state(Survey.restrictions)
    await ask_edit(cb, 7, "Пищевые ограничения?",
        kb(
            ("✅ Нет ограничений", "rest_none"),
            ("🌱 Вегетарианство",  "rest_veg"),
            ("🌿 Веганство",       "rest_vegan"),
            ("☪️ Халяль",          "rest_halal"),
            ("⚠️ Есть аллергии",   "rest_allergy"),
        )
    )


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
        await ask_edit(cb, 8, "На что именно аллергия? Напиши через запятую")
    else:
        await ask_edit(cb, 8, "Продукты которые не любишь или не ешь?\n\nНапиши или отправь *нет*")


# ── ШАГ 8: НЕЛЮБИМОЕ ──────────────────────────────────────────────────────

@router.message(Survey.dislikes)
async def s_dislikes(m: types.Message, state: FSMContext):
    await state.update_data(dislikes=m.text.strip())
    await state.set_state(Survey.budget)
    await ask(m, 9,
        "Бюджет на питание в день?\n\n"
        "Можно написать: `500`, `около 500 рублей`, `пятьсот`"
    )


# ── ШАГ 9: БЮДЖЕТ ──────────────────────────────────────────────────────────

@router.message(Survey.budget)
async def s_budget(m: types.Message, state: FSMContext):
    nums = re.findall(r'\d+', m.text)
    budget = nums[0] if nums else m.text.strip()
    await state.update_data(budget=budget)
    await state.set_state(Survey.meal_plan)
    await ask(m, 10, "Как удобнее питаться?",
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
    await ask_edit(cb, 11,
        "Во сколько просыпаешься и ложишься?\n\n"
        "Напиши как удобно:\n"
        "`07:00 23:00` или `в семь утра, в одиннадцать`\n"
        "_Не знаешь — напиши *не знаю*_"
    )


# ── ШАГ 11: РАСПИСАНИЕ ─────────────────────────────────────────────────────

@router.message(Survey.schedule)
async def s_schedule(m: types.Message, state: FSMContext):
    text = m.text.strip().lower()
    if any(w in text for w in ["не знаю", "незнаю", "стандарт", "default", "обычно"]):
        wake, bed = "07:00", "23:00"
    else:
        wake, bed = parse_time_smart(text)
        if not wake:
            wake, bed = "07:00", "23:00"
    await state.update_data(wake_up_time=wake, bedtime=bed)
    await state.set_state(Survey.timezone)
    await ask(m, 12, "В каком городе живёшь?\n\nНапример: `Москва`, `Хабаровск`")


# ── ШАГ 12: ГОРОД ──────────────────────────────────────────────────────────

@router.message(Survey.timezone)
async def s_timezone(m: types.Message, state: FSMContext):
    city = m.text.strip()
    tz_map = {
        "москва": 3, "санкт-петербург": 3, "питер": 3, "спб": 3,
        "екатеринбург": 5, "новосибирск": 7, "красноярск": 7,
        "иркутск": 8, "якутск": 9, "хабаровск": 10, "владивосток": 10,
        "магадан": 11, "камчатка": 12, "калининград": 2, "самара": 4,
        "уфа": 5, "пермь": 5, "челябинск": 5, "омск": 6, "томск": 7,
        "барнаул": 7, "чита": 9, "казань": 3, "нижний новгород": 3,
        "ростов": 3, "краснодар": 3, "воронеж": 3, "тюмень": 5,
    }
    utc_offset = tz_map.get(city.lower(), 3)
    await state.update_data(city=city, utc_offset=utc_offset)
    await state.set_state(Survey.hobby)
    await ask(m, 13,
        "Последний шаг! 🎉\n\n"
        "Расскажи о себе — хобби, работа, образ жизни?\n"
        "_Это поможет сделать план ближе к реальности_"
    )


# ── ШАГ 13: ХОББИ → переход к психотипу ───────────────────────────────────

@router.message(Survey.hobby)
async def s_hobby(m: types.Message, state: FSMContext):
    await state.update_data(hobby=m.text.strip())
    await state.set_state(Survey.psychotype)

    from core.diet_mode import PSYCHOTYPES
    kb = InlineKeyboardBuilder()
    for key, desc in PSYCHOTYPES.items():
        kb.button(text=desc, callback_data=f"psycho_{key}")
    kb.adjust(1)

    await m.answer(
        "🧠 *Почти готово! Шаг 14/15*\n\n"
        "Как ты обычно ешь?\n"
        "_Это поможет подобрать правильный режим_",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


# ── ШАГ 14: ПСИХОТИП ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("psycho_"), Survey.psychotype)
async def s_psychotype(cb: types.CallbackQuery, state: FSMContext):
    psycho = cb.data.split("_", 1)[1]
    await state.update_data(psychotype=psycho)
    await state.set_state(Survey.diet_level)

    # Получаем данные для умного предложения уровня
    data = await state.get_data()
    from core.diet_mode import suggest_level, LEVELS, get_all_levels_text
    sugg_level, explanation = suggest_level({**data, "psychotype": psycho})

    kb = InlineKeyboardBuilder()
    for lvl, info in LEVELS.items():
        mark = "⭐ " if lvl == sugg_level else ""
        kb.button(text=f"{mark}{info['name']}", callback_data=f"level_{lvl}")
    kb.adjust(1)

    await cb.message.edit_text(
        f"*Шаг 15/15 — Режим питания*\n\n"
        f"💡 {explanation}\n\n"
        f"*1.* 🌿 Интуитивное — общие советы\n"
        f"*2.* 🥗 Сбалансированное — без фанатизма\n"
        f"*3.* ⚡ Активное — чёткий план\n"
        f"*4.* 🏋️ Спортивное — под тренировки\n"
        f"*5.* 🔥 Максимум — жёсткий протокол\n\n"
        f"Выбери свой уровень:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await cb.answer()


# ── ШАГ 15: УРОВЕНЬ + ФИНАЛ ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("level_"), Survey.diet_level)
async def s_final(cb: types.CallbackQuery, state: FSMContext):
    level = int(cb.data.split("_")[1])
    data  = await state.get_data()
    data["diet_level"]   = level
    data["current_vibe"] = "observer"

    from core.diet_mode import LEVELS
    level_info = LEVELS[level]

    user_id = cb.from_user.id
    db      = MemoryManager(user_id)
    db.save_profile(data)
    setup_user_jobs(user_id, data["wake_up_time"], data["bedtime"])

    await state.clear()
    await cb.answer()

    await cb.message.answer(
        f"✅ *Профиль сохранён, {data.get('name')}!*\n\n"
        f"Режим: {level_info['name']}\n"
        f"_{level_info['desc']}_\n\n"
        "Сейчас готовлю твой персональный план — "
        "диету на 7 дней, список покупок и дашборд.\n\n"
        "⏳ Обычно занимает *1-2 минуты* — просто подожди.",
        reply_markup=get_main_keyboard(),
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

    STEPS = [
        ("🥗 Составляю диету на 7 дней...",  "_gen_diet"),
        ("🛒 Формирую список покупок...",     "_gen_shopping"),
        ("☀️ Готовлю дашборд на сегодня...", "_gen_dashboard"),
    ]
    results = {}

    for i, (status_text, key) in enumerate(STEPS):
        bar = "▓" * (i + 1) + "░" * (len(STEPS) - i - 1)
        try:
            await status_msg.edit_text(
                f"`[{bar}]` {i+1}/{len(STEPS)}\n\n{status_text}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await m.bot.send_chat_action(user_id, "typing")

        if key == "_gen_diet":
            results["diet"] = await _safe_call_async(ai.generate_weekly_diet)

        elif key == "_gen_shopping":
            diet = results.get("diet")
            if diet:
                results["shopping"] = await _safe_call_async(
                    lambda: ai.generate_shopping_list_structured(diet)
                )

        elif key == "_gen_dashboard":
            from bot.scheduler_logic import build_dashboard_bytes
            _uid, _data = user_id, data
            results["dashboard_bytes"] = await _safe_call_async(
                lambda uid=_uid, d=_data: build_dashboard_bytes(uid, d)
            )

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
        async def _send_diet(text: str):
            """Отправляет текст с Markdown, при ошибке парсинга — без форматирования."""
            try:
                await m.answer(text, parse_mode="Markdown")
            except Exception:
                await m.answer(text)

        if len(diet) > 4000:
            mid = diet.find("\n*День 4")
            split = mid if mid > 0 else 4000
            await _send_diet(diet[:split])
            await asyncio.sleep(0.3)
            await _send_diet(diet[split:])
        else:
            await _send_diet(diet)
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
