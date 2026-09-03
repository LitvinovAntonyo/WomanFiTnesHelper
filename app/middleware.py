from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from app.config import Settings
from app.database import Database
from app.models import User


class AuthorizationMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, database: Database | None = None):
        self.settings = settings
        self.database = database

    @staticmethod
    def _message_from_event(event: TelegramObject) -> Message | None:
        if isinstance(event, Message):
            return event
        message = getattr(event, "message", None)
        return message if isinstance(message, Message) else None

    @classmethod
    def _is_start_command(cls, event: TelegramObject) -> bool:
        message = cls._message_from_event(event)
        text = (message.text if message else getattr(event, "text", "")) or ""
        command = text.strip().split(maxsplit=1)[0].split("@", 1)[0]
        return command == "/start"

    async def _claimed_owner_id(self) -> int | None:
        if self.database is None:
            return None
        async with self.database.session() as session:
            return await session.scalar(
                select(User.telegram_id).order_by(User.id).limit(1)
            )

    async def _is_allowed(self, event: TelegramObject, telegram_id: int) -> bool:
        if not self.settings.claim_first_user:
            return self.settings.is_telegram_user_allowed(telegram_id)
        if self.settings.admin_telegram_id == telegram_id:
            return True
        owner_id = await self._claimed_owner_id()
        if owner_id is not None:
            return owner_id == telegram_id
        return self._is_start_command(event)

    async def _reject(self, event: TelegramObject, *, unclaimed: bool) -> None:
        text = (
            "Сначала открой /start, чтобы активировать подарок."
            if unclaimed
            else "Этот бот уже активирован для получателя подарка."
        )
        callback = (
            event
            if isinstance(event, CallbackQuery)
            else getattr(event, "callback_query", None)
        )
        if isinstance(callback, CallbackQuery):
            await callback.answer(text, show_alert=True)
            return
        message = self._message_from_event(event)
        if message is not None:
            await message.answer(text)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        actor = getattr(event, "from_user", None)
        if actor is None or await self._is_allowed(event, actor.id):
            return await handler(event, data)
        await self._reject(
            event,
            unclaimed=self.settings.claim_first_user
            and await self._claimed_owner_id() is None,
        )
        return None
