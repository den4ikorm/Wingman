# -*- coding: utf-8 -*-
"""
core/progress_engine.py
Progress Engine v1 — "невидимая" геймификация

Внутри: XP, очки, уровни, дисциплина
Снаружи: "Серия: 6 дней", "Статус: Практик", "−1.2 кг за месяц"

Принципы:
  - Никаких технических слов пользователю
  - Статусы открывают новые функции
  - Достижения — реальные, не случайные
  - Серия дней — главная мотивационная механика
"""

import json
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

# ── СТАТУСЫ (РАНГИ) ───────────────────────────────────────────────────────────
# Пользователь НЕ видит XP — только статус и что до следующего

RANKS = [
    {
        "id":      "newcomer",
        "label":   "Новичок",
        "emoji":   "🌱",
        "min_xp":  0,
        "max_xp":  99,
        "unlocks": [],
        "desc":    "Ты только начинаешь — и это уже первый шаг!",
    },
    {
        "id":      "student",
        "label":   "Ученик",
        "emoji":   "📖",
        "min_xp":  100,
        "max_xp":  299,
        "unlocks": ["weekly_challenges"],
        "desc":    "Привычки начинают формироваться. Так держать!",
    },
    {
        "id":      "practitioner",
        "label":   "Практик",
        "emoji":   "⚡",
        "min_xp":  300,
        "max_xp":  699,
        "unlocks": ["weekly_challenges", "advanced_recipes"],
        "desc":    "Ты уже видишь результаты — и это заметно!",
    },
    {
        "id":      "master",
        "label":   "Мастер привычек",
        "emoji":   "🏆",
        "min_xp":  700,
        "max_xp":  1499,
        "unlocks": ["weekly_challenges", "advanced_recipes", "personal_insights"],
        "desc":    "Дисциплина стала твоей второй натурой.",
    },
    {
        "id":      "mentor",
        "label":   "Наставник",
        "emoji":   "🌟",
        "min_xp":  1500,
        "max_xp":  2999,
        "unlocks": ["weekly_challenges", "advanced_recipes", "personal_insights", "mentor_mode"],
        "desc":    "Ты вдохновляешь. Люди с твоими паттернами — редкость.",
    },
    {
        "id":      "legend",
        "label":   "Легенда",
        "emoji":   "👑",
        "min_xp":  3000,
        "max_xp":  999999,
        "unlocks": ["all"],
        "desc":    "Это уже образ жизни. Легендарно.",
    },
]

# ── XP ЗА СОБЫТИЯ ─────────────────────────────────────────────────────────────
EVENT_XP = {
    "task_completed":   15,
    "task_partial":      5,
    "diet_followed":    20,
    "workout_done":     25,
    "walk_done":        10,
    "weight_loss":      30,
    "weight_stable":     5,
    "sleep_good":       15,
    "mood_great":        5,
    "recipe_liked":      5,
    "streak_milestone": 50,
    "goal_reached":    100,
    "hydration_ok":      3,
    "checkin_done":      5,
}

# Штрафы (XP не уходит — только не начисляется)
# task_skipped, diet_broken, workout_skipped — просто 0 XP

# ── ДОСТИЖЕНИЯ ────────────────────────────────────────────────────────────────
ACHIEVEMENTS = [
    # Серии
    {
        "id": "streak_3",   "emoji": "🔥", "label": "3 дня подряд",
        "desc": "Держишь серию 3 дня — хорошее начало!",
        "check": lambda s: s.get("streak", 0) >= 3,
    },
    {
        "id": "streak_7",   "emoji": "🔥🔥", "label": "Неделя без пропусков",
        "desc": "7 дней подряд! Это уже привычка.",
        "check": lambda s: s.get("streak", 0) >= 7,
    },
    {
        "id": "streak_30",  "emoji": "💎", "label": "Месяц силы",
        "desc": "30 дней подряд. Это редкость. Серьёзно.",
        "check": lambda s: s.get("streak", 0) >= 30,
    },

    # Питание
    {
        "id": "diet_10",    "emoji": "🥗", "label": "10 здоровых дней",
        "desc": "Питание меняет всё — ты это уже чувствуешь.",
        "check": lambda s: s.get("diet_days_total", 0) >= 10,
    },
    {
        "id": "diet_30",    "emoji": "🥗🥗", "label": "Мастер питания",
        "desc": "30 дней здорового питания — это уже образ жизни.",
        "check": lambda s: s.get("diet_days_total", 0) >= 30,
    },

    # Активность
    {
        "id": "walk_10",    "emoji": "🚶", "label": "10 прогулок",
        "desc": "Движение — это жизнь. Ты это понял.",
        "check": lambda s: s.get("walks_total", 0) >= 10,
    },
    {
        "id": "workout_5",  "emoji": "💪", "label": "5 тренировок",
        "desc": "Первые 5 — самые сложные. Дальше легче.",
        "check": lambda s: s.get("workouts_total", 0) >= 5,
    },

    # Вес
    {
        "id": "weight_1kg", "emoji": "⚖️", "label": "−1 кг",
        "desc": "Первый килограмм — самый важный.",
        "check": lambda s: s.get("weight_loss_total", 0) >= 1.0,
    },
    {
        "id": "weight_5kg", "emoji": "🏅", "label": "−5 кг",
        "desc": "Минус 5 кг. Это видно и чувствуется!",
        "check": lambda s: s.get("weight_loss_total", 0) >= 5.0,
    },

    # Задачи
    {
        "id": "tasks_50",   "emoji": "✅", "label": "50 выполненных задач",
        "desc": "50 маленьких побед = большой результат.",
        "check": lambda s: s.get("tasks_total", 0) >= 50,
    },

    # Особые
    {
        "id": "early_bird", "emoji": "🌅", "label": "Ранняя пташка",
        "desc": "7 утренних check-in подряд. Утро твоё!",
        "check": lambda s: s.get("morning_checkins", 0) >= 7,
    },
    {
        "id": "iron_will",  "emoji": "🔩", "label": "Железная воля",
        "desc": "14 дней без пропусков задач.",
        "check": lambda s: s.get("streak", 0) >= 14,
    },
]

# ── ЧЕЛЛЕНДЖИ ─────────────────────────────────────────────────────────────────
CHALLENGES = [
    {
        "id": "no_sugar_7",
        "label": "7 дней без сладкого",
        "emoji": "🍬❌",
        "duration_days": 7,
        "xp_reward": 100,
        "unlock_rank": "student",
    },
    {
        "id": "walk_10_days",
        "label": "10 прогулок за 2 недели",
        "emoji": "🚶",
        "duration_days": 14,
        "xp_reward": 150,
        "unlock_rank": "student",
    },
    {
        "id": "full_week_diet",
        "label": "Неделя по плану питания",
        "emoji": "🥗",
        "duration_days": 7,
        "xp_reward": 200,
        "unlock_rank": "practitioner",
    },
    {
        "id": "hydration_week",
        "label": "7 дней 2л воды",
        "emoji": "💧",
        "duration_days": 7,
        "xp_reward": 80,
        "unlock_rank": "newcomer",
    },
]


class ProgressEngine:
    """
    Управляет прогрессом одного пользователя.
    Всё хранится в SQLite через MemoryManager.
    Пользователю показывается только человеческий язык.
    """

    def __init__(self, user_id: int, db):
        self.user_id = user_id
        self.db = db
        self._xp_cache = None

    # ── XP ───────────────────────────────────────────────────────────────────

    def _load_progress(self) -> dict:
        """Загружает сохранённый прогресс из БД."""
        try:
            row = self.db._fetch_one(
                "SELECT state_json FROM user_state WHERE user_id=?",
                (self.user_id,)
            )
            if row:
                data = json.loads(row["state_json"])
                return data.get("_progress", {})
        except Exception:
            pass
        return {}

    def _save_progress(self, progress: dict):
        """Сохраняет прогресс в user_state JSON (поле _progress)."""
        try:
            row = self.db._fetch_one(
                "SELECT state_json FROM user_state WHERE user_id=?",
                (self.user_id,)
            )
            if row:
                data = json.loads(row["state_json"])
            else:
                data = {}
            data["_progress"] = progress
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db._exec(
                "INSERT OR REPLACE INTO user_state (user_id, state_json, updated_at) VALUES (?,?,?)",
                (self.user_id, json.dumps(data), now)
            )
        except Exception as e:
            logger.error(f"ProgressEngine save error: {e}")

    def add_xp(self, event_type: str) -> int:
        """Начисляет XP за событие. Возвращает добавленное количество."""
        xp_gain = EVENT_XP.get(event_type, 0)
        if xp_gain == 0:
            return 0

        progress = self._load_progress()
        old_xp = progress.get("xp", 0)
        old_rank = self._get_rank(old_xp)

        progress["xp"] = old_xp + xp_gain
        progress["tasks_total"] = progress.get("tasks_total", 0) + (1 if event_type == "task_completed" else 0)
        progress["walks_total"] = progress.get("walks_total", 0) + (1 if event_type == "walk_done" else 0)
        progress["workouts_total"] = progress.get("workouts_total", 0) + (1 if event_type == "workout_done" else 0)
        progress["diet_days_total"] = progress.get("diet_days_total", 0) + (1 if event_type == "diet_followed" else 0)
        if event_type == "task_completed":
            progress["morning_checkins"] = progress.get("morning_checkins", 0)

        self._save_progress(progress)

        # Проверяем повышение ранга
        new_rank = self._get_rank(progress["xp"])
        if new_rank["id"] != old_rank["id"]:
            logger.info(f"User {self.user_id} ranked up: {old_rank['id']} → {new_rank['id']}")

        return xp_gain

    def _get_rank(self, xp: int) -> dict:
        for rank in reversed(RANKS):
            if xp >= rank["min_xp"]:
                return rank
        return RANKS[0]

    def get_rank(self) -> dict:
        progress = self._load_progress()
        return self._get_rank(progress.get("xp", 0))

    def get_xp(self) -> int:
        return self._load_progress().get("xp", 0)

    def xp_to_next_rank(self) -> int:
        """XP до следующего ранга."""
        xp = self.get_xp()
        rank = self._get_rank(xp)
        return max(0, rank["max_xp"] + 1 - xp)

    # ── ДОСТИЖЕНИЯ ───────────────────────────────────────────────────────────

    def check_and_award_achievements(self, stats: dict) -> list[dict]:
        """
        Проверяет все достижения и возвращает список НОВЫХ.
        stats: словарь с накопленной статистикой
        """
        progress = self._load_progress()
        earned = set(progress.get("achievements", []))
        new_achievements = []

        for ach in ACHIEVEMENTS:
            if ach["id"] in earned:
                continue
            try:
                if ach["check"](stats):
                    earned.add(ach["id"])
                    new_achievements.append(ach)
                    logger.info(f"Achievement unlocked: {self.user_id} → {ach['id']}")
            except Exception:
                pass

        if new_achievements:
            progress["achievements"] = list(earned)
            self._save_progress(progress)

        return new_achievements

    def get_achievements(self) -> list[dict]:
        """Все заработанные достижения."""
        progress = self._load_progress()
        earned_ids = set(progress.get("achievements", []))
        return [a for a in ACHIEVEMENTS if a["id"] in earned_ids]

    # ── СТРИК ────────────────────────────────────────────────────────────────

    def get_streak(self) -> int:
        """Текущая серия дней."""
        try:
            return self.db.get_current_streak()
        except Exception:
            return 0

    def get_streak_message(self) -> str:
        """Человеческое сообщение о серии."""
        streak = self.get_streak()
        if streak == 0:
            return "Начни сегодня — и серия пойдёт!"
        elif streak == 1:
            return "🌱 Первый день — главный шаг сделан"
        elif streak < 7:
            return f"🔥 {streak} дней подряд — ты в ритме!"
        elif streak < 14:
            return f"🔥🔥 {streak} дней подряд — это уже привычка!"
        elif streak < 30:
            return f"💪 {streak} дней подряд — впечатляет!"
        else:
            return f"💎 {streak} дней подряд — легендарно!"

    # ── ПРОФИЛЬ ПРОГРЕССА ────────────────────────────────────────────────────

    def get_profile_card(self, weight_start: float = None,
                         weight_now: float = None) -> str:
        """
        Текстовая карточка профиля — только человеческий язык.
        Возвращается в /profile и в дашборд.
        """
        rank = self.get_rank()
        streak = self.get_streak()
        achievements = self.get_achievements()
        xp_left = self.xp_to_next_rank()
        progress_data = self._load_progress()

        lines = [
            f"{rank['emoji']} *{rank['label']}*",
            f"_{rank['desc']}_",
            "",
        ]

        # Серия
        lines.append(self.get_streak_message())

        # Статистика недели — из EventBus если есть
        tasks = progress_data.get("tasks_total", 0)
        diet_days = progress_data.get("diet_days_total", 0)
        if tasks > 0:
            lines.append(f"✅ Задач выполнено всего: {tasks}")
        if diet_days > 0:
            lines.append(f"🥗 Дней здорового питания: {diet_days}")

        # Вес
        if weight_start and weight_now:
            diff = weight_now - weight_start
            if diff < 0:
                lines.append(f"⚖️ Вес изменился: {diff:.1f} кг — отличный прогресс!")
            elif diff > 0:
                lines.append(f"⚖️ Вес: +{diff:.1f} кг (продолжаем работать)")
            else:
                lines.append(f"⚖️ Вес стабилен — это тоже хороший результат")

        # До следующего ранга
        if rank["id"] != "legend":
            next_rank = RANKS[RANKS.index(rank) + 1]
            lines.append(f"\nДо статуса *{next_rank['emoji']} {next_rank['label']}*:")

            # Показываем прогресс без XP — человеческими словами
            if xp_left <= 20:
                lines.append("  Совсем чуть-чуть осталось!")
            elif xp_left <= 100:
                lines.append("  Ещё несколько активных дней")
            elif xp_left <= 300:
                lines.append("  Продолжай в том же темпе — пара недель")
            else:
                lines.append("  Ты на правильном пути — продолжай!")

        # Достижения
        if achievements:
            lines.append("\n🏅 *Достижения:*")
            for a in achievements[-5:]:  # последние 5
                lines.append(f"  {a['emoji']} {a['label']}")

        return "\n".join(lines)

    def get_daily_summary(self, tasks_done: int, tasks_total: int,
                          diet_ok: bool = False) -> str:
        """
        Итог дня — человеческим языком.
        Без XP, без score. Просто факты + мотивация.
        """
        lines = []

        # Задачи
        if tasks_total > 0:
            if tasks_done == tasks_total:
                lines.append(f"👍 Отличный день! Выполнил все {tasks_total} задачи")
            elif tasks_done >= tasks_total * 0.7:
                lines.append(f"✅ Хороший день — {tasks_done} из {tasks_total} задач")
            elif tasks_done > 0:
                lines.append(f"📝 {tasks_done} из {tasks_total} задач — завтра продолжим")
            else:
                lines.append("💭 Сегодня не получилось — бывает. Завтра новый шанс")

        # Питание
        if diet_ok:
            lines.append("🥗 День питания — засчитан!")

        # Серия
        streak = self.get_streak()
        if streak > 0:
            lines.append(f"\n🔥 Серия: {streak} {'день' if streak == 1 else 'дней' if 2 <= streak <= 4 else 'дней'} подряд")

        return "\n".join(lines) if lines else "День засчитан 👍"

    def get_insight_message(self) -> str:
        """
        Персональное наблюдение — имитирует "умного помощника".
        Возвращает случайный инсайт на основе паттернов.
        """
        try:
            patterns = self.db.get_user_patterns()
            if not patterns:
                return ""

            pattern_names = [p["pattern"] for p in patterns]
            messages = []

            if "diet_follower" in pattern_names:
                messages.append("Я заметил, что ты хорошо держишь план питания — это реально сказывается на энергии 💪")
            if "late_sleeper" in pattern_names:
                messages.append("Замечаю, что после коротких ночей тебе сложнее держать план. Попробуй лечь чуть раньше сегодня 🌙")
            if "skips_tasks" in pattern_names:
                messages.append("Маленький совет: попробуй сделать хотя бы одну задачу прямо утром — дальше идёт легче 🌅")
            if "completes_tasks" in pattern_names:
                messages.append("Ты стабильно выполняешь задачи — это редкость. Так держать! ⭐")
            if "workout_avoider" in pattern_names:
                messages.append("Я вижу, что тренировки пока не заходят. Может, попробуем начать с 10-минутной прогулки? 🚶")

            if messages:
                import random
                return random.choice(messages)
        except Exception:
            pass
        return ""

    def notify_new_achievements(self, new_achievements: list[dict]) -> str:
        """Текст уведомления о новых достижениях."""
        if not new_achievements:
            return ""
        if len(new_achievements) == 1:
            a = new_achievements[0]
            return f"🏅 *Новое достижение!*\n{a['emoji']} {a['label']}\n_{a['desc']}_"
        else:
            lines = ["🏅 *Сразу несколько достижений!*"]
            for a in new_achievements:
                lines.append(f"{a['emoji']} {a['label']}")
            return "\n".join(lines)
