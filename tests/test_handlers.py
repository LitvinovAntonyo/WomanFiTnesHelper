from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser

from app.context import AppContext
from app.handlers import build_routers
from app.llm import build_llm_service
from app.services.scheduler import ReminderService


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.methods: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:
            yield b""


def user_message(update_id: int, text: str) -> Update:
    actor = TelegramUser(id=10001, is_bot=False, first_name="Test")
    chat = Chat(id=10001, type="private")
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=chat,
            from_user=actor,
            text=text,
        ),
    )


def callback_update(update_id: int, data: str) -> Update:
    actor = TelegramUser(id=10001, is_bot=False, first_name="Test")
    chat = Chat(id=10001, type="private")
    bot_message = Message(
        message_id=1000 + update_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=TelegramUser(id=999, is_bot=True, first_name="Bot"),
        text="question",
    )
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=f"callback-{update_id}",
            from_user=actor,
            chat_instance="test",
            message=bot_message,
            data=data,
        ),
    )


@pytest.mark.asyncio
async def test_start_and_complete_onboarding_through_dispatcher(app_services):
    settings, database, users, workouts, progress, _ = app_services
    settings.allowed_telegram_ids = [10001]
    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(
        settings=settings,
        database=database,
        bot=bot,
        users=users,
        workouts=workouts,
        progress=progress,
        reminders=reminders,
        llm=llm,
    )
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))

    updates = [
        user_message(1, "/start"),
        user_message(2, "Анна"),
        callback_update(3, "onboarding:days_done"),
        user_message(4, "19:00"),
        callback_update(5, "onboarding:frequency:3"),
        callback_update(6, "onboarding:place:gym"),
        callback_update(7, "onboarding:goal:regularity"),
        callback_update(8, "onboarding:experience:returning"),
    ]
    for update in updates:
        await dispatcher.feed_update(bot, update)

    user = await users.get_by_telegram_id(10001)
    assert user is not None
    assert user.onboarding_complete
    assert user.display_name == "Анна"
    assert user.settings is not None
    assert user.settings.workout_days == "0,2,4"
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Как тебя называть" in text for text in sent_texts)
    assert any("Главная цель" in text for text in sent_texts)
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_workout_starts_with_cardio_choice_then_moves_set_by_set(
    app_services, onboarded_user
):
    settings, database, users, workouts, progress, _ = app_services
    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(
        settings=settings,
        database=database,
        bot=bot,
        users=users,
        workouts=workouts,
        progress=progress,
        reminders=reminders,
        llm=llm,
    )
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))

    await dispatcher.feed_update(bot, user_message(20, "🏋️ Начать тренировку"))
    workout = await workouts.active_or_new(10001)
    await dispatcher.feed_update(
        bot,
        callback_update(21, f"cardio:select:{workout.id}:cardio_elliptical"),
    )
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    assert cardio.exercise.code == "cardio_elliptical"

    await dispatcher.feed_update(
        bot, callback_update(22, f"exercise:set:{cardio.result.id}")
    )
    strength = await workouts.get_step(workout.id, 10001)
    assert strength is not None
    assert strength.item.position == 2

    await dispatcher.feed_update(
        bot, callback_update(23, f"exercise:set:{strength.result.id}")
    )
    state = await workouts.result_state(strength.result.id, 10001)
    assert state[1:3] == (1, 2)
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("С чего начнём кардио-разогрев" in text for text in sent_texts)
    assert any("Заминка в программу не входит" in text for text in sent_texts)
    assert any("Отдохни перед следующим" in text for text in sent_texts)

    await llm.close()
    await bot.session.close()
