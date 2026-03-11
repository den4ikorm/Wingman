"""
core/gemini_ai.py
GeminiEngine — использует PersonaBuilder для динамической сборки промптов
"""

import os
import re
from google import genai
from core.persona import PersonaBuilder

MODEL_NAME = "gemini-2.5-flash"


class GeminiEngine:
    def __init__(self, user_profile: dict):
        self.profile = user_profile
        self.client = genai.Client(api_key=os.getenv("GEMINI_KEY"))
        self.persona = PersonaBuilder()

    def _call(self, contents: str, mode: str) -> str:
        system_prompt = self.persona.build(mode)
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={"system_instruction": system_prompt},
        )
        return response.text.strip()

    # ── УТРО ──────────────────────────────────────────────────────

    def get_dashboard_content(self, is_first_run: bool = False) -> str:
        prompt = (
            f"Составь план дня. Бюджет: {self.profile.get('budget')} руб. "
            f"Цель: {self.profile.get('goal')}."
        )
        if is_first_run:
            prompt += " Первый запуск — начни с тёплого приветствия в tab1."
        raw = self._call(prompt, mode="morning")
        return raw.replace("```html", "").replace("```", "").strip()

    def get_task_list(self, html_content: str) -> list[str]:
        if not html_content:
            return []
        raw = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=f"Извлеки задачи из HTML через точку с запятой: {html_content}",
            config={"system_instruction": "Ты технический парсер. Только список задач через ';'. Без лишнего."},
        ).text
        return [t.strip() for t in raw.split(";") if len(t.strip()) > 2]

    # ── ВЕЧЕР ──────────────────────────────────────────────────────

    def analyze_evening(self, plan_text: str, feedback_text: str) -> str:
        contents = f"План дня:\n{plan_text}\n\nОтчёт пользователя:\n{feedback_text}"
        return self._call(contents, mode="evening")

    # ── ЧАТ ────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        return self._call(user_message, mode="chat")

    # ── ПАРСИНГ МЕТА ───────────────────────────────────────────────

    @staticmethod
    def extract_vibe(text: str) -> str | None:
        """Извлекает предложенный vibe из ответа вечернего анализа"""
        for vibe in ["spark", "observer", "twilight"]:
            if vibe in text.lower():
                return vibe
        return None

    @staticmethod
    def extract_mood(text: str) -> str | None:
        """Извлекает [MOOD:state] из ответа"""
        match = re.search(r"\[MOOD:(upbeat|neutral|low)\]", text)
        return match.group(1) if match else None

    # ── ДИЕТА ──────────────────────────────────────────────────────────────

    def generate_weekly_diet(self) -> str:
        p = self.profile
        prompt = f"""
Составь персональную диету на 7 дней для человека:
— Имя: {p.get('name', 'пользователь')}
— Возраст: {p.get('age')} лет, пол: {p.get('gender')}
— Вес: {p.get('weight')} кг, рост: {p.get('height')} см
— Цель: {p.get('goal')}
— Активность: {p.get('activity')}
— Ограничения: {p.get('restrictions')}
— Не любит: {p.get('dislikes')}
— Бюджет/день: {p.get('budget')} руб.
— График питания: {p.get('meal_plan')}

Формат ответа — строго Markdown:
*День 1*
🌅 Завтрак: ...
☀️ Обед: ...
🌙 Ужин: ...
_(перекусы если нужны)_

И так для каждого из 7 дней.
В конце — краткий комментарий по КБЖУ и логике диеты (3-4 предложения).
"""
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"system_instruction": self.persona.build("morning")},
        )
        return response.text.strip()

    def generate_shopping_list(self, diet_text: str) -> str:
        prompt = f"""
На основе этой диеты составь список покупок на неделю:

{diet_text}

Формат — строго Markdown, сгруппируй по категориям:
*🥩 Мясо и рыба*
— ...

*🥬 Овощи и зелень*
— ...

*🧀 Молочные продукты*
— ...

*🌾 Крупы и бобовые*
— ...

*🫙 Прочее*
— ...

Указывай примерное количество (кг, г, шт).
В конце — примерная общая стоимость в рублях.
"""
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"system_instruction": "Ты диетолог-нутрициолог. Составляй точные списки покупок."},
        )
        return response.text.strip()
