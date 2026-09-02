from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.keyboards import choices_keyboard, days_keyboard, frequency_keyboard, menu_keyboard
from app.states import Onboarding

CONSECUTIVE_DAYS_WARNING = (
    "Все три тренировки нагружают ноги и ягодицы. Лучше оставить между ними день "
    "восстановления, например Пн–Ср–Пт."
)


def has_consecutive_days(days: list[int]) -> bool:
    selected = set(days)
    return any((day + 1) % 7 in selected for day in selected)


def valid_workout_time(value: str) -> bool:
    try:
        parsed = time.fromisoformat(value.strip())
    except ValueError:
        return False
    return time(8, 0) <= parsed <= time(22, 0)


def build_start_router(context: AppContext) -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        assert message.from_user is not None
        user = await context.users.get_or_create(message.from_user.id)
        if user.onboarding_complete:
            await state.clear()
            await message.answer(
                f"Рада тебя видеть, {user.display_name or 'друг'}! Что сделаем?",
                reply_markup=menu_keyboard(context.settings.show_reset_button),
            )
            return
        await state.set_state(Onboarding.name)
        await message.answer(
            "Привет! Я помогу спокойно вернуть регулярность тренировок — без давления и чувства вины.\n\nКак тебя называть?"
        )

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Текущий ввод отменён.",
            reply_markup=menu_keyboard(context.settings.show_reset_button),
        )

    @router.message(Onboarding.name, F.text)
    async def receive_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not 1 <= len(name) <= 100:
            await message.answer("Напиши короткое имя — до 100 символов.")
            return
        await state.update_data(name=name, days=[0, 2, 4])
        await state.set_state(Onboarding.days)
        await message.answer(
            "В какие дни удобно заниматься? Можно выбрать несколько.",
            reply_markup=days_keyboard([0, 2, 4]),
        )

    @router.callback_query(Onboarding.days, F.data.startswith("onboarding:day:"))
    async def toggle_day(callback: CallbackQuery, state: FSMContext) -> None:
        day = int((callback.data or "").rsplit(":", 1)[1])
        data = await state.get_data()
        days = set(data.get("days", []))
        if day in days:
            days.remove(day)
        else:
            days.add(day)
        selected = sorted(days)
        await state.update_data(days=selected)
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=days_keyboard(selected))
        await callback.answer()

    @router.callback_query(Onboarding.days, F.data == "onboarding:days_done")
    async def days_done(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if not data.get("days"):
            await callback.answer("Выбери хотя бы один день.", show_alert=True)
            return
        if has_consecutive_days(data["days"]) and callback.message:
            await callback.message.answer(CONSECUTIVE_DAYS_WARNING)
        await state.set_state(Onboarding.workout_time)
        if callback.message:
            await callback.message.answer("Во сколько обычно удобно? Напиши в формате 19:00.")
        await callback.answer()

    @router.message(Onboarding.workout_time, F.text)
    async def receive_time(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not valid_workout_time(value):
            await message.answer("Напиши время как 19:00. Допустимый диапазон — с 08:00 до 22:00.")
            return
        normalized = time.fromisoformat(value).strftime("%H:%M")
        data = await state.get_data()
        selected_count = len(data.get("days", []))
        await state.update_data(workout_time=normalized)
        await state.set_state(Onboarding.frequency)
        await message.answer(
            f"Сколько тренировок в неделю? Сейчас выбрано дней: {selected_count}.",
            reply_markup=frequency_keyboard(),
        )

    @router.callback_query(Onboarding.frequency, F.data.startswith("onboarding:frequency:"))
    async def receive_frequency(callback: CallbackQuery, state: FSMContext) -> None:
        frequency = int((callback.data or "").rsplit(":", 1)[1])
        data = await state.get_data()
        if frequency != len(data.get("days", [])):
            await callback.answer(
                f"Выбрано дней: {len(data.get('days', []))}. Укажи такую же частоту.",
                show_alert=True,
            )
            return
        await state.update_data(workouts_per_week=frequency)
        await state.set_state(Onboarding.place)
        if callback.message:
            await callback.message.answer(
                "Где занимаешься?",
                reply_markup=choices_keyboard(
                    "onboarding:place", (("В зале", "gym"), ("Дома", "home"))
                ),
            )
        await callback.answer()

    @router.callback_query(Onboarding.place, F.data.startswith("onboarding:place:"))
    async def receive_place(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(place=(callback.data or "").rsplit(":", 1)[1])
        await state.set_state(Onboarding.goal)
        if callback.message:
            await callback.message.answer(
                "Какая основная цель?",
                reply_markup=choices_keyboard(
                    "onboarding:goal",
                    (
                        ("Вернуть регулярность", "regularity"),
                        ("Улучшить форму", "form"),
                        ("Увеличить силу", "strength"),
                        ("Похудеть без крайностей", "weight_loss"),
                    ),
                ),
            )
        await callback.answer()

    @router.callback_query(Onboarding.goal, F.data.startswith("onboarding:goal:"))
    async def receive_goal(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(goal=(callback.data or "").rsplit(":", 1)[1])
        await state.set_state(Onboarding.experience)
        if callback.message:
            await callback.message.answer(
                "Какой у тебя опыт?",
                reply_markup=choices_keyboard(
                    "onboarding:experience",
                    (
                        ("Новичок", "beginner"),
                        ("Занималась раньше", "returning"),
                        ("Занимаюсь регулярно", "regular"),
                    ),
                ),
            )
        await callback.answer()

    @router.callback_query(
        Onboarding.experience, F.data.startswith("onboarding:experience:")
    )
    async def receive_experience(callback: CallbackQuery, state: FSMContext) -> None:
        assert callback.from_user is not None
        data = await state.get_data()
        data["experience"] = (callback.data or "").rsplit(":", 1)[1]
        user = await context.users.complete_onboarding(
            callback.from_user.id,
            name=data["name"],
            days=data["days"],
            workout_time=data["workout_time"],
            workouts_per_week=data["workouts_per_week"],
            place=data["place"],
            goal=data["goal"],
            experience=data["experience"],
        )
        await context.reminders.rebuild_user_reminders(user.id)
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Готово. Главная цель — 10 тренировок за 30 дней. Пропуски не обнуляют общий прогресс.",
                reply_markup=menu_keyboard(context.settings.show_reset_button),
            )
        await callback.answer()

    return router
