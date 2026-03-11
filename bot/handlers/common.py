"""
bot/handlers/common.py
Общие команды + чат через Wingman (SYSTEM_CORE активен)
"""

from aiogram import Router, types, F
from aiogram.filters import Command

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет. Я Wingman — твой проводник по образу жизни 🌿\n\n"
        "Помогу с питанием, планом дня и просто поговорю.\n"
        "Напиши *анкета* чтобы настроить меня под себя.",
        parse_mode="Markdown"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Что умею:\n\n"
        "📋 *анкета* — настройка профиля\n"
        "/vibe — сменить настроение дня\n"
        "/forget — сбросить memory light\n"
        "/seen [название] — добавить в stop-list\n\n"
        "Или просто пиши — отвечу как Wingman.",
        parse_mode="Markdown"
    )


@router.message(Command("vibe"))
async def cmd_vibe(message: types.Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚡ Spark", callback_data="set_vibe_spark"),
        InlineKeyboardButton(text="🌿 Observer", callback_data="set_vibe_observer"),
        InlineKeyboardButton(text="🌙 Twilight", callback_data="set_vibe_twilight"),
    )
    await message.answer("Выбери настроение на завтра:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("set_vibe_"))
async def set_vibe(callback: types.CallbackQuery):
    vibe = callback.data.replace("set_vibe_", "")
    db = MemoryManager(callback.from_user.id)
    db.set_vibe(vibe)
    labels = {
        "spark":    "⚡ Spark — заряд",
        "observer": "🌿 Observer — баланс",
        "twilight": "🌙 Twilight — уют"
    }
    await callback.message.edit_text(f"Вайб на завтра: {labels.get(vibe, vibe)} ✅")
    await callback.answer()


@router.message(Command("forget"))
async def cmd_forget(message: types.Message):
    db = MemoryManager(message.from_user.id)
    db.reset_memory_light()
    await message.answer("Memory Light сброшен. Начинаем с чистого листа 🌱")


@router.message(Command("seen"))
async def cmd_seen(message: types.Message):
    """Добавить в stop-list: /seen Начало"""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Напиши что добавить: /seen Название фильма")
    item = parts[1].strip()
    db = MemoryManager(message.from_user.id)
    db.add_to_stop_list(item)
    await message.answer(f"Записал: «{item}» больше не предложу 👍")


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

    # Проверка на сброс Memory Light
    lowered = message.text.lower()
    if any(phrase in lowered for phrase in ["не угадал", "сегодня не так", "другое настроение"]):
        db.reset_memory_light()

    ai = GeminiEngine(profile)
    reply = ai.chat(message.text)

    # Логируем фичи
    if "[FEATURE]" in reply:
        db.log_insight(reply)

    await message.answer(reply)


@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    """Показать задачи на день + добавить свою"""
    db = MemoryManager(message.from_user.id)
    tasks = db.get_tasks()

    if not tasks:
        return await message.answer(
            "Задач пока нет. Утром бот пришлёт план с задачами.\n"
            "Или напиши: /addtask Название задачи"
        )

    text = "*Задачи на сегодня:*\n" + "\n".join(
        f"{i+1}. {t}" for i, t in enumerate(tasks)
    )
    text += "\n\nДобавить свою: /addtask Название"
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
        await message.answer("Задач уже 10 — максимум на день. Сначала выполни что есть 💪")


@router.message(Command("surprise"))
async def cmd_surprise_toggle(message: types.Message):
    db = MemoryManager(message.from_user.id)
    current = db.get_profile().get("surprise_enabled", True)
    db.toggle_surprise(not current)
    status = "включены ✅" if not current else "отключены 🔕"
    await message.answer(f"Сюрпризы {status}")


@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    db = MemoryManager(message.from_user.id)
    streak = db.get_streak()
    if streak == 0:
        await message.answer("Стрик ещё не начат. Отмечайся каждый вечер в аудите! 🔥")
    else:
        await message.answer(f"🔥 Твой стрик: *{streak} дней* подряд!", parse_mode="Markdown")


@router.message(Command("plan"))
async def cmd_plan(message: types.Message):
    """Ручной запрос плана на день"""
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()

    if not profile:
        return await message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")

    await message.answer("Генерирую план... ⏳")

    from bot.scheduler_logic import send_morning_dashboard
    await send_morning_dashboard(user_id)
