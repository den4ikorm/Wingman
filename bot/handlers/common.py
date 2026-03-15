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
    from bot.keyboard_manager import get_main_kb
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    user_id = message.from_user.id
    name = message.from_user.first_name or "друг"
    db = MemoryManager(user_id)
    profile = db.get_profile()
    has_profile = bool(profile and profile.get("name"))

    builder = InlineKeyboardBuilder()

    if has_profile:
        # Возвращающийся пользователь
        builder.row(
            types.InlineKeyboardButton(text="🥗 Диета и питание", callback_data="menu_diet"),
            types.InlineKeyboardButton(text="🎬 Кино на вечер", callback_data="menu_movie"),
        )
        builder.row(
            types.InlineKeyboardButton(text="🎵 Музыка под настроение", callback_data="menu_music"),
            types.InlineKeyboardButton(text="📚 Книги", callback_data="menu_books"),
        )
        builder.row(
            types.InlineKeyboardButton(text="🏋️ Фитнес", callback_data="menu_fitness"),
            types.InlineKeyboardButton(text="💡 Идеи", callback_data="menu_ideas"),
        )
        # WebApp кнопка если задан URL
        from bot.config import WEBAPP_URL
        if WEBAPP_URL:
            builder.row(
                types.InlineKeyboardButton(
                    text="📱 Открыть дашборд",
                    web_app=types.WebAppInfo(url=WEBAPP_URL)
                )
            )
        else:
            builder.row(
                types.InlineKeyboardButton(text="📊 Мой дашборд", callback_data="menu_dashboard"),
            )
        text = (
            f"С возвращением, {name} 👋\n\n"
            "Чем займёмся сегодня?"
        )
    else:
        # Новый пользователь
        builder.row(
            types.InlineKeyboardButton(text="🥗 Хочу диету на сегодня", callback_data="diet_quick"),
            types.InlineKeyboardButton(text="📅 Диету на неделю", callback_data="diet_week"),
        )
        builder.row(
            types.InlineKeyboardButton(text="🎬 Что посмотреть?", callback_data="menu_movie"),
            types.InlineKeyboardButton(text="🎵 Музыку под настроение", callback_data="menu_music"),
        )
        builder.row(
            types.InlineKeyboardButton(text="✨ Настроить под меня (анкета)", callback_data="start_survey"),
        )
        text = (
            f"Привет, {name}! Я *AEatolog* 🌿\n\n"
            "Твой личный помощник — посоветую что поесть, "
            "что посмотреть, какую музыку включить.\n\n"
            "Выбери что хочешь прямо сейчас — или пройди короткую анкету "
            "чтобы я подстроился под тебя:"
        )

    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # Показываем нижнюю клавиатуру
    await message.answer(
        "Или используй кнопки внизу 👇",
        reply_markup=get_main_kb(user_id)
    )


@router.callback_query(F.data == "start_survey")
async def cb_start_survey(cb: types.CallbackQuery, state):
    await cb.answer()
    from bot.handlers.survey import cmd_start_survey
    await cmd_start_survey(cb.message, state)


@router.callback_query(F.data == "diet_quick")
async def cb_diet_quick(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile or not profile.get("name"):
        await cb.message.answer(
            "Чтобы составить *персональную диету* — нужно заполнить анкету.\n\n"
            "Это займёт 3 минуты 👇",
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(text="✨ Заполнить анкету", callback_data="start_survey"),
                types.InlineKeyboardButton(text="🥗 Общая диета", callback_data="diet_generic"),
            ]])
        )
    else:
        await cb.message.answer("Готовлю диету на сегодня... 🥗")
        await cmd_plan(cb.message)


@router.callback_query(F.data == "diet_generic")
async def cb_diet_generic(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "🥗 *Базовая диета на день* (1800 ккал):\n\n"
        "☀️ *Завтрак:* Овсянка на воде с ягодами + яйцо (400 ккал)\n"
        "🌤 *Обед:* Куриная грудка с гречкой и овощами (550 ккал)\n"
        "🌙 *Ужин:* Рыба запечённая + салат (450 ккал)\n"
        "🍎 *Перекусы:* Фрукт + орехи (400 ккал)\n\n"
        "_Для персональной диеты — заполни анкету_",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="✨ Персональная анкета", callback_data="start_survey"),
        ]])
    )


@router.callback_query(F.data == "diet_week")
async def cb_diet_week(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "📅 *Диета на неделю* — это персональный план.\n\n"
        "Чтобы составить его правильно, мне нужно знать твой вес, цель и предпочтения.\n"
        "Займёт 3 минуты 👇",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="✨ Заполнить анкету", callback_data="start_survey"),
        ]])
    )


@router.callback_query(F.data == "menu_dashboard")
async def cb_menu_dashboard(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return await cb.message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")
    await cb.message.answer("Генерирую дашборд... 📊")
    await cmd_plan(cb.message)


@router.callback_query(F.data == "menu_ideas")
async def cb_menu_ideas(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "💡 *Idea Factory* — 20 методов генерации идей\n\n"
        "Напиши: `/idea твоя тема`\n"
        "Или: `/idea_list` — выбрать модуль",
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu_fitness")
async def cb_menu_fitness(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "🏋️ *Фитнес-тренер*\n\n"
        "Напиши `/fitness` — получи план тренировки на сегодня.\n"
        "_Скоро: персональные программы и уведомления_",
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu_music")
async def cb_menu_music(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    mood = profile.get("emotional_state", "нейтральное") if profile else "нейтральное"
    name = profile.get("name", "") if profile else ""

    from core.provider_manager import generate as pm_generate
    msg = await cb.message.answer("🎵 Подбираю музыку под настроение...")

    prompt = (
        f"Ты — душевный музыкальный советник. Настроение: {mood}.\n"
        f"Порекомендуй 3 трека или альбома — каждый с коротким душевным описанием.\n"
        f"Формат каждого:\n"
        f"🎵 *Исполнитель — Название*\n"
        f"_описание 1-2 предложения — что это за музыка и почему подходит сейчас_\n"
        f"[Слушать на YouTube](ссылка)\n\n"
        f"Ссылки формата: https://www.youtube.com/results?search_query=исполнитель+название\n"
        f"Отвечай на русском, душевно и кратко."
    )
    try:
        result = await pm_generate("Ты музыкальный советник.", prompt, max_tokens=600)
        await msg.edit_text(
            f"🎵 *Музыка под настроение*\n\n{result}",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception:
        await msg.edit_text(
            "🎵 *Музыка на вечер*\n\n"
            "Попробуй:\n"
            "• [Lo-fi Hip Hop](https://www.youtube.com/results?search_query=lofi+hip+hop)\n"
            "• [Acoustic Chill](https://www.youtube.com/results?search_query=acoustic+chill+mix)\n"
            "• [Cinematic Piano](https://www.youtube.com/results?search_query=cinematic+piano+music)",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )


@router.callback_query(F.data == "menu_books")
async def cb_menu_books(cb: types.CallbackQuery):
    await cb.answer()
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    hobby = profile.get("hobby", "") if profile else ""
    goal = profile.get("goal", "") if profile else ""
    psychotype = profile.get("psychotype", "") if profile else ""

    from core.provider_manager import generate as pm_generate
    msg = await cb.message.answer("📚 Подбираю книги под тебя...")

    prompt = (
        f"Ты — библиотекарь с душой. Порекомендуй 3 книги.\n"
        f"Интересы/хобби: {hobby or 'разные'}.\n"
        f"Цель: {goal or 'саморазвитие'}.\n"
        f"Психотип: {psychotype or 'неизвестен'}.\n\n"
        f"Формат каждой:\n"
        f"📖 *Автор — Название*\n"
        f"_душевное описание 2-3 предложения — не аннотация, а ощущение от книги_\n"
        f"Почему именно сейчас: одна строка\n\n"
        f"Отвечай на русском, душевно. Предпочитай книги которые реально меняют взгляд на жизнь."
    )
    try:
        result = await pm_generate("Ты душевный библиотекарь.", prompt, max_tokens=700)
        await msg.edit_text(
            f"📚 *Книги для тебя*\n\n{result}",
            parse_mode="Markdown"
        )
    except Exception:
        await msg.edit_text(
            "📚 *Книги*\n\nНапиши `/books` или скажи мне тему — подберу что-то интересное.",
            parse_mode="Markdown"
        )


# ── WebApp данные от мини-апп ──────────────────────────────────────────────

@router.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    """Принимает данные от WebApp (webapp.html) и сохраняет в БД."""
    import json
    user_id = message.from_user.id
    db = MemoryManager(user_id)

    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    action = data.get("action", "")

    if action == "set_mood":
        mood_map = {"5": "радостное", "4": "хорошее", "3": "нейтральное", "2": "грустное", "1": "раздражённое", "0": "плохое"}
        mood = mood_map.get(str(data.get("mood", "3")), "нейтральное")
        db.set_mood(mood)
        await message.answer(f"Настроение записано: {data.get('emoji', '😐')} {mood}")

    elif action == "add_task":
        text = data.get("text", "").strip()
        if text:
            db.add_task(text)
            await message.answer(f"✅ Задача добавлена: {text}")

    elif action == "toggle_task":
        # Обновляем статус задачи
        tasks = db.get_tasks()
        idx = data.get("index")
        if idx is not None and 0 <= idx < len(tasks):
            if isinstance(tasks[idx], dict):
                tasks[idx]["done"] = data.get("done", False)
            db.save_tasks(tasks)

    elif action == "set_mode":
        level = int(data.get("level", 2))
        db.save_profile({"diet_level": level})
        mode_names = {1:"🌿 Интуитивное", 2:"🥗 Сбалансированное", 3:"⚡ Активное", 4:"🏋️ Спортивное", 5:"🔥 Максимум"}
        await message.answer(f"Режим изменён: {mode_names.get(level, str(level))}")

    elif action == "water":
        ml = int(data.get("ml", 0))
        db.save_profile({"water_today": ml})

    elif action == "open_webapp":
        await message.answer("WebApp открыт ✓")


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

        # Сохраняем текст рецептов для скачивания
        db.save_profile({"last_recipes_text": recipes})

        # Отправляем текст
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬇️ Скачать рецепты HTML", callback_data="recipes_dl"),
            InlineKeyboardButton(text="🛒 Список покупок", callback_data="nav_shopping"),
        )

        if len(recipes) > 4000:
            mid = recipes.find("\n---", 2000)
            split = mid if mid > 0 else 4000
            await message.answer(recipes[:split], parse_mode="Markdown")
            await message.answer(
                recipes[split:],
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                recipes,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
    except Exception:
        await message.answer("Не смог подготовить рецепты, попробуй позже.")


@router.callback_query(F.data == "recipes_dl")
async def cb_recipes_download(cb: types.CallbackQuery):
    """Скачиваем рецепты дня как красивый HTML."""
    await cb.answer("Генерирую HTML...")
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}
    recipes_text = profile.get("last_recipes_text", "")

    if not recipes_text:
        return await cb.message.answer("Нет рецептов для скачивания. Сначала запроси /recipes")

    from core.recipe_html import build_recipe_html, recipe_from_text
    from datetime import date

    # Пробуем разбить на отдельные рецепты по разделителям
    import re
    blocks = re.split(r'\n---+\n|\n#{2,3}\s', recipes_text)
    blocks = [b.strip() for b in blocks if len(b.strip()) > 50]

    if not blocks:
        blocks = [recipes_text]

    # Генерируем общую HTML-страницу со всеми рецептами
    html = _build_recipes_page(blocks, profile, str(date.today()))

    import tempfile, os, aiofiles
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                     encoding='utf-8', delete=False) as f:
        f.write(html)
        tmp_path = f.name

    try:
        async with aiofiles.open(tmp_path, 'rb') as f:
            content = await f.read()
        from aiogram.types import BufferedInputFile
        await cb.message.answer_document(
            BufferedInputFile(content, filename=f"recipes_{date.today()}.html"),
            caption=f"🍳 Рецепты на {date.today().strftime('%d.%m.%Y')}"
        )
    finally:
        os.unlink(tmp_path)


def _build_recipes_page(blocks: list, profile: dict, today: str) -> str:
    """Строит HTML-страницу со всеми рецептами дня."""
    import urllib.parse
    name = profile.get("name", "")

    # Карточка для каждого блока
    cards_html = ""
    meal_emojis = ["🌅", "☀️", "🌙", "🍎"]
    meal_names  = ["Завтрак", "Обед", "Ужин", "Перекус"]

    for i, block in enumerate(blocks):
        emoji   = meal_emojis[i % len(meal_emojis)]
        mname   = meal_names[i % len(meal_names)]
        # Первая строка — часто название блюда
        lines   = block.strip().splitlines()
        title   = lines[0].lstrip("#* ") if lines else mname
        content = "\n".join(lines[1:]) if len(lines) > 1 else block

        # YouTube ссылка
        yt_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(f"рецепт {title}")
        # Фото
        img_url = f"https://source.unsplash.com/600x400/?food,{urllib.parse.quote(title.split()[0].lower() if title.split() else 'food')}"

        # Форматируем текст блока
        content_html = ""
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(("**", "##", "###")):
                clean = line.lstrip("#* ")
                content_html += f'<div class="block-title">{clean}</div>'
            elif line.startswith(("-", "•", "*")):
                content_html += f'<div class="list-item">{line.lstrip("-•* ")}</div>'
            elif line[0].isdigit() and line[1:3] in (". ", ") "):
                content_html += f'<div class="step-item"><span class="sn">{line[0]}</span>{line[2:]}</div>'
            else:
                content_html += f'<p>{line}</p>'

        cards_html += f"""
        <div class="recipe-card" id="recipe-{i}">
          <div class="recipe-img-wrap">
            <img src="{img_url}" alt="{title}"
                 onerror="this.src='https://source.unsplash.com/600x400/?food'">
            <div class="recipe-img-overlay">
              <span class="meal-badge">{emoji} {mname}</span>
            </div>
          </div>
          <div class="recipe-body">
            <h2>{title}</h2>
            <div class="recipe-content">{content_html}</div>
            <a href="{yt_url}" target="_blank" class="yt-link">▶ Рецепт на YouTube</a>
          </div>
        </div>"""

    greeting = f"Рецепты для {name}" if name else "Рецепты на день"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Рецепты · {today}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@400;700;900&family=Inter:wght@300;400;500&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:#07090d;color:#e8e8e8;padding:20px}}
.page-header{{max-width:720px;margin:0 auto 32px;padding-top:16px}}
.page-title{{font-family:'Unbounded',sans-serif;font-size:clamp(1.4rem,5vw,2.2rem);font-weight:900;background:linear-gradient(135deg,#39ff6a,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}}
.page-date{{font-size:0.8rem;color:#555}}
.recipes{{max-width:720px;margin:0 auto;display:flex;flex-direction:column;gap:24px}}
.recipe-card{{background:#0d1318;border:1px solid rgba(255,255,255,0.07);border-radius:20px;overflow:hidden}}
.recipe-img-wrap{{position:relative;height:240px}}
.recipe-img-wrap img{{width:100%;height:100%;object-fit:cover}}
.recipe-img-overlay{{position:absolute;inset:0;background:linear-gradient(to top,rgba(13,19,24,0.9) 0%,transparent 60%);display:flex;align-items:flex-end;padding:16px}}
.meal-badge{{background:rgba(57,255,106,0.15);border:1px solid rgba(57,255,106,0.3);border-radius:100px;padding:5px 14px;font-size:0.75rem;color:#39ff6a;font-weight:600}}
.recipe-body{{padding:20px}}
h2{{font-family:'Unbounded',sans-serif;font-size:1.1rem;font-weight:700;margin-bottom:14px;line-height:1.3}}
.recipe-content{{font-size:0.85rem;line-height:1.7;color:#aaa;margin-bottom:16px}}
.recipe-content p{{margin-bottom:8px}}
.block-title{{font-weight:600;color:#ccc;margin:12px 0 6px;font-size:0.88rem}}
.list-item{{padding:4px 0 4px 16px;position:relative;color:#aaa}}
.list-item::before{{content:'·';position:absolute;left:4px;color:#39ff6a}}
.step-item{{display:flex;gap:10px;padding:6px 0;color:#aaa;align-items:flex-start}}
.sn{{min-width:22px;height:22px;background:rgba(57,255,106,0.1);border:1px solid rgba(57,255,106,0.2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.68rem;font-weight:700;color:#39ff6a;flex-shrink:0;margin-top:1px}}
.yt-link{{display:inline-flex;align-items:center;gap:8px;background:#ff0000;color:#fff;font-weight:600;font-size:0.8rem;padding:10px 18px;border-radius:10px;text-decoration:none;transition:opacity 0.2s}}
.yt-link:hover{{opacity:0.85}}
.footer{{text-align:center;color:#333;font-size:0.72rem;padding:32px 0 16px}}
</style>
</head>
<body>
<div class="page-header">
  <div class="page-title">{greeting}</div>
  <div class="page-date">{today}</div>
</div>
<div class="recipes">
{cards_html}
</div>
<div class="footer">@AEatolog · Wingman v3.9</div>
</body>
</html>"""


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


# ── ФИДБЕК ─────────────────────────────────────────────────────────────────

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


# ── Course Orchestrator API ────────────────────────────────────────────────

@router.message(Command("thought"))
async def cmd_thought(message: types.Message):
    """Мысль дня — для теста. В продакшне приходит автоматически в 8:00."""
    user_id = message.from_user.id
    msg = await message.answer("✦ ...")
    try:
        from core.course_orchestrator import CourseOrchestrator
        orch = CourseOrchestrator(user_id)
        thought = await orch.get_thought()
        await msg.edit_text(f"✦ {thought}")
    except Exception as e:
        await msg.edit_text("Не удалось получить мысль дня.")


@router.message(Command("story"))
async def cmd_story(message: types.Message):
    """История дня."""
    user_id = message.from_user.id
    msg = await message.answer("✦ Пишу историю...")
    try:
        from core.course_orchestrator import CourseOrchestrator
        orch = CourseOrchestrator(user_id)
        story = await orch.get_story()
        text = story.get("text", "")
        author = story.get("author", "")
        await msg.edit_text(
            f"✦ {text}\n\n_{author}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.edit_text("Не удалось получить историю.")


@router.callback_query(F.data.startswith("course_"))
async def cb_course(cb: types.CallbackQuery):
    """Обработка действий курса из WebApp."""
    await cb.answer()
    action = cb.data.replace("course_", "")
    user_id = cb.from_user.id

    if action == "thought":
        try:
            from core.course_orchestrator import CourseOrchestrator
            orch = CourseOrchestrator(user_id)
            thought = await orch.get_thought()
            await cb.message.answer(f"✦ {thought}")
        except Exception:
            await cb.message.answer("Попробуй позже.")

    elif action == "story":
        try:
            from core.course_orchestrator import CourseOrchestrator
            orch = CourseOrchestrator(user_id)
            story = await orch.get_story()
            await cb.message.answer(
                f"✦ {story.get('text', '')}\n\n_{story.get('author', '')}_",
                parse_mode="Markdown"
            )
        except Exception:
            await cb.message.answer("Попробуй позже.")

