from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Reminder, UserSettings, utc_now
from app.services.scheduler import (
    MORNING_MOTIVATIONS,
    PRE_WORKOUT_MOTIVATIONS,
    PRIMARY_REMINDER_LEAD_MINUTES,
    ReminderService,
    is_quiet_hour,
    local_to_utc_naive,
    morning_motivation_text,
    morning_motivation_time,
    pre_workout_motivation_text,
    utc_naive_to_local,
)


@pytest.mark.asyncio
async def test_schedule_only_creates_daily_time_questions(
    app_services, onboarded_user
):
    _, database, _, _, _, reminders = app_services
    created = await reminders.ensure_user_reminders(onboarded_user.id)
    assert created > 0
    async with database.session() as session:
        kinds = set((await session.scalars(select(Reminder.kind))).all())
        count = await session.scalar(select(func.count()).select_from(Reminder))
    assert kinds == {"daily_time"}
    assert count and count >= 3

    async with database.session() as session:
        primary = await session.scalar(
            select(Reminder)
            .where(Reminder.kind == "daily_time")
            .order_by(Reminder.workout_at)
        )
    assert primary is not None
    assert primary.scheduled_at.strftime("%H:%M") == "07:00"
    assert await reminders.ensure_user_reminders(onboarded_user.id) == 0


def test_pre_workout_motivations_are_varied_and_do_not_mention_lead_time():
    assert len(PRE_WORKOUT_MOTIVATIONS) == 20
    assert len(set(PRE_WORKOUT_MOTIVATIONS)) == 20
    assert all("два часа" not in text.lower() for text in PRE_WORKOUT_MOTIVATIONS)
    assert all("120 минут" not in text.lower() for text in PRE_WORKOUT_MOTIVATIONS)
    assert any("Я Ангелина" in text for text in PRE_WORKOUT_MOTIVATIONS)

    workout_at = local_to_utc_naive(datetime.fromisoformat("2026-09-07T19:00:00+05:00"))
    assert pre_workout_motivation_text(workout_at, "Asia/Yekaterinburg") in (
        PRE_WORKOUT_MOTIVATIONS
    )


def test_motivation_is_scheduled_at_seven_local_before_evening_workout():
    workout_local = datetime.fromisoformat("2026-09-07T19:00:00+05:00")
    workout_at = local_to_utc_naive(workout_local)

    scheduled_at = morning_motivation_time(workout_at, "Asia/Yekaterinburg")

    assert scheduled_at is not None
    local_scheduled = utc_naive_to_local(scheduled_at, "Asia/Yekaterinburg")
    assert local_scheduled.date() == workout_local.date()
    assert local_scheduled.strftime("%H:%M") == "07:00"


def test_motivation_is_not_scheduled_after_early_workout():
    workout_local = datetime.fromisoformat("2026-09-07T06:00:00+05:00")
    workout_at = local_to_utc_naive(workout_local)

    assert morning_motivation_time(workout_at, "Asia/Yekaterinburg") is None


@pytest.mark.asyncio
async def test_reschedule_and_skip_do_not_delete_progress(app_services, onboarded_user):
    _, database, _, _, _, reminders = app_services
    async with database.session() as session:
        session.add(Reminder(user_id=onboarded_user.id, kind="pre90",
                             workout_at=utc_now()+timedelta(days=1), scheduled_at=utc_now()))
    async with database.session() as session:
        original = await session.scalar(
            select(Reminder)
            .where(Reminder.user_id == onboarded_user.id, Reminder.kind == "pre90")
            .order_by(Reminder.workout_at)
        )
        assert original is not None
        reminder_id = original.id
    new_time = (utc_now() + timedelta(days=5)).replace(hour=19, minute=0)
    await reminders.reschedule(reminder_id, 10001, new_time)
    async with database.session() as session:
        moved = await session.scalar(
            select(Reminder).where(
                Reminder.user_id == onboarded_user.id,
                Reminder.workout_at == new_time,
                Reminder.kind == "pre90",
            )
        )
        assert moved is not None
        moved_id = moved.id
    await reminders.skip(moved_id, 10001)
    async with database.session() as session:
        statuses = set(
            (
                await session.scalars(
                    select(Reminder.status).where(
                        Reminder.user_id == onboarded_user.id,
                        Reminder.workout_at == new_time,
                    )
                )
            ).all()
        )
    assert statuses == {"skipped"}


def test_quiet_hours_are_blocked():
    assert is_quiet_hour(utc_now().replace(hour=2), "UTC")
    assert not is_quiet_hour(utc_now().replace(hour=12), "UTC")


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))


@pytest.mark.asyncio
async def test_due_reminder_is_delivered_once(
    app_services, onboarded_user, monkeypatch
):
    settings, database, _, _, _, _ = app_services
    fake_bot = FakeBot()
    service = ReminderService(database, settings, fake_bot)  # type: ignore[arg-type]
    now = datetime(2026, 9, 7, 12, 0)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    async with database.session() as session:
        session.add(
            Reminder(
                user_id=onboarded_user.id,
                workout_at=now + timedelta(minutes=PRIMARY_REMINDER_LEAD_MINUTES),
                scheduled_at=now - timedelta(seconds=1),
                kind="pre90",
            )
        )
    async with database.session() as session:
        reminder_id = await session.scalar(
            select(Reminder.id).where(Reminder.user_id == onboarded_user.id)
        )
    assert reminder_id is not None
    await service._deliver(reminder_id)
    await service._deliver(reminder_id)
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0][0] == 10001
    assert any(text in fake_bot.sent[0][1] for text in PRE_WORKOUT_MOTIVATIONS)


@pytest.mark.asyncio
async def test_morning_question_is_delivered_once_at_seven_with_buttons(
    app_services, onboarded_user, monkeypatch
):
    settings, database, _, _, _, _ = app_services
    fake_bot = FakeBot()
    service = ReminderService(database, settings, fake_bot)  # type: ignore[arg-type]
    now = datetime(2026, 9, 7, 7, 0)
    workout_at = now + timedelta(hours=7)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    async with database.session() as session:
        session.add(
            Reminder(
                user_id=onboarded_user.id,
                workout_at=workout_at,
                scheduled_at=now - timedelta(seconds=1),
                kind="daily_time",
            )
        )
    async with database.session() as session:
        reminder_id = await session.scalar(
            select(Reminder.id).where(Reminder.user_id == onboarded_user.id)
        )
    assert reminder_id is not None

    await service._deliver(reminder_id)
    await service._deliver(reminder_id)

    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0][1] == morning_motivation_text(workout_at, "UTC", "Тест")
    labels = [b.text for row in fake_bot.sent[0][2].inline_keyboard for b in row]
    assert labels == ["В 18:00", "В 19:00", "В 20:00", "Другое время", "Сегодня не получится"]


@pytest.mark.asyncio
@pytest.mark.parametrize("timezone", ["UTC", "Asia/Yekaterinburg", "Europe/Moscow"])
async def test_daily_choice_uses_profile_timezone_and_survives_restart(
    app_services, onboarded_user, monkeypatch, timezone
):
    settings, database, _, _, _, reminders = app_services
    from zoneinfo import ZoneInfo

    now = local_to_utc_naive(datetime(2026, 9, 7, 6, 59, tzinfo=ZoneInfo(timezone)))
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    async with database.session() as session:
        prefs = await session.scalar(select(UserSettings).where(UserSettings.user_id == onboarded_user.id))
        prefs.timezone = timezone
    await reminders.ensure_user_reminders(onboarded_user.id)
    async with database.session() as session:
        prompt = await session.scalar(select(Reminder).order_by(Reminder.workout_at))
        assert utc_naive_to_local(prompt.scheduled_at, timezone).strftime("%H:%M") == "07:00"
        prompt_id = prompt.id
    now += timedelta(minutes=1)
    workout_at, due = await reminders.choose_daily_time(prompt_id, 10001, "19:00")
    assert workout_at - due == timedelta(hours=1)
    assert utc_naive_to_local(workout_at, timezone).strftime("%H:%M") == "19:00"
    assert utc_naive_to_local(due, timezone).strftime("%H:%M") == "18:00"
    restarted = ReminderService(database, settings)
    await restarted.ensure_user_reminders(onboarded_user.id)
    with pytest.raises(ValueError, match="уже сохранён"):
        await restarted.choose_daily_time(prompt_id, 10001, "20:00")
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Reminder).where(Reminder.kind == "pre90")) == 1
        assert await session.scalar(select(func.count()).select_from(Reminder).where(Reminder.kind == "pre10")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["skip", "near", "foreign", "stale", "past", "invalid", "paused"])
async def test_daily_choice_guards(app_services, onboarded_user, monkeypatch, mode):
    _, database, _, _, _, reminders = app_services
    now = datetime(2026, 9, 7, 18, 30)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    async with database.session() as session:
        prompt = Reminder(user_id=onboarded_user.id, kind="daily_time", status="sent",
                          workout_at=now.replace(hour=23, minute=59),
                          scheduled_at=now.replace(hour=7, minute=0))
        if mode == "stale":
            prompt.workout_at -= timedelta(days=1)
        if mode == "paused":
            prefs = await session.scalar(select(UserSettings).where(UserSettings.user_id == onboarded_user.id))
            prefs.paused_until = now + timedelta(days=1)
        session.add(prompt)
        await session.flush()
        prompt_id = prompt.id
    if mode == "skip":
        assert await reminders.choose_daily_time(prompt_id, 10001, None) is None
    elif mode == "near":
        result = await reminders.choose_daily_time(prompt_id, 10001, "19:00")
        assert result == (now.replace(hour=19, minute=0), None)
    else:
        with pytest.raises(ValueError):
            await reminders.choose_daily_time(prompt_id, 99999 if mode == "foreign" else 10001,
                                              "18:00" if mode == "past" else "nope" if mode == "invalid" else "19:00")
    async with database.session() as session:
        pending = await session.scalar(select(func.count()).select_from(Reminder).where(
            Reminder.kind == "pre90", Reminder.status == "pending"))
        assert pending == 0


def test_twenty_distinct_morning_messages():
    assert len(MORNING_MOTIVATIONS) == len(set(MORNING_MOTIVATIONS)) == 20


@pytest.mark.asyncio
async def test_no_question_is_created_late_and_unanswered_does_not_remind(
    app_services, onboarded_user, monkeypatch
):
    _, database, _, _, _, reminders = app_services
    now = datetime(2026, 9, 7, 7, 1)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    await reminders.ensure_user_reminders(onboarded_user.id)
    async with database.session() as session:
        rows = list((await session.scalars(select(Reminder))).all())
    assert all(r.scheduled_at.date() > now.date() and r.kind == "daily_time" for r in rows)


@pytest.mark.asyncio
async def test_migration_cancels_only_old_pending_and_is_idempotent(app_services, onboarded_user):
    from sqlalchemy import text

    _, database, _, _, _, _ = app_services
    async with database.session() as session:
        for index, (kind, status) in enumerate((('pre90', 'pending'), ('motivation', 'pending'),
                                               ('pre10', 'pending'), ('pre90', 'sent'), ('daily_time', 'pending'))):
            session.add(Reminder(user_id=onboarded_user.id, kind=kind, status=status,
                                 workout_at=utc_now()+timedelta(days=index+1), scheduled_at=utc_now()))
        await session.execute(text("PRAGMA user_version=3"))
    await database.initialize()
    await database.initialize()
    async with database.session() as session:
        statuses = list((await session.scalars(select(Reminder.status).order_by(Reminder.id))).all())
    assert statuses == ['superseded', 'superseded', 'superseded', 'sent', 'pending']


@pytest.mark.asyncio
async def test_full_daily_lifecycle_only_sends_at_seven_and_one_hour_before(
    app_services, onboarded_user, monkeypatch
):
    settings, database, _, _, _, _ = app_services
    now = datetime(2026, 9, 7, 6, 59)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    bot = FakeBot()
    service = ReminderService(database, settings, bot)
    await service.tick()
    assert bot.sent == []
    now = now.replace(hour=7, minute=0)
    await service.tick()
    assert len(bot.sent) == 1
    async with database.session() as session:
        prompt = await session.scalar(select(Reminder).where(Reminder.kind == "daily_time").order_by(Reminder.workout_at))
    await service.choose_daily_time(prompt.id, 10001, "19:00")
    now = now.replace(hour=17, minute=59)
    await service.tick()
    assert len(bot.sent) == 1
    now = now.replace(hour=18, minute=0)
    await service.tick()
    assert len(bot.sent) == 2
    assert "19:00 по твоему местному времени" in bot.sent[-1][1]
    service = ReminderService(database, settings, bot)
    now = now.replace(hour=18, minute=50)
    await service.tick()
    assert len(bot.sent) == 2


@pytest.mark.asyncio
async def test_old_morning_question_expires_after_long_downtime(app_services, onboarded_user, monkeypatch):
    settings, database, _, _, _, _ = app_services
    now = datetime(2026, 9, 7, 9)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    async with database.session() as session:
        prompt = Reminder(user_id=onboarded_user.id, kind="daily_time",
                          scheduled_at=now.replace(hour=7), workout_at=now.replace(hour=23))
        session.add(prompt)
        await session.flush()
        prompt_id = prompt.id
    bot = FakeBot()
    service = ReminderService(database, settings, bot)
    await service._deliver(prompt_id)
    assert bot.sent == []
    async with database.session() as session:
        assert (await session.get(Reminder, prompt_id)).status == "expired"
