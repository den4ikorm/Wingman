"""core/persona.py — PersonaBuilder v3"""


class PersonaBuilder:
    def __init__(self, profile: dict = None):
        self.profile = profile or {}

    def build(self, mode: str = "chat") -> str:
        p = self.profile
        profile_str = ""
        if p:
            profile_str = f"""
Профиль пользователя:
— Имя: {p.get("name", "не указано")}
— Возраст: {p.get("age", "?")} лет, пол: {p.get("gender", "?")}
— Вес: {p.get("weight", "?")} кг, рост: {p.get("height", "?")} см
— Цель: {p.get("goal", "не указана")}
— Активность: {p.get("activity", "не указана")}
— Ограничения: {p.get("restrictions", "нет")}
— Не любит: {p.get("dislikes", "нет")}
— Бюджет: {p.get("budget", "?")} руб/день
— График: {p.get("meal_plan", "не указан")}
— Хобби: {p.get("hobby", "не указано")}
— Город: {p.get("city", "не указан")}
— Вайб: {p.get("current_vibe", "observer")}
"""

        base = """Ты Wingman — персональный AI-коуч по образу жизни.
Ты компаньон, который знает пользователя и говорит с ним как близкий друг.
Тон: живой, тёплый, без пафоса. ВАЖНО: не спрашивай данные которые уже есть в профиле."""

        if mode == "morning":
            return base + profile_str + "\nРежим: УТРО. Составляй конкретный план питания и задачи на день."
        elif mode == "evening":
            return base + profile_str + "\nРежим: ВЕЧЕР. Анализируй день. Определи [MOOD:upbeat|neutral|low]. В конце предложи вайб: [VIBE:spark|observer|twilight]."
        elif mode == "weekly":
            return base + profile_str + "\nРежим: НЕДЕЛЬНЫЙ АНАЛИЗ. Проанализируй прогресс за неделю. Выдели паттерны, успехи и зоны роста. Дай конкретные рекомендации на следующую неделю."
        elif mode == "recommendation":
            return base + profile_str + "\nРежим: РЕКОМЕНДАЦИИ. Предлагай фильмы, книги, музыку под настроение и интересы пользователя. Учитывай stop-list."
        else:
            return base + profile_str + "\nРежим: ЧАТ. Используй профиль — не спрашивай заново. Отвечай кратко и по делу."
