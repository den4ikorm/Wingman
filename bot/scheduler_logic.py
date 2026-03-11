"""
bot/scheduler_logic.py
Планировщик v3: утро, сюрприз, еда, вечер, недельный отчёт
"""

import logging
import random
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import bot, scheduler
from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from core.html_builder import DashboardBuilder

logger = logging.getLogger(__name__)

_user_registry: dict[int, dict] = {}
WEBAPP_DOMAIN = "bot-production-55d2.up.railway.app"


# ── УТРО ───────────────────────────────────────────────────────────────────

async def send_morning_dashboard(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return

    if db.is_report_pending():
        await bot.send_message(
            user_id,
            "☀️ Доброе утро! Вчера не успели разобрать итоги.\n"
            "Напиши пару слов — как прошло вчера?"
        )
        db.mark_report_pending(False)

    # Контекст для утреннего промпта
    yesterday_summary = db.get_day_summary()  # вчера уже сохранён
    week_summary = db.get_latest_week_summary()

    ai = GeminiEngine(profile)

    try:
        dashboard_data = ai.get_dashboard_content(
            yesterday_summary=yesterday_summary,
            week_summary=week_summary,
        )
        # Если вернулась строка (старый формат) — оборачиваем
        if isinstance(dashboard_data, str):
            dashboard_data = {"html_sections": dashboard_data, "tasks": [], "meals": {}, "surprise": ""}

        db.save_last_plan(dashboard_data.get("html_sections", ""))
        db.save_tasks(dashboard_data.get("tasks", []))

        builder_obj = DashboardBuilder(user_id, profile)
        html_path = builder_obj.render(dashboard_data)

        name = profile.get("name", "")
        greeting = f"☀️ Доброе утро{', ' + name if name else ''}!"

        await bot.send_document(
            user_id,
            FSInputFile(html_path, filename="my_day.html"),
            caption=f"{greeting}\nТвой план на сегодня 👇"
        )

        tasks = dashboard_data.get("tasks", [])
        if tasks:
            kb = InlineKeyboardBuilder()
            kb.row(
                InlineKeyboardButton(text="✅ Мои задачи",  callback_data="show_tasks"),
                InlineKeyboardButton(text="🍽 Рацион",      callback_data="show_meals"),
                InlineKeyboardButton(text="🛒 Покупки",     callback_data="show_shopping"),
            )
            await bot.send_message(
                user_id,
                "*Задачи на день:*\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks)),
                reply_markup=kb.as_markup(),
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Morning dashboard error for {user_id}: {e}")
        await bot.send_message(user_id, "☀️ Доброе утро! Не смог сгенерировать план — попробуй /plan")


# ── СЮРПРИЗ ────────────────────────────────────────────────────────────────

async def send_surprise(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile or not profile.get("surprise_enabled", True):
        return
    ai = GeminiEngine(profile)
    try:
        surprise = ai.get_surprise()
        await bot.send_message(user_id, surprise, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Surprise error for {user_id}: {e}")


# ── НАПОМИНАНИЯ ────────────────────────────────────────────────────────────

async def remind_meal(user_id: int, meal_name: str):
    db = MemoryManager(user_id)
    if not db.get_profile():
        return
    emojis = {"завтрак": "🌅", "обед": "☀️", "ужин": "🌙", "перекус": "🍎"}
    emoji = emojis.get(meal_name.lower(), "🍽")
    await bot.send_message(user_id, f"{emoji} Время {meal_name}! Не забудь про рацион 💪")


# ── ВЕЧЕР ──────────────────────────────────────────────────────────────────

async def send_evening_prompt(user_id: int):
    db = MemoryManager(user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✨ Подвести итоги", callback_data="start_evening_review"))
    await bot.send_message(
        user_id,
        "Вечер добрый 🌙 Расскажешь как прошёл день?",
        reply_markup=kb.as_markup()
    )
    db.mark_report_pending(True)


# ── НЕДЕЛЬНЫЙ ОТЧЁТ (воскресенье 20:00) ───────────────────────────────────

async def send_weekly_summary(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return

    summaries = db.get_last_7_summaries()
    if not summaries:
        return

    ai = GeminiEngine(profile)
    try:
        week_text = ai.generate_week_summary(summaries)
        db.save_week_summary(week_text)
        await bot.send_message(
            user_id,
            f"📊 *Итоги недели*\n\n{week_text}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Weekly summary error for {user_id}: {e}")


# ── НАСТРОЙКА JOB'ОВ ───────────────────────────────────────────────────────

def setup_user_jobs(user_id: int, wake_up_time: str, bedtime: str):
    profile = MemoryManager(user_id).get_profile()
    utc_offset = profile.get("utc_offset", 3) if profile else 3

    _user_registry[user_id] = {
        "wake_up_time": wake_up_time,
        "bedtime": bedtime,
        "utc_offset": utc_offset,
    }

    # Утро: подъём + 15 мин → UTC
    wake_h, wake_m = map(int, wake_up_time.split(":"))
    wake_h_utc = (wake_h - utc_offset) % 24
    morning_dt = datetime.now().replace(hour=wake_h_utc, minute=wake_m) + timedelta(minutes=15)

    scheduler.add_job(
        send_morning_dashboard, "cron",
        hour=morning_dt.hour, minute=morning_dt.minute,
        args=[user_id], id=f"morning_{user_id}", replace_existing=True,
    )

    # Сюрприз: случайное время 10-18
    surprise_h = random.randint(10, 18)
    surprise_m = random.randint(0, 59)
    surprise_h_utc = (surprise_h - utc_offset) % 24
    scheduler.add_job(
        send_surprise, "cron",
        hour=surprise_h_utc, minute=surprise_m,
        args=[user_id], id=f"surprise_{user_id}", replace_existing=True,
    )

    # Напоминания еды (UTC)
    meal_times = [
        ((wake_h_utc + 1) % 24, wake_m, "Завтрак"),
        ((13 - utc_offset) % 24, 0, "Обед"),
        ((19 - utc_offset) % 24, 0, "Ужин"),
    ]
    for h, m, name in meal_times:
        scheduler.add_job(
            remind_meal, "cron",
            hour=h, minute=m,
            args=[user_id, name],
            id=f"meal_{name.lower()}_{user_id}", replace_existing=True,
        )

    # Вечер: за 2 часа до сна → UTC
    bed_h, bed_m = map(int, bedtime.split(":"))
    bed_h_utc = (bed_h - utc_offset) % 24
    eve_dt = datetime.now().replace(hour=bed_h_utc, minute=bed_m) - timedelta(hours=2)
    scheduler.add_job(
        send_evening_prompt, "cron",
        hour=eve_dt.hour, minute=eve_dt.minute,
        args=[user_id], id=f"evening_{user_id}", replace_existing=True,
    )

    # Недельный отчёт: воскресенье 20:00 по UTC
    weekly_h = (20 - utc_offset) % 24
    scheduler.add_job(
        send_weekly_summary, "cron",
        day_of_week="sun", hour=weekly_h, minute=0,
        args=[user_id], id=f"weekly_{user_id}", replace_existing=True,
    )

    logger.info(
        f"Jobs set for {user_id}: morning={morning_dt.hour:02d}:{morning_dt.minute:02d}, "
        f"surprise={surprise_h_utc:02d}:{surprise_m:02d}, evening={eve_dt.hour:02d}:{eve_dt.minute:02d}"
    )


def setup_scheduler():
    logger.info("Scheduler configured")
