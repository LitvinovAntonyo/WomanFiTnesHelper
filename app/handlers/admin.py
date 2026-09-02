from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from app.context import AppContext
from app.models import User, WorkoutSession


def human_duration(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}д {hours}ч {minutes}м" if days else f"{hours}ч {minutes}м"


def build_admin_router(context: AppContext) -> Router:
    router = Router(name="admin")

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        if context.settings.admin_telegram_id != message.from_user.id:
            await message.answer("Команда доступна только администратору.")
            return
        db_ok = await context.database.healthcheck()
        async with context.database.session() as session:
            users = await session.scalar(select(func.count()).select_from(User))
            workouts = await session.scalar(
                select(func.count()).select_from(WorkoutSession).where(
                    WorkoutSession.status == "completed"
                )
            )
        uptime = int((datetime.now(timezone.utc) - context.started_at).total_seconds())
        if context.llm.provider_name == "template":
            llm_state = "template fallback"
        elif context.llm.last_error:
            llm_state = "unavailable"
        elif context.llm.last_success_at:
            llm_state = "OK"
        else:
            llm_state = "configured, not tested yet"
        last_error = context.last_error or context.reminders.last_error or context.llm.last_error or "нет"
        await message.answer(
            "Bot: online\n"
            f"Uptime: {human_duration(uptime)}\n"
            f"DB: {'OK' if db_ok else 'ERROR'}\n"
            f"Scheduler: {'OK' if context.reminders.running else 'stopped'}\n"
            f"LLM: {llm_state}\n"
            f"LLM provider: {context.llm.provider_name} (configured: {context.llm.configured_provider})\n"
            f"Последняя ошибка: {last_error}\n"
            f"Пользователей: {int(users or 0)}\n"
            f"Завершённых тренировок: {int(workouts or 0)}"
        )

    return router
