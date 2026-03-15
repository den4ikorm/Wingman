# -*- coding: utf-8 -*-
"""
core/human_state.py
Human State Engine v1

Хранит и обновляет latent state пользователя:
  energy, stress, mood, discipline, health, sleep_quality, motivation

Правила обновления:
  - Каждое событие (event) изменяет несколько метрик
  - Все метрики 0–100
  - Decay: без активности метрики медленно стремятся к 50 (нейтраль)
  - Состояние хранится в SQLite (персистентно), кэшируется в памяти
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── ДЕЛЬТЫ СОБЫТИЙ ────────────────────────────────────────────────────────────
# event_type → {metric: delta}
EVENT_DELTAS: dict[str, dict[str, float]] = {
    # Задачи
    "task_completed":     {"discipline": +5,  "motivation": +3,  "mood": +3},
    "task_skipped":       {"discipline": -4,  "motivation": -2},
    "task_partial":       {"discipline": +2,  "motivation": +1},

    # Питание
    "diet_followed":      {"health": +4,      "discipline": +3,  "energy": +3},
    "diet_broken":        {"health": -3,      "discipline": -2},
    "recipe_liked":       {"mood": +2,        "motivation": +1},
    "recipe_disliked":    {"mood": -1},

    # Вес
    "weight_loss":        {"health": +5,      "motivation": +5,  "mood": +4},
    "weight_gain":        {"health": -3,      "mood": -3,        "motivation": -2},
    "weight_stable":      {"health": +1},

    # Сон
    "sleep_good":         {"energy": +15,     "mood": +8,        "stress": -10},
    "sleep_normal":       {"energy": +5,      "mood": +2},
    "sleep_bad":          {"energy": -15,     "mood": -8,        "stress": +10},

    # Настроение (утренний check-in)
    "mood_great":         {"mood": +10,       "motivation": +5,  "energy": +5},
    "mood_good":          {"mood": +5,        "energy": +3},
    "mood_neutral":       {},
    "mood_bad":           {"mood": -8,        "stress": +8,      "energy": -5},
    "mood_terrible":      {"mood": -15,       "stress": +15,     "energy": -10},

    # Активность
    "workout_done":       {"health": +6,      "energy": +5,      "discipline": +5,  "stress": -8},
    "workout_skipped":    {"health": -3,      "discipline": -4},
    "walk_done":          {"health": +3,      "energy": +4,      "stress": -5,      "mood": +3},

    # Развлечения
    "movie_liked":        {"mood": +4,        "stress": -3},
    "movie_disliked":     {"mood": -2},
    "music_liked":        {"mood": +3,        "stress": -2},

    # Прочее
    "streak_milestone":   {"motivation": +10, "mood": +5,        "discipline": +5},
    "goal_reached":       {"motivation": +15, "mood": +10,       "health": +5},
    "hydration_ok":       {"health": +2,      "energy": +2},
}

# ── ДЕФОЛТНОЕ СОСТОЯНИЕ ───────────────────────────────────────────────────────
DEFAULT_STATE = {
    "energy":        60,
    "stress":        40,
    "mood":          60,
    "discipline":    50,
    "health":        55,
    "sleep_quality": 60,
    "motivation":    60,
}

# ── ПОРОГИ ДЛЯ ОРКЕСТРАТОРА ──────────────────────────────────────────────────
THRESHOLDS = {
    "low_energy":       {"energy": (0,  35)},
    "high_stress":      {"stress": (65, 100)},
    "low_mood":         {"mood":   (0,  35)},
    "low_discipline":   {"discipline": (0, 40)},
    "high_motivation":  {"motivation": (70, 100)},
    "needs_rest":       {"energy": (0, 30), "stress": (60, 100)},
    "great_day":        {"mood": (70, 100), "energy": (70, 100)},
}


class HumanStateEngine:
    """
    Управляет состоянием одного пользователя.
    Использует MemoryManager для персистентности.
    """

    def __init__(self, user_id: int, db=None):
        self.user_id = user_id
        self.db = db  # MemoryManager instance или None
        self._state: dict[str, float] = {}
        self._load()

    # ── ЗАГРУЗКА / СОХРАНЕНИЕ ────────────────────────────────────────────────

    def _load(self):
        """Загружает состояние из БД или инициализирует дефолтом."""
        if self.db:
            try:
                raw = self.db._fetch_one(
                    "SELECT state_json FROM user_state WHERE user_id=?",
                    (self.user_id,)
                )
                if raw:
                    self._state = json.loads(raw["state_json"])
                    return
            except Exception as e:
                logger.warning(f"HumanState load error for {self.user_id}: {e}")
        self._state = dict(DEFAULT_STATE)

    def _save(self):
        """Сохраняет состояние в БД."""
        if not self.db:
            return
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db._exec(
                """INSERT OR REPLACE INTO user_state
                   (user_id, state_json, updated_at)
                   VALUES (?, ?, ?)""",
                (self.user_id, json.dumps(self._state), now)
            )
        except Exception as e:
            logger.error(f"HumanState save error: {e}")

    # ── CORE API ─────────────────────────────────────────────────────────────

    def get(self) -> dict[str, float]:
        """Возвращает текущее состояние."""
        return dict(self._state)

    def apply_event(self, event_type: str, magnitude: float = 1.0) -> dict:
        """
        Применяет событие к состоянию.
        magnitude: усилитель (0.5 = слабый эффект, 2.0 = сильный)
        Возвращает dict изменений.
        """
        deltas = EVENT_DELTAS.get(event_type, {})
        changes = {}
        for metric, delta in deltas.items():
            scaled = delta * magnitude
            old_val = self._state.get(metric, DEFAULT_STATE.get(metric, 50))
            new_val = max(0.0, min(100.0, old_val + scaled))
            self._state[metric] = round(new_val, 1)
            changes[metric] = round(scaled, 1)

        if changes:
            self._save()
        return changes

    def apply_daily_decay(self):
        """
        Ежедневный decay — все метрики стремятся к нейтральным значениям (50).
        Вызывать раз в день из планировщика.
        decay rate: 5% от расстояния до 50.
        """
        DECAY_RATE = 0.05
        NEUTRAL = {"energy": 60, "stress": 40, "mood": 55,
                   "discipline": 50, "health": 50, "sleep_quality": 55, "motivation": 55}
        for metric, neutral in NEUTRAL.items():
            current = self._state.get(metric, neutral)
            diff = neutral - current
            self._state[metric] = round(current + diff * DECAY_RATE, 1)
        self._save()

    def set_metric(self, metric: str, value: float):
        """Явно устанавливает метрику (например из вечернего опроса)."""
        if metric in DEFAULT_STATE:
            self._state[metric] = max(0.0, min(100.0, float(value)))
            self._save()

    # ── АНАЛИЗ СОСТОЯНИЯ ─────────────────────────────────────────────────────

    def get_active_conditions(self) -> list[str]:
        """
        Возвращает список активных условий для Orchestrator.
        Пример: ["low_energy", "high_stress"]
        """
        active = []
        for condition, metrics in THRESHOLDS.items():
            match = True
            for metric, (lo, hi) in metrics.items():
                val = self._state.get(metric, 50)
                if not (lo <= val <= hi):
                    match = False
                    break
            if match:
                active.append(condition)
        return active

    def get_daily_score(self) -> int:
        """
        Вычисляет Daily Score 0–100 — главная метрика для пользователя.
        Взвешенная сумма всех метрик (без технических терминов).
        """
        weights = {
            "energy":        0.20,
            "mood":          0.20,
            "health":        0.20,
            "discipline":    0.15,
            "motivation":    0.15,
            "sleep_quality": 0.10,
            # stress инвертируем
        }
        stress_inv = 100 - self._state.get("stress", 40)
        score = sum(self._state.get(m, 50) * w for m, w in weights.items())
        score += stress_inv * 0.00  # stress пока не включаем в score чтобы не пугать
        return min(100, max(0, int(score)))

    def get_user_friendly_summary(self) -> str:
        """
        Текстовая сводка состояния — без технических слов.
        Для отображения пользователю.
        """
        score = self.get_daily_score()
        energy = self._state.get("energy", 60)
        mood   = self._state.get("mood", 60)
        stress = self._state.get("stress", 40)

        if score >= 75:
            overall = "отличное"
        elif score >= 55:
            overall = "хорошее"
        elif score >= 40:
            overall = "среднее"
        else:
            overall = "нужно восстановиться"

        parts = [f"Самочувствие: {overall} ({score}/100)"]

        if energy < 35:
            parts.append("⚡ Энергии маловато — полегче с нагрузками")
        elif energy > 75:
            parts.append("⚡ Энергии хоть отбавляй!")

        if stress > 65:
            parts.append("😌 Чувствуется напряжение — нужна разгрузка")

        if mood > 70:
            parts.append("😊 Настроение отличное")
        elif mood < 35:
            parts.append("😔 Настроение не очень — это временно")

        return "\n".join(parts)

    def get_recommendations_context(self) -> str:
        """
        Контекст для Gemini промпта — что сейчас с человеком.
        """
        state = self._state
        conditions = self.get_active_conditions()
        score = self.get_daily_score()

        ctx = f"[Состояние пользователя: score={score}/100, "
        ctx += f"энергия={state.get('energy',60):.0f}, "
        ctx += f"стресс={state.get('stress',40):.0f}, "
        ctx += f"настроение={state.get('mood',60):.0f}, "
        ctx += f"дисциплина={state.get('discipline',50):.0f}]"

        if conditions:
            ctx += f"\n[Активные условия: {', '.join(conditions)}]"
            # Конкретные инструкции для оркестратора
            if "low_energy" in conditions or "needs_rest" in conditions:
                ctx += "\n→ Предлагай только лёгкие задачи, короткий отдых, лёгкую еду"
            if "high_stress" in conditions:
                ctx += "\n→ Включи расслабляющий контент, медитацию, прогулку"
            if "low_mood" in conditions:
                ctx += "\n→ Добавь тёплое обращение, любимый контент, маленькую победу"
            if "great_day" in conditions:
                ctx += "\n→ Можно предложить более амбициозные задачи, новые рецепты"

        return ctx


# ── УТИЛИТЫ ───────────────────────────────────────────────────────────────────

def mood_to_event(mood_answer: str) -> str:
    """Конвертирует ответ пользователя в event_type."""
    mapping = {
        "отлично": "mood_great", "🔥": "mood_great", "великолепно": "mood_great",
        "хорошо":  "mood_good",  "🙂": "mood_good",  "нормально": "mood_good",
        "средне":  "mood_neutral","😐": "mood_neutral",
        "плохо":   "mood_bad",   "😴": "mood_bad",    "устал": "mood_bad",
        "ужасно":  "mood_terrible","😢": "mood_terrible",
    }
    answer_lower = mood_answer.lower().strip()
    for key, event in mapping.items():
        if key in answer_lower:
            return event
    return "mood_neutral"


def sleep_hours_to_event(hours: float) -> str:
    if hours >= 7.5:
        return "sleep_good"
    elif hours >= 6:
        return "sleep_normal"
    else:
        return "sleep_bad"
