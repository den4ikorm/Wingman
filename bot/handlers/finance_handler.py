# -*- coding: utf-8 -*-
"""
bot/handlers/finance_handler.py
FinanceAgent handler — цели, расходы, чеки.
"""

import logging
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database import MemoryManager

logger = logging.getLogger(__name__)
router = Router()


class FinanceStates(StatesGroup):
    adding_goal_title  = State()
    adding_goal_amount = State()
    adding_goal_date   = State()
    adding_income      = State()
    adding_expense_cat = State()
    adding_expense_amt = State()
    waiting_receipt    = State()


# ── /finance — главное меню ───────────────────────────────────────────────

@router.message(Command("finance"), StateFilter(default_state))
@router.message(F.text.in_({"💰 Финансы", "💸 Финансы"}), StateFilter(default_state))
async def cmd_finance(message: types.Message):
    user_id = message.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent
    agent = FinanceAgent(user_id, db.get_profile() or {})

    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Мои цели", callback_data="fin_goals")
    kb.button(text="📊 За этот месяц", callback_data="fin_month")
    kb.button(text="➕ Добавить доход", callback_data="fin_add_income")
    kb.button(text="➖ Добавить расход", callback_data="fin_add_expense")
    kb.button(text="📸 Сфотографировать чек", callback_data="fin_receipt")
    kb.button(text="🤖 Анализ и советы", callback_data="fin_analysis")
    kb.adjust(2)

    await message.answer(
        "💰 *Финансы*\n\nЧто делаем?",
        parse_mode="Markdown", reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "fin_goals")
async def cb_goals(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent
    agent = FinanceAgent(user_id, db.get_profile() or {})

    text = agent.goals_summary()
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новая цель", callback_data="fin_new_goal")
    goals = agent.get_goals()
    for g in goals[:3]:
        kb.button(text=f"📥 Внести в «{g['title'][:15]}»", callback_data=f"fin_contrib_{g['id']}")
    kb.adjust(1)
    await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "fin_month")
async def cb_month(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent
    agent = FinanceAgent(user_id, db.get_profile() or {})
    text = agent.month_summary()
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 Советы по экономии", callback_data="fin_analysis")
    await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "fin_analysis")
async def cb_analysis(cb: types.CallbackQuery):
    await cb.message.edit_text("🤖 Анализирую расходы... ⏳")
    await cb.answer()
    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent
    agent = FinanceAgent(user_id, db.get_profile() or {})
    try:
        result = await agent.get_analysis()
        await cb.message.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"finance analysis error: {e}")
        await cb.message.edit_text("⚠️ Не смог проанализировать, попробуй позже.")


# ── Добавить доход ────────────────────────────────────────────────────────

@router.callback_query(F.data == "fin_add_income")
async def cb_add_income(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(FinanceStates.adding_income)
    await cb.message.edit_text(
        "💚 *Доход*\n\nНапиши сумму и что это:\n`15000 зарплата`\n`3500 фриланс`",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.message(FinanceStates.adding_income)
async def s_add_income(m: types.Message, state: FSMContext):
    import re
    nums = re.findall(r'\d+[\.,]?\d*', m.text)
    if not nums:
        return await m.answer("Напиши число — например: `15000`", parse_mode="Markdown")

    amount = float(nums[0].replace(',', '.'))
    text_lower = m.text.lower()
    category = "freelance" if any(w in text_lower for w in ["фриланс", "подработк", "проект"]) else "salary"
    note = m.text.strip()

    user_id = m.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent
    FinanceAgent(user_id, db.get_profile() or {}).add_income(amount, category, note)
    await state.clear()
    await m.answer(f"✅ Записал доход: {amount:.0f}₽")


# ── Добавить расход ───────────────────────────────────────────────────────

@router.callback_query(F.data == "fin_add_expense")
async def cb_add_expense(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(FinanceStates.adding_expense_cat)
    from core.finance_agent import EXPENSE_CATEGORIES
    kb = InlineKeyboardBuilder()
    for key, (emoji, label) in EXPENSE_CATEGORIES.items():
        kb.button(text=f"{emoji} {label}", callback_data=f"fcat_{key}")
    kb.adjust(2)
    await cb.message.edit_text(
        "🔴 *Расход*\n\nКатегория?",
        parse_mode="Markdown", reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data.startswith("fcat_"), FinanceStates.adding_expense_cat)
async def cb_expense_cat(cb: types.CallbackQuery, state: FSMContext):
    cat = cb.data.replace("fcat_", "")
    await state.update_data(expense_cat=cat)
    await state.set_state(FinanceStates.adding_expense_amt)
    await cb.message.edit_text(
        "🔴 *Расход*\n\nСколько? Напиши сумму:\n`450`",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.message(FinanceStates.adding_expense_amt)
async def s_expense_amt(m: types.Message, state: FSMContext):
    import re
    nums = re.findall(r'\d+[\.,]?\d*', m.text)
    if not nums:
        return await m.answer("Напиши число — например: `450`", parse_mode="Markdown")

    amount = float(nums[0].replace(',', '.'))
    data = await state.get_data()
    cat = data.get("expense_cat", "other")

    user_id = m.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent, EXPENSE_CATEGORIES
    FinanceAgent(user_id, db.get_profile() or {}).add_expense(amount, cat, m.text.strip())
    await state.clear()
    emoji, label = EXPENSE_CATEGORIES.get(cat, ("📦", cat))
    await m.answer(f"✅ Записал расход: {amount:.0f}₽ ({emoji} {label})")


# ── Новая цель ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "fin_new_goal")
async def cb_new_goal(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(FinanceStates.adding_goal_title)
    await cb.message.edit_text(
        "🎯 *Новая финансовая цель*\n\nНапиши название цели:\n`Отпуск в Сочи`\n`Новый телефон`\n`Подушка безопасности`",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.message(FinanceStates.adding_goal_title)
async def s_goal_title(m: types.Message, state: FSMContext):
    await state.update_data(goal_title=m.text.strip())
    await state.set_state(FinanceStates.adding_goal_amount)
    await m.answer(
        f"🎯 *{m.text.strip()}*\n\nНа сколько копить? Напиши сумму:\n`80000`",
        parse_mode="Markdown"
    )


@router.message(FinanceStates.adding_goal_amount)
async def s_goal_amount(m: types.Message, state: FSMContext):
    import re
    nums = re.findall(r'\d+', m.text)
    if not nums:
        return await m.answer("Напиши сумму числом — например: `80000`", parse_mode="Markdown")
    await state.update_data(goal_amount=int(nums[0]))
    await state.set_state(FinanceStates.adding_goal_date)
    await m.answer(
        "📅 До какого числа нужно накопить?\nНапиши дату или *нет* если без срока:\n`2025-07-01` или `июль 2025`",
        parse_mode="Markdown"
    )


@router.message(FinanceStates.adding_goal_date)
async def s_goal_date(m: types.Message, state: FSMContext):
    import re
    data = await state.get_data()
    title = data.get("goal_title", "Цель")
    amount = data.get("goal_amount", 0)

    # Парсим дату
    deadline = None
    text = m.text.strip().lower()
    if text not in ("нет", "no", "-", "без срока"):
        # Пробуем ISO
        iso = re.search(r'(\d{4}-\d{2}-\d{2})', m.text)
        if iso:
            deadline = iso.group(1)
        else:
            # Пробуем "июль 2025"
            months = {"январ": "01","феврал": "02","март": "03","апрел": "04",
                      "май": "05","мая": "05","июн": "06","июл": "07",
                      "август": "08","сентябр": "09","октябр": "10",
                      "ноябр": "11","декабр": "12"}
            year = re.search(r'20\d{2}', m.text)
            if year:
                yr = year.group(0)
                for key, mn in months.items():
                    if key in text:
                        deadline = f"{yr}-{mn}-01"
                        break

    user_id = m.from_user.id
    db = MemoryManager(user_id)
    from core.finance_agent import FinanceAgent

    goal_id = FinanceAgent(user_id, db.get_profile() or {}).add_goal(
        title=title, target=amount, deadline=deadline
    )
    await state.clear()
    dl_str = f" к {deadline}" if deadline else ""
    await m.answer(
        f"✅ Цель создана!\n\n"
        f"🎯 *{title}*\n"
        f"Накопить: {amount:,}₽{dl_str}\n\n"
        f"Используй /finance → 📥 Внести чтобы отслеживать прогресс.",
        parse_mode="Markdown"
    )


# ── Взнос в цель ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("fin_contrib_"))
async def cb_contrib(cb: types.CallbackQuery, state: FSMContext):
    goal_id = int(cb.data.split("_")[-1])
    await state.update_data(contrib_goal_id=goal_id)
    await cb.message.answer(
        "💰 Сколько вносишь сейчас?\n`5000`",
        parse_mode="Markdown"
    )
    await cb.answer()
    # Принимаем следующее сообщение как сумму
    await state.set_state(FinanceStates.adding_income)  # reuse


# ── Фото чека ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "fin_receipt")
async def cb_receipt_start(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(FinanceStates.waiting_receipt)
    await cb.message.edit_text(
        "📸 *Фото чека*\n\n"
        "Сфотографируй чек и отправь мне.\n"
        "_Чем чётче фото — тем точнее распознавание_",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.message(FinanceStates.waiting_receipt, F.photo)
async def handle_receipt_photo(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("📸 Распознаю чек... ⏳")

    user_id = m.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}

    try:
        # Скачиваем фото
        photo = m.photo[-1]  # максимальный размер
        file = await m.bot.get_file(photo.file_id)
        photo_bytes = await m.bot.download_file(file.file_path)
        photo_data = photo_bytes.read() if hasattr(photo_bytes, 'read') else bytes(photo_bytes)

        from core.receipt_agent import ReceiptAgent
        agent = ReceiptAgent(user_id, profile)
        result = await agent.parse_photo(photo_data)

        if not result.get("ok"):
            return await m.answer(
                f"⚠️ Не удалось распознать чек.\n{result.get('error','')}\n\n"
                "Попробуй сфотографировать чётче при хорошем освещении."
            )

        data = result["data"]
        text = agent.format_receipt(data)

        # Кнопки подтверждения
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Верно, сохранить", callback_data="receipt_save")
        kb.button(text="❌ Отмена", callback_data="receipt_cancel")
        kb.adjust(2)

        await m.answer(text, parse_mode="Markdown", reply_markup=kb.as_markup())
        # Сохраняем данные в state для подтверждения
        await state.update_data(receipt_data=data)

    except Exception as e:
        logger.error(f"receipt photo error: {e}")
        await m.answer("⚠️ Ошибка при обработке фото. Попробуй ещё раз.")


@router.callback_query(F.data == "receipt_save")
async def cb_receipt_save(cb: types.CallbackQuery, state: FSMContext):
    fsm_data = await state.get_data()
    receipt_data = fsm_data.get("receipt_data")
    await state.clear()

    if not receipt_data:
        return await cb.answer("Данные утеряны, попробуй снова")

    user_id = cb.from_user.id
    db = MemoryManager(user_id)
    profile = db.get_profile() or {}

    from core.receipt_agent import ReceiptAgent
    agent = ReceiptAgent(user_id, profile)
    receipt_id = agent.save(receipt_data)

    # Синхронизация со списком покупок
    checked = agent.sync_with_shopping_list(receipt_data.get("items", []), db)
    checked_str = ""
    if checked:
        checked_str = f"\n\n✅ Вычеркнул из списка покупок:\n" + "\n".join(f"• {i}" for i in checked[:5])

    # Добавляем расход
    total = receipt_data.get("total", 0)
    if total > 0:
        from core.finance_agent import FinanceAgent
        FinanceAgent(user_id, profile).add_expense(total, "food", receipt_data.get("store", "магазин"))

    await cb.message.edit_text(
        f"✅ Чек сохранён! (#{receipt_id})\n"
        f"Расход {total:.0f}₽ записан в финансы.{checked_str}",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.callback_query(F.data == "receipt_cancel")
async def cb_receipt_cancel(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.answer()
