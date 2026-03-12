import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()

from bot.config import bot, storage, scheduler
from bot.handlers import survey, common, evening_handler
from bot.handlers.diet_mode_handler import router as diet_mode_router
from bot.scheduler_logic import setup_scheduler, setup_nightly_patterns, setup_healer_scheduler
from core.database import init_db
from core.pattern_cache import init_pattern_tables
from plugins.idea_factory import router as idea_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


async def main():
    init_db()
    init_pattern_tables()

    from aiogram import Dispatcher
    dp = Dispatcher(storage=storage)

    from bot.handlers import healer_handler
    from bot.handlers import travel_handler
    dp.include_router(survey.router)
    dp.include_router(evening_handler.router)
    dp.include_router(diet_mode_router)
    dp.include_router(idea_router)
    dp.include_router(healer_handler.router)
    dp.include_router(travel_handler.router)
    dp.include_router(common.router)

    setup_scheduler()
    setup_nightly_patterns()
    setup_healer_scheduler(bot)   # 🔧 Self-Healing

    # Weekly Summary Agent
    from core.weekly_summary import setup_weekly_scheduler
    from core.database import get_all_user_ids
    setup_weekly_scheduler(bot, get_all_user_ids)

    scheduler.start()
    logging.info("Wingman v3.5 started — Multi-Agent + Travel + Weekly")

    # Регистрируем команды в меню Telegram
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="plan",      description="Мой план на сегодня"),
        BotCommand(command="profile",   description="Мой прогресс и статус"),
        BotCommand(command="streak",    description="Серия дней"),
        BotCommand(command="weight",    description="Записать вес"),
        BotCommand(command="progress",  description="График веса"),
        BotCommand(command="morning",   description="Утренний настрой"),
        BotCommand(command="shopping",  description="Список покупок"),
        BotCommand(command="fridge",    description="Что приготовить"),
        BotCommand(command="recipes",   description="Мои рецепты"),
        BotCommand(command="mode",      description="Режим питания"),
        BotCommand(command="survey",    description="Пройти анкету заново"),
        BotCommand(command="healer",    description="🔧 Лечилка (только admin)"),
        BotCommand(command="travel",    description="✈️ Планировщик путешествий"),
    ])

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
