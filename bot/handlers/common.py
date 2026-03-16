"""
bot/handlers/common.py
Общие команды + чат с историей + вес + холодильник + список покупок
"""

import re
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import default_state
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from bot.config import ADMIN_ID

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "друг"
    db = MemoryManager(user_id)
    profile = db.get_profile()
    has_profile = bool(profile and profile.get("name"))

    # Получаем текущий LifeMode если есть
    mode_str = ""
    if has_profile:
        try:
            from core.lifemode_agent import LifeModeAgent
            lm = LifeModeAgent(user_id)
            mode_str = f"\n{lm.label()}"
        except Exception:
            pass

    if has_profile:
        greeting = f"С возвращением, {name} 👋{mode_str}"
        subtitle = "Выбери раздел:"
    else:
        greeting = f"Привет, {name}! Я *Wingman* 🌿"
        subtitle = "Твой личный помощник по питанию, финансам и досугу.\nВыбери с чего начать:"

    await message.answer(
        f"{greeting}\n\n{subtitle}",
        parse_mode="Markdown",
        reply_markup=_main_menu_kb(has_profile)
    )


def _main_menu_kb(has_profile: bool = True):
    """Главное меню — 1 большая кнопка + 6 разделов 2×3."""
    kb = InlineKeyboardBuilder()

    # Большая зелёная START / МЕНЮ кнопка
    if has_profile:
        kb.row(InlineKeyboardButton(
            text="🟢  ОТКРЫТЬ МОЙ ПЛАН  🟢",
            callback_data="menu_plan"
        ))
    else:
        kb.row(InlineKeyboardButton(
            text="🟢  НАЧАТЬ  —  ЗАПОЛНИТЬ АНКЕТУ  🟢",
            callback_data="menu_survey"
        ))

    # 6 разделов — 2 столбца × 3 строки
    kb.row(
        InlineKeyboardButton(text="🥗\nДиета",    callback_data="sect_diet"),
        InlineKeyboardButton(text="🏋️\nФитнес",   callback_data="sect_fitness"),
    )
    kb.row(
        InlineKeyboardButton(text="💰\nФинансы",  callback_data="sect_finance"),
        InlineKeyboardButton(text="🎬\nКино",     callback_data="sect_movie"),
    )
    kb.row(
        InlineKeyboardButton(text="🎵📚\nМузыка & Книги", callback_data="sect_media"),
        InlineKeyboardButton(text="🎯\nРежим",    callback_data="sect_lifemode"),
    )
    return kb.as_markup()


# ── Обработчики главного меню ─────────────────────────────────────────────

@router.callback_query(F.data == "menu_plan")
async def cb_menu_plan(cb: types.CallbackQuery):
    await cb.answer()
    await cb.bot.send_message(cb.from_user.id, "/plan")


@router.callback_query(F.data == "menu_survey")
async def cb_menu_survey(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.answer("📝 Начинаем анкету!\n\nНапиши *анкета* или /survey", parse_mode="Markdown")


@router.callback_query(F.data == "menu_back")
async def cb_menu_back(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    has_profile = bool(db.get_profile())
    await cb.message.edit_reply_markup(reply_markup=_main_menu_kb(has_profile))
    await cb.answer()


# ── Подменю разделов ──────────────────────────────────────────────────────

SUBMENUS_INLINE = {

    "sect_diet": {
        "title": "🥗 *Диета и питание*",
        "items": [
            ("📋 План на сегодня",     "nav_plan"),
            ("🥗 Меню на неделю",      "nav_diet"),
            ("🍳 Рецепты",             "nav_recipes"),
            ("🛒 Список покупок",      "nav_shopping"),
            ("🧊 Из холодильника",     "nav_fridge"),
            ("🎯 Режим питания",       "nav_mode"),
        ],
    },

    "sect_fitness": {
        "title": "🏋️ *Фитнес и активность*",
        "items": [
            ("⚖️ Внести вес",          "nav_weight"),
            ("📊 Прогресс / график",   "nav_progress"),
            ("🔥 Мой стрик",          "nav_streak"),
            ("☀️ Утренний настрой",    "nav_morning"),
            ("📅 Событие дня",        "nav_event"),
            ("👤 Мой профиль",        "nav_profile"),
        ],
    },

    "sect_finance": {
        "title": "💰 *Финансы*",
        "items": [
            ("🎯 Мои цели",            "fin_goals"),
            ("📊 За этот месяц",       "fin_month"),
            ("➕ Добавить доход",      "fin_add_income"),
            ("➖ Добавить расход",     "fin_add_expense"),
            ("📸 Сфотографировать чек","fin_receipt"),
            ("🤖 Анализ и советы",    "fin_analysis"),
        ],
    },

    "sect_movie": {
        "title": "🎬 *Кино*",
        "items": [
            ("😂 Комедия / лёгкое",    "cg_funny"),
            ("🧠 Умное / артхаус",    "cg_smart"),
            ("🌟 Вдохновляющее",      "cg_inspiring"),
            ("😱 Триллер / ужасы",    "cg_horror"),
            ("🌍 Приключения",        "cg_adventure"),
            ("🤷 Любой жанр",         "cg_any"),
        ],
    },

    "sect_media": {
        "title": "🎵📚 *Музыка и книги*",
        "items": [
            ("⚡ Энергичная музыка",   "mm_energetic"),
            ("😌 Расслабляющая",      "mm_chill"),
            ("🌙 Ночная атмосфера",   "mm_night"),
            ("📚 Книга под цель",     "bk_nonfiction"),
            ("🚀 Фантастика",         "bk_sci-fi"),
            ("🧘 Психология / рост",  "bk_psychology"),
        ],
    },

    "sect_lifemode": {
        "title": "🎯 *Режим жизни (LifeMode)*",
        "items": [
            ("🔥 Сушка",              "lm_set_cut"),
            ("💪 Набор массы",        "lm_set_bulk"),
            ("❤️ Здоровье",           "lm_set_health"),
            ("⚡ Энергия",            "lm_set_energy"),
            ("🧘 Детокс",             "lm_set_detox"),
            ("✈️ Отпуск / цель",      "lm_set_vacation"),
        ],
    },
}


@router.callback_query(F.data.startswith("sect_"))
async def cb_section(cb: types.CallbackQuery):
    sect = cb.data
    cfg = SUBMENUS_INLINE.get(sect)
    if not cfg:
        await cb.answer("Раздел не найден")
        return

    kb = InlineKeyboardBuilder()
    items = cfg["items"]
    # 2 кнопки в ряд
    for i in range(0, len(items), 2):
        row = []
        for label, data in items[i:i+2]:
            row.append(InlineKeyboardButton(text=label, callback_data=data))
        kb.row(*row)
    # Кнопка назад
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back"))

    await cb.message.edit_text(
        cfg["title"] + "\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "*Команды:*\n\n"
        "📋 *анкета* — настройка профиля\n"
        "/plan — план на день\n"
        "/tasks — задачи на сегодня\n"
        "/recipes — рецепты на сегодня 🍳\n"
        "/weight 78.5 — записать вес\n"
        "/progress — динамика веса\n"
        "/shopping — список покупок\n"
        "/fridge — рецепты из холодильника\n\n"
        "🎯 *Режим питания:*\n"
        "/mode — текущий режим\n"
        "/setmode — выбрать уровень 1-5\n"
        "/psychotype — мой психотип\n"
        "/morning — настроение утром\n"
        "/event [событие] — событие сегодня\n"
        "/streak — мой стрик\n\n"
        "/vibe — сменить настроение\n"
        "/seen [название] — в stop-list\n"
        "/feedback [текст] — отзыв\n"
        "/streak — мой стрик\n\n"
        "💡 *Idea Factory:*\n"
        "/idea [тема] — сгенерировать идею\n"
        "/idea\\_pipeline [тема] — топ-3 из 5 модулей\n"
        "/idea\\_list — список 20 субмодулей\n\n"
        "🔑 /keys — статус API ключей\n",
        parse_mode="Markdown"
    )


@router.message(Command("keys"))
async def cmd_keys(message: types.Message):
    """Статус ротации Gemini API ключей."""
    from core.key_manager import health, _km
    report = health()
    if not report:
        return await message.answer(
            "❌ Ключи не загружены! Проверь GEMINI\\_KEY\\_1 в Railway Variables.",
            parse_mode="Markdown"
        )
    lines = [f"🔑 *API ключи* ({_km.count()} шт.):\n"]
    lines.extend(f"`{line}`" for line in report)
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── ВАЙБ ───────────────────────────────────────────────────────────────────

@router.message(Command("vibe"))
async def cmd_vibe(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚡ Spark",    callback_data="set_vibe_spark"),
        InlineKeyboardButton(text="🌿 Observer", callback_data="set_vibe_observer"),
        InlineKeyboardButton(text="🌙 Twilight", callback_data="set_vibe_twilight"),
    )
    await message.answer("Выбери настроение на завтра:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("set_vibe_"))
async def set_vibe(cb: types.CallbackQuery):
    vibe = cb.data.replace("set_vibe_", "")
    db = MemoryManager(cb.from_user.id)
    db.set_vibe(vibe)
    labels = {
        "spark": "⚡ Spark — заряд",
        "observer": "🌿 Observer — баланс",
        "twilight": "🌙 Twilight — уют"
    }
    await cb.message.edit_text(f"Вайб на завтра: {labels.get(vibe, vibe)} ✅")
    await cb.answer()


# ── ПАМЯТЬ ─────────────────────────────────────────────────────────────────

@router.message(Command("forget"))
async def cmd_forget(message: types.Message):
    db = MemoryManager(message.from_user.id)
    db.reset_memory_light()
    await message.answer("Memory Light сброшен 🌱")


@router.message(Command("seen"))
async def cmd_seen(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Напиши: /seen Название")
    item = parts[1].strip()
    db = MemoryManager(message.from_user.id)
    db.add_to_stop_list(item)
    await message.answer(f"Записал: «{item}» — больше не предложу 👍")


# ── ЗАДАЧИ ─────────────────────────────────────────────────────────────────

@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    db = MemoryManager(message.from_user.id)
    tasks = db.get_tasks()
    if not tasks:
        return await message.answer(
            "Задач пока нет. Утром бот пришлёт план.\n"
            "Или добавь: /addtask Название"
        )
    text = "*Задачи на сегодня:*\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
    text += "\n\nДобавить: /addtask Название"
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("addtask"))
async def cmd_addtask(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Напиши: /addtask Название задачи")
    task = parts[1].strip()
    db = MemoryManager(message.from_user.id)
    ok = db.add_user_task(task)
    if ok:
        await message.answer(f"✅ Добавил: «{task}»")
    else:
        await message.answer("Задач уже 10 — максимум на день 💪")


# ── ПЛАН ───────────────────────────────────────────────────────────────────

@router.message(Command("plan"))
async def cmd_plan(message: types.Message):
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    if not db.get_profile():
        return await message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")
    await message.answer("Генерирую план... ⏳")
    from bot.scheduler_logic import send_morning_dashboard
    await send_morning_dashboard(user_id)


# ── ТРЕКЕР ВЕСА ────────────────────────────────────────────────────────────

@router.message(Command("weight"))
async def cmd_weight(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(
            "Напиши: /weight 78.5\n"
            "Для истории: /progress"
        )
    # Парсим число из текста
    nums = re.findall(r'\d+[.,]?\d*', parts[1])
    if not nums:
        return await message.answer("Не понял число. Напиши: /weight 78.5")

    weight = float(nums[0].replace(",", "."))
    db = MemoryManager(message.from_user.id)
    db.log_weight(weight)

    # Event Bus — обновляем состояние
    try:
        from core.event_bus import EventBus
        history_prev = db.get_weight_history(days=7)
        prev_weight = history_prev[1]["weight"] if len(history_prev) > 1 else None
        bus = EventBus(message.from_user.id, db)
        bus.emit_weight(weight, prev_weight)
    except Exception as _e:
        pass

    # Показываем динамику
    history = db.get_weight_history(days=30)
    if len(history) > 1:
        first = history[0]["weight"]
        diff = weight - first
        sign = "+" if diff > 0 else ""
        # Добавляем Daily Score
        try:
            from core.human_state import HumanStateEngine
            _state = HumanStateEngine(message.from_user.id, db)
            score = _state.get_daily_score()
            score_line = f"\nСамочувствие: {score}/100"
        except Exception:
            score_line = ""
        await message.answer(
            f"⚖️ Записал: *{weight} кг*\n"
            f"За месяц: {sign}{diff:.1f} кг\n"
            f"Цель: {db.get_profile().get('goal', '?')}{score_line}",
            parse_mode="Markdown"
        )
    else:
        await message.answer(f"⚖️ Записал: *{weight} кг* — первая запись!", parse_mode="Markdown")


@router.message(Command("progress"))
async def cmd_progress(message: types.Message):
    db = MemoryManager(message.from_user.id)
    history = db.get_weight_history(days=30)
    if not history:
        return await message.answer("Пока нет данных. Записывай вес: /weight 78.5")

    profile = db.get_profile()
    ai = GeminiEngine(profile)
    analysis = ai.analyze_weight_progress(history, profile.get("goal", ""))

    # Текстовый график
    weights = [h["weight"] for h in history]
    dates = [h["date"][-5:] for h in history]  # MM-DD
    chart = "\n".join(f"`{d}` {'█' * int((w - min(weights)) / max(1, max(weights) - min(weights)) * 10 + 1)} {w} кг"
                      for d, w in zip(dates[-7:], weights[-7:]))

    await message.answer(
        f"📊 *Прогресс веса:*\n\n{chart}\n\n{analysis}",
        parse_mode="Markdown"
    )


# ── СПИСОК ПОКУПОК ─────────────────────────────────────────────────────────

@router.message(Command("shopping"))
async def cmd_shopping(message: types.Message):
    db = MemoryManager(message.from_user.id)
    items = db.get_shopping_list()
    if not items:
        return await message.answer(
            "Список покупок пуст.\n"
            "Он генерируется автоматически после анкеты.\n"
            "Или напиши: *составь список покупок на неделю*",
            parse_mode="Markdown"
        )

    # Группируем по категориям
    categories = {}
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    # Inline кнопки для отметки
    builder = InlineKeyboardBuilder()
    text_parts = ["🛒 *Список покупок:*\n"]

    for cat, cat_items in categories.items():
        text_parts.append(f"\n*{cat}*")
        for it in cat_items:
            status = "✅" if it["checked"] else "⬜"
            text_parts.append(f"{status} {it['item']}")
            builder.button(
                text=f"{'✅' if it['checked'] else '⬜'} {it['item'][:20]}",
                callback_data=f"shop_toggle_{it['id']}"
            )

    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="🗑 Очистить купленное", callback_data="shop_clear_checked"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="shop_refresh"),
    )

    await message.answer(
        "\n".join(text_parts),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("shop_toggle_"))
async def shop_toggle(cb: types.CallbackQuery):
    item_id = int(cb.data.replace("shop_toggle_", ""))
    db = MemoryManager(cb.from_user.id)
    db.toggle_shopping_item(item_id)
    await cb.answer("Отмечено!")
    # Обновляем список
    await cmd_shopping_refresh(cb)


@router.callback_query(F.data == "shop_refresh")
async def shop_toggle_refresh(cb: types.CallbackQuery):
    await cmd_shopping_refresh(cb)


async def cmd_shopping_refresh(cb: types.CallbackQuery):
    db = MemoryManager(cb.from_user.id)
    items = db.get_shopping_list()

    categories = {}
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    builder = InlineKeyboardBuilder()
    text_parts = ["🛒 *Список покупок:*\n"]

    for cat, cat_items in categories.items():
        text_parts.append(f"\n*{cat}*")
        for it in cat_items:
            status = "✅" if it["checked"] else "⬜"
            text_parts.append(f"{status} {it['item']}")
            builder.button(
                text=f"{'✅' if it['checked'] else '⬜'} {it['item'][:20]}",
                callback_data=f"shop_toggle_{it['id']}"
            )

    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="🗑 Очистить купленное", callback_data="shop_clear_checked"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="shop_refresh"),
    )

    try:
        await cb.message.edit_text(
            "\n".join(text_parts),
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data == "shop_clear_checked")
async def shop_clear(cb: types.CallbackQuery):
    db = MemoryManager(cb.from_user.id)
    items = db.get_shopping_list()
    # Убираем отмеченные — просто снимаем галочки для удобства
    for it in items:
        if it["checked"]:
            db.toggle_shopping_item(it["id"])
    await cb.answer("Список обновлён!")
    await cmd_shopping_refresh(cb)


# ── ХОЛОДИЛЬНИК → РЕЦЕПТЫ ──────────────────────────────────────────────────

@router.message(Command("fridge"))
async def cmd_fridge(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(
            "Напиши что есть в холодильнике:\n"
            "/fridge курица, рис, помидоры, яйца"
        )
    ingredients = parts[1].strip()
    db = MemoryManager(message.from_user.id)
    profile = db.get_profile()
    if not profile:
        return await message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")

    await message.answer("Подбираю рецепты... 🍳")
    ai = GeminiEngine(profile)
    try:
        recipes = ai.fridge_to_recipes(ingredients)
        await message.answer(recipes, parse_mode="Markdown")
    except Exception as e:
        await message.answer("Не смог подобрать рецепты, попробуй позже.")


# ── РЕЦЕПТЫ НА СЕГОДНЯ ─────────────────────────────────────────────────────

@router.message(Command("recipes"))
async def cmd_recipes(message: types.Message):
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return await message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")

    await message.answer("Готовлю рецепты на сегодня... 🍳")
    ai = GeminiEngine(profile)
    try:
        import asyncio
        recipes = await asyncio.to_thread(ai.generate_recipes_for_day)
        if len(recipes) > 4000:
            mid = recipes.find("\n---", 2000)
            split = mid if mid > 0 else 4000
            await message.answer(recipes[:split], parse_mode="Markdown")
            await message.answer(recipes[split:], parse_mode="Markdown")
        else:
            await message.answer(recipes, parse_mode="Markdown")
    except Exception:
        await message.answer("Не смог подготовить рецепты, попробуй позже.")


# ── СЮРПРИЗ ────────────────────────────────────────────────────────────────

@router.message(Command("surprise"))
async def cmd_surprise_toggle(message: types.Message):
    db = MemoryManager(message.from_user.id)
    current = db.get_profile().get("surprise_enabled", True)
    db.toggle_surprise(not current)
    status = "включены ✅" if not current else "отключены 🔕"
    await message.answer(f"Сюрпризы {status}")


# ── СТРИК ──────────────────────────────────────────────────────────────────

@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    db = MemoryManager(message.from_user.id)
    try:
        from core.progress_engine import ProgressEngine
        pe = ProgressEngine(message.from_user.id, db)
        await message.answer(pe.get_streak_message(), parse_mode="Markdown")
    except Exception as _e:
        streak = db.get_current_streak()
        if streak == 0:
            await message.answer("Начни сегодня — и серия пойдёт! 🔥")
        else:
            await message.answer(f"🔥 *{streak} дней подряд!*", parse_mode="Markdown")


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Профиль прогресса — человеческим языком, без технических слов."""
    uid = message.from_user.id
    db  = MemoryManager(uid)

    try:
        from core.progress_engine import ProgressEngine
        pe = ProgressEngine(uid, db)

        # Вес
        profile = db.get_profile()
        weight_history = db.get_weight_history(days=90)
        weight_start = profile.get("weight")
        weight_now   = weight_history[0]["weight"] if weight_history else None

        card = pe.get_profile_card(
            weight_start=float(weight_start) if weight_start else None,
            weight_now=weight_now
        )

        # Персональный инсайт
        insight = pe.get_insight_message()
        if insight:
            card += f"\n\n💡 _{insight}_"

        await message.answer(card, parse_mode="Markdown")

    except Exception as e:
        # Простой fallback
        db2 = MemoryManager(uid)
        streak = db2.get_current_streak()
        profile = db2.get_profile()
        await message.answer(
            f"👤 *Твой профиль*\n\n"
            f"Цель: {profile.get('goal', '?')}\n"
            f"🔥 Серия: {streak} дней\n"
            f"\nПродолжай — всё идёт хорошо!",
            parse_mode="Markdown"
        )


# ── FIX B2a: вспомогательные функции с явным user_id ──────────────────────
# Вызываются из keyboard_manager.py где from_user — это бот, не пользователь.

async def _profile_for_user(user_id: int, reply_to: types.Message):
    """Показывает профиль для user_id, отправляет ответ в reply_to чат."""
    db = MemoryManager(user_id)
    try:
        from core.progress_engine import ProgressEngine
        pe = ProgressEngine(user_id, db)
        profile = db.get_profile()
        weight_history = db.get_weight_history(days=90)
        weight_start = profile.get("weight") if profile else None
        weight_now   = weight_history[0]["weight"] if weight_history else None
        card = pe.get_profile_card(
            weight_start=float(weight_start) if weight_start else None,
            weight_now=weight_now
        )
        insight = pe.get_insight_message()
        if insight:
            card += f"\n\n💡 _{insight}_"
        await reply_to.answer(card, parse_mode="Markdown")
    except Exception as e:
        db2 = MemoryManager(user_id)
        streak = db2.get_current_streak()
        profile = db2.get_profile() or {}
        await reply_to.answer(
            f"👤 *Твой профиль*\n\n"
            f"Цель: {profile.get('goal', '?')}\n"
            f"🔥 Серия: {streak} дней\n\nПродолжай — всё идёт хорошо!",
            parse_mode="Markdown"
        )


async def _streak_for_user(user_id: int, reply_to: types.Message):
    """Показывает стрик для user_id."""
    db = MemoryManager(user_id)
    try:
        from core.progress_engine import ProgressEngine
        pe = ProgressEngine(user_id, db)
        await reply_to.answer(pe.get_streak_message(), parse_mode="Markdown")
    except Exception:
        streak = db.get_current_streak()
        if streak == 0:
            await reply_to.answer("Начни сегодня — и серия пойдёт! 🔥")
        else:
            await reply_to.answer(f"🔥 *{streak} дней подряд!*", parse_mode="Markdown")


# ── FIX B4: отдельный handler для недельного меню (не дублирует /plan) ─────

async def cmd_diet_week(user_id: int, reply_to: types.Message):
    """Генерирует недельное меню — отдельно от ежедневного плана."""
    db = MemoryManager(user_id)
    if not db.get_profile():
        return await reply_to.answer(
            "Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown"
        )
    await reply_to.answer("🥗 Генерирую меню на неделю... ⏳")
    try:
        profile = db.get_profile()
        ai = GeminiEngine(profile)
        history = db.get_recent_history(limit=5)
        menu = await ai.generate_weekly_menu(history=history)
        await reply_to.answer(menu, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"cmd_diet_week error: {e}")
        await reply_to.answer(
            "🥗 *Меню на неделю*\n\nНе смог сгенерировать прямо сейчас.\n"
            "Попробуй через минуту или используй /plan для плана на сегодня.",
            parse_mode="Markdown"
        )



@router.message(Command("feedback"))
async def cmd_feedback(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Напиши: /feedback твой отзыв или предложение")

    text = parts[1].strip()
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    db.save_feedback(text)

    # Уведомляем админа
    if ADMIN_ID:
        try:
            profile = db.get_profile()
            name = profile.get("name", str(user_id))
            from bot.config import bot
            await bot.send_message(
                ADMIN_ID,
                f"📩 *Новый фидбек*\n"
                f"От: {name} (id={user_id})\n\n{text}",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await message.answer("Спасибо за отзыв! Учту 🙏")


# ── ЧАТ С ИСТОРИЕЙ ─────────────────────────────────────────────────────────



@router.message(Command("update_patterns"))
async def cmd_update_patterns(message: types.Message):
    """Запустить анализ паттернов вручную."""
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    if not db.get_profile():
        return await message.answer("Сначала заполни анкету.")

    msg = await message.answer("🧠 Gemini анализирует твои паттерны...\nЗаймёт ~30 секунд ⏳")
    await message.bot.send_chat_action(user_id, "typing")

    from core.pattern_cache import analyze_and_update_patterns
    result = await analyze_and_update_patterns(user_id)

    try:
        await msg.delete()
    except Exception:
        pass

    if result:
        await message.answer(
            f"✅ *Паттерны обновлены!*\n\n_{result}_",
            parse_mode="Markdown"
        )
    else:
        await message.answer("Не смог обновить паттерны — мало данных. Пообщайся ещё немного.")


@router.message(Command("cache_stats"))
async def cmd_cache_stats(message: types.Message):
    """Статистика кэша шаблонов."""
    from core.pattern_cache import PatternCache
    cache = PatternCache(message.from_user.id)
    stats = cache.get_stats()

    lines = ["📊 *Статистика кэша*\n"]

    if stats["patterns"]:
        lines.append("*Шаблоны рекомендаций:*")
        for r in stats["patterns"]:
            lines.append(f"  {r['category']}: {r['cnt']} записей, показано {r['uses'] or 0} раз")
    else:
        lines.append("Шаблонов пока нет — запусти /update_patterns")

    lines.append("")

    if stats["cache"]:
        lines.append("*Кэш ответов:*")
        for r in stats["cache"]:
            lines.append(f"  {r['query_type']}: {r['cnt']} записей, {r['hits'] or 0} попаданий")
    else:
        lines.append("Кэш ответов пуст")

    patterns = cache.get_user_patterns()
    if patterns.get("insights"):
        lines.append(f"\n*Инсайт Gemini:*\n_{patterns['insights']}_")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(F.text, StateFilter(default_state))
async def handle_chat(message: types.Message):
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()

    if not profile:
        return await message.answer(
            "Напиши *анкета* — я настроюсь под тебя.",
            parse_mode="Markdown"
        )

    user_text = message.text

    # Сохраняем сообщение пользователя
    db.save_message("user", user_text)

    # Проверка на сброс Memory Light
    lowered = user_text.lower()
    if any(p in lowered for p in ["не угадал", "сегодня не так", "другое настроение"]):
        db.reset_memory_light()

    # Typing пока думаем
    await message.bot.send_chat_action(user_id, "typing")

    # Orchestrator — маршрутизируем к нужному агенту
    try:
        from core.orchestrator import Orchestrator
        orch = Orchestrator(user_id, profile, db)
        agent_name, reply = await orch.route(user_text)
        # Сохраняем ответ
        db.save_message("assistant", reply)
        # EventBus — событие чата для CoachAgent
        if agent_name == "CoachAgent":
            try:
                from core.event_bus import EventBus
                EventBus(user_id, db).emit("checkin_done")
            except Exception:
                pass
        await message.answer(reply, parse_mode="Markdown")
    except Exception as _oe:
        err_str = str(_oe)
        # При 429 — не делаем fallback, просто сообщаем пользователю
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            logger.warning(f"Orchestrator 429, пропускаем fallback")
            await message.answer("⚠️ Сервис временно перегружен, попробуй через минуту.")
            return
        # При других ошибках — fallback на старый GeminiEngine
        logger.warning(f"Orchestrator failed ({_oe}), fallback to GeminiEngine")
        try:
            history = db.get_recent_history(limit=20)
            ai = GeminiEngine(profile)
            reply = ai.chat(user_text, history=history[:-1])
            db.save_message("assistant", reply)
            if "[FEATURE]" in reply:
                db.log_insight(reply)
            await message.answer(reply, parse_mode="Markdown")
        except Exception as _fe:
            logger.error(f"Fallback also failed: {_fe}")
            await message.answer("⚠️ Что-то пошло не так, попробуй ещё раз.")
