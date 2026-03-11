from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

router = Router()


class EveningAudit(StatesGroup):
    checking_tasks = State()
    waiting_feedback = State()


@router.callback_query(F.data == "start_evening_review")
async def start_review(callback: types.CallbackQuery, state: FSMContext):
    db = MemoryManager(callback.from_user.id)
    profile = db.get_profile()
    ai = GeminiEngine(profile)

    html = db.get_last_plan()
    tasks = ai.get_task_list(html)

    if not tasks:
        await callback.message.answer(
            "Добрый вечер! Сегодня план был пуст.\n"
            "Расскажи — как прошёл день?"
        )
        await state.set_state(EveningAudit.waiting_feedback)
        await callback.answer()
        return

    await state.update_data(tasks=tasks, index=0, results=[])
    await callback.message.edit_text("Добрый вечер! Пробежимся по задачам ✨")
    await _ask_task(callback.message, tasks[0])
    await state.set_state(EveningAudit.checking_tasks)
    await callback.answer()


async def _ask_task(message: types.Message, task: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да", callback_data="audit_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="audit_no"),
    )
    await message.answer(f"📍 {task}", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("audit_"), EveningAudit.checking_tasks)
async def process_task(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tasks = data["tasks"]
    index = data["index"]
    results = data["results"]

    mark = "✅" if "yes" in callback.data else "❌"
    results.append(f"{tasks[index]}: {mark}")

    next_index = index + 1

    if next_index < len(tasks):
        await state.update_data(index=next_index, results=results)
        await callback.message.edit_text(
            f"📍 {tasks[next_index]}",
            reply_markup=callback.message.reply_markup
        )
    else:
        await state.update_data(results=results)
        await state.set_state(EveningAudit.waiting_feedback)
        await callback.message.edit_text(
            "Список пройден! 📋\n\n"
            "Как тебе день в целом? Есть что улучшить в боте?"
        )

    await callback.answer()


@router.message(EveningAudit.waiting_feedback)
async def finish_evening(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db = MemoryManager(message.from_user.id)
    ai = GeminiEngine(db.get_profile())

    results_text = "\n".join(data.get("results", []))
    full_text = f"Итоги:\n{results_text}\n\nФидбек: {message.text}"

    analysis = ai.analyze_evening(db.get_last_plan(), full_text)

    if "[FEATURE]" in analysis:
        db.log_insight(analysis)

    # Извлекаем предложенный vibe и применяем
    for vibe in ["spark", "observer", "twilight"]:
        if vibe in analysis.lower():
            db.set_vibe(vibe)
            break

    db.mark_report_pending(False)

    await message.answer(analysis)
    await message.answer("Записала. Отдыхай, завтра увидимся 🌙")
    await state.clear()
