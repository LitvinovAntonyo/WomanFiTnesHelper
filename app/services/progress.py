from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import Database
from app.models import Achievement, Reminder, User, WorkoutSession, utc_now


@dataclass(slots=True)
class Progress:
    month_completed: int
    monthly_target: int
    total_completed: int
    streak: int
    last_completed: datetime | None
    next_workout: datetime | None
    achievements: list[str]
    recent_weeks: list[int]


class ProgressService:
    def __init__(self, database: Database):
        self.database = database

    async def get(self, telegram_id: int) -> Progress:
        async with self.database.session() as session:
            user = await session.scalar(
                select(User)
                .options(selectinload(User.settings))
                .where(User.telegram_id == telegram_id)
            )
            if user is None:
                raise ValueError("Пользователь не найден")
            tz = ZoneInfo(user.settings.timezone if user.settings else "UTC")
            local_now = utc_now().replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
            start_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_day = monthrange(local_now.year, local_now.month)[1]
            end_local = start_local.replace(day=last_day) + timedelta(days=1)
            start_utc = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            end_utc = end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            base = (
                WorkoutSession.user_id == user.id,
                WorkoutSession.status == "completed",
            )
            month_completed = await session.scalar(
                select(func.count()).select_from(WorkoutSession).where(
                    *base,
                    WorkoutSession.completed_at >= start_utc,
                    WorkoutSession.completed_at < end_utc,
                )
            )
            total_completed = await session.scalar(
                select(func.count()).select_from(WorkoutSession).where(*base)
            )
            last_completed = await session.scalar(
                select(WorkoutSession.completed_at)
                .where(*base)
                .order_by(WorkoutSession.completed_at.desc())
                .limit(1)
            )
            latest_skip = await session.scalar(
                select(Reminder.workout_at)
                .where(Reminder.user_id == user.id, Reminder.status == "skipped")
                .order_by(Reminder.workout_at.desc())
                .limit(1)
            )
            streak_query = select(func.count()).select_from(WorkoutSession).where(*base)
            if latest_skip:
                streak_query = streak_query.where(WorkoutSession.completed_at > latest_skip)
            streak = await session.scalar(streak_query)
            next_workout = await session.scalar(
                select(Reminder.workout_at)
                .where(
                    Reminder.user_id == user.id,
                    Reminder.kind == "pre90",
                    Reminder.status.in_(("pending", "sent", "accepted")),
                    Reminder.workout_at > utc_now(),
                )
                .order_by(Reminder.workout_at)
                .limit(1)
            )
            codes = list(
                (
                    await session.scalars(
                        select(Achievement.code)
                        .where(Achievement.user_id == user.id)
                        .order_by(Achievement.awarded_at)
                    )
                ).all()
            )
            current_week_start = (
                local_now - timedelta(days=local_now.weekday())
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            recent_weeks = []
            for weeks_ago in range(5, -1, -1):
                week_start_local = current_week_start - timedelta(weeks=weeks_ago)
                week_end_local = week_start_local + timedelta(weeks=1)
                week_start_utc = week_start_local.astimezone(ZoneInfo("UTC")).replace(
                    tzinfo=None
                )
                week_end_utc = week_end_local.astimezone(ZoneInfo("UTC")).replace(
                    tzinfo=None
                )
                count = await session.scalar(
                    select(func.count()).select_from(WorkoutSession).where(
                        *base,
                        WorkoutSession.completed_at >= week_start_utc,
                        WorkoutSession.completed_at < week_end_utc,
                    )
                )
                recent_weeks.append(int(count or 0))
            return Progress(
                month_completed=int(month_completed or 0),
                monthly_target=user.settings.monthly_target if user.settings else 10,
                total_completed=int(total_completed or 0),
                streak=int(streak or 0),
                last_completed=last_completed,
                next_workout=next_workout,
                achievements=codes,
                recent_weeks=recent_weeks,
            )
