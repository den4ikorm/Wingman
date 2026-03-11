import os
import json
from google import genai

MODEL_NAME = "gemini-2.5-flash"


class GeminiEngine:
    def __init__(self, user_profile: dict):
        self.profile = user_profile
        self.vibe = user_profile.get("current_vibe", "observer")
        self.client = genai.Client(api_key=os.getenv("GEMINI_KEY"))

    def _system_prompt(self, mode: str = "daily") -> str:
        base = (
            f"Ты — добрый и внимательный личный ассистент. "
            f"Профиль пользователя: {json.dumps(self.profile, ensure_ascii=False)}. "
            "Помогаешь вести быт и следить за питанием и настроением."
        )

        if mode == "daily":
            vibe_map = {
                "spark":    "Настроение: ЗАРЯД. Тон бодрый, предлагай активность.",
                "observer": "Настроение: БАЛАНС. Тон спокойный, фокус на гармонии.",
                "twilight": "Настроение: УЮТ. Тон мягкий, только лёгкие дела.",
            }
            return base + f"""
            Режим: {vibe_map.get(self.vibe, 'Обычный день')}.

            СТРОГИЕ ПРАВИЛА — выдай ТОЛЬКО три секции в HTML:
            <section id="tab1">...план дня...</section>
            <section id="tab2">...список покупок...</section>
            <section id="tab3">...релакс/восстановление...</section>
            Без лишнего текста, без markdown!
            """

        elif mode == "review":
            return base + """
            ТЫ — АНАЛИТИК ДНЯ:
            1. Сравни план и итоги пользователя.
            2. Идеи по улучшению помечай тегом [FEATURE].
            3. В конце предложи vibe на завтра: spark, observer или twilight.
            """

        elif mode == "chat":
            return base + "Отвечай коротко и по делу, как личный помощник."

        return base

    def get_dashboard_content(self, is_first_run: bool = False) -> str:
        prompt = (
            f"Составь план дня. Бюджет: {self.profile.get('budget')} руб. "
            f"Цель: {self.profile.get('goal')}."
        )
        if is_first_run:
            prompt += " Первый запуск — начни с тёплого приветствия в tab1."

        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"system_instruction": self._system_prompt("daily")},
        )
        return response.text.replace("```html", "").replace("```", "").strip()

    def get_task_list(self, html_content: str) -> list[str]:
        if not html_content:
            return []
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=f"Извлеки задачи из HTML через точку с запятой: {html_content}",
            config={"system_instruction": "Ты технический парсер. Только список задач через ';'. Без лишнего текста."},
        )
        return [t.strip() for t in response.text.split(";") if len(t.strip()) > 2]

    def analyze_evening(self, plan_text: str, feedback_text: str) -> str:
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=f"План дня:\n{plan_text}\n\nОтчёт пользователя:\n{feedback_text}",
            config={"system_instruction": self._system_prompt("review")},
        )
        return response.text

    def chat(self, user_message: str) -> str:
        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=user_message,
            config={"system_instruction": self._system_prompt("chat")},
        )
        return response.text
