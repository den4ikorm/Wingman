"""
bot/handlers/evening_handler.py
Вечерний аудит + day_summary + рекомендации (фильмы/музыка/книга)
"""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

router = Router()


class EveningAudit(StatesGroup):
    checking_tasks   = State()
    waiting_feedback = State()


@router.callback_query(F.data == "start_evening_review")
async def start_review(cb: types.CallbackQuery, state: FSMContext):
    db = MemoryManager(cb.from_user.id)
    profile = db.get_profile()
    ai = GeminiEngine(profile)

    html = db.get_last_plan()
    tasks = ai.get_task_list(html)

    if not tasks:
        await cb.message.answer(
            "Добрый вечер! Сегодня план был пуст.\n"
            "Расскажи — как прошёл день?"
        )
        await state.set_state(EveningAudit.waiting_feedback)
        await cb.answer()
        return

    await state.update_data(tasks=tasks, index=0, results=[])
    await cb.message.edit_text("Добрый вечер! Пробежимся по задачам ✨")
    await _ask_task(cb.message, tasks[0])
    await state.set_state(EveningAudit.checking_tasks)
    await cb.answer()


async def _ask_task(message: types.Message, task: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да",  callback_data="audit_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="audit_no"),
    )
    await message.answer(f"📍 {task}", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("audit_"), EveningAudit.checking_tasks)
async def process_task(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tasks = data["tasks"]
    index = data["index"]
    results = data["results"]

    mark = "✅" if "yes" in cb.data else "❌"
    results.append(f"{tasks[index]}: {mark}")
    next_index = index + 1

    if next_index < len(tasks):
        await state.update_data(index=next_index, results=results)
        await cb.message.edit_text(
            f"📍 {tasks[next_index]}",
            reply_markup=cb.message.reply_markup
        )
    else:
        await state.update_data(results=results)
        await state.set_state(EveningAudit.waiting_feedback)
        await cb.message.edit_text(
            "Список пройден! 📋\n\n"
            "Как тебе день в целом? Расскажи свободно — что было, что съел, как настроение."
        )
    await cb.answer()


@router.message(EveningAudit.waiting_feedback)
async def finish_evening(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    ai = GeminiEngine(profile)

    results_text = "\n".join(data.get("results", []))
    full_text = f"Итоги:\n{results_text}\n\nФидбек: {message.text}"

    # Анализ вечера
    analysis = ai.analyze_evening(db.get_last_plan(), full_text)

    # Сохраняем day_summary
    day_summary = ai.generate_day_summary(message.text, results_text)
    mood = GeminiEngine.extract_mood(analysis) or "neutral"
    db.save_day_summary(day_summary, mood)
    db.set_mood(mood)

    # Применяем вайб
    vibe = GeminiEngine.extract_vibe(analysis)
    if vibe:
        db.set_vibe(vibe)

    db.mark_report_pending(False)
    db.update_streak()

    if "[FEATURE]" in analysis:
        db.log_insight(analysis)

    await message.answer(analysis)

    # Рекомендации на вечер
    await message.answer("Подбираю рекомендации на вечер... 🎬")
    try:
        stop_list = db.get_stop_list()
        recs = ai.get_evening_recommendations(mood, stop_list)
        await message.answer(recs, parse_mode="Markdown")
    except Exception:
        pass

    await message.answer("Записал. Отдыхай, завтра увидимся 🌙")
    await state.clear()
