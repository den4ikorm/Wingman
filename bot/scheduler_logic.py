import logging
from aiogram.types import FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import bot, scheduler
from core.database import MemoryManager
from core.gemini_ai import GeminiEngine

# Реестр пользователей для восстановления job'ов после перезапуска
_user_registry: dict[int, dict] = {}


async def send_morning_dashboard(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()

    if not profile:
        logging.error(f"No profile for user {user_id}")
        return

    # Напоминание если вечерний отчёт был пропущен
    if db.is_report_pending():
        await bot.send_message(
            user_id,
            "☀️ Доброе утро! Вчера не успели разобрать итоги дня.\n"
            "Напиши пару слов — как прошло вчера?"
        )
        db.mark_report_pending(False)

    ai = GeminiEngine(profile)

    try:
        html_content = ai.get_dashboard_content()
        db.save_last_plan(html_content)

        # Кнопка открытия Mini App
        # После деплоя замени URL на реальный
        webapp_url = f"https://YOUR_DOMAIN/dashboard/{user_id}"

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="📊 Открыть дашборд",
                # web_app=WebAppInfo(url=webapp_url)  # раскомментировать после деплоя
                url=webapp_url  # временно как обычная ссылка
            )
        )

        await bot.send_message(
            user_id,
            "☀️ Твой план на сегодня готов!",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logging.error(f"Morning dashboard error for {user_id}: {e}")


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


def setup_user_jobs(user_id: int, wake_up_time: str, bedtime: str):
    """Регистрирует cron-задачи для пользователя"""
    _user_registry[user_id] = {
        "wake_up_time": wake_up_time,
        "bedtime": bedtime
    }

    wake_h, wake_m = wake_up_time.split(":")

    scheduler.add_job(
        send_morning_dashboard,
        "cron",
        hour=int(wake_h),
        minute=int(wake_m),
        args=[user_id],
        id=f"morning_{user_id}",
        replace_existing=True,
    )

    scheduler.add_job(
        send_evening_prompt,
        "cron",
        hour=21,
        minute=0,
        args=[user_id],
        id=f"evening_{user_id}",
        replace_existing=True,
    )

    logging.info(f"Jobs set for user {user_id}: morning={wake_up_time}, evening=21:00")


def setup_scheduler():
    """Вызывается один раз при старте бота"""
    logging.info("Scheduler configured (jobs will be added after user survey)")
