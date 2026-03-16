# -*- coding: utf-8 -*-
"""
bot/handlers/lifemode_handler.py
LifeMode handler — выбор и управление режимом жизни.
"""

import logging
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import default_state
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager

logger = logging.getLogger(__name__)
router = Router()

MODES_MENU = [
    ("🔥 Сушка", "cut"), ("💪 Набор массы", "bulk"),
    ("❤️ Здоровье", "health"), ("⚡ Энергия", "energy"),
    ("🧘 Детокс", "detox"), ("✈️ Отпуск / цель", "vacation"),
]

CONTROL_MENU = [
    ("🌿 Мягкий", "soft"), ("⚖️ Умеренный", "moderate"), ("🔒 Жёсткий", "strict"),
]


@router.message(Command("lifemode"), StateFilter(default_state))
@router.message(F.text.in_({"🎯 LifeMode", "🎯 Режим"}), StateFilter(default_state))
async def cmd_lifemode(message: types.Message):
    user_id = message.from_user.id

    from core.lifemode_agent import LifeModeAgent
    lm = LifeModeAgent(user_id)

    kb = InlineKeyboardBuilder()
    for label, key in MODES_MENU:
        kb.button(text=label, callback_data=f"lm_set_{key}")
    kb.button(text="📊 Текущий статус", callback_data="lm_status")
    kb.adjust(2)

    await message.answer(
        f"🎯 *LifeMode*\n\n"
        f"Текущий режим: {lm.label()}\n\n"
        f"Выбери новый режим:",
        parse_mode="Markdown",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("lm_set_"))
async def cb_set_mode(cb: types.CallbackQuery):
    mode = cb.data.replace("lm_set_", "")

    kb = InlineKeyboardBuilder()
    for label, ctrl in CONTROL_MENU:
        kb.button(text=label, callback_data=f"lm_ctrl_{mode}_{ctrl}")
    kb.adjust(3)

    await cb.message.edit_text(
        f"🎯 Выбран режим.\n\nУровень контроля?\n\n"
        f"🌿 *Мягкий* — только советы\n"
        f"⚖️ *Умеренный* — замечу отклонения\n"
        f"🔒 *Жёсткий* — активно возвращаю к цели",
        parse_mode="Markdown",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lm_ctrl_"))
async def cb_set_control(cb: types.CallbackQuery):
    parts = cb.data.split("_")
    # lm_ctrl_cut_soft → parts = ['lm', 'ctrl', 'cut', 'soft']
    mode = parts[2]
    ctrl = parts[3]

    user_id = cb.from_user.id
    from core.lifemode_agent import LifeModeAgent
    lm = LifeModeAgent(user_id)
    lm.set(mode, ctrl)

    await cb.message.edit_text(
        lm.status_text() + "\n\n✅ Режим активирован! Все агенты перестроены.",
        parse_mode="Markdown"
    )
    await cb.answer("Режим активирован!")


@router.callback_query(F.data == "lm_status")
async def cb_status(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    from core.lifemode_agent import LifeModeAgent
    lm = LifeModeAgent(user_id)
    await cb.message.edit_text(lm.status_text(), parse_mode="Markdown")
    await cb.answer()
