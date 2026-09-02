from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Settings


class AuthorizationMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        actor = getattr(event, "from_user", None)
        if actor is None or self.settings.is_telegram_user_allowed(actor.id):
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("Этот бот работает только для приглашённого пользователя.", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("Этот бот работает только для приглашённого пользователя.")
        return None
