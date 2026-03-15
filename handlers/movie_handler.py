# -*- coding: utf-8 -*-
"""
bot/handlers/movie_handler.py
Кино-советчик v1 — подбор фильмов по настроению с характером.

Флоу:
  /movie или кнопка "🎬 Кино"
    → Какое настроение?
      → Популярное / Среднее / Редкий бриллиант
        → Бот даёт 1 фильм с душевным описанием
        → Постер + трейлер YouTube + кнопка "Другой фильм"
        → Скачать карточку фильма в HTML
"""

import asyncio
import logging
import urllib.parse
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.provider_manager import generate as ai_generate

logger = logging.getLogger(__name__)
router = Router()


class MovieStates(StatesGroup):
    choosing_mood   = State()
    choosing_rarity = State()
    choosing_genre  = State()


MOODS = [
    ("😄 Весёлое и лёгкое",   "happy"),
    ("😢 Грустить и думать",  "sad"),
    ("😱 Страх и адреналин",  "thriller"),
    ("🤩 Вдохновиться",       "inspiring"),
    ("😴 Фоном, не думать",   "easy"),
    ("🤔 Что-то необычное",   "arthouse"),
    ("💑 С партнёром",        "romantic"),
    ("👨‍👩‍👦 Всей семьёй",        "family"),
]

RARITY = [
    ("🔥 Популярное — хочу гарантированно хорошее", "popular"),
    ("✨ Среднее — чуть менее известное, но крутое", "mid"),
    ("💎 Редкий бриллиант — что-то особенное",       "rare"),
]

MOOD_NAMES = {
    "happy":     "весёлое и лёгкое",
    "sad":       "грустное и глубокое",
    "thriller":  "напряжённое и страшное",
    "inspiring": "вдохновляющее",
    "easy":      "лёгкое фоновое",
    "arthouse":  "необычное и артхаусное",
    "romantic":  "романтическое",
    "family":    "семейное",
}


# ── ТОЧКА ВХОДА ────────────────────────────────────────────────────────────

@router.message(Command("movie"))
@router.message(F.text.in_({"🎬 Кино", "🎬 Кино на вечер"}), StateFilter(default_state))
async def cmd_movie(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for label, data in MOODS:
        builder.button(text=label, callback_data=f"mov_mood_{data}")
    builder.adjust(2)
    await message.answer(
        "🎬 *Кино на вечер*\n\n"
        "Какое у тебя сейчас настроение?\n"
        "_Подберу что-то точно под тебя_",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(MovieStates.choosing_mood)


@router.callback_query(F.data == "menu_movie")
async def cb_menu_movie(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_movie(cb.message, state)


# ── ШАГ 1: НАСТРОЕНИЕ ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mov_mood_"), StateFilter(MovieStates.choosing_mood))
async def movie_mood_chosen(cb: types.CallbackQuery, state: FSMContext):
    mood = cb.data.replace("mov_mood_", "")
    await state.update_data(mood=mood)
    await cb.answer()

    builder = InlineKeyboardBuilder()
    for label, data in RARITY:
        builder.button(text=label, callback_data=f"mov_rare_{data}")
    builder.adjust(1)

    await cb.message.edit_text(
        f"Отлично — {MOOD_NAMES.get(mood, mood)} 👌\n\n"
        "Что предпочитаешь по известности?",
        reply_markup=builder.as_markup()
    )
    await state.set_state(MovieStates.choosing_rarity)


# ── ШАГ 2: РЕДКОСТЬ → ГЕНЕРАЦИЯ ────────────────────────────────────────────

@router.callback_query(F.data.startswith("mov_rare_"), StateFilter(MovieStates.choosing_rarity))
async def movie_rarity_chosen(cb: types.CallbackQuery, state: FSMContext):
    rarity = cb.data.replace("mov_rare_", "")
    data = await state.get_data()
    mood = data.get("mood", "happy")
    await state.update_data(rarity=rarity)
    await cb.answer()
    await state.set_state(default_state)

    # Достаём seen_list из профиля (фильмы которые уже видел)
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    seen = profile.get("seen_movies", []) if profile else []
    seen_str = ", ".join(seen[-10:]) if seen else "нет"

    # Специальная вступительная фраза для редких
    if rarity == "rare":
        intro = "Ищу настоящий бриллиант... 💎"
    elif rarity == "mid":
        intro = "Подбираю что-то особенное... ✨"
    else:
        intro = "Подбираю проверенное кино... 🎬"

    thinking = await cb.message.answer(intro)

    prompt = _build_movie_prompt(mood, rarity, seen_str, profile)

    try:
        result = await ai_generate("", prompt, max_tokens=1200)
        await thinking.delete()
        await _send_movie_card(cb.message, result, mood, rarity, user_id, state)
    except Exception as e:
        logger.error(f"Movie generation error: {e}")
        await thinking.edit_text("Не смог подобрать фильм, попробуй ещё раз 🙏")


def _build_movie_prompt(mood: str, rarity: str, seen: str, profile: dict) -> str:
    rarity_map = {
        "popular": "очень известный, топ-250 IMDb или кассовый хит, высокий рейтинг",
        "mid":     "менее известный широкой публике, но высоко оценённый критиками и киноманами, рейтинг 7.0-8.0",
        "rare":    "редкий, малоизвестный широкой публике, настоящий артхаус или скрытый шедевр, рейтинг может быть нишевым но очень высоким среди тех кто смотрел",
    }
    mood_map = {
        "happy":     "весёлый, комедийный, лёгкий, поднимает настроение",
        "sad":       "глубокий, драматичный, заставляет думать и чувствовать",
        "thriller":  "напряжённый, триллер, хоррор или детектив с адреналином",
        "inspiring": "вдохновляющий, мотивирующий, о преодолении и победе духа",
        "easy":      "лёгкий, необременительный, можно смотреть вполглаза",
        "arthouse":  "артхаус, необычная структура, нелинейный нарратив, авторское кино",
        "romantic":  "романтический, о любви, тёплый и душевный",
        "family":    "семейный, подходит всем возрастам, добрый и интересный",
    }
    name = profile.get("name", "") if profile else ""
    name_str = f"Зовут {name}." if name else ""

    rare_intro = ""
    if rarity == "rare":
        rare_intro = (
            "ВАЖНО: это должен быть действительно редкий и малоизвестный фильм — "
            "не Форрест Гамп, не Побег из Шоушенка, не Крёстный отец. "
            "Что-то что обычный зритель вряд ли видел, но это настоящий шедевр своего жанра. "
            "Представь его как 'редкий бриллиант'."
        )

    return f"""Ты — душевный кино-советчик с характером и вкусом. {name_str}
Настроение зрителя: {mood_map.get(mood, mood)}.
Тип фильма: {rarity_map.get(rarity, rarity)}.
{rare_intro}
Уже видел (НЕ предлагай): {seen}.

Посоветуй ОДИН конкретный фильм. Ответь СТРОГО в таком формате (каждый блок с новой строки):

TITLE: [Название на русском] / [Оригинальное название]
YEAR: [Год]
GENRE: [Жанр]
COUNTRY: [Страна]
RATING: [Рейтинг IMDb или Кинопоиск]
TAGLINE: [Одна фраза — твой личный тэглайн для этого фильма, не официальный]
DESCRIPTION: [3-4 предложения — душевное описание от лица друга. Не пересказывай сюжет дословно. Передай ощущение, атмосферу, почему именно сейчас стоит посмотреть. Пиши живо, по-человечески.]
WHY_NOW: [1-2 предложения — почему именно сейчас, именно при таком настроении]
YOUTUBE_SEARCH: [поисковый запрос для YouTube трейлера — название фильма + trailer + год]
POSTER_SEARCH: [запрос для поиска постера — название на английском + poster + год]"""


async def _send_movie_card(message, raw: str, mood: str, rarity: str, user_id: int, state: FSMContext):
    """Парсит ответ AI и отправляет красивую карточку фильма."""
    fields = {}
    for line in raw.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()

    title    = fields.get("TITLE", "Неизвестный фильм")
    year     = fields.get("YEAR", "")
    genre    = fields.get("GENRE", "")
    country  = fields.get("COUNTRY", "")
    rating   = fields.get("RATING", "")
    tagline  = fields.get("TAGLINE", "")
    desc     = fields.get("DESCRIPTION", "")
    why      = fields.get("WHY_NOW", "")
    yt_q     = fields.get("YOUTUBE_SEARCH", f"{title} trailer")
    poster_q = fields.get("POSTER_SEARCH", title)

    yt_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(yt_q)

    # Формируем сообщение
    rarity_prefix = {
        "rare":    "💎 *Редкий бриллиант*\n\n",
        "mid":     "✨ *Моя находка*\n\n",
        "popular": "🔥 *Проверенное кино*\n\n",
    }.get(rarity, "🎬 ")

    text = (
        f"{rarity_prefix}"
        f"*{title}*\n"
        f"_{tagline}_\n\n"
        f"📅 {year}  🎭 {genre}  🌍 {country}  ⭐ {rating}\n\n"
        f"{desc}\n\n"
        f"💬 _{why}_"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="▶️ Смотреть трейлер", url=yt_url),
    )
    builder.row(
        types.InlineKeyboardButton(text="⬇️ Скачать карточку", callback_data=f"mov_dl_{user_id}"),
        types.InlineKeyboardButton(text="🎬 Другой фильм", callback_data=f"mov_again_{mood}_{rarity}"),
    )
    builder.row(
        types.InlineKeyboardButton(text="👀 Уже видел", callback_data=f"mov_seen_{title[:30]}"),
    )

    # Сохраняем данные для скачивания
    db = MemoryManager(user_id)
    db.save_profile({"last_movie": fields})

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# ── ДРУГОЙ ФИЛЬМ ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mov_again_"))
async def movie_again(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.replace("mov_again_", "").split("_", 1)
    mood   = parts[0] if len(parts) > 0 else "happy"
    rarity = parts[1] if len(parts) > 1 else "popular"

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile()
    seen = profile.get("seen_movies", []) if profile else []
    seen_str = ", ".join(seen[-10:]) if seen else "нет"

    thinking = await cb.message.answer("Ищу другой вариант... 🎬")
    prompt = _build_movie_prompt(mood, rarity, seen_str, profile)

    try:
        result = await ai_generate("", prompt, max_tokens=1200)
        await thinking.delete()
        await _send_movie_card(cb.message, result, mood, rarity, user_id, state)
    except Exception as e:
        logger.error(f"Movie again error: {e}")
        await thinking.edit_text("Не смог подобрать, попробуй ещё раз 🙏")


# ── ВИДЕЛ / СТОП-ЛИСТ ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mov_seen_"))
async def movie_seen(cb: types.CallbackQuery):
    await cb.answer("Добавлено в просмотренные!")
    title = cb.data.replace("mov_seen_", "")
    db = MemoryManager(cb.from_user.id)
    profile = db.get_profile() or {}
    seen = profile.get("seen_movies", [])
    if title not in seen:
        seen.append(title)
    db.save_profile({"seen_movies": seen[-50:]})  # храним последние 50


# ── СКАЧАТЬ КАРТОЧКУ HTML ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mov_dl_"))
async def movie_download(cb: types.CallbackQuery):
    await cb.answer("Генерирую карточку...")
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}
    fields = profile.get("last_movie", {})

    if not fields:
        return await cb.message.answer("Нет данных для скачивания 🤷")

    html = _build_movie_html(fields)

    import tempfile, os, aiofiles
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                     encoding='utf-8', delete=False) as f:
        f.write(html)
        tmp_path = f.name

    title_safe = fields.get("TITLE", "film")[:30].replace("/", "-").replace(" ", "_")

    try:
        async with aiofiles.open(tmp_path, 'rb') as f:
            content = await f.read()
        from aiogram.types import BufferedInputFile
        await cb.message.answer_document(
            BufferedInputFile(content, filename=f"movie_{title_safe}.html"),
            caption="🎬 Карточка фильма"
        )
    finally:
        os.unlink(tmp_path)


def _build_movie_html(f: dict) -> str:
    title    = f.get("TITLE", "Фильм")
    year     = f.get("YEAR", "")
    genre    = f.get("GENRE", "")
    country  = f.get("COUNTRY", "")
    rating   = f.get("RATING", "")
    tagline  = f.get("TAGLINE", "")
    desc     = f.get("DESCRIPTION", "")
    why      = f.get("WHY_NOW", "")
    yt_q     = f.get("YOUTUBE_SEARCH", title)
    poster_q = f.get("POSTER_SEARCH", title)

    yt_url     = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(yt_q)
    poster_url = f"https://source.unsplash.com/600x900/?movie,cinema,{urllib.parse.quote(poster_q.split()[0])}"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@400;700;900&family=Inter:wght@300;400;500&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:#07090d;color:#e8e8e8;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
.card{{max-width:520px;width:100%;background:#0d1318;border:1px solid rgba(255,255,255,0.08);border-radius:24px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.5)}}
.poster{{width:100%;height:320px;object-fit:cover;display:block}}
.poster-fallback{{width:100%;height:320px;background:linear-gradient(135deg,#1a2a3a,#0d1318);display:flex;align-items:center;justify-content:center;font-size:5rem}}
.body{{padding:28px}}
.genre-row{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}}
.tag{{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:100px;padding:4px 12px;font-size:0.72rem;color:#aaa}}
h1{{font-family:'Unbounded',sans-serif;font-size:1.4rem;font-weight:900;line-height:1.2;margin-bottom:6px}}
.tagline{{font-size:0.85rem;color:#39ff6a;font-style:italic;margin-bottom:20px}}
.desc{{font-size:0.88rem;line-height:1.7;color:#ccc;margin-bottom:16px}}
.why{{background:rgba(57,255,106,0.06);border:1px solid rgba(57,255,106,0.15);border-radius:12px;padding:14px 16px;font-size:0.82rem;color:#aaa;line-height:1.6;margin-bottom:20px}}
.why::before{{content:'💬  ';}}
.btn{{display:block;text-align:center;background:linear-gradient(135deg,#39ff6a,#00d4ff);color:#000;font-family:'Unbounded',sans-serif;font-weight:700;font-size:0.85rem;padding:14px;border-radius:12px;text-decoration:none;transition:opacity 0.2s}}
.btn:hover{{opacity:0.85}}
.meta{{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}}
.meta-item{{font-size:0.75rem;color:#666}}
.meta-item span{{color:#ccc;font-weight:500}}
</style>
</head>
<body>
<div class="card">
  <img class="poster" src="{poster_url}" alt="{title}"
       onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
  <div class="poster-fallback" style="display:none">🎬</div>
  <div class="body">
    <div class="genre-row">
      <span class="tag">🎭 {genre}</span>
      <span class="tag">🌍 {country}</span>
      <span class="tag">⭐ {rating}</span>
      <span class="tag">📅 {year}</span>
    </div>
    <h1>{title}</h1>
    <div class="tagline">{tagline}</div>
    <div class="desc">{desc}</div>
    <div class="why">{why}</div>
    <a href="{yt_url}" target="_blank" class="btn">▶️ Смотреть трейлер на YouTube</a>
  </div>
</div>
</body>
</html>"""
