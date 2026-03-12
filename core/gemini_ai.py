"""
core/gemini_ai.py
GeminiEngine v3 — ротация ключей, история чата, рекомендации
"""

import os
import re
import logging
from google import genai
from core.persona import PersonaBuilder
from core.key_manager import KeyManager

MODEL_NAME = "gemini-2.5-flash"
logger = logging.getLogger(__name__)


class GeminiEngine:
    def __init__(self, user_profile: dict):
        self.profile = user_profile
        self.persona = PersonaBuilder(user_profile)
        self._key_manager = KeyManager()
        self._make_client()

    def _make_client(self):
        self.client = genai.Client(api_key=self._key_manager.get_key())

    def _call(self, contents, mode: str, max_retries: int = 3) -> str:
        system_prompt = self.persona.build(mode)
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=MODEL_NAME,
                    contents=contents,
                    config={"system_instruction": system_prompt},
                )
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                    logger.warning(f"Rate limit на ключе {attempt+1}, ротирую...")
                    self._key_manager.rotate()
                    self._make_client()
                else:
                    logger.error(f"Gemini error: {e}")
                    raise
        raise RuntimeError("Все ключи исчерпали лимит")

    # ── ЧАТ С ИСТОРИЕЙ ────────────────────────────────────────────

    def chat(self, user_message: str, history: list[dict] = None) -> str:
        """
        history = [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        if history:
            # Строим мультиходовой контекст
            context_parts = []
            for msg in history[-20:]:  # последние 20 сообщений
                role = "Пользователь" if msg["role"] == "user" else "Wingman"
                context_parts.append(f"{role}: {msg['content']}")
            context = "\n".join(context_parts)
            contents = f"История диалога:\n{context}\n\nПользователь: {user_message}"
        else:
            contents = user_message
        return self._call(contents, mode="chat")

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
        raw = self._call(prompt, mode="morning")
        return raw.replace("```html", "").replace("```", "").strip()

    def get_task_list(self, html_content: str) -> list[str]:
        if not html_content:
            return []
        try:
            raw = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=f"Извлеки задачи из HTML через точку с запятой: {html_content}",
                config={"system_instruction": "Ты технический парсер. Только список задач через ';'. Без лишнего."},
            ).text
            return [t.strip() for t in raw.split(";") if len(t.strip()) > 2]
        except Exception:
            return []

    # ── ВЕЧЕР ──────────────────────────────────────────────────────

    def analyze_evening(self, plan_text: str, feedback_text: str) -> str:
        contents = f"План дня:\n{plan_text}\n\nОтчёт пользователя:\n{feedback_text}"
        return self._call(contents, mode="evening")

    def generate_day_summary(self, feedback_text: str, tasks_results: str) -> str:
        """Краткий дайджест дня для хранения"""
        prompt = (
            f"Сделай краткий дайджест дня (2-3 предложения) на основе:\n"
            f"Задачи: {tasks_results}\n"
            f"Фидбек: {feedback_text}\n\n"
            "Формат: факты без воды. Это будет использоваться как контекст завтра."
        )
        try:
            return self._call(prompt, mode="evening")
        except Exception:
            return feedback_text[:200]

    # ── НЕДЕЛЬНЫЙ АНАЛИЗ ───────────────────────────────────────────

    def generate_week_summary(self, day_summaries: list[dict]) -> str:
        days_text = "\n".join(
            f"{d['date']} ({d.get('mood','?')}): {d['summary']}"
            for d in day_summaries
        )
        prompt = f"Вот итоги 7 дней:\n{days_text}\n\nСделай недельный анализ."
        return self._call(prompt, mode="weekly")

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
        return self._call(prompt, mode="recommendation")

    # ── ДИЕТА ──────────────────────────────────────────────────────

    def generate_weekly_diet(self) -> str:
        p = self.profile
        # Подключаем живой режим
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
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"system_instruction": self.persona.build("morning")},
        )
        return response.text.strip()

    def generate_shopping_list_structured(self, diet_text: str) -> list[dict]:
        """Возвращает структурированный список для БД"""
        prompt = f"""
На основе диеты составь список покупок. Отвечай ТОЛЬКО JSON-массивом:
[{{"item": "Куриное филе", "category": "Мясо и рыба", "amount": "1.5 кг"}}, ...]

Категории: Мясо и рыба, Овощи и зелень, Фрукты, Молочные продукты, Крупы и бобовые, Хлеб и выпечка, Прочее

Диета:
{diet_text}
"""
        try:
            raw = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={"system_instruction": "Ты JSON-генератор. Только валидный JSON-массив без пояснений."},
            ).text
            raw = raw.replace("```json", "").replace("```", "").strip()
            import json
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Shopping list parse error: {e}")
            return []

    def generate_shopping_list(self, diet_text: str) -> str:
        """Текстовый вариант для отправки в чат"""
        prompt = f"""
На основе диеты составь список покупок на неделю.
Формат Markdown, по категориям с количеством:
*🥩 Мясо и рыба*
— ...

Диета:
{diet_text}

В конце примерная стоимость в рублях.
"""
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"system_instruction": "Ты диетолог. Составляй точные списки покупок."},
        )
        return response.text.strip()

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
        return self._call(prompt, mode="chat")

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
        return self._call(prompt, mode="morning")

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
        return self._call(prompt, mode="morning")

    # ── ТРЕКЕР ВЕСА ────────────────────────────────────────────────

    def analyze_weight_progress(self, history: list[dict], goal: str) -> str:
        if not history:
            return "Пока нет данных о весе. Записывай вес командой /weight 78.5"
        points = "\n".join(f"{h['date']}: {h['weight']} кг" for h in history)
        prompt = f"Цель: {goal}\nИстория веса:\n{points}\n\nДай краткий анализ прогресса и рекомендацию."
        return self._call(prompt, mode="chat")

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
