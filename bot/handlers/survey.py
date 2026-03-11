from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.database import MemoryManager
from bot.scheduler_logic import setup_user_jobs

router = Router()


class Survey(StatesGroup):
    age = State()
    goal = State()
    budget = State()
    hobby = State()
    wake_up_time = State()
    bedtime = State()


@router.message(F.text.casefold() == "анкета")
@router.message(Command("survey"))
async def start_survey(message: types.Message, state: FSMContext):
    await state.set_state(Survey.age)
    await message.answer("Настройка персонального ассистента 🛠\n\nСколько тебе лет?")


@router.message(Survey.age)
async def s_age(m: types.Message, state: FSMContext):
    await state.update_data(age=m.text)
    await state.set_state(Survey.goal)
    await m.answer("Какая главная цель?\n(например: Похудение, Продуктивность, Баланс)")


@router.message(Survey.goal)
async def s_goal(m: types.Message, state: FSMContext):
    await state.update_data(goal=m.text)
    await state.set_state(Survey.budget)
    await m.answer("Примерный бюджет на день (в рублях)?")


@router.message(Survey.budget)
async def s_budget(m: types.Message, state: FSMContext):
    await state.update_data(budget=m.text)
    await state.set_state(Survey.hobby)
    await m.answer("Главные хобби? (через запятую)")


@router.message(Survey.hobby)
async def s_hobby(m: types.Message, state: FSMContext):
    await state.update_data(hobby=m.text)
    await state.set_state(Survey.wake_up_time)
    await m.answer("⏰ Во сколько обычно просыпаешься? (например: 07:00)")


@router.message(Survey.wake_up_time)
async def s_wake(m: types.Message, state: FSMContext):
    await state.update_data(wake_up_time=m.text)
    await state.set_state(Survey.bedtime)
    await m.answer("🌙 Во сколько ложишься спать? (например: 23:00)")


@router.message(Survey.bedtime)
async def s_final(m: types.Message, state: FSMContext):
    data = await state.get_data()
    data["bedtime"] = m.text

    db = MemoryManager(m.from_user.id)
    db.save_profile(data)

    setup_user_jobs(m.from_user.id, data["wake_up_time"], data["bedtime"])

    await state.clear()
    await m.answer(
        "✅ Профиль настроен!\n\n"
        "Утром пришлю план дня, вечером сверимся.\n"
        "Напиши что угодно — я всегда на связи."
    )
