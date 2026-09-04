from __future__ import annotations

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.keyboards import menu_keyboard, text_input_reply
from app.services.scheduler import utc_naive_to_local
from app.states import DailyTimeInput


def build_daily_schedule_router(context: AppContext) -> Router:
    router = Router(name="daily_schedule")

    async def save_time(message: Message, telegram_id: int, reminder_id: int, clock: str) -> bool:
        try:
            result = await context.reminders.choose_daily_time(reminder_id, telegram_id, clock)
        except ValueError as exc:
            await message.answer(str(exc))
            return False
        assert result is not None
        workout_at, due = result
        timezone = await context.reminders.user_timezone(telegram_id)
        local = utc_naive_to_local(workout_at, timezone)
        followup = (
            f"Напомню за час — в {utc_naive_to_local(due, timezone):%H:%M}."
            if due else "До тренировки не больше часа — отдельного напоминания уже не будет."
        )
        await message.answer(
            f"Договорились, сегодня в {local:%H:%M} по твоему местному времени! 💪\n{followup}",
            reply_markup=menu_keyboard(context.settings.show_reset_button),
        )
        return True

    @router.callback_query(F.data.regexp(r"^daily:time:\d+:\d{4}$"))
    async def quick_time(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, raw_id, raw_time = (callback.data or "").split(":")
        if callback.message:
            saved = await save_time(callback.message, callback.from_user.id, int(raw_id),
                                    f"{raw_time[:2]}:{raw_time[2:]}")
            if saved:
                await state.clear()
                with suppress(TelegramAPIError):
                    await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()

    @router.callback_query(F.data.regexp(r"^daily:custom:\d+$"))
    async def custom_time(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(DailyTimeInput.clock)
        await state.update_data(
            daily_reminder_id=int((callback.data or "").rsplit(":", 1)[1]),
            daily_question_message_id=callback.message.message_id if callback.message else None,
        )
        if callback.message:
            await callback.message.answer(
                "Во сколько сегодня? Напиши местное время, например 19:30 (с 08:00 до 22:00).",
                reply_markup=text_input_reply("Например: 19:30"),
            )
        await callback.answer()

    @router.message(DailyTimeInput.clock, F.text)
    async def receive_time(message: Message, state: FSMContext) -> None:
        assert message.from_user is not None
        data = await state.get_data()
        if await save_time(message, message.from_user.id, data["daily_reminder_id"],
                           (message.text or "").strip()):
            if data.get("daily_question_message_id"):
                with suppress(TelegramAPIError):
                    await context.bot.edit_message_reply_markup(
                        chat_id=message.chat.id, message_id=data["daily_question_message_id"], reply_markup=None
                    )
            await state.clear()

    @router.callback_query(F.data.regexp(r"^daily:skip:\d+$"))
    async def skip_today(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            await context.reminders.choose_daily_time(
                int((callback.data or "").rsplit(":", 1)[1]), callback.from_user.id, None
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await state.clear()
        if callback.message:
            with suppress(TelegramAPIError):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("Хорошо, сегодня без напоминаний. Общий прогресс сохранён 💛",
                                          reply_markup=menu_keyboard(context.settings.show_reset_button))
        await callback.answer()

    return router
