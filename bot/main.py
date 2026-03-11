import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Dispatcher

load_dotenv()

from bot.config import bot, storage, scheduler
from bot.handlers import survey, common, evening_handler
from bot.scheduler_logic import setup_scheduler
from core.database import init_db

# ── ПЛАГИНЫ (подключаются независимо) ─────────────────────────────────
from plugins.idea_factory import router as idea_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


async def main():
    init_db()

    dp = Dispatcher(storage=storage)

    # Порядок важен: survey первым
    dp.include_router(survey.router)
    dp.include_router(evening_handler.router)
    dp.include_router(idea_router)      # плагин Idea Factory
    dp.include_router(common.router)   # common последним (ловит F.text)

    setup_scheduler()
    scheduler.start()
    logging.info("Wingman v3 started")

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
