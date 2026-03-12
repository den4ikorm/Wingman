# -*- coding: utf-8 -*-
"""
core/weekly_summary.py
Weekly Summary Agent v1

Каждое воскресенье:
  1. Собирает данные за неделю (события, вес, задачи, паттерны)
  2. Gemini делает "выжимку" — краткий конспект
  3. Конспект сохраняется в week_summaries
  4. Следующая неделя получает контекст без огромного промпта

Принцип AI Distillation:
  raw events (сотни записей) → weekly digest (300 токенов)
  → следующий промпт использует digest, не сырые данные
"""

import json
import logging
import asyncio
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


class WeeklySummaryAgent:
    """
    Генерирует недельный дайджест и отправляет пользователю.
    Вызывается из планировщика каждое воскресенье в 20:00.
    """

    def __init__(self, bot=None):
        self.bot = bot

    async def run_for_user(self, user_id: int):
        """Генерирует и отправляет недельный отчёт одному пользователю."""
        from core.database import MemoryManager
        from core.event_bus import EventBus
        from core.progress_engine import ProgressEngine

        db = MemoryManager(user_id)
        profile = db.get_profile()
        if not profile:
            return

        try:
            bus      = EventBus(user_id, db)
            pe       = ProgressEngine(user_id, db)
            stats    = bus.get_week_stats()
            streak   = pe.get_streak()
            patterns = bus.get_patterns()
            weight_h = db.get_weight_history(days=7)

            # Вес за неделю
            weight_change = None
            if len(weight_h) >= 2:
                weight_change = round(weight_h[0]["weight"] - weight_h[-1]["weight"], 1)

            # Генерируем AI-выжимку
            digest = await self._generate_digest(
                profile, stats, streak, patterns, weight_change
            )

            # Сохраняем в БД
            week_start = (date.today() - timedelta(days=6)).isoformat()
            db.save_week_summary(week_start, digest)

            # Отправляем пользователю
            if self.bot:
                report = self._build_report(
                    profile, stats, streak, weight_change, patterns, digest
                )
                await self.bot.send_message(
                    user_id, report, parse_mode="Markdown"
                )

            logger.info(f"Weekly summary done for {user_id}")

        except Exception as e:
            logger.error(f"Weekly summary error for {user_id}: {e}", exc_info=True)

    async def _generate_digest(self, profile: dict, stats: dict,
                                streak: int, patterns: list,
                                weight_change: float = None) -> str:
        """
        Gemini делает краткий конспект недели (200-300 токенов).
        Этот конспект будет контекстом для следующей недели.
        """
        from core.key_manager import KeyManager
        from google import genai

        name = profile.get("name", "пользователь")
        goal = profile.get("goal", "")

        pattern_names = [p["pattern"] for p in patterns[:5]] if patterns else []
        weight_line = f"Вес изменился: {weight_change:+.1f} кг" if weight_change is not None else ""

        prompt = f"""Составь краткий психологический портрет недели пользователя.
Это будет контекстом для AI на следующей неделе.

ДАННЫЕ НЕДЕЛИ:
- Имя: {name}, Цель: {goal}
- Выполнено задач: {stats.get('tasks_completed', 0)}
- Пропущено задач: {stats.get('tasks_skipped', 0)}
- Дней по диете: {stats.get('diet_days', 0)}/7
- Тренировок: {stats.get('workouts_done', 0)}
- Настроение хорошее: {stats.get('good_mood_days', 0)} дней
- Серия дней: {streak}
- {weight_line}
- Паттерны: {', '.join(pattern_names) if pattern_names else 'нет данных'}

Напиши 3-5 предложений:
1. Как прошла неделя в целом
2. Что работает хорошо
3. Что стоит улучшить
4. Главный совет на следующую неделю

Пиши от лица AI-коуча, тепло и конкретно. Без шаблонных фраз."""

        try:
            km = KeyManager()
            client = genai.Client(api_key=km.get_key())

            def _call():
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={"max_output_tokens": 512}
                )
                return resp.text.strip()

            return await asyncio.get_event_loop().run_in_executor(None, _call)

        except Exception as e:
            logger.error(f"Weekly digest generation error: {e}")
            return (
                f"Неделя завершена. "
                f"Задач выполнено: {stats.get('tasks_completed',0)}, "
                f"серия: {streak} дней."
            )

    def _build_report(self, profile: dict, stats: dict, streak: int,
                      weight_change: float, patterns: list, digest: str) -> str:
        """Строит красивый отчёт для Telegram."""
        name  = profile.get("name", "")
        goal  = profile.get("goal", "")
        tasks = stats.get("tasks_completed", 0)
        skipped = stats.get("tasks_skipped", 0)
        diet  = stats.get("diet_days", 0)
        sport = stats.get("workouts_done", 0)
        mood  = stats.get("good_mood_days", 0)

        # Оценка недели
        total_possible = tasks + skipped
        completion = round(tasks / total_possible * 100) if total_possible > 0 else 0

        if completion >= 80:
            week_emoji = "🔥"
            week_label = "Отличная неделя!"
        elif completion >= 60:
            week_emoji = "✅"
            week_label = "Хорошая неделя"
        elif completion >= 40:
            week_emoji = "📈"
            week_label = "Средняя неделя — есть куда расти"
        else:
            week_emoji = "💪"
            week_label = "Неделя была непростой — всё наладится"

        lines = [
            f"{week_emoji} *Итоги недели*",
            f"_{week_label}_\n",
        ]

        # Статистика
        lines.append("📊 *Статистика:*")
        lines.append(f"✅ Задач выполнено: {tasks}")
        if skipped > 0:
            lines.append(f"⏭ Пропущено: {skipped}")
        lines.append(f"🥗 Дней по питанию: {diet}/7")
        if sport > 0:
            lines.append(f"💪 Тренировок: {sport}")
        lines.append(f"😊 Хороших дней: {mood}/7")

        # Вес
        if weight_change is not None:
            if weight_change < 0:
                lines.append(f"⚖️ Вес: *{weight_change:+.1f} кг* — прогресс!")
            elif weight_change > 0:
                lines.append(f"⚖️ Вес: {weight_change:+.1f} кг")
            else:
                lines.append("⚖️ Вес стабилен")

        # Серия
        if streak > 0:
            lines.append(f"\n🔥 Серия дней: *{streak}*")

        # AI выжимка
        lines.append(f"\n💬 *Мои наблюдения:*\n_{digest}_")

        # Паттерны (если есть интересные)
        pattern_msgs = {
            "diet_follower":   "🥗 Ты хорошо держишь план питания",
            "completes_tasks": "⭐ Задачи выполняются стабильно",
            "workout_avoider": "🏃 Стоит добавить больше движения",
            "chronic_stress":  "😌 Уделяй больше времени отдыху",
            "late_sleeper":    "🌙 Попробуй нормализовать сон",
        }
        if patterns:
            for p in patterns[:2]:
                msg = pattern_msgs.get(p["pattern"])
                if msg:
                    lines.append(f"\n{msg}")

        lines.append(f"\n_Новая неделя начнётся с улучшенным планом. До встречи утром!_ 🌅")

        return "\n".join(lines)


def setup_weekly_scheduler(bot, db_get_all_users_fn):
    """
    Подключает WeeklySummaryAgent к APScheduler.
    db_get_all_users_fn — функция возвращающая список user_id.
    Запускается каждое воскресенье в 20:00 UTC.
    """
    from bot.config import scheduler

    agent = WeeklySummaryAgent(bot=bot)

    async def _run_all():
        try:
            user_ids = db_get_all_users_fn()
            logger.info(f"WeeklySummary: running for {len(user_ids)} users")
            for uid in user_ids:
                try:
                    await agent.run_for_user(uid)
                except Exception as e:
                    logger.error(f"WeeklySummary error for {uid}: {e}")
        except Exception as e:
            logger.error(f"WeeklySummary scheduler error: {e}")

    import asyncio
    scheduler.add_job(
        lambda: asyncio.create_task(_run_all()),
        "cron",
        day_of_week="sun",
        hour=20,
        minute=0,
        id="weekly_summary",
        replace_existing=True,
    )
    logger.info("WeeklySummary scheduler: every Sunday 20:00")
    return agent
