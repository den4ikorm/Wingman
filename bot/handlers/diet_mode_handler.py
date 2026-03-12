"""
bot/handlers/diet_mode_handler.py
════════════════════════════════════════════════════════
Хендлеры «Живого режима»:
  /mode          — показать текущий режим
  /mode 1-5      — сменить уровень
  /setmode       — выбор уровня с кнопками
  /psychotype    — выбор психотипа
  /event [текст] — событие сегодня
  /morning       — утреннее настроение (эмодзи)
  /streak        — стрик с жизнями
════════════════════════════════════════════════════════
"""

import asyncio
import logging
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import default_state
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager
from core.diet_mode import (
    DietModeManager, LEVELS, PSYCHOTYPES,
    suggest_level, get_all_levels_text, get_psychotypes_text,
    MORNING_MOODS,
)

router = Router()
logger = logging.getLogger(__name__)


# ── /mode — показать или сменить уровень ───────────────────────────────────

@router.message(Command("mode"))
async def cmd_mode(message: types.Message):
    user_id = message.from_user.id
    db      = MemoryManager(user_id)
    profile = db.get_profile()

    if not profile:
        return await message.answer(
            "Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown"
        )

    parts = message.text.split(maxsplit=1)

    # /mode без аргумента — показываем текущий
    if len(parts) == 1:
        mgr      = DietModeManager(profile)
        lvl_info = mgr.get_level_info()
        psycho   = PSYCHOTYPES.get(profile.get("psychotype", "disciplined"), "")
        season   = mgr.get_current_season()
        weekend  = "да 🎉" if mgr.is_weekend() else "нет"

        kb = InlineKeyboardBuilder()
        for lvl in LEVELS:
            mark = "✅ " if lvl == mgr.level else ""
            kb.button(text=f"{mark}{LEVELS[lvl]['name']}", callback_data=f"setmode_{lvl}")
        kb.adjust(1)

        await message.answer(
            f"*Твой текущий режим:*\n\n"
            f"{lvl_info['name']} (уровень {mgr.level}/5)\n"
            f"_{lvl_info['desc']}_\n\n"
            f"🧠 Психотип: {psycho}\n"
            f"🌿 Сезон: {season}\n"
            f"📅 Выходной: {weekend}\n\n"
            f"Нажми чтобы сменить:",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
        )
        return

    # /mode 3 — сменить уровень
    try:
        new_level = int(parts[1].strip())
        if new_level not in LEVELS:
            raise ValueError
    except ValueError:
        return await message.answer("Укажи уровень от 1 до 5. Например: /mode 3")

    db.save_profile({"diet_level": new_level})
    info = LEVELS[new_level]
    await message.answer(
        f"✅ Режим изменён!\n\n"
        f"*{info['name']}*\n_{info['desc']}_\n\n"
        f"Строгость: {info['strictness']}",
        parse_mode="Markdown",
    )


# ── Callback: кнопки выбора уровня ────────────────────────────────────────

@router.callback_query(F.data.startswith("setmode_"), StateFilter(default_state))
async def cb_setmode(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    db      = MemoryManager(user_id)
    profile = db.get_profile()

    new_level = int(cb.data.split("_")[1])
    psycho    = profile.get("psychotype", "disciplined")

    # Предупреждение для психотипа
    from core.diet_mode import PSYCHOTYPE_ADJUSTMENTS
    adj     = PSYCHOTYPE_ADJUSTMENTS.get(psycho, {})
    max_lvl = adj.get("max_level", 5)
    warning = ""
    if new_level > max_lvl and adj.get("note"):
        warning = f"\n\n⚠️ {adj['note']}"

    db.save_profile({"diet_level": new_level})
    info = LEVELS[new_level]

    await cb.message.edit_text(
        f"✅ *Режим установлен:* {info['name']}\n"
        f"_{info['desc']}_"
        f"{warning}",
        parse_mode="Markdown",
    )
    await cb.answer()


# ── /psychotype — выбор психотипа ─────────────────────────────────────────

@router.message(Command("psychotype"))
async def cmd_psychotype(message: types.Message):
    kb = InlineKeyboardBuilder()
    for key, desc in PSYCHOTYPES.items():
        kb.button(text=desc, callback_data=f"psycho_{key}")
    kb.adjust(1)

    await message.answer(
        get_psychotypes_text() + "\n\nВыбери свой тип:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("psycho_"), StateFilter(default_state))
async def cb_psychotype(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    db      = MemoryManager(user_id)
    psycho  = cb.data.split("_", 1)[1]

    db.save_profile({"psychotype": psycho})

    # После выбора психотипа — предлагаем оптимальный уровень
    profile    = db.get_profile()
    sugg_level, explanation = suggest_level(profile)

    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Принять уровень {sugg_level}", callback_data=f"setmode_{sugg_level}")
    kb.button(text="🔧 Выбрать вручную", callback_data="show_levels")
    kb.adjust(1)

    await cb.message.edit_text(
        f"✅ Психотип сохранён: {PSYCHOTYPES[psycho]}\n\n"
        f"💡 {explanation}",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )
    await cb.answer()


@router.callback_query(F.data == "show_levels")
async def cb_show_levels(cb: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    for lvl, info in LEVELS.items():
        kb.button(text=f"{info['name']}", callback_data=f"setmode_{lvl}")
    kb.adjust(1)
    await cb.message.edit_text(
        get_all_levels_text(),
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )
    await cb.answer()


# ── /morning — утреннее настроение ────────────────────────────────────────

@router.message(Command("morning"))
async def cmd_morning(message: types.Message):
    kb = InlineKeyboardBuilder()
    for emoji, (key, desc) in MORNING_MOODS.items():
        kb.button(text=f"{emoji} {desc[:30]}...", callback_data=f"mood_{emoji}")
    kb.adjust(1)

    await message.answer(
        "☀️ *Как ты сегодня?*\n\nВыбери настроение — я подстрою план дня:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("mood_"))
async def cb_morning_mood(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    db      = MemoryManager(user_id)
    profile = db.get_profile()
    emoji   = cb.data.replace("mood_", "")

    mgr  = DietModeManager(profile)
    desc = mgr.set_morning_mood(emoji)
    db.save_profile({"morning_mood": profile.get("morning_mood", "neutral")})

    await cb.message.edit_text(
        f"{emoji} *{desc}*\n\n"
        f"План на сегодня скорректирован. Напиши /plan чтобы увидеть.",
        parse_mode="Markdown",
    )
    await cb.answer()


# ── /event — событие сегодня ──────────────────────────────────────────────

@router.message(Command("event"))
async def cmd_event(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(
            "Укажи событие. Примеры:\n"
            "/event день рождения подруги\n"
            "/event корпоратив\n"
            "/event еду в гости\n\n"
            "Бот учтёт это в плане и не будет считать отступление срывом."
        )

    event = parts[1].strip()
    db    = MemoryManager(message.from_user.id)
    db.save_profile({"today_event": event})

    await message.answer(
        f"📅 Событие записано: *{event}*\n\n"
        f"Сегодня план будет с поправкой на это. "
        f"Обновить план: /plan",
        parse_mode="Markdown",
    )


# ── /streak — стрик с жизнями ─────────────────────────────────────────────

@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    user_id = message.from_user.id
    db      = MemoryManager(user_id)
    profile = db.get_profile()

    if not profile:
        return await message.answer("Сначала заполни анкету — напиши *анкета*", parse_mode="Markdown")

    mgr      = DietModeManager(profile)
    history  = db.get_compliance_history()
    info     = mgr.calculate_streak_info(history)
    text     = mgr.format_streak_message(info)

    # Проверяем нужно ли менять уровень
    recent = [h.get("followed", False) for h in history[-5:]]
    suggestion = mgr.should_suggest_level_change(recent)

    if suggestion:
        text += f"\n\n💡 {suggestion}"

    await message.answer(text, parse_mode="Markdown")


# ── /setmode — полный выбор с описаниями ──────────────────────────────────

@router.message(Command("setmode"))
async def cmd_setmode(message: types.Message):
    user_id   = message.from_user.id
    db        = MemoryManager(user_id)
    profile   = db.get_profile()

    sugg_level, explanation = suggest_level(profile)

    kb = InlineKeyboardBuilder()
    for lvl, info in LEVELS.items():
        mark = "⭐ " if lvl == sugg_level else ""
        kb.button(text=f"{mark}{info['name']}", callback_data=f"setmode_{lvl}")
    kb.adjust(1)

    await message.answer(
        get_all_levels_text() +
        f"\n💡 *Для тебя рекомендуется:* {explanation}",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )
