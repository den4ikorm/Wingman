# -*- coding: utf-8 -*-
"""
core/course_orchestrator.py
════════════════════════════════════════════════════════
Регистратор курса — дирижирует агентами.

Агенты:
  MentorAgent    — ведёт курс, помнит историю, даёт контекст
  ThoughtAgent   — мысль дня (1-2 предложения, ненавязчиво)
  StoryAgent     — история дня (под профиль пользователя)
  RecommendAgent — фильм/музыка/книга под настроение

Запуск:
  orchestrator = CourseOrchestrator(user_id)
  await orchestrator.run_morning()   # каждое утро в 7:00
  thought = await orchestrator.get_thought()
  story   = await orchestrator.get_story()
════════════════════════════════════════════════════════
"""

import json
import logging
import asyncio
from datetime import date, datetime, timedelta

from core.database import MemoryManager
from core.provider_manager import generate as pm_generate

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  MENTOR AGENT — помнит всё, даёт контекст остальным
# ══════════════════════════════════════════════════════

class MentorAgent:
    """
    Знает пользователя. Строит контекст для других агентов.
    Не общается напрямую — только даёт данные.
    """

    def __init__(self, user_id: int):
        self.db = MemoryManager(user_id)
        self._profile = None
        self._context = None

    def profile(self) -> dict:
        if not self._profile:
            self._profile = self.db.get_profile() or {}
        return self._profile

    def course_day(self) -> int:
        return int(self.profile().get("course_day", 1))

    def advance_day(self):
        """Продвигаем курс на следующий день."""
        day = self.course_day()
        last = self.profile().get("course_last_date", "")
        today = str(date.today())
        if last != today:
            self.db.save_profile({"course_day": day + 1, "course_last_date": today})

    def recent_topics(self, n: int = 7) -> list[str]:
        """Темы последних N дней чтобы не повторяться."""
        try:
            history = self.db.get_profile().get("course_topics", [])
            return history[-n:] if history else []
        except Exception:
            return []

    def save_topic(self, topic: str):
        """Сохраняем тему дня."""
        try:
            profile = self.db.get_profile() or {}
            topics = profile.get("course_topics", [])
            topics.append(topic)
            if len(topics) > 30:
                topics = topics[-30:]
            self.db.save_profile({"course_topics": topics})
        except Exception as e:
            logger.error(f"MentorAgent.save_topic: {e}")

    def build_context(self) -> dict:
        """Строим контекст для других агентов."""
        if self._context:
            return self._context

        p = self.profile()
        weights = self.db.get_weight_history(days=14)

        # Тренд веса
        weight_trend = "неизвестен"
        if len(weights) >= 2:
            try:
                w_start = float(weights[0].get("weight", 0))
                w_end = float(weights[-1].get("weight", 0))
                diff = round(w_end - w_start, 1)
                if diff < -0.5:
                    weight_trend = f"снижается ({diff} кг за 2 недели)"
                elif diff > 0.5:
                    weight_trend = f"растёт (+{diff} кг за 2 недели)"
                else:
                    weight_trend = "стабильный"
            except Exception:
                pass

        # Настроение
        mood_map = {
            "5": "отличное", "4": "хорошее", "3": "нормальное",
            "2": "грустное", "1": "раздражённое", "0": "плохое",
        }
        mood = mood_map.get(str(p.get("emotional_state", "3")), "нормальное")

        # Срывы за неделю (дни без чекина)
        streak = p.get("streak", 0)

        self._context = {
            "name": p.get("name", ""),
            "age": p.get("age", ""),
            "goal": p.get("goal", ""),
            "hobby": p.get("hobby", ""),
            "diet_level": p.get("diet_level", 2),
            "mood": mood,
            "streak": streak,
            "weight_trend": weight_trend,
            "course_day": self.course_day(),
            "recent_topics": self.recent_topics(),
            "stress_coping": p.get("stress_coping", ""),
            "food_meaning": p.get("food_meaning", ""),
            "self_attitude": p.get("self_attitude", ""),
        }
        return self._context


# ══════════════════════════════════════════════════════
#  THOUGHT AGENT — мысль дня
# ══════════════════════════════════════════════════════

class ThoughtAgent:
    """
    Генерирует одну мысль на день.
    Ненавязчиво, как друг который заметил кое-что.
    """

    SYSTEM = """Ты — умный ненавязчивый друг. Не психолог, не тренер.
Твоя задача — написать одну мысль на день. Одну. Короткую.

Правила (строго):
- 1-2 предложения максимум
- Никаких вопросов
- Никаких советов в лоб ("тебе нужно...", "попробуй...")
- Никаких слов: психология, осознанность, паттерн, терапия, эмоции, анализ
- Говори как будто просто заметил кое-что интересное
- Иногда просто факт. Иногда наблюдение. Иногда тихая поддержка.
- Без восклицательных знаков
- Без пафоса"""

    async def generate(self, ctx: dict) -> str:
        recent = ", ".join(ctx.get("recent_topics", [])) or "нет"
        prompt = f"""Пользователь: {ctx.get('name', '')}, цель — {ctx.get('goal', 'похудеть')}.
Настроение: {ctx.get('mood', 'нормальное')}.
Стрик: {ctx.get('streak', 0)} дней.
Вес: {ctx.get('weight_trend', 'неизвестен')}.
День курса: {ctx.get('course_day', 1)}.
Темы последних дней (не повторять): {recent}.

Напиши одну мысль на сегодня. Только текст, без кавычек."""

        try:
            result = await pm_generate(self.SYSTEM, prompt, max_tokens=150)
            return result.strip().strip('"').strip("'")
        except Exception as e:
            logger.error(f"ThoughtAgent.generate: {e}")
            return _fallback_thought(ctx.get("course_day", 1))


def _fallback_thought(day: int) -> str:
    fallbacks = [
        "Иногда холодильник открывается сам. Просто так. Все так делают.",
        "Когда нормально высыпаешься — сладкого хочется меньше. Это не сила воли, просто физиология.",
        "Ну и ладно. Вчера было как было. Сегодня другой день.",
        "Мозг получает сигнал о сытости через 20 минут. Поэтому если есть быстро — всегда кажется что мало.",
        "На хрустящее тянет когда нервничаешь. Не слабость характера — просто так работает.",
        "После 22:00 холодильник — самое популярное место в квартире. Обычно это не голод.",
        "Семь дней. Большинство бросают на третий — это статистика.",
        "Вода реально помогает. Банально, но правда.",
        "Еда вкуснее когда ешь не торопясь.",
        "Десять дней — это уже не случайность.",
    ]
    return fallbacks[(day - 1) % len(fallbacks)]


# ══════════════════════════════════════════════════════
#  STORY AGENT — история дня
# ══════════════════════════════════════════════════════

class StoryAgent:
    """
    Генерирует короткую историю под профиль пользователя.
    Не поучительно — просто живая история.
    """

    SYSTEM = """Ты пишешь короткие истории для людей которые хотят изменить жизнь к лучшему.
Стиль: живой, тёплый, без морали в конце. Как будто рассказываешь другу за чаем.

Правила:
- 3-5 предложений
- Реальная ситуация, реальные люди (без имён или с простыми именами)
- Никакой явной морали ("вывод: ...", "урок: ...")
- Читатель сам делает вывод — или не делает
- Никаких слов: психолог, терапия, осознанность
- Тема связана с едой, телом, усталостью, привычками, маленькими победами"""

    async def generate(self, ctx: dict) -> dict:
        goal = ctx.get("goal", "чувствовать себя лучше")
        mood = ctx.get("mood", "нормальное")
        hobby = ctx.get("hobby", "")

        prompt = f"""Цель пользователя: {goal}.
Настроение сегодня: {mood}.
Хобби: {hobby or 'разные интересы'}.
День курса: {ctx.get('course_day', 1)}.

Напиши короткую историю. Только текст истории, без заголовка."""

        try:
            text = await pm_generate(self.SYSTEM, prompt, max_tokens=250)
            text = text.strip().strip('"')

            # Подпись — краткая, без пафоса
            sign_prompt = f"Придумай короткую подпись (3-5 слов) для этой истории, начиная с тире: {text[:100]}"
            sign = await pm_generate("Пиши кратко.", sign_prompt, max_tokens=30)
            sign = sign.strip()
            if not sign.startswith("—"):
                sign = "— " + sign

            return {"text": text, "author": sign}
        except Exception as e:
            logger.error(f"StoryAgent.generate: {e}")
            return _fallback_story(ctx.get("course_day", 1))


def _fallback_story(day: int) -> dict:
    stories = [
        {
            "text": "Один мужик три года хотел похудеть. Ничего не получалось. Потом его сын попросил играть в футбол во дворе. Он начал. Через полгода минус 15 кг. Он не считал калории.",
            "author": "— Просто история"
        },
        {
            "text": "Женщина в 45 лет первый раз поела в тишине. Без телефона, без телевизора. Говорит: впервые почувствовала когда наелась. Оказывается это можно было всё это время.",
            "author": "— История о тишине"
        },
        {
            "text": "Она не меняла рацион. Просто начала ложиться в 23:00 вместо 2:00. Через месяц сама удивилась — тяга к сладкому почти пропала. Тело нашло откуда брать энергию.",
            "author": "— Про сон"
        },
        {
            "text": "Знаешь что самое сложное в изменении привычек? Не начать. Продолжать когда уже не интересно — вот где настоящая работа. Первые дни на энтузиазме. Потом просто потому что решил.",
            "author": "— Честно"
        },
    ]
    return stories[(day - 1) % len(stories)]


# ══════════════════════════════════════════════════════
#  RECOMMEND AGENT — фильм/музыка/книга
# ══════════════════════════════════════════════════════

class RecommendAgent:
    """
    Подбирает фильм, музыку или книгу под настроение.
    Учитывает стоп-лист и историю рекомендаций.
    """

    SYSTEM = """Ты подбираешь культурные рекомендации под настроение человека.
Говоришь как друг — тепло, без снобизма.
Для редких рекомендаций добавляй фразу вроде "советую один малоизвестный фильм — думаю тебе зайдёт"."""

    async def recommend(self, category: str, ctx: dict, rarity: str = "medium") -> dict:
        stop = self._get_stop_list(ctx.get("user_id"))
        stop_str = ", ".join(stop[:15]) if stop else "нет"

        rarity_map = {
            "popular": "популярное, все слышали",
            "medium": "хорошее но не хит",
            "rare": "малоизвестное, редкий бриллиант — не из топ-1000",
        }

        prompt = f"""Категория: {category} (фильм/музыка/книга).
Настроение: {ctx.get('mood', 'нормальное')}.
Желаемая известность: {rarity_map.get(rarity, 'среднее')}.
Стоп-лист: {stop_str}.

Ответь JSON:
{{
  "title": "название",
  "author_or_director": "автор/режиссёр",
  "year": "год",
  "why": "почему сейчас — 1 предложение душевно",
  "rare_phrase": "если редкое — особая фраза, иначе пусто",
  "link_query": "запрос для YouTube"
}}"""

        try:
            raw = await pm_generate(self.SYSTEM, prompt, max_tokens=300)
            import re
            m = re.search(r'\{[\s\S]+\}', raw)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.error(f"RecommendAgent.recommend: {e}")

        return {"title": "Не удалось подобрать", "why": "Попробуй позже", "rare_phrase": "", "link_query": ""}

    def _get_stop_list(self, user_id) -> list:
        if not user_id:
            return []
        try:
            return MemoryManager(user_id).get_stop_list() or []
        except Exception:
            return []


# ══════════════════════════════════════════════════════
#  COURSE ORCHESTRATOR — регистратор
# ══════════════════════════════════════════════════════

class CourseOrchestrator:
    """
    Главный регистратор. Запускает агентов в нужном порядке.
    Кеширует результаты чтобы не генерировать дважды за день.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.db = MemoryManager(user_id)
        self.mentor = MentorAgent(user_id)
        self.thought = ThoughtAgent()
        self.story = StoryAgent()
        self.recommend = RecommendAgent()

    async def run_morning(self) -> dict:
        """
        Утренний запуск — генерирует всё на день.
        Возвращает готовый пакет данных для WebApp и бота.
        """
        # Проверяем — уже генерировали сегодня?
        today = str(date.today())
        cached = self._get_cache()
        if cached and cached.get("date") == today:
            logger.info(f"CourseOrchestrator: кеш актуален для user {self.user_id}")
            return cached

        logger.info(f"CourseOrchestrator: генерирую утренний пакет для user {self.user_id}")

        ctx = self.mentor.build_context()
        ctx["user_id"] = self.user_id

        # Параллельно генерируем мысль и историю
        thought_task = asyncio.create_task(self.thought.generate(ctx))
        story_task = asyncio.create_task(self.story.generate(ctx))

        thought_text, story_data = await asyncio.gather(thought_task, story_task)

        # Сохраняем тему дня
        self.mentor.save_topic(thought_text[:50])

        # Продвигаем курс
        self.mentor.advance_day()

        result = {
            "date": today,
            "course_day": ctx["course_day"],
            "thought": thought_text,
            "story": story_data,
            "mood": ctx["mood"],
            "streak": ctx["streak"],
        }

        self._save_cache(result)
        logger.info(f"CourseOrchestrator: готово для user {self.user_id}")
        return result

    async def get_thought(self) -> str:
        """Получить мысль дня (из кеша или сгенерировать)."""
        cached = self._get_cache()
        if cached and cached.get("date") == str(date.today()):
            return cached.get("thought", "")
        result = await self.run_morning()
        return result.get("thought", "")

    async def get_story(self) -> dict:
        """Получить историю дня."""
        cached = self._get_cache()
        if cached and cached.get("date") == str(date.today()):
            return cached.get("story", {})
        result = await self.run_morning()
        return result.get("story", {})

    async def get_recommendation(self, category: str, rarity: str = "medium") -> dict:
        """Получить рекомендацию (фильм/музыка/книга)."""
        ctx = self.mentor.build_context()
        ctx["user_id"] = self.user_id
        return await self.recommend.recommend(category, ctx, rarity)

    def _get_cache(self) -> dict | None:
        try:
            raw = self.db.get_profile().get("course_cache", "")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def _save_cache(self, data: dict):
        try:
            self.db.save_profile({"course_cache": json.dumps(data, ensure_ascii=False)})
        except Exception as e:
            logger.error(f"CourseOrchestrator._save_cache: {e}")


# ══════════════════════════════════════════════════════
#  SCHEDULER SETUP — подключение к планировщику
# ══════════════════════════════════════════════════════

def setup_course_scheduler(bot, get_all_user_ids_fn):
    """
    Регистрирует утренний запуск курса для всех пользователей.
    Добавить в main_combined.py:
      from core.course_orchestrator import setup_course_scheduler
      setup_course_scheduler(bot, get_all_user_ids)
    """
    from bot.config import scheduler
    import asyncio

    async def _run_for_user(user_id: int):
        try:
            orchestrator = CourseOrchestrator(user_id)
            result = await orchestrator.run_morning()
            # Отправляем мысль дня в Telegram
            thought = result.get("thought", "")
            if thought and bot:
                await bot.send_message(
                    user_id,
                    f"✦ {thought}",
                    disable_notification=True  # тихое уведомление
                )
        except Exception as e:
            logger.error(f"course morning error for {user_id}: {e}")

    async def _run_all():
        try:
            ids = get_all_user_ids_fn()
            tasks = [_run_for_user(uid) for uid in ids]
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"course scheduler error: {e}")

    def _sync_wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_all())
        finally:
            loop.close()

    import concurrent.futures

    def _job():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_sync_wrapper).result()

    # Каждый день в 8:00 UTC (11:00 МСК)
    scheduler.add_job(
        _job,
        trigger="cron",
        hour=8,
        minute=0,
        id="course_morning",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("CourseOrchestrator: утренний планировщик зарегистрирован (8:00 UTC)")
