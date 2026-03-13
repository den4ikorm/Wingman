"""
Единый запуск: FastAPI (healthcheck) + Telegram bot в одном процессе.
Railway видит HTTP на порту $PORT → не убивает контейнер.
v3.5-fix: добавлены healer_handler, travel_handler, setup_healer_scheduler, setup_weekly_scheduler
"""
import asyncio
import logging
import os
import threading
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from bot.config import bot, storage, scheduler
from bot.handlers import survey, common, evening_handler
from bot.handlers.diet_mode_handler import router as diet_mode_router
from bot.handlers import healer_handler
from bot.handlers import travel_handler
from bot.scheduler_logic import setup_scheduler, setup_nightly_patterns, setup_healer_scheduler
from core.database import init_db, get_all_user_ids
from core.pattern_cache import init_pattern_tables
from plugins.idea_factory import router as idea_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


async def run_bot():
    from aiogram import Dispatcher
    dp = Dispatcher(storage=storage)

    dp.include_router(survey.router)
    dp.include_router(evening_handler.router)
    dp.include_router(diet_mode_router)
    dp.include_router(idea_router)
    dp.include_router(healer_handler.router)
    dp.include_router(travel_handler.router)
    dp.include_router(common.router)   # common — последним (ловит всё остальное)

    setup_scheduler()
    setup_nightly_patterns()
    setup_healer_scheduler(bot)

    from core.weekly_summary import setup_weekly_scheduler
    setup_weekly_scheduler(bot, get_all_user_ids)

    scheduler.start()
    logging.info("Wingman v3.5-fix started")

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def run_web():
    """FastAPI в отдельном потоке — отвечает на healthcheck Railway."""
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    init_db()
    init_pattern_tables()

    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    logging.info("Web server started in background thread")

    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
