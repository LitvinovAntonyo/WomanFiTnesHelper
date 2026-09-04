from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import SendPhoto, TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    ForceReply,
    FSInputFile,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from app.context import AppContext
from app.handlers import build_routers
from app.handlers import workout as workout_module
from app.handlers.start import has_consecutive_days
from app.keyboards import RESET_TODAY_TEXT
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


class PhotoFailingSession(RecordingSession):
    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if isinstance(method, SendPhoto):
            raise TelegramBadRequest(method=method, message="photo unavailable")
        return True


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


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", ["quick", "custom", "skip"])
async def test_daily_time_question_through_dispatcher(app_services, onboarded_user, monkeypatch, choice):
    settings, database, users, workouts, progress, _ = app_services
    now = datetime(2026, 9, 7, 7)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(settings, database, bot, users, workouts, progress, reminders, llm)
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))
    async with database.session() as db_session:
        prompt = Reminder(user_id=onboarded_user.id, kind="daily_time", status="sent",
                          scheduled_at=now, workout_at=now.replace(hour=23, minute=59))
        db_session.add(prompt)
        await db_session.flush()
        prompt_id = prompt.id
    if choice == "custom":
        await dispatcher.feed_update(bot, callback_update(1900, f"daily:custom:{prompt_id}"))
        assert isinstance(session.methods[0].reply_markup, ForceReply)
        await dispatcher.feed_update(bot, user_message(1901, "ошибка"))
        assert await dispatcher.storage.get_state(workout_storage_key(bot)) == "DailyTimeInput:clock"
        await dispatcher.feed_update(bot, user_message(1902, "19:30"))
        assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
    else:
        if choice == "quick":
            await dispatcher.feed_update(bot, callback_update(1899, f"daily:custom:{prompt_id}"))
        data = f"daily:time:{prompt_id}:1900" if choice == "quick" else f"daily:skip:{prompt_id}"
        await dispatcher.feed_update(bot, callback_update(1903, data))
        assert await dispatcher.storage.get_state(workout_storage_key(bot)) is None
        await dispatcher.feed_update(bot, callback_update(1904, data))
    texts = [getattr(m, "text", "") or "" for m in session.methods]
    if choice == "skip":
        assert any("сегодня без напоминаний" in text for text in texts)
    else:
        expected = "18:30" if choice == "custom" else "18:00"
        assert sum(f"Напомню за час — в {expected}" in text for text in texts) == 1
    async with database.session() as db_session:
        rows = list((await db_session.scalars(select(Reminder).where(Reminder.kind == "pre90"))).all())
    assert len(rows) == (0 if choice == "skip" else 1)
    await llm.close()
    await bot.session.close()


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
async def test_gift_recipient_is_greeted_by_name_and_skips_name_input(app_services):
    settings, database, users, workouts, progress, _ = app_services
    settings.gift_recipient_name = "Ангелина"
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
        user_message(101, "/start"),
        callback_update(102, "onboarding:days_done"),
        callback_update(104, "onboarding:frequency:3"),
        callback_update(105, "onboarding:place:gym"),
        callback_update(106, "onboarding:goal:regularity"),
        callback_update(107, "onboarding:experience:returning"),
    ]
    for update in updates:
        await dispatcher.feed_update(bot, update)

    user = await users.get_by_telegram_id(10001)
    assert user is not None
    assert user.onboarding_complete
    assert user.display_name == "Ангелина"
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Привет, Ангелина!" in text for text in sent_texts)
    assert not any("Как тебя называть" in text for text in sent_texts)
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

    assert await dispatcher.storage.get_state(workout_storage_key(bot)) == ScheduleEdit.frequency.state
    sent_texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Лучше оставить между ними день восстановления" in text for text in sent_texts)
    assert any("07:00 по местному времени" in text for text in sent_texts)
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
    loaded_plan = await workouts.get_plan(workout.id, 10001)
    before_cardio = [
        getattr(method, "text", "") or "" for method in session.methods
    ]
    plan_index = next(
        index for index, text in enumerate(before_cardio) if "Полный план:" in text
    )
    cardio_index = next(
        index
        for index, text in enumerate(before_cardio)
        if "С чего начнём кардио-разогрев" in text
    )
    assert plan_index < cardio_index
    assert loaded_plan.template.name in before_cardio[plan_index]
    assert loaded_plan.template.focus in before_cardio[plan_index]
    plan_method = session.methods[plan_index]
    assert isinstance(plan_method.reply_markup, ReplyKeyboardMarkup)
    plan_labels = [
        button.text
        for row in plan_method.reply_markup.keyboard
        for button in row
    ]
    assert RESET_TODAY_TEXT in plan_labels
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
    assert any("50–60 минут" in text for text in sent_texts)
    assert any("запасом 3–4" in text for text in sent_texts)
    assert any("Заминка в программу не входит" in text for text in sent_texts)
    assert sum("Полный план:" in text for text in sent_texts) == 1
    assert any("Напиши вес и повторения" in text for text in sent_texts)
    set_prompt = next(
        method
        for method in session.methods
        if "Напиши вес и повторения" in (getattr(method, "text", "") or "")
    )
    assert isinstance(set_prompt.reply_markup, ForceReply)
    assert set_prompt.reply_markup.force_reply is True
    assert set_prompt.reply_markup.input_field_placeholder == "Например: 25 12"

    await dispatcher.feed_update(
        bot, callback_update(26, f"exercise:repeat:{strength.result.id}")
    )
    effort_prompt = next(
        method
        for method in session.methods
        if "Как ощущалась нагрузка в этом упражнении?"
        in (getattr(method, "text", "") or "")
    )
    effort_callbacks = [
        button.callback_data
        for row in effort_prompt.reply_markup.inline_keyboard
        for button in row
    ]
    assert f"effort:{strength.result.id}:easy" in effort_callbacks
    waiting = await workouts.get_step(workout.id, 10001)
    assert waiting is not None
    assert waiting.result.id == strength.result.id
    assert waiting.awaiting_effort is True
    await dispatcher.feed_update(
        bot, callback_update(27, f"effort:{strength.result.id}:easy")
    )
    next_step = await workouts.get_step(workout.id, 10001)
    assert next_step is not None
    assert next_step.result.id != strength.result.id

    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_photo_send_failure_falls_back_to_text_and_actions(
    app_services, onboarded_user, monkeypatch, tmp_path
):
    settings, database, users, workouts, progress, _ = app_services
    session = PhotoFailingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(settings, database, bot, users, workouts, progress, reminders, llm)
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))
    card = tmp_path / "approved-card.png"
    card.write_bytes(b"test-card")
    monkeypatch.setattr(workout_module, "card_path_for", lambda _code: card)
    workout = await workouts.active_or_new(10001)
    await workouts.choose_cardio(workout.id, 10001, "cardio_treadmill")
    await workouts.begin(workout.id, 10001)

    await dispatcher.feed_update(
        bot, callback_update(700, f"cardio:select:{workout.id}:cardio_treadmill")
    )

    assert any(isinstance(method, SendPhoto) for method in session.methods)
    technique = next(
        method
        for method in session.methods
        if "Техника —" in (getattr(method, "text", "") or "")
    )
    assert "1/6 · Кардио" in technique.text
    callbacks = [
        button.callback_data
        for row in technique.reply_markup.inline_keyboard
        for button in row
    ]
    assert any(value.startswith("exercise:set:") for value in callbacks)
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_changed_card_bypasses_legacy_telegram_file_id(
    app_services, onboarded_user, monkeypatch, tmp_path
):
    settings, database, users, workouts, progress, _ = app_services
    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(settings, database, bot, users, workouts, progress, reminders, llm)
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))
    card = tmp_path / "approved-card.png"
    card.write_bytes(b"new-card")
    monkeypatch.setattr(workout_module, "card_path_for", lambda _code: card)
    await workouts.remember_media_file_id("cardio_treadmill", "OLD_FILE_ID")
    workout = await workouts.active_or_new(10001)
    await workouts.choose_cardio(workout.id, 10001, "cardio_treadmill")
    await workouts.begin(workout.id, 10001)

    await dispatcher.feed_update(
        bot, callback_update(701, f"cardio:select:{workout.id}:cardio_treadmill")
    )

    sent_photo = next(method for method in session.methods if isinstance(method, SendPhoto))
    assert isinstance(sent_photo.photo, FSInputFile)
    assert "1/6 · Кардио" in sent_photo.caption
    assert "Техника —" in sent_photo.caption
    assert sent_photo.reply_markup is not None
    assert not any(
        "Техника —" in (getattr(method, "text", "") or "")
        for method in session.methods
    )
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_legacy_rest_callbacks_use_fixed_rest_and_reject_stale_targets(
    app_services, onboarded_user, monkeypatch
):
    settings, database, users, workouts, progress, _ = app_services
    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(settings, database, bot, users, workouts, progress, reminders, llm)
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))
    started = []

    async def fake_start_rest(rest_tasks, context, message, telegram_id, result_id, seconds):
        started.append((result_id, seconds))

    monkeypatch.setattr(workout_module, "start_rest_task", fake_start_rest)
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    strength = await workouts.get_step(workout.id, 10001)
    assert strength is not None
    await workouts.record_set(strength.result.id, 10001, 12, None)

    await dispatcher.feed_update(
        bot, callback_update(710, f"rest:timer:{strength.result.id}:999")
    )
    await dispatcher.feed_update(
        bot, callback_update(711, f"rest:ready:{strength.result.id}")
    )
    assert started == [(strength.result.id, 75)]
    texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Следующий подход" in text for text in texts)

    await workouts.skip_exercise(strength.result.id, 10001)
    await dispatcher.feed_update(
        bot, callback_update(712, f"rest:timer:{strength.result.id}:60")
    )
    assert started == [(strength.result.id, 75)]
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_replayed_replace_callback_keeps_first_replacement(
    app_services, onboarded_user
):
    settings, database, users, workouts, progress, _ = app_services
    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(settings, database, bot, users, workouts, progress, reminders, llm)
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))

    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    leg_curl = await workouts.get_step(workout.id, 10001)
    assert leg_curl is not None
    await workouts.complete_exercise(leg_curl.result.id, 10001)
    await workouts.record_effort(leg_curl.result.id, 10001, "ok")
    glute = await workouts.get_step(workout.id, 10001)
    assert glute is not None
    assert glute.exercise.code == "glute_kickback"

    callback_data = f"exercise:replace:{glute.result.id}"
    await dispatcher.feed_update(bot, callback_update(720, callback_data))
    first = await workouts.get_step(workout.id, 10001)
    assert first is not None
    assert first.exercise.code == "hip_abduction"
    assert first.was_replaced is True

    await dispatcher.feed_update(bot, callback_update(721, callback_data))
    replayed = await workouts.get_step(workout.id, 10001)
    assert replayed is not None
    assert replayed.exercise.code == "hip_abduction"
    answers = [
        method for method in session.methods if getattr(method, "callback_query_id", None)
    ]
    assert any("уже заменено" in (getattr(method, "text", "") or "") for method in answers)
    await llm.close()
    await bot.session.close()


@pytest.mark.asyncio
async def test_adapted_target_is_visible_in_telegram_plan_after_two_easy_results(
    app_services, onboarded_user
):
    settings, database, users, workouts, progress, _ = app_services

    async def complete_with_chest_effort(effort: str) -> None:
        workout = await workouts.active_or_new(10001)
        await workouts.begin(workout.id, 10001)
        while (step := await workouts.get_step(workout.id, 10001)) is not None:
            await workouts.complete_exercise(step.result.id, 10001)
            if step.exercise.requires_weight:
                await workouts.record_effort(
                    step.result.id,
                    10001,
                    effort if step.exercise.code == "chest_press" else "ok",
                )
        assert await workouts.finish_if_complete(workout.id)

    await complete_with_chest_effort("easy")
    await complete_with_chest_effort("easy")
    await complete_with_chest_effort("ok")

    session = RecordingSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    reminders = ReminderService(database, settings, bot)
    llm = build_llm_service(settings, database)
    context = AppContext(settings, database, bot, users, workouts, progress, reminders, llm)
    dispatcher = Dispatcher()
    dispatcher.include_routers(*build_routers(context))

    await dispatcher.feed_update(bot, user_message(730, "🏋️ Начать тренировку"))
    workout = await workouts.active_or_new(10001)
    await dispatcher.feed_update(
        bot,
        callback_update(731, f"cardio:select:{workout.id}:cardio_treadmill"),
    )

    texts = [getattr(method, "text", "") or "" for method in session.methods]
    assert any("Жим в тренажёре" in text and "Цель сегодня: 11 повторений" in text for text in texts)
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
        await dispatcher.feed_update(
            bot, callback_update(update_id, f"effort:{step.result.id}:ok")
        )
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
    resume_method = next(
        method
        for method in session.methods
        if "Продолжаем с того места" in (getattr(method, "text", "") or "")
    )
    assert isinstance(resume_method.reply_markup, ReplyKeyboardMarkup)
    resume_labels = [
        button.text
        for row in resume_method.reply_markup.keyboard
        for button in row
    ]
    assert RESET_TODAY_TEXT in resume_labels
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
