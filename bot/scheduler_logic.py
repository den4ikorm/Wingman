"""
bot/scheduler_logic.py
Планировщик v3.4 — FIXED:
  - build_dashboard_bytes() → HTML в памяти, без файловой системы
  - send_morning_dashboard() → BufferedInputFile + asyncio.to_thread
  - Sync Gemini вызовы через to_thread — event loop не блокируется
"""

import asyncio
import logging
import json
import random
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import bot, scheduler
from core.database import MemoryManager
from core.gemini_ai import GeminiEngine
from core.html_builder import DashboardBuilder

logger = logging.getLogger(__name__)

_user_registry: dict[int, dict] = {}
WEBAPP_DOMAIN = "bot-production-55d2.up.railway.app"


# ── ХЕЛПЕР: HTML в памяти ─────────────────────────────────────────────────

def build_dashboard_bytes(user_id: int, profile: dict,
                          yesterday_summary: str = "",
                          week_summary: str = "") -> bytes | None:
    """
    Синхронная — вызывать через asyncio.to_thread().
    Возвращает HTML как bytes, не пишет файлы на диск.
    """
    try:
        ai = GeminiEngine(profile)
        raw = ai.get_dashboard_content(
            yesterday_summary=yesterday_summary,
            week_summary=week_summary,
        )

        if isinstance(raw, dict):
            dashboard_data = raw
        else:
            raw_stripped = raw.strip()
            dashboard_data = {}
            if raw_stripped.startswith("{"):
                try:
                    dashboard_data = json.loads(raw_stripped)
                except Exception:
                    pass
            if not dashboard_data.get("tasks"):
                dashboard_data["tasks"] = _extract_tasks(raw)
            if not dashboard_data.get("meals"):
                dashboard_data["meals"] = _extract_meals(raw)
            dashboard_data.setdefault("html_sections", raw)
            dashboard_data.setdefault("surprise", "")

        builder_obj = DashboardBuilder(user_id, profile)

        if hasattr(builder_obj, "render_to_string"):
            html_str = builder_obj.render_to_string(dashboard_data)
        else:
            # Fallback: render() пишет файл, читаем его
            html_path = builder_obj.render(dashboard_data)
            with open(html_path, "r", encoding="utf-8") as f:
                html_str = f.read()

        return html_str.encode("utf-8")

    except Exception as e:
        logger.error(f"build_dashboard_bytes error for {user_id}: {e}", exc_info=True)
        return None


def _extract_tasks(text: str) -> list[str]:
    tasks = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("- ", "• ", "* ", "1.", "2.", "3.", "4.", "5.")):
            task = line.lstrip("-•*0123456789. ").strip()
            if 5 < len(task) < 120:
                tasks.append(task)
    return tasks[:10]


def _extract_meals(text: str) -> dict:
    meals = {}
    for line in text.splitlines():
        low = line.lower()
        if "завтрак" in low and "завтрак" not in meals:
            meals["завтрак"] = line.split(":", 1)[-1].strip()
        elif "обед" in low and "обед" not in meals:
            meals["обед"] = line.split(":", 1)[-1].strip()
        elif "ужин" in low and "ужин" not in meals:
            meals["ужин"] = line.split(":", 1)[-1].strip()
    return meals


# ── УТРО ──────────────────────────────────────────────────────────────────

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

    yesterday_summary = db.get_day_summary()
    week_summary = db.get_latest_week_summary()

    try:
        html_bytes = await asyncio.to_thread(
            build_dashboard_bytes, user_id, profile,
            yesterday_summary, week_summary
        )
        if not html_bytes:
            raise ValueError("build_dashboard_bytes вернул None")

        name = profile.get("name", "")
        greeting = f"☀️ Доброе утро{', ' + name if name else ''}!"

        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="🛒 Покупки", callback_data="show_shopping"),
            InlineKeyboardButton(text="📊 Прогресс", callback_data="noop"),
        )

        await bot.send_document(
            user_id,
            BufferedInputFile(html_bytes, filename="my_day.html"),
            caption=f"{greeting}\nТвой план на сегодня 👇\nОткрой файл в браузере 📂",
            reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"Morning dashboard error for {user_id}: {e}")
        await bot.send_message(user_id, "☀️ Доброе утро! Не смог сгенерировать план — попробуй /plan")


# ── СЮРПРИЗ ───────────────────────────────────────────────────────────────

async def send_surprise(user_id: int):
    db = MemoryManager(user_id)
    profile = db.get_profile()
    if not profile or not profile.get("surprise_enabled", True):
        return
    ai = GeminiEngine(profile)
    try:
        surprise = await asyncio.to_thread(ai.get_surprise)
        await bot.send_message(user_id, surprise, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Surprise error for {user_id}: {e}")


# ── НАПОМИНАНИЯ ───────────────────────────────────────────────────────────

async def remind_meal(user_id: int, meal_name: str):
    db = MemoryManager(user_id)
    if not db.get_profile():
        return
    emojis = {"завтрак": "🌅", "обед": "☀️", "ужин": "🌙", "перекус": "🍎"}
    emoji = emojis.get(meal_name.lower(), "🍽")
    await bot.send_message(user_id, f"{emoji} Время {meal_name}! Не забудь про рацион 💪")


# ── ВЕЧЕР ─────────────────────────────────────────────────────────────────

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


# ── НЕДЕЛЬНЫЙ ОТЧЁТ ───────────────────────────────────────────────────────

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
        week_text = await asyncio.to_thread(ai.generate_week_summary, summaries)
        db.save_week_summary(week_text)
        await bot.send_message(user_id, f"📊 *Итоги недели*\n\n{week_text}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Weekly summary error for {user_id}: {e}")


# ── НАСТРОЙКА JOB'ОВ ──────────────────────────────────────────────────────

def setup_user_jobs(user_id: int, wake_up_time: str, bedtime: str):
    profile = MemoryManager(user_id).get_profile()
    utc_offset = profile.get("utc_offset", 3) if profile else 3

    _user_registry[user_id] = {
        "wake_up_time": wake_up_time,
        "bedtime": bedtime,
        "utc_offset": utc_offset,
    }

    wake_h, wake_m = map(int, wake_up_time.split(":"))
    wake_h_utc = (wake_h - utc_offset) % 24

    scheduler.add_job(
        send_morning_dashboard, "cron",
        hour=wake_h_utc, minute=(wake_m + 15) % 60,
        args=[user_id], id=f"morning_{user_id}", replace_existing=True,
    )

    surprise_h_utc = (random.randint(10, 18) - utc_offset) % 24
    scheduler.add_job(
        send_surprise, "cron",
        hour=surprise_h_utc, minute=random.randint(0, 59),
        args=[user_id], id=f"surprise_{user_id}", replace_existing=True,
    )

    for local_h, m, meal_name in [
        (wake_h + 1, wake_m, "Завтрак"),
        (13, 0, "Обед"),
        (19, 0, "Ужин"),
    ]:
        scheduler.add_job(
            remind_meal, "cron",
            hour=(local_h - utc_offset) % 24, minute=m,
            args=[user_id, meal_name],
            id=f"meal_{meal_name.lower()}_{user_id}", replace_existing=True,
        )

    bed_h, bed_m = map(int, bedtime.split(":"))
    bed_h_utc = (bed_h - utc_offset) % 24
    eve_h = (bed_h_utc - 2) % 24
    scheduler.add_job(
        send_evening_prompt, "cron",
        hour=eve_h, minute=bed_m,
        args=[user_id], id=f"evening_{user_id}", replace_existing=True,
    )

    weekly_h = (20 - utc_offset) % 24
    scheduler.add_job(
        send_weekly_summary, "cron",
        day_of_week="sun", hour=weekly_h, minute=0,
        args=[user_id], id=f"weekly_{user_id}", replace_existing=True,
    )

    logger.info(f"Jobs set for user {user_id}: morning={wake_h_utc:02d}:{(wake_m+15)%60:02d} UTC")


def setup_scheduler():
    logger.info("Scheduler ready")


# ── НОЧНОЕ ОБНОВЛЕНИЕ ПАТТЕРНОВ ───────────────────────────────────────────

async def run_nightly_pattern_update():
    from core.pattern_cache import analyze_and_update_patterns
    logger.info("Nightly pattern update started")
    for user_id in list(_user_registry.keys()):
        try:
            result = await analyze_and_update_patterns(user_id)
            if result:
                logger.info(f"Patterns updated for {user_id}")
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Pattern update failed for {user_id}: {e}")


def setup_nightly_patterns():
    scheduler.add_job(
        run_nightly_pattern_update, "cron",
        hour=2, minute=0,
        id="nightly_patterns", replace_existing=True,
    )
    logger.info("Nightly pattern update scheduled at 02:00 UTC")
