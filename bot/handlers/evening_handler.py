"""
bot/handlers/evening_handler.py
Вечерний аудит v2 — рекомендации из PatternCache, Gemini только если кэш пустой
"""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from core.pattern_cache import PatternCache

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
    tasks   = data["tasks"]
    index   = data["index"]
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
    data    = await state.get_data()
    user_id = message.from_user.id
    db      = MemoryManager(user_id)
    profile = db.get_profile()
    ai      = GeminiEngine(profile)
    cache   = PatternCache(user_id)

    results_text = "\n".join(data.get("results", []))
    full_text    = f"Итоги:\n{results_text}\n\nФидбек: {message.text}"

    # Анализ вечера (Gemini)
    analysis = ai.analyze_evening(db.get_last_plan(), full_text)

    # Сохраняем day_summary
    day_summary = ai.generate_day_summary(message.text, results_text)
    mood = GeminiEngine.extract_mood(analysis) or "neutral"
    db.save_day_summary(day_summary, mood)
    db.set_mood(mood)

    vibe = GeminiEngine.extract_vibe(analysis)
    if vibe:
        db.set_vibe(vibe)

    db.mark_report_pending(False)
    db.update_streak()

    if "[FEATURE]" in analysis:
        db.log_insight(analysis)

    await message.answer(analysis)

    # ── РЕКОМЕНДАЦИИ: сначала из кэша ──────────────────────────────────
    await message.answer("🎬 Подбираю рекомендации на вечер...")

    stop_list = db.get_stop_list()

    film  = cache.get_recommendation(mood, vibe or "observer", "film")
    music = cache.get_recommendation(mood, vibe or "observer", "music")
    book  = cache.get_recommendation(mood, vibe or "observer", "book")

    if film and music and book:
        # Всё из кэша — Gemini не нужен
        rec_text = _format_recs_from_cache(film, music, book)
        await message.answer(rec_text, parse_mode="Markdown")
    else:
        # Идём к Gemini
        try:
            recs_raw = ai.get_evening_recommendations(mood, stop_list)
            await message.answer(recs_raw, parse_mode="Markdown")

            # Парсим и сохраняем в кэш для следующего раза
            parsed = ai.parse_recommendations(recs_raw)
            if parsed:
                for cat, items in parsed.items():
                    cache.save_recommendations(mood, vibe or "observer", cat, items)
        except Exception:
            await message.answer("Не смог подобрать рекомендации — попробуй позже.")

    # ── Инлайн-кнопки лайк/дизлайк ────────────────────────────────────
    if film:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(
                text=f"👍 {film.get('title','')[:25]}",
                callback_data=f"rec_like_film_{film.get('title','')[:20]}"
            ),
            types.InlineKeyboardButton(
                text="👎 Не то",
                callback_data=f"rec_skip_film_{film.get('title','')[:20]}"
            ),
        )
        await message.answer("Как тебе рекомендация?", reply_markup=builder.as_markup())

    await message.answer("Записал. Отдыхай, завтра увидимся 🌙")
    await state.clear()


def _format_recs_from_cache(film: dict, music: dict, book: dict) -> str:
    lines = ["*Вечерние рекомендации* 🌙\n"]
    lines.append(f"🎬 *{film.get('title', '?')}*")
    if film.get('why'):
        lines.append(f"_{film['why']}_")
    lines.append(f"\n🎵 *{music.get('title', '?')}*")
    if music.get('mood'):
        lines.append(f"_{music['mood']}_")
    lines.append(f"\n📚 *{book.get('title', '?')}*")
    if book.get('author'):
        lines.append(f"_{book['author']}_")
    if book.get('why'):
        lines.append(f"_{book['why']}_")
    return "\n".join(lines)


# ── ЛАЙК/ДИЗЛАЙК РЕКОМЕНДАЦИЙ ────────────────────────────────────────

@router.callback_query(F.data.startswith("rec_like_"))
async def rec_liked(cb: types.CallbackQuery):
    parts = cb.data.split("_", 3)  # rec_like_film_title
    if len(parts) < 4:
        return await cb.answer()
    category = parts[2]
    title    = parts[3]
    cache = PatternCache(cb.from_user.id)
    cache.mark_liked(category, title, liked=True)
    await cb.answer("👍 Запомнил!")
    await cb.message.edit_text(f"👍 Отлично! Буду рекомендовать похожее.")


@router.callback_query(F.data.startswith("rec_skip_"))
async def rec_skipped(cb: types.CallbackQuery):
    parts = cb.data.split("_", 3)
    if len(parts) < 4:
        return await cb.answer()
    category = parts[2]
    title    = parts[3]
    cache = PatternCache(cb.from_user.id)
    cache.mark_liked(category, title, liked=False)
    db = MemoryManager(cb.from_user.id)
    db.add_to_stop_list(title)
    await cb.answer("👎 Запомнил, больше не покажу")
    await cb.message.edit_text(f"👎 Добавил в стоп-лист. Подберу что-то другое.")
