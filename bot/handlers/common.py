from aiogram import Router, types, F
from aiogram.filters import Command

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я твой персональный ассистент 🤖\n\n"
        "Напиши *анкета* чтобы настроить меня под себя.",
        parse_mode="Markdown"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Команды:\n"
        "/start — начало\n"
        "/survey — заполнить анкету\n"
        "/vibe — сменить настроение дня\n\n"
        "Или просто напиши — отвечу как ассистент."
    )


@router.message(Command("vibe"))
async def cmd_vibe(message: types.Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚡ Spark — заряд", callback_data="set_vibe_spark"),
        InlineKeyboardButton(text="🌿 Observer — баланс", callback_data="set_vibe_observer"),
        InlineKeyboardButton(text="🌙 Twilight — уют", callback_data="set_vibe_twilight"),
    )
    await message.answer("Выбери настроение на завтра:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("set_vibe_"))
async def set_vibe(callback: types.CallbackQuery):
    vibe = callback.data.replace("set_vibe_", "")
    db = MemoryManager(callback.from_user.id)
    db.set_vibe(vibe)
    labels = {"spark": "⚡ Spark", "observer": "🌿 Observer", "twilight": "🌙 Twilight"}
    await callback.message.edit_text(f"Вайб на завтра: {labels.get(vibe, vibe)} ✅")
    await callback.answer()


@router.message(F.text)
async def handle_chat(message: types.Message):
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()

    if not profile:
        return await message.answer(
            "Сначала заполни анкету — напиши *анкета*",
            parse_mode="Markdown"
        )

    ai = GeminiEngine(profile)
    reply = ai.chat(message.text)

    # Если AI предлагает фичу — логируем
    if "[FEATURE]" in reply:
        db.log_insight(reply)

    await message.answer(reply)
