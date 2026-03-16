# -*- coding: utf-8 -*-
"""
bot/handlers/content_handler.py
ContentAgent handler — кино, музыка, книги.
"""

import logging
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager

logger = logging.getLogger(__name__)
router = Router()


class ContentStates(StatesGroup):
    waiting_genre   = State()
    waiting_company = State()
    waiting_music_mood = State()
    waiting_book_genre = State()
    waiting_custom  = State()


# ── КИНО ─────────────────────────────────────────────────────────────────

@router.message(Command("movie"), StateFilter(default_state))
@router.message(F.text.in_({"🎬 Кино", "🎬 Фильм"}), StateFilter(default_state))
async def cmd_movie(message: types.Message, state: FSMContext):
    await state.set_state(ContentStates.waiting_genre)
    kb = InlineKeyboardBuilder()
    genres = [
        ("😂 Смешное", "funny"), ("😢 Тяжёлое", "drama"),
        ("🌟 Вдохновляющее", "inspiring"), ("😱 Страшное", "horror"),
        ("🧠 Умное", "smart"), ("🍿 Лёгкое", "easy"),
        ("🌍 Приключения", "adventure"), ("❤️ Романтика", "romance"),
        ("🤷 Любое", "any"),
    ]
    for label, data in genres:
        kb.button(text=label, callback_data=f"cg_{data}")
    kb.adjust(2)
    await message.answer(
        "🎬 *Кино*\n\nКакое настроение?",
        parse_mode="Markdown",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("cg_"))
async def cb_genre(cb: types.CallbackQuery, state: FSMContext):
    genre_map = {
        "funny": "комедия/смешное", "drama": "драма/тяжёлое",
        "inspiring": "вдохновляющее", "horror": "ужасы/триллер",
        "smart": "умное/интеллектуальное", "easy": "лёгкое/фоновое",
        "adventure": "приключения", "romance": "романтика", "any": "любой жанр",
    }
    genre = genre_map.get(cb.data.replace("cg_", ""), "любой")
    await state.update_data(genre=genre)
    await state.set_state(ContentStates.waiting_company)

    kb = InlineKeyboardBuilder()
    for label, data in [
        ("🧍 Один", "solo"), ("💑 С партнёром", "partner"),
        ("👫 С друзьями", "friends"), ("👨‍👩‍👧 С семьёй", "family"),
    ]:
        kb.button(text=label, callback_data=f"cc_{data}")
    kb.adjust(2)
    await cb.message.edit_text(
        "🎬 *Кино*\n\nС кем смотришь?",
        parse_mode="Markdown", reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data.startswith("cc_"), ContentStates.waiting_company)
async def cb_company(cb: types.CallbackQuery, state: FSMContext):
    company_map = {
        "solo": "один", "partner": "с партнёром",
        "friends": "с друзьями", "family": "с семьёй/детьми",
    }
    company = company_map.get(cb.data.replace("cc_", ""), "один")
    await state.update_data(company=company)
    await state.clear()

    data = await state.get_data() if False else {}  # данные уже сохранены
    # Получаем из FSM
    from aiogram.fsm.context import FSMContext as _FSMCtx
    fsm_data = {"genre": "любой", "company": company}

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}

    await cb.message.edit_text("🎬 Подбираю рекомендации... ⏳")
    await cb.answer()

    try:
        from core.content_agent import ContentAgent
        agent = ContentAgent(user_id, profile)
        # Восстанавливаем genre из предыдущего шага через cb.message текст
        genre = "любой"
        result = await agent.get_movie_recs(genre=genre, company=company)
        text, titles = agent.format_with_copy_buttons(result)

        # Кнопки копирования
        kb = InlineKeyboardBuilder()
        for i, title in enumerate(titles[:5]):
            short = title[:30] + "…" if len(title) > 30 else title
            kb.button(text=f"📋 {short}", callback_data=f"copy_movie_{i}")
        kb.button(text="🔄 Ещё рекомендации", callback_data="movie_more")
        kb.adjust(1)

        await cb.message.edit_text(
            text, parse_mode="Markdown", reply_markup=kb.as_markup()
        )
        # Сохраняем titles для копирования
        await state.update_data(movie_titles=titles)

    except Exception as e:
        logger.error(f"movie recs error: {e}")
        await cb.message.edit_text("⚠️ Не смог подобрать рекомендации, попробуй позже.")


@router.callback_query(F.data.startswith("copy_movie_"))
async def cb_copy_movie(cb: types.CallbackQuery, state: FSMContext):
    idx = int(cb.data.split("_")[-1])
    data = await state.get_data()
    titles = data.get("movie_titles", [])
    if idx < len(titles):
        title = titles[idx]
        await cb.answer(f"Скопировано: {title[:50]}", show_alert=True)
        # Отправляем как отдельное сообщение для лёгкого копирования
        await cb.message.answer(f"`{title}`", parse_mode="Markdown")
    else:
        await cb.answer("Название не найдено")


@router.callback_query(F.data == "movie_more")
async def cb_movie_more(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_movie(cb.message, state)


# ── МУЗЫКА ────────────────────────────────────────────────────────────────

@router.message(Command("music"), StateFilter(default_state))
@router.message(F.text.in_({"🎵 Музыка"}), StateFilter(default_state))
async def cmd_music(message: types.Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    moods = [
        ("⚡ Энергия", "energetic"), ("😌 Расслабление", "chill"),
        ("🔥 Мотивация", "motivation"), ("💭 Задумчивое", "thoughtful"),
        ("❤️ Романтика", "romantic"), ("😢 Грусть", "sad"),
        ("🎉 Веселье", "party"), ("🌙 Ночное", "night"),
    ]
    for label, data in moods:
        kb.button(text=label, callback_data=f"mm_{data}")
    kb.adjust(2)
    await message.answer(
        "🎵 *Музыка*\n\nКакое настроение?",
        parse_mode="Markdown", reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("mm_"), StateFilter(default_state))
async def cb_music_mood(cb: types.CallbackQuery, state: FSMContext):
    mood_map = {
        "energetic": "энергичное", "chill": "расслабленное",
        "motivation": "мотивационное", "thoughtful": "задумчивое",
        "romantic": "романтичное", "sad": "грустное",
        "party": "праздничное", "night": "ночное",
    }
    mood = mood_map.get(cb.data.replace("mm_", ""), "нейтральное")
    await cb.message.edit_text("🎵 Подбираю треки... ⏳")
    await cb.answer()

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}

    try:
        from core.content_agent import ContentAgent
        agent = ContentAgent(user_id, profile)
        result = await agent.get_music_rec(mood=mood)
        await cb.message.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"music recs error: {e}")
        await cb.message.edit_text("⚠️ Не смог подобрать музыку, попробуй позже.")


# ── КНИГИ ─────────────────────────────────────────────────────────────────

@router.message(Command("books"), StateFilter(default_state))
@router.message(F.text.in_({"📚 Книги"}), StateFilter(default_state))
async def cmd_books(message: types.Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    genres = [
        ("🚀 Фантастика", "sci-fi"), ("🕵️ Детектив", "detective"),
        ("🧠 Нон-фикшн", "nonfiction"), ("💼 Бизнес", "business"),
        ("🧘 Психология", "psychology"), ("🌍 Приключения", "adventure"),
        ("❤️ Роман", "romance"), ("📖 Классика", "classic"),
    ]
    for label, data in genres:
        kb.button(text=label, callback_data=f"bk_{data}")
    kb.adjust(2)
    await message.answer(
        "📚 *Книги*\n\nКакой жанр?",
        parse_mode="Markdown", reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("bk_"), StateFilter(default_state))
async def cb_book_genre(cb: types.CallbackQuery, state: FSMContext):
    genre = cb.data.replace("bk_", "")
    await cb.message.edit_text("📚 Подбираю книги... ⏳")
    await cb.answer()

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}

    try:
        from core.content_agent import ContentAgent
        agent = ContentAgent(user_id, profile)
        result = await agent.get_book_rec(genre=genre)
        await cb.message.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"book recs error: {e}")
        await cb.message.edit_text("⚠️ Не смог подобрать книги, попробуй позже.")
