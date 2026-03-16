# -*- coding: utf-8 -*-
"""
core/content_agent.py
ContentAgent v1 — рекомендации фильмов, музыки и книг.

Структура кино-рекомендации (5 позиций):
  1. Аниме / мультфильм
  2. Сериал
  3. Артхаус (редкий бриллиант)
  4. Среднее (хорошее, не хит)
  5. Мейнстрим (популярное)

Режим: разовый (без профиля) или LifeMode (с контекстом).
"""

from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

CONTENT_PROMPT = """Ты эксперт по кино, музыке и книгам. Твои рекомендации точные, неожиданные и всегда объяснены.

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
{user_context}

ЗАПРОС:
{request}

ЖАНР/НАСТРОЕНИЕ: {genre}
С КЕМ СМОТРИТ: {company}
ВРЕМЯ: {time_context}
LIFEMODE: {lifemode}

ЗАДАЧА: Дай ровно 5 рекомендаций фильмов в строгой структуре:

1. 🎌 АНИМЕ или МУЛЬТФИЛЬМ
Название (год)
Почему подходит прямо сейчас: [1-2 предложения, конкретно]

2. 📺 СЕРИАЛ (1-2 сезона, не больше)
Название (год, кол-во сезонов)
Почему стоит начать именно сейчас: [1-2 предложения]

3. 💎 АРТХАУС / РЕДКИЙ БРИЛЛИАНТ
Название (год, страна)
Почему это шедевр и почему мало кто видел: [2-3 предложения]

4. 🎯 СРЕДНЕЕ — не хит, но качественное
Название (год)
Почему именно это: [1-2 предложения]

5. 🍿 МЕЙНСТРИМ — популярное и понятное
Название (год)
Почему подойдёт: [1 предложение]

---
СТОП-ЛИСТ (не предлагать): {stop_list}

Отвечай только в этом формате. Без вступления и заключения."""

MUSIC_PROMPT = """Ты музыкальный куратор. Рекомендации точные и неожиданные.

НАСТРОЕНИЕ: {mood}
LIFEMODE: {lifemode}
ВРЕМЯ СУТОК: {time_context}
УЖЕ СЛЫШАЛ: {stop_list}

Дай 3 музыкальных рекомендации в структуре:

1. 🎵 MAINSTREAM — известный трек
Исполнитель — Название трека
Настроение трека: [1 предложение]
🔍 Найти: Яндекс Музыка / VK Музыка / YouTube

2. 💎 HIDDEN GEM — менее известное
Исполнитель — Название трека
Почему стоит послушать: [1 предложение]
🔍 Найти: YouTube

3. 🌊 DEEP CUT — редкость для знатоков
Исполнитель — Название трека
Что особенного: [1 предложение]
🔍 Найти: YouTube

Только этот формат."""

BOOK_PROMPT = """Ты книжный куратор. Рекомендуешь только то что сам бы прочитал.

ЦЕЛЬ ПОЛЬЗОВАТЕЛЯ: {goal}
LIFEMODE: {lifemode}
ЖАНР: {genre}
УЖЕ ЧИТАЛ: {stop_list}

Дай 3 рекомендации книг:

1. 📚 ПОД ЦЕЛЬ — прямо помогает с целью
Автор — Название
О чём: [1 предложение]
Где найти: ЛитРес / Букмейт / Яндекс Книги

2. 🌟 КЛАССИКА — обязательно прочитать
Автор — Название
Почему не стареет: [1 предложение]
Где найти: ЛитРес / Google Books

3. 💡 НЕОЖИДАННОЕ — из другой области
Автор — Название
Почему расширяет мышление: [1 предложение]
Где найти: ЛитРес / Букмейт

Только этот формат."""


class ContentAgent:
    def __init__(self, user_id: int, profile: dict = None):
        self.user_id = user_id
        self.profile = profile or {}

    def _hour(self) -> int:
        return datetime.now().hour

    def _time_context(self) -> str:
        h = self._hour()
        if 5 <= h < 12:  return "утро"
        if 12 <= h < 17: return "день"
        if 17 <= h < 22: return "вечер"
        return "ночь"

    def _weekday_context(self) -> str:
        wd = datetime.now().weekday()
        if wd == 4: return "пятница вечер — время расслабиться"
        if wd in (5, 6): return "выходной день — есть время"
        if wd == 0: return "понедельник — начало недели"
        return "будний день"

    def _stop_list(self, category: str) -> str:
        from core.db_extensions import get_content_history
        items = get_content_history(self.user_id, category, limit=20)
        return ", ".join(items[:15]) if items else "нет"

    def _lifemode_str(self) -> str:
        try:
            from core.lifemode_agent import LifeModeAgent
            lm = LifeModeAgent(self.user_id)
            return lm.get_content_context()
        except Exception:
            return "обычный режим"

    def _user_context(self) -> str:
        if not self.profile:
            return "профиль не заполнен — разовый запрос"
        name = self.profile.get("name", "")
        goal = self.profile.get("goal", "")
        hobby = self.profile.get("hobby", "")
        return f"имя: {name}, цель: {goal}, интересы: {hobby}"

    async def get_movie_recs(self, genre: str = "любой",
                              company: str = "один",
                              custom_request: str = "") -> str:
        """Генерирует 5 рекомендаций фильмов."""
        from core.provider_manager import generate as pm_gen

        time_ctx = f"{self._time_context()}, {self._weekday_context()}"
        prompt = CONTENT_PROMPT.format(
            user_context=self._user_context(),
            request=custom_request or "посоветуй фильм",
            genre=genre,
            company=company,
            time_context=time_ctx,
            lifemode=self._lifemode_str(),
            stop_list=self._stop_list("movie"),
        )
        result = await pm_gen(prompt, mode="chat")
        # Логируем первый заголовок в стоп-лист
        self._log_recommendations(result, "movie")
        return result

    async def get_music_rec(self, mood: str = "нейтральное") -> str:
        from core.provider_manager import generate as pm_gen
        prompt = MUSIC_PROMPT.format(
            mood=mood,
            lifemode=self._lifemode_str(),
            time_context=self._time_context(),
            stop_list=self._stop_list("music"),
        )
        result = await pm_gen(prompt, mode="chat")
        return result

    async def get_book_rec(self, genre: str = "любой",
                            goal: str = "") -> str:
        from core.provider_manager import generate as pm_gen
        prompt = BOOK_PROMPT.format(
            goal=goal or self.profile.get("goal", "саморазвитие"),
            lifemode=self._lifemode_str(),
            genre=genre,
            stop_list=self._stop_list("book"),
        )
        result = await pm_gen(prompt, mode="chat")
        self._log_recommendations(result, "book")
        return result

    def _log_recommendations(self, text: str, category: str):
        """Сохраняем рекомендованные названия в content_log."""
        try:
            import re
            from core.db_extensions import log_content
            # Ищем строки с названиями (после номера и эмодзи)
            titles = re.findall(r'(?:^|\n)[1-5][.\)]\s+[^\n]+\n([^\n]{3,60})', text)
            for title in titles[:5]:
                title = title.strip()
                if title:
                    log_content(self.user_id, category, title[:100])
        except Exception as e:
            logger.debug(f"log_recommendations error: {e}")

    def format_with_copy_buttons(self, text: str) -> tuple[str, list]:
        """
        Возвращает (форматированный_текст, список_названий_для_кнопок).
        Кнопки копирования создаются в handler'е через InlineKeyboardBuilder.
        """
        import re
        lines = text.split('\n')
        titles = []
        for line in lines:
            # Ищем строки типа "Название (год)" или "Автор — Название"
            m = re.match(r'^([A-ZА-ЯЁa-zа-яё][^({\n]{3,50})(?:\s*[\(\{]|\s*$)', line)
            if m and len(titles) < 5:
                candidate = m.group(1).strip()
                if len(candidate) > 3 and not candidate.startswith(('Почему', 'Настроение', 'О чём', 'Где', 'Найти')):
                    titles.append(candidate)
        return text, titles
