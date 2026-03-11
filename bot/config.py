import os
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import timezone

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_DIR = os.getenv("BASE_DIR", "./data")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # твой Telegram user_id для фидбека

bot = Bot(token=TOKEN)
storage = MemoryStorage()
scheduler = AsyncIOScheduler(timezone=timezone.utc)
