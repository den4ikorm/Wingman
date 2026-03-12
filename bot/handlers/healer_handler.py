# -*- coding: utf-8 -*-
"""
bot/handlers/healer_handler.py
Telegram-обработчик для HealerAgent

Команды (только для ADMIN_ID):
  /healer status   — статус лечилки
  /healer history  — последние патчи
  /healer rollback — откатить последний патч
  /healer check    — запустить проверку вручную
  /healer disable  — выключить
  /healer enable   — включить

Кнопки:
  healer_approve_{log_id}_{pr_number}
  healer_reject_{log_id}
  healer_rollback
"""

import os
import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "7709651193"))

# Глобальный инстанс — инициализируется в main.py
_healer = None

def get_healer():
    return _healer

def set_healer(h):
    global _healer
    _healer = h


def admin_only(func):
    """Декоратор — только для администратора."""
    import functools
    @functools.wraps(func)
    async def wrapper(obj, *args, **kwargs):
        uid = obj.from_user.id if hasattr(obj, 'from_user') else None
        if uid != ADMIN_ID:
            return
        return await func(obj, *args, **kwargs)
    return wrapper


# ── КОМАНДЫ ───────────────────────────────────────────────────────────────────

@router.message(Command("healer"))
@admin_only
async def cmd_healer(message: types.Message):
    parts = message.text.split(maxsplit=1)
    sub   = parts[1].strip().lower() if len(parts) > 1 else "status"

    healer = get_healer()
    if not healer:
        return await message.answer("⚠️ HealerAgent не инициализирован.")

    if sub == "status":
        text = await healer.cmd_status()
        await message.answer(text, parse_mode="Markdown")

    elif sub == "history":
        text = await healer.cmd_history()
        await message.answer(text, parse_mode="Markdown")

    elif sub == "rollback":
        await message.answer("🔄 Выполняю откат...")
        await healer.rollback()

    elif sub == "check":
        await message.answer("🔍 Запускаю проверку логов...")
        await healer.run_check()

    elif sub == "disable":
        from bot.scheduler_logic import pause_healer
        pause_healer()
        await message.answer("⏸ Лечилка приостановлена.")

    elif sub == "enable":
        from bot.scheduler_logic import resume_healer
        resume_healer()
        await message.answer("▶️ Лечилка возобновлена.")

    else:
        await message.answer(
            "🔧 *HealerAgent команды:*\n\n"
            "/healer status — состояние\n"
            "/healer history — история патчей\n"
            "/healer check — проверить логи сейчас\n"
            "/healer rollback — откатить последний патч\n"
            "/healer disable — выключить\n"
            "/healer enable — включить",
            parse_mode="Markdown"
        )


# ── КНОПКИ ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("healer_approve_"))
@admin_only
async def cb_healer_approve(cb: types.CallbackQuery):
    """healer_approve_{log_id}_{pr_number}"""
    parts = cb.data.split("_")
    # healer_approve_123_456 → parts = ['healer','approve','123','456']
    try:
        log_id    = int(parts[2])
        pr_number = int(parts[3])
    except (IndexError, ValueError):
        return await cb.answer("Ошибка параметров")

    await cb.answer("⏳ Применяю патч...")
    await cb.message.edit_text(
        cb.message.text + "\n\n⏳ _Мёрджим PR..._",
        parse_mode="Markdown"
    )

    healer = get_healer()
    if healer:
        await healer.approve_patch(log_id, pr_number)
    else:
        await cb.message.answer("⚠️ HealerAgent недоступен")


@router.callback_query(F.data.startswith("healer_reject_"))
@admin_only
async def cb_healer_reject(cb: types.CallbackQuery):
    """healer_reject_{log_id}"""
    try:
        log_id = int(cb.data.split("_")[2])
    except (IndexError, ValueError):
        return await cb.answer("Ошибка параметров")

    await cb.answer("Патч отклонён")
    await cb.message.edit_text(
        cb.message.text + "\n\n❌ _Патч отклонён._",
        parse_mode="Markdown"
    )

    healer = get_healer()
    if healer:
        await healer.reject_patch(log_id)


@router.callback_query(F.data == "healer_rollback")
@admin_only
async def cb_healer_rollback(cb: types.CallbackQuery):
    await cb.answer("🔄 Откатываю...")
    await cb.message.edit_text(
        cb.message.text + "\n\n🔄 _Выполняю откат..._",
        parse_mode="Markdown"
    )
    healer = get_healer()
    if healer:
        await healer.rollback()
