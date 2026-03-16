"""
bot/main.py — Wingman v4.0
Multi-Agent: LifeMode + ContentAgent + FinanceAgent + ReceiptAgent + Travel + Psychology
"""
import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()

from bot.config import bot, storage, scheduler
from bot.handlers import survey, common, evening_handler
from bot.handlers.diet_mode_handler import router as diet_mode_router
from bot.keyboard_manager import nav_router
from bot.scheduler_logic import setup_scheduler, setup_nightly_patterns, setup_healer_scheduler
from core.database import init_db
from core.pattern_cache import init_pattern_tables
from core.db_extensions import init_extensions
from plugins.idea_factory import router as idea_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


async def main():
    init_db()
    init_pattern_tables()
    init_extensions()

    from aiogram import Dispatcher
    dp = Dispatcher(storage=storage)

    from bot.handlers import healer_handler, travel_handler
    from bot.handlers import content_handler, finance_handler, lifemode_handler

    dp.include_router(survey.router)
    dp.include_router(nav_router)
    dp.include_router(evening_handler.router)
    dp.include_router(diet_mode_router)
    dp.include_router(idea_router)
    dp.include_router(healer_handler.router)
    dp.include_router(travel_handler.router)
    dp.include_router(content_handler.router)
    dp.include_router(finance_handler.router)
    dp.include_router(lifemode_handler.router)
    dp.include_router(common.router)

    setup_scheduler()
    setup_nightly_patterns()
    setup_healer_scheduler(bot)

    from core.weekly_summary import setup_weekly_scheduler
    from core.database import get_all_user_ids
    setup_weekly_scheduler(bot, get_all_user_ids)

    scheduler.start()
    logging.info("Wingman v4.0 — LifeMode + ContentAgent + FinanceAgent + ReceiptAgent")

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start",    description="Главное меню"),
        BotCommand(command="lifemode", description="🎯 Режим жизни"),
        BotCommand(command="plan",     description="📋 План на сегодня"),
        BotCommand(command="movie",    description="🎬 Посоветуй фильм"),
        BotCommand(command="music",    description="🎵 Музыка под настроение"),
        BotCommand(command="books",    description="📚 Книги"),
        BotCommand(command="finance",  description="💰 Финансы и цели"),
        BotCommand(command="weight",   description="⚖️ Записать вес"),
        BotCommand(command="progress", description="📊 Прогресс"),
        BotCommand(command="shopping", description="🛒 Список покупок"),
        BotCommand(command="travel",   description="✈️ Планировщик путешествий"),
        BotCommand(command="survey",   description="📝 Анкета заново"),
        BotCommand(command="profile",  description="👤 Мой профиль"),
    ])

    await bot.delete_webhook(drop_pending_updates=True)

    # Ждём секунду чтобы старый инстанс успел завершиться
    import asyncio as _asyncio
    await _asyncio.sleep(2)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
