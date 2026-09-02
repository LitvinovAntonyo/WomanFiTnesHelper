from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.context import AppContext


def build_conversation_router(context: AppContext) -> Router:
    router = Router(name="conversation")

    @router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
    async def conversation(message: Message) -> None:
        assert message.from_user is not None
        user = await context.users.get_by_telegram_id(message.from_user.id)
        if user is None or not user.onboarding_complete:
            await message.answer("Сначала напиши /start, чтобы настроить расписание.")
            return
        text = message.text or ""
        if text.lower().strip() in {"я не хочу идти", "не хочу в зал", "не хочу тренироваться"}:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Устала", callback_data="support:Устала")],
                    [InlineKeyboardButton(text="Нет времени", callback_data="support:Нет времени")],
                    [InlineKeyboardButton(text="Просто лень", callback_data="support:Просто лень")],
                    [InlineKeyboardButton(text="Плохое настроение", callback_data="support:Плохое настроение")],
                ]
            )
            await message.answer("Что именно мешает больше всего?", reply_markup=keyboard)
            return
        reply = await context.llm.reply(user.id, text)
        await message.answer(reply.text)

    @router.callback_query(F.data.startswith("support:"))
    async def support_choice(callback) -> None:
        user = await context.users.get_by_telegram_id(callback.from_user.id)
        if user is None:
            await callback.answer()
            return
        text = (callback.data or "").split(":", 1)[1]
        reply = await context.llm.reply(user.id, text)
        if callback.message:
            await callback.message.answer(reply.text)
        await callback.answer()

    return router
