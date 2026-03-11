"""
bot/scheduler_logic.py
Планировщик: утро (+15 мин), сюрприз (случайное время), напоминания еды, вечер
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

_user_registry: dict[int, dict] = {}

WEBAPP_DOMAIN = "bot-production-55d2.up.railway.app"


# ── УТРО ───────────────────────────────────────────────────────────────────

async def send_morning_dashboard(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return

    # Напоминание если вчерашний отчёт пропущен
    if db.is_report_pending():
        await bot.send_message(
            user_id,
            "☀️ Доброе утро! Вчера не успели разобрать итоги.\n"
            "Напиши пару слов — как прошло вчера?"
        )
        db.mark_report_pending(False)

    ai = GeminiEngine(profile)

    try:
        # 1. Генерируем контент дашборда
        dashboard_data = ai.get_morning_dashboard()
        db.save_last_plan(dashboard_data["html_sections"])
        db.save_tasks(dashboard_data["tasks"])

        # 2. Строим HTML-файл
        builder = DashboardBuilder(user_id, profile)
        html_path = builder.render(dashboard_data)

        name = profile.get("name", "")
        greeting = f"☀️ Доброе утро{', ' + name if name else ''}!"

        # 3. Отправляем HTML-файл
        await bot.send_document(
            user_id,
            FSInputFile(html_path, filename="my_day.html"),
            caption=f"{greeting}\nТвой план на сегодня 👇"
        )

        # 4. Кнопка Mini App
        builder_kb = InlineKeyboardBuilder()
        builder_kb.row(
            InlineKeyboardButton(
                text="📊 Открыть дашборд",
                url=f"https://{WEBAPP_DOMAIN}/dashboard/{user_id}"
                # После активации Mini App заменить на:
                # web_app=WebAppInfo(url=f"https://{WEBAPP_DOMAIN}/dashboard/{user_id}")
            )
        )
        builder_kb.row(
            InlineKeyboardButton(text="✅ Мои задачи", callback_data="show_tasks"),
            InlineKeyboardButton(text="🍽 Рацион", callback_data="show_meals"),
        )

        await bot.send_message(
            user_id,
            f"*Задачи на день:*\n" + "\n".join(
                f"{i+1}. {t}" for i, t in enumerate(dashboard_data["tasks"])
            ),
            reply_markup=builder_kb.as_markup(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logging.error(f"Morning dashboard error for {user_id}: {e}")
        await bot.send_message(user_id, "☀️ Доброе утро! Не смог сгенерировать план — попробуй /plan")


# ── СЮРПРИЗ (случайное время между 10:00 и 19:00) ─────────────────────────

async def send_surprise(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return
    if not profile.get("surprise_enabled", True):
        return

    ai = GeminiEngine(profile)
    try:
        surprise = ai.get_surprise()
        await bot.send_message(user_id, surprise, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Surprise error for {user_id}: {e}")


# ── НАПОМИНАНИЯ ЕДЫ ────────────────────────────────────────────────────────

async def remind_meal(user_id: int, meal_name: str):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile:
        return

    meal_emojis = {"завтрак": "🌅", "обед": "☀️", "ужин": "🌙", "перекус": "🍎"}
    emoji = meal_emojis.get(meal_name.lower(), "🍽")

    await bot.send_message(
        user_id,
        f"{emoji} Время {meal_name}!\n"
        f"Не забудь про свой рацион 💪"
    )


# ── ВЕЧЕР ──────────────────────────────────────────────────────────────────

async def send_evening_prompt(user_id: int):
    db = MemoryManager(user_id)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✨ Подвести итоги дня",
            callback_data="start_evening_review"
        )
    )

    await bot.send_message(
        user_id,
        "Вечер добрый 🌙 Расскажешь как прошёл день?",
        reply_markup=builder.as_markup()
    )
    db.mark_report_pending(True)


# ── НАСТРОЙКА JOB'ОВ ───────────────────────────────────────────────────────

def setup_user_jobs(user_id: int, wake_up_time: str, bedtime: str):
    _user_registry[user_id] = {
        "wake_up_time": wake_up_time,
        "bedtime": bedtime
    }

    # Утро: время подъёма + 15 минут
    wake_h, wake_m = map(int, wake_up_time.split(":"))
    wake_dt = datetime.now().replace(hour=wake_h, minute=wake_m, second=0)
    morning_dt = wake_dt + timedelta(minutes=15)

    scheduler.add_job(
        send_morning_dashboard,
        "cron",
        hour=morning_dt.hour,
        minute=morning_dt.minute,
        args=[user_id],
        id=f"morning_{user_id}",
        replace_existing=True,
    )

    # Сюрприз: случайное время между 10:00 и 19:00
    surprise_hour = random.randint(10, 18)
    surprise_min  = random.randint(0, 59)
    scheduler.add_job(
        send_surprise,
        "cron",
        hour=surprise_hour,
        minute=surprise_min,
        args=[user_id],
        id=f"surprise_{user_id}",
        replace_existing=True,
    )

    # Напоминания еды (базовые — 3 раза в день)
    meal_times = [
        (wake_h + 1, wake_m, "Завтрак"),
        (13, 0, "Обед"),
        (19, 0, "Ужин"),
    ]
    for h, m, name in meal_times:
        scheduler.add_job(
            remind_meal,
            "cron",
            hour=h % 24,
            minute=m,
            args=[user_id, name],
            id=f"meal_{name.lower()}_{user_id}",
            replace_existing=True,
        )

    # Вечер: за 2 часа до сна
    bed_h, bed_m = map(int, bedtime.split(":"))
    bed_dt = datetime.now().replace(hour=bed_h, minute=bed_m)
    eve_dt = bed_dt - timedelta(hours=2)

    scheduler.add_job(
        send_evening_prompt,
        "cron",
        hour=eve_dt.hour,
        minute=eve_dt.minute,
        args=[user_id],
        id=f"evening_{user_id}",
        replace_existing=True,
    )

    logging.info(
        f"Jobs set for {user_id}: "
        f"morning={morning_dt.hour:02d}:{morning_dt.minute:02d}, "
        f"surprise={surprise_hour:02d}:{surprise_min:02d}, "
        f"evening={eve_dt.hour:02d}:{eve_dt.minute:02d}"
    )


def setup_scheduler():
    logging.info("Scheduler configured")
