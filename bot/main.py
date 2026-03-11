import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Dispatcher

load_dotenv()

from bot.config import bot, storage, scheduler
from bot.handlers import survey, common, evening_handler
from bot.scheduler_logic import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


async def main():
    dp = Dispatcher(storage=storage)

    # Порядок важен: survey имеет высший приоритет
    dp.include_router(survey.router)
    dp.include_router(evening_handler.router)
    dp.include_router(common.router)

    setup_scheduler()
    scheduler.start()
    logging.info("Scheduler started")

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Dietolog v2 bot started")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
