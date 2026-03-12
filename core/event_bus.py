# -*- coding: utf-8 -*-
"""
core/event_bus.py
Event Bus v1

Центральная шина событий. Все действия пользователя превращаются в события.
События → State Engine → Patterns → Orchestrator

Таблица events:
  id, user_id, event_type, value, metadata_json, created_at

Используется для:
  - обновления HumanState
  - накопления поведенческих паттернов
  - аналитики
  - обучения рекомендательной системы
"""

import json
import logging
from datetime import datetime, date, timedelta
from core.human_state import HumanStateEngine, EVENT_DELTAS

logger = logging.getLogger(__name__)


class EventBus:
    """
    Принимает события, обновляет состояние, сохраняет историю.
    
    Использование:
        bus = EventBus(user_id, db)
        bus.emit("task_completed", value=1)
        bus.emit("weight_update", value=81.5, metadata={"prev": 82.0})
        bus.emit("recipe_liked", value=1, metadata={"recipe": "Овсянка"})
    """

    def __init__(self, user_id: int, db):
        self.user_id = user_id
        self.db = db
        self.state = HumanStateEngine(user_id, db)

    def emit(self, event_type: str, value=None, metadata: dict = None,
             magnitude: float = 1.0) -> dict:
        """
        Отправляет событие.
        Возвращает изменения состояния.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        # Сохраняем в БД
        try:
            self.db._exec(
                """INSERT INTO events (user_id, event_type, value, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.user_id, event_type, str(value) if value is not None else None,
                 meta_json, now)
            )
        except Exception as e:
            logger.error(f"EventBus save error: {e}")

        # Обновляем состояние
        changes = self.state.apply_event(event_type, magnitude)

        # Проверяем паттерны
        self._check_patterns(event_type, value, metadata)

        # Начисляем XP (невидимая геймификация)
        try:
            from core.progress_engine import ProgressEngine
            pe = ProgressEngine(self.user_id, self.db)
            xp_gained = pe.add_xp(event_type)
            if xp_gained > 0:
                changes["_xp"] = xp_gained
        except Exception as _xe:
            pass

        logger.debug(f"[{self.user_id}] event={event_type} value={value} changes={changes}")
        return changes

    def emit_weight(self, new_weight: float, prev_weight: float = None):
        """Умное событие веса — автоматически определяет тип."""
        if prev_weight is not None:
            diff = new_weight - prev_weight
            if diff < -0.1:
                event = "weight_loss"
                magnitude = min(2.0, abs(diff) * 2)  # чем больше потеря — тем сильнее эффект
            elif diff > 0.2:
                event = "weight_gain"
                magnitude = min(2.0, diff * 2)
            else:
                event = "weight_stable"
                magnitude = 1.0
        else:
            event = "weight_stable"
            magnitude = 1.0

        return self.emit(event, value=new_weight,
                        metadata={"prev": prev_weight, "diff": round(new_weight - (prev_weight or new_weight), 1)},
                        magnitude=magnitude)

    def emit_mood_checkin(self, mood_text: str):
        """Событие утреннего check-in настроения."""
        from core.human_state import mood_to_event
        event_type = mood_to_event(mood_text)
        return self.emit(event_type, value=mood_text)

    def emit_sleep(self, hours: float):
        """Событие сна."""
        from core.human_state import sleep_hours_to_event
        event_type = sleep_hours_to_event(hours)
        # Обновляем sleep_quality отдельно
        self.state.set_metric("sleep_quality", min(100, hours / 9 * 100))
        return self.emit(event_type, value=hours, metadata={"hours": hours})

    def emit_feedback(self, content_type: str, item_name: str, score: int):
        """
        Обратная связь по контенту (рецепты, фильмы, музыка).
        score: 3=лайк, 1=нейтрально, 0=дизлайк
        """
        if score >= 3:
            event = f"{content_type}_liked"
        elif score == 0:
            event = f"{content_type}_disliked"
        else:
            return {}  # нейтрально — не меняем состояние

        return self.emit(event, value=score, metadata={"item": item_name})

    # ── ПАТТЕРНЫ ─────────────────────────────────────────────────────────────

    def _check_patterns(self, event_type: str, value, metadata: dict = None):
        """Анализирует последние события и обновляет паттерны."""
        try:
            # Получаем последние 14 дней событий
            rows = self.db._fetch_all(
                """SELECT event_type, value, created_at FROM events
                   WHERE user_id=? AND created_at >= datetime('now', '-14 days')
                   ORDER BY created_at DESC LIMIT 100""",
                (self.user_id,)
            )
            events = [dict(r) for r in rows]
            self._update_patterns(events)
        except Exception as e:
            logger.warning(f"Pattern check error: {e}")

    def _update_patterns(self, events: list[dict]):
        """Обновляет таблицу patterns на основе истории событий."""
        if not events:
            return

        type_counts = {}
        for e in events:
            et = e["event_type"]
            type_counts[et] = type_counts.get(et, 0) + 1

        total = len(events)
        patterns_to_update = []

        # late_sleeper: много sleep_bad
        sleep_bad = type_counts.get("sleep_bad", 0)
        if sleep_bad >= 3:
            patterns_to_update.append(("late_sleeper", min(1.0, sleep_bad / 7)))

        # skips_tasks: много task_skipped
        skipped = type_counts.get("task_skipped", 0)
        completed = type_counts.get("task_completed", 0)
        if skipped + completed > 3:
            skip_ratio = skipped / (skipped + completed)
            if skip_ratio > 0.5:
                patterns_to_update.append(("skips_tasks", skip_ratio))
            elif skip_ratio < 0.2:
                patterns_to_update.append(("completes_tasks", 1 - skip_ratio))

        # high_stress_pattern
        stress_events = type_counts.get("mood_bad", 0) + type_counts.get("mood_terrible", 0)
        if stress_events >= 3:
            patterns_to_update.append(("chronic_stress", min(1.0, stress_events / 7)))

        # workout_avoider
        w_done = type_counts.get("workout_done", 0)
        w_skip = type_counts.get("workout_skipped", 0)
        if w_skip > w_done and w_skip >= 2:
            patterns_to_update.append(("workout_avoider", min(1.0, w_skip / 7)))

        # diet_follower
        diet_ok = type_counts.get("diet_followed", 0)
        diet_br = type_counts.get("diet_broken", 0)
        if diet_ok + diet_br >= 3:
            if diet_ok > diet_br:
                patterns_to_update.append(("diet_follower", diet_ok / (diet_ok + diet_br)))

        # Сохраняем паттерны
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pattern_name, confidence in patterns_to_update:
            try:
                self.db._exec(
                    """INSERT OR REPLACE INTO user_patterns
                       (user_id, pattern_name, confidence, detected_at)
                       VALUES (?, ?, ?, ?)""",
                    (self.user_id, pattern_name, round(confidence, 2), now)
                )
            except Exception as e:
                logger.warning(f"Pattern save error: {e}")

    # ── АНАЛИТИКА ────────────────────────────────────────────────────────────

    def get_recent_events(self, days: int = 7, event_type: str = None) -> list[dict]:
        sql = """SELECT event_type, value, metadata_json, created_at FROM events
                 WHERE user_id=? AND created_at >= datetime('now', ?, 'days')"""
        params = [self.user_id, f"-{days}"]
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        sql += " ORDER BY created_at DESC"
        rows = self.db._fetch_all(sql, tuple(params))
        return [dict(r) for r in rows]

    def get_week_stats(self) -> dict:
        """Статистика за последние 7 дней для weekly report."""
        events = self.get_recent_events(days=7)
        type_counts = {}
        for e in events:
            type_counts[e["event_type"]] = type_counts.get(e["event_type"], 0) + 1

        return {
            "tasks_completed": type_counts.get("task_completed", 0),
            "tasks_skipped":   type_counts.get("task_skipped", 0),
            "workouts_done":   type_counts.get("workout_done", 0),
            "diet_days":       type_counts.get("diet_followed", 0),
            "good_mood_days":  type_counts.get("mood_good", 0) + type_counts.get("mood_great", 0),
            "total_events":    len(events),
            "daily_score":     self.state.get_daily_score(),
        }

    def get_patterns(self) -> list[dict]:
        """Загружает паттерны пользователя из БД."""
        try:
            rows = self.db._fetch_all(
                "SELECT pattern_name, confidence FROM user_patterns WHERE user_id=? ORDER BY confidence DESC",
                (self.user_id,)
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_context_for_ai(self) -> str:
        """Полный контекст для Gemini — состояние + паттерны + статистика."""
        state_ctx = self.state.get_recommendations_context()
        patterns = self.get_patterns()
        stats = self.get_week_stats()

        ctx = state_ctx

        if patterns:
            pattern_names = [p["pattern_name"] for p in patterns[:5]]
            ctx += f"\n[Паттерны: {', '.join(pattern_names)}]"

        ctx += (f"\n[Неделя: выполнено задач={stats['tasks_completed']}, "
                f"тренировок={stats['workouts_done']}, "
                f"дней диеты={stats['diet_days']}]")

        return ctx
