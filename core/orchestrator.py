# -*- coding: utf-8 -*-
"""
core/orchestrator.py
Multi-Agent Orchestrator v1

Маршрутизирует сообщения пользователя к нужному агенту.
Каждый агент — отдельный системный промпт, своя специализация.

Агенты:
  DietAgent      🥗  питание, рецепты, план еды
  CoachAgent     💪  задачи, мотивация, привычки
  ChatAgent      💬  поддержка, разговор по душам
  FilmAgent      🎬  фильмы, сериалы, музыка
  FinanceAgent   💰  бюджет, экономия
  TravelAgent    ✈️  путешествия (→ travel_handler.py)

Роутинг:
  1. Ключевые слова → быстрый роутинг (без токенов)
  2. Если неясно → маленький Gemini Flash для классификации
  3. Context из HumanState → уточняет агента
"""

import re
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


# ── АГЕНТЫ ────────────────────────────────────────────────────────────────────

AGENTS = {
    "diet": {
        "name":   "DietAgent",
        "emoji":  "🥗",
        "system": """Ты персональный диетолог и кулинарный консультант.
Специализация: рецепты, питание, план еды, подсчёт калорий, список покупок.
Отвечай конкретно: ингредиенты, шаги приготовления, советы по хранению.
Учитывай бюджет и ограничения пользователя.
Тон: дружелюбный, практичный. Без длинных вступлений.""",
    },
    "coach": {
        "name":   "CoachAgent",
        "emoji":  "💪",
        "system": """Ты личный коуч по привычкам и продуктивности.
Специализация: задачи на день, мотивация, формирование привычек, планирование.
Давай конкретные маленькие задачи — не большие цели а следующий шаг.
Знаешь о состоянии пользователя и его паттернах.
Тон: заряжающий, честный, без пустых фраз.""",
    },
    "chat": {
        "name":   "ChatAgent",
        "emoji":  "💬",
        "system": """Ты тёплый и внимательный собеседник, задушевный друг.
Специализация: поддержка, разговор по душам, эмпатия, работа со стрессом.
Слушай, задавай вопросы, не навязывай решения.
Если человеку плохо — просто будь рядом прежде чем давать советы.
Тон: тёплый, живой, как друг который всегда выслушает.""",
    },
    "film": {
        "name":   "FilmAgent",
        "emoji":  "🎬",
        "system": """Ты эксперт по кино, сериалам и музыке.
Специализация: рекомендации фильмов/сериалов/музыки под настроение и вкусы.
Учитывай что уже смотрел/слушал пользователь и его лайки/дизлайки.
Давай конкретные рекомендации с кратким описанием почему именно это.
Тон: увлечённый, как друг-киноман.""",
    },
    "finance": {
        "name":   "FinanceAgent",
        "emoji":  "💰",
        "system": """Ты советник по личным финансам и экономии.
Специализация: бюджет на питание, экономия, умные покупки, планирование расходов.
Давай конкретные числа и практические советы.
Знаешь бюджет пользователя на питание.
Тон: практичный, без осуждения.""",
    },
}

# ── КЛЮЧЕВЫЕ СЛОВА ДЛЯ БЫСТРОГО РОУТИНГА ─────────────────────────────────────

KEYWORDS = {
    "diet": [
        "рецепт", "приготовить", "поесть", "завтрак", "обед", "ужин",
        "блюдо", "еда", "питание", "калории", "похудеть", "диета",
        "продукты", "холодильник", "готовить", "меню", "перекус",
        "белки", "жиры", "углеводы", "ккал",
    ],
    "coach": [
        "задача", "план", "цель", "привычка", "мотивация", "продуктивность",
        "не могу", "лень", "прокрастинация", "успеть", "сделать",
        "тренировка", "спорт", "зарядка", "прогулка", "упражнение",
    ],
    "film": [
        "фильм", "сериал", "посмотреть", "кино", "аниме", "музыка",
        "послушать", "плейлист", "рекомендуй", "что посмотреть",
    ],
    "finance": [
        "деньги", "бюджет", "сэкономить", "дорого", "дёшево", "стоит",
        "потратил", "расходы", "финансы", "цена",
    ],
    "chat": [
        "устал", "грустно", "плохо", "одиноко", "стресс", "тревога",
        "поговорить", "поддержи", "как дела", "не знаю что делать",
        "скучно", "переживаю", "не получается",
    ],
    "travel": [
        "поездка", "путешествие", "отпуск", "лететь", "виза", "отель",
        "туризм", "страна", "город", "достопримечательности", "маршрут",
    ],
}


def classify_by_keywords(text: str) -> Optional[str]:
    """Быстрая классификация по ключевым словам. O(n) без токенов."""
    text_lower = text.lower()
    scores = {agent: 0 for agent in KEYWORDS}
    for agent, words in KEYWORDS.items():
        for word in words:
            if word in text_lower:
                scores[agent] += 1
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return None


async def classify_by_gemini(text: str, profile: dict) -> str:
    """Классификация через Gemini Flash — только если ключевые слова не помогли."""
    try:
        from core.key_manager import KeyManager
        from google import genai

        km = KeyManager()
        client = genai.Client(api_key=km.get_key())

        prompt = (
            f"Определи к какому агенту относится сообщение. "
            f"Ответь ОДНИМ словом из: diet, coach, chat, film, finance, travel\n\n"
            f"Сообщение: {text[:200]}"
        )

        def _call():
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={"max_output_tokens": 10}
            )
            return resp.text.strip().lower()

        result = await asyncio.get_event_loop().run_in_executor(None, _call)
        for agent in AGENTS:
            if agent in result:
                return agent
    except Exception as e:
        logger.warning(f"Orchestrator classify error: {e}")
    return "chat"  # default


# ── ГЛАВНЫЙ КЛАСС ─────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Маршрутизатор сообщений.
    Определяет агента и генерирует ответ с его системным промптом.
    """

    def __init__(self, user_id: int, profile: dict, db=None):
        self.user_id = user_id
        self.profile = profile
        self.db      = db

    async def route(self, text: str) -> tuple[str, str]:
        """
        Возвращает (agent_name, response_text).
        """
        # 1. Быстрый роутинг
        agent_id = classify_by_keywords(text)

        # 2. Travel → редирект на /travel команду
        if agent_id == "travel":
            return "travel", (
                "✈️ Для планирования поездки используй команду /travel — "
                "там я задам несколько вопросов и составлю персональный план!"
            )

        # 3. Если не определили — Gemini классифицирует
        if not agent_id:
            agent_id = await classify_by_gemini(text, self.profile)

        # 4. Получаем контекст состояния
        state_ctx = await self._get_state_context()

        # 5. Генерируем ответ нужным агентом
        agent  = AGENTS.get(agent_id, AGENTS["chat"])
        response = await self._call_agent(agent, text, state_ctx)

        return agent["name"], response

    async def _get_state_context(self) -> str:
        """Собирает контекст из HumanState и паттернов."""
        if not self.db:
            return ""
        try:
            from core.event_bus import EventBus
            bus = EventBus(self.user_id, self.db)
            return bus.get_context_for_ai()
        except Exception:
            return ""

    async def _call_agent(self, agent: dict, user_text: str,
                           state_ctx: str) -> str:
        """Вызывает Gemini с полным промптом нужного агента."""
        from core.key_manager import KeyManager
        from core.agent_prompts import get_agent_prompt
        from google import genai

        # История диалога
        history_ctx = ""
        if self.db:
            try:
                history = self.db.get_recent_history(limit=6)
                if history:
                    history_ctx = ""
                    for h in history[-4:]:
                        role = "Пользователь" if h["role"] == "user" else "Ты"
                        history_ctx += f"{role}: {h['message'][:120]}\n"
            except Exception:
                pass

        # Недельный дайджест если есть
        week_digest = ""
        if self.db:
            try:
                week_digest = self.db.get_last_week_summary() or ""
            except Exception:
                pass

        # Определяем agent_id из имени агента
        agent_id_map = {
            "DietAgent":    "diet",
            "CoachAgent":   "coach",
            "ChatAgent":    "chat",
            "FilmAgent":    "film",
            "FinanceAgent": "finance",
        }
        agent_id = agent_id_map.get(agent["name"], "chat")

        # Строим полный промпт
        system = get_agent_prompt(
            agent_id    = agent_id,
            profile     = self.profile,
            state_ctx   = state_ctx,
            history_ctx = history_ctx,
            week_digest = week_digest,
        )

        try:
            km = KeyManager()
            client = genai.Client(api_key=km.get_key())

            def _call():
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=user_text,
                    config={
                        "system_instruction": system,
                        "max_output_tokens": 1500,
                    }
                )
                return resp.text.strip()

            return await asyncio.get_event_loop().run_in_executor(None, _call)

        except Exception as e:
            logger.error(f"Agent {agent['name']} error: {e}")
            return "Прости, что-то пошло не так. Попробуй ещё раз."
