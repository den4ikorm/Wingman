# bot/main.py — синхронизирован с main_combined.py
# Railway запускает main_combined.py, этот файл для локального запуска
import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()

from bot.config import bot, storage, scheduler
from bot.handlers import survey, common, evening_handler
from bot.handlers.diet_mode_handler import router as diet_mode_router
from bot.handlers import healer_handler, travel_handler, movie_handler
from bot.keyboard_manager import nav_router
from bot.scheduler_logic import setup_scheduler, setup_nightly_patterns, setup_healer_scheduler
from core.database import init_db, get_all_user_ids
from core.pattern_cache import init_pattern_tables
from plugins.idea_factory import router as idea_router

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")


async def main():
    init_db()
    init_pattern_tables()

    from aiogram import Dispatcher
    dp = Dispatcher(storage=storage)

    dp.include_router(survey.router)
    dp.include_router(nav_router)
    dp.include_router(evening_handler.router)
    dp.include_router(diet_mode_router)
    dp.include_router(idea_router)
    dp.include_router(healer_handler.router)
    dp.include_router(travel_handler.router)
    dp.include_router(movie_handler.router)
    dp.include_router(common.router)

    setup_scheduler()
    setup_nightly_patterns()
    setup_healer_scheduler(bot)

    from core.weekly_summary import setup_weekly_scheduler
    setup_weekly_scheduler(bot, get_all_user_ids)

    scheduler.start()
    logging.info("Wingman v3.9 started")

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
