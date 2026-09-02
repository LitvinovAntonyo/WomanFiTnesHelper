from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Reminder, utc_now
from app.services.scheduler import (
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
async def test_schedule_is_persisted_and_has_three_reminder_types(
    app_services, onboarded_user
):
    _, database, _, _, _, reminders = app_services
    created = await reminders.ensure_user_reminders(onboarded_user.id)
    assert created > 0
    async with database.session() as session:
        kinds = set((await session.scalars(select(Reminder.kind))).all())
        count = await session.scalar(select(func.count()).select_from(Reminder))
    assert kinds == {"motivation", "pre90", "pre10"}
    assert count and count >= 3

    async with database.session() as session:
        primary = await session.scalar(
            select(Reminder)
            .where(Reminder.kind == "pre90")
            .order_by(Reminder.workout_at)
        )
    assert primary is not None
    assert primary.workout_at - primary.scheduled_at == timedelta(
        minutes=PRIMARY_REMINDER_LEAD_MINUTES
    )


def test_pre_workout_motivations_are_varied_and_do_not_mention_lead_time():
    assert len(PRE_WORKOUT_MOTIVATIONS) == 20
    assert len(set(PRE_WORKOUT_MOTIVATIONS)) == 20
    assert all("два часа" not in text.lower() for text in PRE_WORKOUT_MOTIVATIONS)
    assert all("120 минут" not in text.lower() for text in PRE_WORKOUT_MOTIVATIONS)

    workout_at = local_to_utc_naive(datetime.fromisoformat("2026-09-07T19:00:00+05:00"))
    assert pre_workout_motivation_text(workout_at, "Asia/Yekaterinburg") in (
        PRE_WORKOUT_MOTIVATIONS
    )


def test_motivation_is_scheduled_at_nine_local_before_evening_workout():
    workout_local = datetime.fromisoformat("2026-09-07T19:00:00+05:00")
    workout_at = local_to_utc_naive(workout_local)

    scheduled_at = morning_motivation_time(workout_at, "Asia/Yekaterinburg")

    assert scheduled_at is not None
    local_scheduled = utc_naive_to_local(scheduled_at, "Asia/Yekaterinburg")
    assert local_scheduled.date() == workout_local.date()
    assert local_scheduled.strftime("%H:%M") == "09:00"


def test_motivation_is_not_scheduled_after_early_workout():
    workout_local = datetime.fromisoformat("2026-09-07T08:00:00+05:00")
    workout_at = local_to_utc_naive(workout_local)

    assert morning_motivation_time(workout_at, "Asia/Yekaterinburg") is None


@pytest.mark.asyncio
async def test_reschedule_and_skip_do_not_delete_progress(app_services, onboarded_user):
    _, database, _, _, _, reminders = app_services
    await reminders.ensure_user_reminders(onboarded_user.id)
    async with database.session() as session:
        original = await session.scalar(
            select(Reminder)
            .where(Reminder.user_id == onboarded_user.id, Reminder.kind == "pre90")
            .order_by(Reminder.workout_at)
        )
        assert original is not None
        reminder_id = original.id
    new_time = utc_now() + timedelta(days=5, hours=12)
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
async def test_morning_motivation_is_delivered_once_without_buttons(
    app_services, onboarded_user, monkeypatch
):
    settings, database, _, _, _, _ = app_services
    fake_bot = FakeBot()
    service = ReminderService(database, settings, fake_bot)  # type: ignore[arg-type]
    now = datetime(2026, 9, 7, 12, 0)
    workout_at = now + timedelta(hours=7)
    monkeypatch.setattr("app.services.scheduler.utc_now", lambda: now)
    async with database.session() as session:
        session.add(
            Reminder(
                user_id=onboarded_user.id,
                workout_at=workout_at,
                scheduled_at=now - timedelta(seconds=1),
                kind="motivation",
            )
        )
    async with database.session() as session:
        reminder_id = await session.scalar(
            select(Reminder.id).where(Reminder.user_id == onboarded_user.id)
        )
    assert reminder_id is not None

    await service._deliver(reminder_id)
    await service._deliver(reminder_id)

    assert fake_bot.sent == [
        (
            10001,
            morning_motivation_text(workout_at, "UTC"),
            None,
        )
    ]
    assert "для себя" in fake_bot.sent[0][1] or "себе" in fake_bot.sent[0][1]
