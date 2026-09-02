from __future__ import annotations

import random
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.handlers.start import CONSECUTIVE_DAYS_WARNING, has_consecutive_days, valid_workout_time
from app.keyboards import days_keyboard, frequency_keyboard, menu_keyboard, settings_keyboard
from app.services.scheduler import utc_naive_to_local
from app.states import ScheduleEdit

NUTRITION_STEPS = (
    "Небольшой шаг на сегодня: добавь один нормальный белковый приём пищи. Без подсчёта калорий.",
    "Небольшой шаг на сегодня: поставь рядом воду и сделай несколько глотков сейчас.",
    "Небольшой шаг на сегодня: добавь овощи к одному привычному приёму пищи.",
    "Небольшой шаг на сегодня: не откладывай всю еду до вечера — выбери один спокойный приём пищи днём.",
)


def build_menu_router(context: AppContext) -> Router:
    router = Router(name="menu")

    @router.message(F.text == "📊 Мой прогресс")
    async def progress(message: Message) -> None:
        assert message.from_user is not None
        data = await context.progress.get(message.from_user.id)
        user = await context.users.get_by_telegram_id(message.from_user.id)
        timezone = user.settings.timezone if user and user.settings else context.settings.timezone
        filled = min(10, round(10 * data.month_completed / max(data.monthly_target, 1)))
        bar = "█" * filled + "░" * (10 - filled)
        last = (
            utc_naive_to_local(data.last_completed, timezone).strftime("%d.%m.%Y")
            if data.last_completed
            else "ещё не было"
        )
        next_workout = (
            utc_naive_to_local(data.next_workout, timezone).strftime("%d.%m.%Y, %H:%M")
            if data.next_workout
            else "не запланирована"
        )
        achievement_map = {
            "bronze_3": "🥉 3 тренировки",
            "silver_5": "🥈 5 тренировок",
            "gold_10": "🥇 10 тренировок",
        }
        achievements = ", ".join(achievement_map[code] for code in data.achievements) or "пока впереди"
        weekly_bar = "".join(
            "▁" if value == 0 else "▃" if value == 1 else "▆" if value == 2 else "█"
            for value in data.recent_weeks
        )
        weekly_values = " · ".join(str(value) for value in data.recent_weeks)
        await message.answer(
            "Мой прогресс\n\n"
            f"Цель месяца:\n{bar} {data.month_completed}/{data.monthly_target} тренировок\n\n"
            f"Тренировок за месяц: {data.month_completed}\n"
            f"Текущая серия: {data.streak}\n"
            f"Всего тренировок: {data.total_completed}\n"
            f"Последняя тренировка: {last}\n"
            f"Следующая: {next_workout}\n\n"
            f"Последние 6 недель: {weekly_bar}\n"
            f"По неделям: {weekly_values}\n\n"
            f"Достижения: {achievements}"
        )

    @router.message(F.text == "🥗 Небольшой шаг")
    async def nutrition_step(message: Message) -> None:
        await message.answer(random.choice(NUTRITION_STEPS))

    @router.message(F.text == "⚙️ Настройки")
    async def show_settings(message: Message) -> None:
        assert message.from_user is not None
        user = await context.users.get_by_telegram_id(message.from_user.id)
        enabled = bool(user and user.settings and user.settings.reminders_enabled)
        pause = ""
        if user and user.settings and user.settings.paused_until:
            pause = f"\nПауза до: {user.settings.paused_until.strftime('%d.%m.%Y %H:%M')} UTC"
        await message.answer(
            f"Настройки напоминаний.{pause}", reply_markup=settings_keyboard(enabled)
        )

    @router.callback_query(F.data == "settings:pause")
    async def pause(callback: CallbackQuery) -> None:
        await context.users.pause_for_week(callback.from_user.id)
        if callback.message:
            await callback.message.answer(
                "Напоминания поставлены на паузу на 7 дней. Общий прогресс сохранён."
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("settings:reminders:"))
    async def toggle_reminders(callback: CallbackQuery) -> None:
        enabled = (callback.data or "").endswith(":on")
        await context.users.set_reminders(callback.from_user.id, enabled)
        if callback.message:
            await callback.message.answer(
                "Напоминания включены." if enabled else "Напоминания отключены."
            )
        await callback.answer()

    @router.callback_query(F.data == "settings:schedule")
    async def edit_schedule(callback: CallbackQuery, state: FSMContext) -> None:
        user = await context.users.get_by_telegram_id(callback.from_user.id)
        selected = (
            [int(day) for day in user.settings.workout_days.split(",")]
            if user and user.settings
            else [0, 2, 4]
        )
        await state.set_state(ScheduleEdit.days)
        await state.update_data(days=selected)
        if callback.message:
            await callback.message.answer(
                "Выбери новые дни тренировок.",
                reply_markup=days_keyboard(selected, prefix="schedule"),
            )
        await callback.answer()

    @router.callback_query(ScheduleEdit.days, F.data.startswith("schedule:day:"))
    async def edit_toggle_day(callback: CallbackQuery, state: FSMContext) -> None:
        day = int((callback.data or "").rsplit(":", 1)[1])
        data = await state.get_data()
        days = set(data.get("days", []))
        days.remove(day) if day in days else days.add(day)
        selected = sorted(days)
        await state.update_data(days=selected)
        if callback.message:
            await callback.message.edit_reply_markup(
                reply_markup=days_keyboard(selected, prefix="schedule")
            )
        await callback.answer()

    @router.callback_query(ScheduleEdit.days, F.data == "schedule:days_done")
    async def edit_days_done(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if not data.get("days"):
            await callback.answer("Выбери хотя бы один день.", show_alert=True)
            return
        if has_consecutive_days(data["days"]) and callback.message:
            await callback.message.answer(CONSECUTIVE_DAYS_WARNING)
        await state.set_state(ScheduleEdit.workout_time)
        if callback.message:
            await callback.message.answer("Новое время в формате 19:00:")
        await callback.answer()

    @router.message(ScheduleEdit.workout_time, F.text)
    async def edit_time(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not valid_workout_time(value):
            await message.answer("Напиши время как 19:00, с 08:00 до 22:00.")
            return
        normalized = datetime.strptime(value, "%H:%M").strftime("%H:%M")
        data = await state.get_data()
        await state.update_data(workout_time=normalized)
        await state.set_state(ScheduleEdit.frequency)
        await message.answer(
            f"Подтверди число тренировок: выбрано дней {len(data['days'])}.",
            reply_markup=frequency_keyboard(prefix="schedule"),
        )

    @router.callback_query(ScheduleEdit.frequency, F.data.startswith("schedule:frequency:"))
    async def edit_frequency(callback: CallbackQuery, state: FSMContext) -> None:
        frequency = int((callback.data or "").rsplit(":", 1)[1])
        data = await state.get_data()
        if frequency != len(data["days"]):
            await callback.answer(
                f"Выбрано дней: {len(data['days'])}. Укажи такую же частоту.", show_alert=True
            )
            return
        settings = await context.users.update_schedule(
            callback.from_user.id,
            days=data["days"],
            workout_time=data["workout_time"],
            workouts_per_week=frequency,
        )
        await context.reminders.rebuild_user_reminders(settings.user_id)
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Расписание обновлено.",
                reply_markup=menu_keyboard(context.settings.show_reset_button),
            )
        await callback.answer()

    return router
