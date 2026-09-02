from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from app.context import AppContext
from app.handlers import build_routers
from app.handlers import workout as workout_module
from app.handlers.start import has_consecutive_days
from app.llm import build_llm_service
from app.models import ExerciseSetResult, Reminder, WorkoutSessionFeedback
from app.services.scheduler import ReminderService
from app.states import ScheduleEdit


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


def workout_storage_key(bot: Bot) -> StorageKey:
    return StorageKey(bot_id=bot.id, chat_id=10001, user_id=10001)


def test_consecutive_day_detection_wraps_across_week():
    assert not has_consecutive_days([0, 2, 4])
    assert has_consecutive_days([0, 1, 4])
    assert has_consecutive_days([0, 6])


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
        callback_update(3, "onboarding:day:2"),
        callback_update(4, "onboarding:day:1"),
        callback_update(5, "onboarding:days_done"),
        user_message(6, "19:00"),
        callback_update(7, "onboarding:frequency:3"),
        callback_update(8, "onboarding:place:gym"),
        callback_update(9, "onboarding:goal:regularity"),
        callback_update(10, "onboarding:experience:returning"),
    ]
    for update in updates:
        await dispatcher.feed_update(bot, update)

    user = await users.get_by_telegram_id(10001)
    assert user is not None
    assert user.onboarding_complete
    assert user.display_name == "Анна"
    assert user.settings is not None
    assert user.settings.workout_days == "0,1,4"
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Как тебя называть" in text for text in sent_texts)
    assert any("Главная цель" in text for text in sent_texts)
    assert any("Лучше оставить между ними день восстановления" in text for text in sent_texts)
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_schedule_edit_warns_about_consecutive_days_without_blocking(app_services, onboarded_user):
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

    await dispatcher.feed_update(bot, callback_update(11, "settings:schedule"))
    await dispatcher.feed_update(bot, callback_update(12, "schedule:day:2"))
    await dispatcher.feed_update(bot, callback_update(13, "schedule:day:1"))
    await dispatcher.feed_update(bot, callback_update(14, "schedule:days_done"))

    assert await dispatcher.storage.get_state(workout_storage_key(bot)) == ScheduleEdit.workout_time.state
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Лучше оставить между ними день восстановления" in text for text in sent_texts)
    assert any("Новое время" in text for text in sent_texts)
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_workout_starts_with_cardio_choice_then_moves_set_by_set(
    app_services, onboarded_user, monkeypatch
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
    started: list[tuple[int, int]] = []

    async def fake_start_rest(
        rest_tasks, context, message, telegram_id, result_id, seconds
    ):
        started.append((result_id, seconds))

    monkeypatch.setattr(workout_module, "start_rest_task", fake_start_rest)

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
        bot, callback_update(23, f"exercise:log:{strength.result.id}")
    )
    await dispatcher.feed_update(bot, user_message(24, "20"))
    async with database.session() as database_session:
        assert (
            await database_session.scalar(
                select(ExerciseSetResult).where(
                    ExerciseSetResult.exercise_result_id == strength.result.id
                )
            )
            is None
        )
    await dispatcher.feed_update(bot, user_message(25, "20 12"))
    state = await workouts.result_state(strength.result.id, 10001)
    assert state[1:3] == (1, 2)
    async with database.session() as database_session:
        logged = await database_session.scalar(
            select(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id == strength.result.id
            )
        )
    assert logged is not None
    assert (logged.weight_kg, logged.reps) == (Decimal("20.00"), 12)
    assert started == [(strength.result.id, 75)]
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("С чего начнём кардио-разогрев" in text for text in sent_texts)
    assert any("Заминка в программу не входит" in text for text in sent_texts)
    assert any("Напиши вес и повторения" in text for text in sent_texts)

    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_pain_advances_and_completed_session_collects_feedback(
    app_services, onboarded_user, monkeypatch
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

    async def fake_start_rest(
        rest_tasks, context, message, telegram_id, result_id, seconds
    ):
        return None

    monkeypatch.setattr(workout_module, "start_rest_task", fake_start_rest)

    workout = await workouts.active_or_new(10001)
    await workouts.choose_cardio(workout.id, 10001, "cardio_bike")
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await dispatcher.feed_update(
        bot, callback_update(30, f"exercise:set:{cardio.result.id}")
    )
    painful = await workouts.get_step(workout.id, 10001)
    assert painful is not None
    await dispatcher.feed_update(
        bot, callback_update(31, f"exercise:pain:{painful.result.id}")
    )
    following = await workouts.get_step(workout.id, 10001)
    assert following is not None
    assert following.result.id != painful.result.id

    update_id = 32
    while (step := await workouts.get_step(workout.id, 10001)) is not None:
        for _ in range(step.result.sets_planned):
            await dispatcher.feed_update(
                bot,
                callback_update(update_id, f"exercise:log:{step.result.id}"),
            )
            update_id += 1
            await dispatcher.feed_update(bot, user_message(update_id, "- 12"))
            update_id += 1

    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("не продолжай через острую" in text.lower() for text in sent_texts)
    assert any("Насколько комфортной была нагрузка?" in text for text in sent_texts)

    await dispatcher.feed_update(
        bot,
        callback_update(update_id, f"session:feedback:{workout.id}:ok"),
    )
    async with database.session() as database_session:
        feedback = await database_session.scalar(
            select(WorkoutSessionFeedback).where(
                WorkoutSessionFeedback.session_id == workout.id
            )
        )
    assert feedback is not None
    assert feedback.effort == "ok"

    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_repeat_clears_pending_set_input_even_when_it_finishes_exercise(
    app_services, onboarded_user, monkeypatch
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

    async def fake_start_rest(
        rest_tasks, context, message, telegram_id, result_id, seconds
    ):
        return None

    monkeypatch.setattr(workout_module, "start_rest_task", fake_start_rest)

    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await dispatcher.feed_update(
        bot, callback_update(400, f"exercise:set:{cardio.result.id}")
    )
    strength = await workouts.get_step(workout.id, 10001)
    assert strength is not None

    await dispatcher.feed_update(
        bot, callback_update(401, f"exercise:log:{strength.result.id}")
    )
    await dispatcher.feed_update(bot, user_message(402, "20 12"))
    await dispatcher.feed_update(
        bot, callback_update(403, f"exercise:log:{strength.result.id}")
    )
    assert (
        await dispatcher.storage.get_state(workout_storage_key(bot))
        == "WorkoutInput:set_result"
    )

    await dispatcher.feed_update(
        bot, callback_update(404, f"exercise:repeat:{strength.result.id}")
    )

    assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    await dispatcher.feed_update(bot, user_message(405, "30 10"))
    async with database.session() as database_session:
        logged_sets = list(
            (
                await database_session.scalars(
                    select(ExerciseSetResult).where(
                        ExerciseSetResult.exercise_result_id == strength.result.id
                    )
                )
            ).all()
        )
    assert len(logged_sets) == 2
    assert all(row.weight_kg == Decimal("20.00") for row in logged_sets)

    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_skip_replace_and_pain_clear_pending_set_input(
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

    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await dispatcher.feed_update(
        bot, callback_update(500, f"exercise:set:{cardio.result.id}")
    )
    skipped = await workouts.get_step(workout.id, 10001)
    assert skipped is not None

    await dispatcher.feed_update(
        bot, callback_update(501, f"exercise:log:{skipped.result.id}")
    )
    await dispatcher.feed_update(
        bot, callback_update(502, f"exercise:skip:{skipped.result.id}")
    )
    assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    await dispatcher.feed_update(bot, user_message(503, "25 12"))

    replaced = await workouts.get_step(workout.id, 10001)
    assert replaced is not None
    assert replaced.exercise.code == "glute_kickback"
    await dispatcher.feed_update(
        bot, callback_update(504, f"exercise:log:{replaced.result.id}")
    )
    await dispatcher.feed_update(
        bot, callback_update(505, f"exercise:replace:{replaced.result.id}")
    )
    assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    await dispatcher.feed_update(bot, user_message(506, "25 12"))

    painful = await workouts.get_step(workout.id, 10001)
    assert painful is not None
    assert painful.result.id == replaced.result.id
    await dispatcher.feed_update(
        bot, callback_update(507, f"exercise:log:{painful.result.id}")
    )
    await dispatcher.feed_update(
        bot, callback_update(508, f"exercise:pain:{painful.result.id}")
    )
    assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    await dispatcher.feed_update(bot, user_message(509, "25 12"))

    async with database.session() as database_session:
        set_count = await database_session.scalar(
            select(func.count()).select_from(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id.in_(
                    (skipped.result.id, replaced.result.id)
                )
            )
        )
    assert set_count == 0

    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_start_menu_and_reminder_accept_clear_pending_set_input(
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

    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await dispatcher.feed_update(
        bot, callback_update(600, f"exercise:set:{cardio.result.id}")
    )
    strength = await workouts.get_step(workout.id, 10001)
    assert strength is not None

    await dispatcher.feed_update(
        bot, callback_update(601, f"exercise:log:{strength.result.id}")
    )
    assert (
        await dispatcher.storage.get_state(workout_storage_key(bot))
        == "WorkoutInput:set_result"
    )
    await dispatcher.feed_update(bot, user_message(602, "🏋️ Начать тренировку"))
    assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    assert (await workouts.active_or_new(10001)).id == workout.id
    await dispatcher.feed_update(bot, user_message(603, "25 12"))

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with database.session() as database_session:
        reminder = Reminder(
            user_id=onboarded_user.id,
            workout_at=now,
            scheduled_at=now,
            kind="pre90",
        )
        database_session.add(reminder)
        await database_session.flush()
        reminder_id = reminder.id

    await dispatcher.feed_update(
        bot, callback_update(604, f"exercise:log:{strength.result.id}")
    )
    assert (
        await dispatcher.storage.get_state(workout_storage_key(bot))
        == "WorkoutInput:set_result"
    )
    await dispatcher.feed_update(
        bot, callback_update(605, f"reminder:yes:{reminder_id}")
    )
    assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    await dispatcher.feed_update(bot, user_message(606, "25 12"))

    async with database.session() as database_session:
        set_count = await database_session.scalar(
            select(func.count()).select_from(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id == strength.result.id
            )
        )
    assert set_count == 0

    await llm.close()
    await bot.session.close()
