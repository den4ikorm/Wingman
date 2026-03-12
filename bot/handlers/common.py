"""
bot/handlers/common.py
Общие команды + чат с историей + вес + холодильник + список покупок
"""

import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from bot.config import ADMIN_ID

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    from plugins.idea_factory import get_main_keyboard
    await message.answer(
        "Привет. Я Wingman — твой проводник по образу жизни 🌿\n\n"
        "Помогу с питанием, планом дня и просто поговорю.\n"
        "Напиши *анкета* чтобы настроить меня под себя.",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "*Команды:*\n\n"
        "📋 *анкета* — настройка профиля\n"
        "/plan — план на день\n"
        "/tasks — задачи на сегодня\n"
        "/weight 78.5 — записать вес\n"
        "/progress — динамика веса\n"
        "/shopping — список покупок\n"
        "/fridge — рецепты из холодильника\n"
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

    # Показываем динамику
    history = db.get_weight_history(days=30)
    if len(history) > 1:
        first = history[0]["weight"]
        diff = weight - first
        sign = "+" if diff > 0 else ""
        await message.answer(
            f"⚖️ Записал: *{weight} кг*\n"
            f"За месяц: {sign}{diff:.1f} кг\n"
            f"Цель: {db.get_profile().get('goal', '?')}",
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
    streak = db.get_streak()
    if streak == 0:
        await message.answer("Стрик ещё не начат. Отмечайся каждый вечер! 🔥")
    else:
        await message.answer(f"🔥 Твой стрик: *{streak} дней* подряд!", parse_mode="Markdown")


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

@router.message(F.text)
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

    # Получаем историю для контекста
    history = db.get_recent_history(limit=20)

    # Typing пока Gemini думает
    await message.bot.send_chat_action(user_id, "typing")

    ai = GeminiEngine(profile)
    reply = ai.chat(user_text, history=history[:-1])

    # Сохраняем ответ бота
    db.save_message("assistant", reply)

    if "[FEATURE]" in reply:
        db.log_insight(reply)

    await message.answer(reply)
