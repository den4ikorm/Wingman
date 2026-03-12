"""
core/diet_mode.py
═══════════════════════════════════════════════════════════════
«Живой режим» — система адаптивных режимов питания.

Слой 1 — ПРОФИЛЬ: уровень 1-5 + психотип + умный подбор
Слой 2 — НЕДЕЛЯ:  будни/выходные + события + сезон/погода
Слой 3 — АДАПТАЦИЯ: утреннее настроение + динамическая коррекция
Слой 4 — МОТИВАЦИЯ: стрик с жизнями + прогресс-фото
═══════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import json
import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ── КОНСТАНТЫ ──────────────────────────────────────────────────────────────

LEVELS = {
    1: {
        "name": "🌿 Интуитивное",
        "desc": "Общие советы, без строгих ограничений. Просто питайся осознанно.",
        "strictness": "мягкая",
        "prompt_tone": "Давай мягкие рекомендации, допускай замены блюд, не критикуй отступления.",
        "lives": 5,
        "reminder_freq": "low",
    },
    2: {
        "name": "🥗 Сбалансированное",
        "desc": "Здоровый рацион без фанатизма. Можно иногда отступить.",
        "strictness": "умеренная",
        "prompt_tone": "Предлагай здоровые варианты, допускай 1-2 замены в день, поддерживай мотивацию.",
        "lives": 3,
        "reminder_freq": "medium",
    },
    3: {
        "name": "⚡ Активное",
        "desc": "Чёткий план, минимум отступлений. Баланс БЖУ под контролем.",
        "strictness": "строгая",
        "prompt_tone": "Строго следуй плану, контролируй БЖУ, допускай замену только внутри категории продуктов.",
        "lives": 2,
        "reminder_freq": "high",
    },
    4: {
        "name": "🏋️ Спортивное",
        "desc": "Протокол под тренировки. Питание как топливо для результата.",
        "strictness": "очень строгая",
        "prompt_tone": "Рассчитывай питание под тренировки, учитывай до/послетренировочные окна, никаких случайных замен.",
        "lives": 1,
        "reminder_freq": "high",
    },
    5: {
        "name": "🔥 Максимум",
        "desc": "Жёсткий протокол. Только план, никаких отступлений.",
        "strictness": "жёсткая",
        "prompt_tone": "Строжайший контроль. Никаких замен. Только утверждённый план. При малейшем отступлении — напоминать о цели.",
        "lives": 1,
        "reminder_freq": "maximum",
    },
}

PSYCHOTYPES = {
    "emotional":    "😔 Эмоциональный едок — ешь когда стресс или скука",
    "forgetful":    "🧠 Забывашка — пропускаешь приёмы пищи",
    "perfectionist":"✅ Перфекционист — всё или ничего",
    "social":       "🎉 Социальный — сложно отказаться в компании",
    "disciplined":  "💪 Дисциплинированный — легко следуешь плану",
}

PSYCHOTYPE_ADJUSTMENTS = {
    "emotional": {
        "max_level": 3,
        "note": "Жёсткий режим вызовет срыв. Рекомендую не выше уровня 3.",
        "evening_tone": "мягкий и поддерживающий — не осуждать, если день прошёл не идеально",
    },
    "forgetful": {
        "max_level": 5,
        "note": None,
        "evening_tone": "напоминать о пропущенных приёмах пищи без осуждения",
    },
    "perfectionist": {
        "max_level": 4,
        "note": "Уровень 5 может вызвать тревогу при малейшем отступлении.",
        "evening_tone": "хвалить за любой прогресс, не акцентировать на ошибках",
    },
    "social": {
        "max_level": 5,
        "note": None,
        "evening_tone": "учитывать социальные ситуации как норму, а не срыв",
    },
    "disciplined": {
        "max_level": 5,
        "note": None,
        "evening_tone": "стандартный",
    },
}

SEASONS = {
    12: "зима", 1: "зима", 2: "зима",
    3: "весна", 4: "весна", 5: "весна",
    6: "лето", 7: "лето", 8: "лето",
    9: "осень", 10: "осень", 11: "осень",
}

SEASON_HINTS = {
    "зима": "Тёплые блюда — супы, каши, запечённые овощи. Больше белка для иммунитета.",
    "весна": "Лёгкие салаты, зелень, детокс. Меньше тяжёлой пищи после зимы.",
    "лето":  "Свежие овощи, смузи, лёгкие блюда. Следи за водным балансом.",
    "осень": "Тыква, корнеплоды, согревающие специи. Готовься к зиме — витамины.",
}

MORNING_MOODS = {
    "🔥": ("fire",    "Отличный настрой! Сегодня строго следуем плану на 100%."),
    "😊": ("good",    "Хороший день впереди. Придерживаемся плана, всё по графику."),
    "😐": ("neutral", "Обычный день. Делаем что можем — без давления."),
    "😴": ("tired",   "Устал — бережный режим. Простые блюда, не перегружаемся."),
    "🤒": ("sick",    "Болеешь — лечебный режим. Лёгкое питание, больше жидкости."),
    "😤": ("stress",  "Стресс — особое внимание. Не заедаем, придерживаемся плана."),
}

MOOD_DIET_ADJUSTMENTS = {
    "fire":    "Максимально строго по плану. Пользователь мотивирован — используй это.",
    "good":    "Стандартный план без изменений.",
    "neutral": "Слегка упрости план — убери сложные блюда, замени на простые аналоги.",
    "tired":   "Упрости максимально. Быстрые блюда, минимум готовки. Не требуй строгости.",
    "sick":    "Переключись на лечебное питание: бульоны, каши, фрукты. Забудь про диету на день.",
    "stress":  "Добавь в план антистресс-продукты: тёмный шоколад, орехи, бананы. Мягкий тон.",
}


# ── УМНЫЙ ПОДБОР УРОВНЯ ────────────────────────────────────────────────────

def suggest_level(profile: dict) -> tuple[int, str]:
    """
    Автоматически предлагает уровень 1-5 на основе профиля.
    Возвращает (уровень, объяснение).
    """
    goal     = profile.get("goal", "")
    budget   = profile.get("budget", 500)
    activity = profile.get("activity", "")
    psycho   = profile.get("psychotype", "disciplined")

    score = 3  # базовый уровень
    reasons = []

    # Цель
    if "похуд" in goal.lower() or "сжечь" in goal.lower():
        score += 1
        reasons.append("цель — похудение")
    elif "масс" in goal.lower() or "набрать" in goal.lower():
        score += 1
        reasons.append("цель — набор массы")
    elif "поддерж" in goal.lower():
        reasons.append("цель — поддержание")

    # Активность
    if "высок" in activity.lower() or "спорт" in activity.lower():
        score += 1
        reasons.append("высокая активность")
    elif "низк" in activity.lower() or "сидяч" in activity.lower():
        score -= 1
        reasons.append("низкая активность")

    # Бюджет (низкий бюджет = проще придерживаться строгого плана)
    try:
        b = int(budget)
        if b < 200:
            score += 1
            reasons.append("ограниченный бюджет")
    except (ValueError, TypeError):
        pass

    # Психотип — ограничиваем максимум
    max_lvl = PSYCHOTYPE_ADJUSTMENTS.get(psycho, {}).get("max_level", 5)
    score = max(1, min(score, max_lvl))

    reason_str = ", ".join(reasons) if reasons else "стандартный профиль"
    explanation = f"Рекомендую уровень {score} ({LEVELS[score]['name']}) — {reason_str}."

    return score, explanation


# ── МЕНЕДЖЕР РЕЖИМА ────────────────────────────────────────────────────────

class DietModeManager:
    """Управляет всеми аспектами живого режима для одного пользователя."""

    def __init__(self, profile: dict):
        self.profile = profile
        self.level   = int(profile.get("diet_level", 2))
        self.psycho  = profile.get("psychotype", "disciplined")

    # ── СЛОЙ 1: ПРОФИЛЬ ───────────────────────────────────────────

    def get_level_info(self) -> dict:
        return LEVELS.get(self.level, LEVELS[2])

    def get_prompt_instructions(self) -> str:
        """Возвращает инструкции для Gemini с учётом уровня + психотипа + сезона + настроения."""
        level_info   = self.get_level_info()
        psycho_adj   = PSYCHOTYPE_ADJUSTMENTS.get(self.psycho, {})
        season       = self.get_current_season()
        season_hint  = SEASON_HINTS.get(season, "")
        morning_mood = self.profile.get("morning_mood", "neutral")
        mood_adj     = MOOD_DIET_ADJUSTMENTS.get(morning_mood, "")
        is_weekend   = self.is_weekend()
        events       = self.profile.get("today_event", "")

        parts = [
            f"РЕЖИМ ПИТАНИЯ: {level_info['name']} (уровень {self.level}/5).",
            f"СТРОГОСТЬ: {level_info['prompt_tone']}",
        ]

        if psycho_adj.get("evening_tone") and psycho_adj["evening_tone"] != "стандартный":
            parts.append(f"ПСИХОТИП ПОЛЬЗОВАТЕЛЯ: {psycho_adj['evening_tone']}")

        if season_hint:
            parts.append(f"СЕЗОН ({season}): {season_hint}")

        if mood_adj:
            parts.append(f"НАСТРОЕНИЕ СЕГОДНЯ: {mood_adj}")

        if is_weekend:
            parts.append("ДЕНЬ НЕДЕЛИ: выходной — можно чуть смягчить план, допустить 1 послабление.")

        if events:
            parts.append(f"СОБЫТИЕ СЕГОДНЯ: {events} — учти это в плане, не считай отступление срывом.")

        return "\n".join(parts)

    # ── СЛОЙ 2: НЕДЕЛЯ ────────────────────────────────────────────

    def is_weekend(self) -> bool:
        return date.today().weekday() >= 5  # 5=сб, 6=вс

    def get_current_season(self) -> str:
        return SEASONS.get(date.today().month, "лето")

    def get_effective_level(self) -> int:
        """Уровень с поправкой на выходной день."""
        if self.is_weekend() and self.level >= 3:
            return max(1, self.level - 1)
        return self.level

    # ── СЛОЙ 3: АДАПТАЦИЯ ─────────────────────────────────────────

    def set_morning_mood(self, emoji: str) -> str:
        """Принимает эмодзи, возвращает текстовое описание."""
        if emoji in MORNING_MOODS:
            mood_key, mood_desc = MORNING_MOODS[emoji]
            self.profile["morning_mood"] = mood_key
            return mood_desc
        return "Настроение записано."

    def should_suggest_level_change(self, recent_compliance: list[bool]) -> Optional[str]:
        """
        Анализирует последние 5 дней соблюдения плана.
        Возвращает предложение изменить уровень или None.
        """
        if len(recent_compliance) < 3:
            return None

        failures = sum(1 for c in recent_compliance[-5:] if not c)
        successes = sum(1 for c in recent_compliance[-5:] if c)

        if failures >= 3 and self.level > 1:
            return (
                f"Последние {failures} дня план не соблюдался. "
                f"Может, снизим уровень с {self.level} до {self.level - 1}? "
                f"Напиши /mode {self.level - 1} чтобы изменить."
            )
        elif successes == 5 and self.level < 5:
            return (
                f"🔥 5 дней подряд — план выполнен! "
                f"Готов попробовать уровень {self.level + 1}? "
                f"Напиши /mode {self.level + 1}"
            )
        return None

    # ── СЛОЙ 4: МОТИВАЦИЯ ─────────────────────────────────────────

    def get_lives(self) -> int:
        level_info = self.get_level_info()
        return level_info.get("lives", 3)

    def calculate_streak_info(self, compliance_history: list[dict]) -> dict:
        """
        Считает стрик с учётом «жизней».
        compliance_history — список {'date': ..., 'followed': bool}
        """
        lives_total  = self.get_lives()
        lives_left   = lives_total
        streak       = 0
        longest      = 0
        current_run  = 0

        for day in sorted(compliance_history, key=lambda x: x["date"]):
            if day.get("followed"):
                current_run += 1
                streak = current_run
                longest = max(longest, current_run)
            else:
                if lives_left > 0:
                    lives_left -= 1
                    current_run += 1  # жизнь сохраняет стрик
                else:
                    current_run = 0
                    streak = 0

        return {
            "streak":      streak,
            "longest":     longest,
            "lives_left":  lives_left,
            "lives_total": lives_total,
        }

    def format_streak_message(self, streak_info: dict) -> str:
        s = streak_info
        lives_display = "❤️" * s["lives_left"] + "🖤" * (s["lives_total"] - s["lives_left"])
        msg = f"🔥 Стрик: *{s['streak']} дней*\n"
        msg += f"🏆 Рекорд: {s['longest']} дней\n"
        if s["lives_total"] > 1:
            msg += f"Жизни: {lives_display}\n"
        return msg


# ── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ────────────────────────────────────────────────

def get_all_levels_text() -> str:
    """Текст для отображения всех уровней пользователю."""
    lines = ["*Выбери режим питания:*\n"]
    for lvl, info in LEVELS.items():
        lines.append(f"*{lvl}. {info['name']}*\n_{info['desc']}_\n")
    return "\n".join(lines)


def get_psychotypes_text() -> str:
    lines = ["*Как ты обычно ешь?*\n"]
    for key, desc in PSYCHOTYPES.items():
        lines.append(f"• {desc}")
    return "\n".join(lines)
