"""
core/gemini_ai.py
GeminiEngine v4 — Groq основной для текста, Gemini для JSON-структур

Текстовые методы (chat, analyze, summaries, recommendations):
  → provider_manager.generate() → Groq сначала, Gemini fallback

JSON-методы (get_structured_dashboard, generate_shopping_list_structured):
  → напрямую Gemini (Groq плохо держит большой JSON)
  → при ошибке — fallback на Groq с упрощённым форматом
"""

import os
import re
import asyncio
import logging
from google import genai
from core.persona import PersonaBuilder
from core.key_manager import KeyManager

MODEL_NAME = "gemini-2.5-flash-lite"
logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    import re as _re, json as _json
    s = text.strip()
    s = _re.sub(r'/\*.*?\*/', '""', s, flags=_re.DOTALL)
    m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', s, _re.DOTALL)
    if m:
        s = m.group(1)
    start = s.find('{')
    end   = s.rfind('}')
    if start != -1 and end != -1 and end > start:
        s = s[start:end+1]
    for attempt in range(3):
        try:
            return _json.loads(s)
        except _json.JSONDecodeError as e:
            if attempt == 0:
                s = _re.sub(r',\s*([}\]])', r'\1', s)
            elif attempt == 1:
                s = _re.sub(r"(?!<[\\])'", '"', s)
            else:
                logger.error(f"_extract_json failed: {e}")
                raise
    raise ValueError("JSON extraction failed")


class GeminiEngine:
    def __init__(self, user_profile: dict):
        self.profile = user_profile
        self.persona = PersonaBuilder(user_profile)
        self._key_manager = KeyManager()
        self._make_client()

    def _make_client(self):
        self.client = genai.Client(api_key=self._key_manager.get_key())

    # ── ВНУТРЕННИЙ ВЫЗОВ GEMINI (синхронный, только для JSON) ──────

    def _call_gemini_sync(self, contents, mode: str, max_retries: int = 3) -> str:
        """Прямой вызов Gemini — только для JSON-методов."""
        system_prompt = self.persona.build(mode)
        config = {
            "system_instruction": system_prompt,
            "max_output_tokens": 8192,
        }
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=MODEL_NAME,
                    contents=contents,
                    config=config,
                )
                text = response.text.strip()
                # Дочитываем если обрезан
                try:
                    finish = response.candidates[0].finish_reason
                    MAX_CONT = 3
                    cont = 0
                    while (str(finish) in ("FinishReason.MAX_TOKENS", "2", "MAX_TOKENS")
                           and cont < MAX_CONT):
                        cont_prompt = (
                            f"Предыдущий ответ оборвался на:\n...{text[-300:]}\n\n"
                            f"Продолжи точно с места где остановился, не повторяй написанное."
                        )
                        cr = self.client.models.generate_content(
                            model=MODEL_NAME, contents=cont_prompt, config=config)
                        text += "\n" + cr.text.strip()
                        try:
                            finish = cr.candidates[0].finish_reason
                        except Exception:
                            finish = None
                        cont += 1
                except Exception:
                    pass
                return text
            except Exception as e:
                err = str(e)
                if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                    import time
                    wait = min(3 * (attempt + 1), 9)
                    logger.warning(f"Gemini rate limit, ротирую, жду {wait}s...")
                    self._key_manager.rotate()
                    self._make_client()
                    time.sleep(wait)
                else:
                    logger.error(f"Gemini error: {e}")
                    raise
        raise RuntimeError("Gemini: все ключи исчерпали лимит")

    # ── УНИВЕРСАЛЬНЫЙ ВЫЗОВ ЧЕРЕЗ PROVIDER (Groq → Gemini) ────────

    async def _call_provider(self, prompt: str, mode: str, max_tokens: int = 1200) -> str:
        """Groq основной, Gemini fallback — для текстовых ответов."""
        from core.provider_manager import generate as pm_generate
        system = self.persona.build(mode)
        return await pm_generate(system, prompt, max_tokens)

    def _call_provider_sync(self, prompt: str, mode: str, max_tokens: int = 1200) -> str:
        """Синхронная обёртка для _call_provider."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Уже внутри event loop — используем to_thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._call_provider(prompt, mode, max_tokens)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._call_provider(prompt, mode, max_tokens))
        except Exception as e:
            logger.error(f"_call_provider_sync error: {e}")
            # Fallback на прямой Gemini
            return self._call_gemini_sync(prompt, mode)

    # ── ЧАТ С ИСТОРИЕЙ ────────────────────────────────────────────

    def chat(self, user_message: str, history: list[dict] = None) -> str:
        if history:
            context_parts = []
            for msg in history[-20:]:
                role = "Пользователь" if msg["role"] == "user" else "Wingman"
                context_parts.append(f"{role}: {msg['content']}")
            context = "\n".join(context_parts)
            contents = f"История диалога:\n{context}\n\nПользователь: {user_message}"
        else:
            contents = user_message
        return self._call_provider_sync(contents, mode="chat", max_tokens=1000)

    # ── УТРО ──────────────────────────────────────────────────────

    def get_dashboard_content(self, is_first_run: bool = False,
                               yesterday_summary: str = "",
                               week_summary: str = "") -> str:
        p = self.profile
        context = ""
        if yesterday_summary:
            context += f"\nВчера: {yesterday_summary}"
        if week_summary:
            context += f"\nИтоги недели: {week_summary}"
        prompt = (
            f"Составь план дня. Бюджет: {p.get('budget')} руб. "
            f"Цель: {p.get('goal')}.{context}"
        )
        if is_first_run:
            prompt += " Первый запуск — начни с тёплого приветствия."
        raw = self._call_provider_sync(prompt, mode="morning", max_tokens=1500)
        return raw.replace("```html", "").replace("```", "").strip()

    def get_structured_dashboard(self, yesterday_summary: str = "", week_summary: str = "") -> dict:
        """
        Генерирует JSON-дашборд.
        Gemini основной (лучше держит большой JSON), Groq fallback с упрощённым форматом.
        """
        p = self.profile
        ctx = ""
        if yesterday_summary: ctx += f"\nВчера: {yesterday_summary}"
        if week_summary:      ctx += f"\nИтоги недели: {week_summary}"

        from core.diet_mode import DietModeManager
        mgr = DietModeManager(p)
        mode_instructions = mgr.get_prompt_instructions()
        level = int(p.get("diet_level", 2))
        alts_instruction = "" if level >= 5 else "Для каждого блюда дай 2-3 альтернативы (поле alternatives)."

        prompt = f"""Ты AI-коуч по питанию и образу жизни. Составь полный план дня в JSON.

ПРОФИЛЬ: имя={p.get('name')}, цель={p.get('goal')}, бюджет={p.get('budget')} руб/день,
ограничения={p.get('restrictions')}, не любит={p.get('dislikes')}{ctx}

{mode_instructions}

ВАЖНО: Верни ТОЛЬКО валидный JSON. Никакого текста до или после. Никаких ```json``` блоков.
Начинай ответ сразу с символа {{

{{
  "quote": "Вдохновляющая цитата дня (короткая, 1 предложение)",
  "quote_author": "Автор цитаты",
  "tasks": ["задача 1", "задача 2", "задача 3", "задача 4", "задача 5"],
  "tips": [
    {{"time": "Утро", "text": "Совет на утро"}},
    {{"time": "День",  "text": "Совет на день"}},
    {{"time": "Вечер", "text": "Совет на вечер"}}
  ],
  "surprise": "Тёплая мотивирующая фраза лично для {p.get('name', 'тебя')}",
  "html_sections": "Краткий приветственный текст плана (2-3 предложения)",
  "meals": {{
    "breakfast": {{
      "name": "Название блюда",
      "desc": "Описание 1-2 предложения",
      "kcal": "~350",
      "img_query": "english search query for photo",
      "recipe": ["Шаг 1", "Шаг 2", "Шаг 3", "Шаг 4"],
      "alternatives": [
        {{"name": "Альтернатива 1", "desc": "краткое описание"}},
        {{"name": "Альтернатива 2", "desc": "краткое описание"}}
      ]
    }},
    "lunch": {{ /* то же самое */ }},
    "dinner": {{ /* то же самое */ }}
  }},
  "week": [
    {{
      "meals": {{
        "breakfast": {{"name":"...", "desc":"...", "kcal":"...", "img_query":"...", "recipe":["..."], "alternatives":[{{"name":"...","desc":"..."}}]}},
        "lunch":     {{"name":"...", "desc":"...", "kcal":"...", "img_query":"...", "recipe":["..."], "alternatives":[]}},
        "dinner":    {{"name":"...", "desc":"...", "kcal":"...", "img_query":"...", "recipe":["..."], "alternatives":[]}}
      }}
    }}
  ],
  "shopping": [
    {{"name": "Продукт", "qty": "500г"}}
  ]
}}

Неделя должна содержать РОВНО 7 элементов (понедельник-воскресенье).
{alts_instruction}
Только JSON. Ничего больше."""

        raw = ""
        try:
            # JSON-структуры — Gemini справляется лучше
            raw = self._call_gemini_sync(prompt, mode="morning")
            return _extract_json(raw)
        except Exception as e:
            logger.error(f"get_structured_dashboard Gemini error: {e}, пробую Groq...")
            # Fallback на Groq с упрощённым JSON
            try:
                simplified = self._call_provider_sync(
                    prompt + "\n\nОТВЕЧАЙ ТОЛЬКО ВАЛИДНЫМ JSON, без комментариев.",
                    mode="morning",
                    max_tokens=4000
                )
                return _extract_json(simplified)
            except Exception as e2:
                logger.error(f"get_structured_dashboard Groq fallback error: {e2}")
                return {
                    "tasks": [], "html_sections": "Ошибка генерации",
                    "meals": {}, "week": [], "shopping": [], "surprise": "",
                    "quote": "", "quote_author": "", "tips": [],
                }

    def get_task_list(self, html_content: str) -> list[str]:
        if not html_content:
            return []
        try:
            raw = self._call_provider_sync(
                f"Извлеки задачи из HTML через точку с запятой: {html_content}",
                mode="chat",
                max_tokens=300
            )
            return [t.strip() for t in raw.split(";") if len(t.strip()) > 2]
        except Exception:
            return []

    # ── ВЕЧЕР ──────────────────────────────────────────────────────

    def analyze_evening(self, plan_text: str, feedback_text: str) -> str:
        contents = f"План дня:\n{plan_text}\n\nОтчёт пользователя:\n{feedback_text}"
        return self._call_provider_sync(contents, mode="evening", max_tokens=1200)

    def generate_day_summary(self, feedback_text: str, tasks_results: str) -> str:
        prompt = (
            f"Сделай краткий дайджест дня (2-3 предложения) на основе:\n"
            f"Задачи: {tasks_results}\n"
            f"Фидбек: {feedback_text}\n\n"
            "Формат: факты без воды. Это будет использоваться как контекст завтра."
        )
        try:
            return self._call_provider_sync(prompt, mode="evening", max_tokens=400)
        except Exception:
            return feedback_text[:200]

    # ── НЕДЕЛЬНЫЙ АНАЛИЗ ───────────────────────────────────────────

    def generate_week_summary(self, day_summaries: list[dict]) -> str:
        days_text = "\n".join(
            f"{d['date']} ({d.get('mood','?')}): {d['summary']}"
            for d in day_summaries
        )
        prompt = f"Вот итоги 7 дней:\n{days_text}\n\nСделай недельный анализ."
        return self._call_provider_sync(prompt, mode="weekly", max_tokens=1200)

    # ── РЕКОМЕНДАЦИИ (вечер) ───────────────────────────────────────

    def get_evening_recommendations(self, mood: str, stop_list: list) -> str:
        p = self.profile
        stop = ", ".join(stop_list[-20:]) if stop_list else "нет"
        prompt = f"""
Составь вечерние рекомендации для {p.get('name', 'пользователя')}.
Настроение сейчас: {mood}
Хобби и интересы: {p.get('hobby', 'не указаны')}
Уже видел/слышал (не предлагай): {stop}

Формат ответа:

🎬 *Фильмы на вечер* (5 штук — 2 мейнстрим, 2 пореже, 1 редкий бриллиант):
1. Название (год) — одна строка почему подойдёт

📺 *Мультфильм/Сериал* (3 штуки — 1 мейнстрим, 1 пореже, 1 бриллиант):
1. Название — одна строка

📚 *Книга*:
Название — автор — одна строка почему

🎵 *Плейлист 15 треков* (по 3 в каждой категории):
Современные популярные:
— Исполнитель — Трек

Ретро 90-2000е:
— Исполнитель — Трек

2000-2020:
— Исполнитель — Трек

Классика советская 50-90е:
— Исполнитель — Трек

Редкие (минимум 3):
— Исполнитель — Трек

Приоритет: русскоязычная музыка. Учитывай настроение {mood}.
"""
        return self._call_provider_sync(prompt, mode="recommendation", max_tokens=1500)

    # ── ДИЕТА ──────────────────────────────────────────────────────

    def generate_weekly_diet(self) -> str:
        p = self.profile
        from core.diet_mode import DietModeManager
        mgr = DietModeManager(p)
        mode_instructions = mgr.get_prompt_instructions()

        prompt = f"""
Составь персональную диету на 7 дней:
— Имя: {p.get('name')}, {p.get('age')} лет, {p.get('gender')}
— Вес: {p.get('weight')} кг, рост: {p.get('height')} см
— Цель: {p.get('goal')}, активность: {p.get('activity')}
— Ограничения: {p.get('restrictions')}, не любит: {p.get('dislikes')}
— Бюджет/день: {p.get('budget')} руб, график: {p.get('meal_plan')}

{mode_instructions}

Формат — Markdown:
*День 1*
🌅 Завтрак: ...
☀️ Обед: ...
🌙 Ужин: ...
_(перекусы)_

И так для каждого дня. В конце — краткий комментарий по КБЖУ.
"""
        return self._call_provider_sync(prompt, mode="morning", max_tokens=2000)

    def generate_shopping_list_structured(self, diet_text: str) -> list[dict]:
        """JSON список покупок — через Gemini (лучше держит JSON), fallback Groq."""
        prompt = f"""
На основе диеты составь список покупок. Отвечай ТОЛЬКО JSON-массивом:
[{{"item": "Куриное филе", "category": "Мясо и рыба", "amount": "1.5 кг"}}, ...]

Категории: Мясо и рыба, Овощи и зелень, Фрукты, Молочные продукты, Крупы и бобовые, Хлеб и выпечка, Прочее

Диета:
{diet_text}
"""
        import json
        for caller in [
            lambda: self._call_gemini_sync(prompt, mode="morning"),
            lambda: self._call_provider_sync(prompt, mode="morning", max_tokens=1500),
        ]:
            try:
                raw = caller()
                raw = raw.replace("```json", "").replace("```", "").strip()
                return json.loads(raw)
            except Exception as e:
                logger.warning(f"generate_shopping_list_structured attempt failed: {e}")
        return []

    def generate_shopping_list(self, diet_text: str) -> str:
        prompt = f"""
На основе диеты составь список покупок на неделю.
Формат Markdown, по категориям с количеством:
*🥩 Мясо и рыба*
— ...

Диета:
{diet_text}

В конце примерная стоимость в рублях.
"""
        return self._call_provider_sync(prompt, mode="morning", max_tokens=1200)

    # ── СЮРПРИЗ ────────────────────────────────────────────────────

    def get_surprise(self) -> str:
        import random
        surprise_types = [
            "интересный факт о питании или здоровье",
            "мотивирующую цитату великого человека",
            "необычный лайфхак для продуктивности",
            "короткую медитативную практику на 2 минуты",
            "рекомендацию подкаста или видео по интересам пользователя",
        ]
        surprise_type = random.choice(surprise_types)
        hobby = self.profile.get("hobby", "")
        prompt = f"Придумай {surprise_type}. Учитывай хобби: {hobby}. Формат: короткий пост до 150 слов с эмодзи."
        return self._call_provider_sync(prompt, mode="chat", max_tokens=500)

    # ── РЕЦЕПТЫ ПО ПЛАНУ ──────────────────────────────────────────

    def generate_recipes_for_day(self, day_plan: str = None) -> str:
        p = self.profile
        plan_context = f"\nПлан дня:\n{day_plan}" if day_plan else ""
        prompt = f"""
Составь подробные рецепты для завтрака, обеда и ужина.
Учитывай профиль: цель — {p.get('goal')}, ограничения — {p.get('restrictions')}, не любит — {p.get('dislikes')}.{plan_context}

Для каждого приёма пищи дай рецепт в формате:

🌅 *Завтрак: Название*
⏱ Время: X мин | 📊 ~X ккал | 🥩 Б: Xг | 🧈 Ж: Xг | 🌾 У: Xг

📝 Ингредиенты:
— ...

👨‍🍳 Приготовление:
1. ...
2. ...
3. ...

---

То же самое для Обеда и Ужина.
"""
        return self._call_provider_sync(prompt, mode="morning", max_tokens=1500)

    # ── АНАЛИЗ ХОЛОДИЛЬНИКА ────────────────────────────────────────

    def fridge_to_recipes(self, ingredients: str) -> str:
        p = self.profile
        prompt = f"""
У пользователя есть: {ingredients}

Предложи 3 рецепта которые можно приготовить из этих продуктов.
Учитывай цель ({p.get('goal')}) и ограничения ({p.get('restrictions')}).

Для каждого рецепта:
🍽 Название
⏱ Время: X мин
📊 КБЖУ: ~X ккал
📝 Ингредиенты: ...
👨‍🍳 Приготовление: (3-4 шага)
"""
        return self._call_provider_sync(prompt, mode="morning", max_tokens=1200)

    # ── ТРЕКЕР ВЕСА ────────────────────────────────────────────────

    def analyze_weight_progress(self, history: list[dict], goal: str) -> str:
        if not history:
            return "Пока нет данных о весе. Записывай вес командой /weight 78.5"
        points = "\n".join(f"{h['date']}: {h['weight']} кг" for h in history)
        prompt = f"Цель: {goal}\nИстория веса:\n{points}\n\nДай краткий анализ прогресса и рекомендацию."
        return self._call_provider_sync(prompt, mode="chat", max_tokens=600)

    # ── ПАРСИНГ МЕТА ───────────────────────────────────────────────

    @staticmethod
    def extract_vibe(text: str) -> str | None:
        match = re.search(r"\[VIBE:(spark|observer|twilight)\]", text)
        if match:
            return match.group(1)
        for vibe in ["spark", "observer", "twilight"]:
            if vibe in text.lower():
                return vibe
        return None

    @staticmethod
    def extract_mood(text: str) -> str | None:
        match = re.search(r"\[MOOD:(upbeat|neutral|low)\]", text)
        return match.group(1) if match else None
