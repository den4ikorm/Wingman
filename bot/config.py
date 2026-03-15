import os
import logging
from dotenv import load_dotenv
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import timezone

load_dotenv()

TOKEN    = os.getenv("TELEGRAM_TOKEN")
BASE_DIR = os.getenv("BASE_DIR", "./data")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
REDIS_URL  = os.getenv("REDIS_URL", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")  # URL задеплоенного webapp.html на Railway

# ── FSM STORAGE ─────────────────────────────────────────────────────────────
# Если задан REDIS_URL — используем Redis (состояние анкеты выживает рестарт).
# Иначе — MemoryStorage (локальная разработка).
if REDIS_URL:
    try:
        from aiogram.fsm.storage.redis import RedisStorage
        storage = RedisStorage.from_url(REDIS_URL)
        logging.info("FSM storage: Redis ✅")
    except ImportError:
        logging.warning("aiogram-redis не установлен, падаю на MemoryStorage")
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
else:
    from aiogram.fsm.storage.memory import MemoryStorage
    storage = MemoryStorage()
    logging.warning("FSM storage: Memory (анкета сбрасывается при рестарте!)")

bot       = Bot(token=TOKEN)
scheduler = AsyncIOScheduler(timezone=timezone.utc)
