from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.database import Database
from app.models import User, UserSettings, utc_now


class UserService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    async def get_or_create(self, telegram_id: int) -> User:
        async with self.database.session() as session:
            user = await session.scalar(
                select(User)
                .options(selectinload(User.settings))
                .where(User.telegram_id == telegram_id)
            )
            if user is None:
                user = User(telegram_id=telegram_id)
                session.add(user)
                await session.flush()
            return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        async with self.database.session() as session:
            return await session.scalar(
                select(User)
                .options(selectinload(User.settings))
                .where(User.telegram_id == telegram_id)
            )

    async def complete_onboarding(
        self,
        telegram_id: int,
        *,
        name: str,
        days: list[int],
        workout_time: str,
        workouts_per_week: int,
        place: str,
        goal: str,
        experience: str,
    ) -> User:
        async with self.database.session() as session:
            user = await session.scalar(
                select(User)
                .options(selectinload(User.settings))
                .where(User.telegram_id == telegram_id)
            )
            preferences = user.settings if user is not None else None
            if user is None:
                user = User(telegram_id=telegram_id)
                session.add(user)
                await session.flush()
            user.display_name = name[:100]
            user.onboarding_complete = True
            if preferences is None:
                preferences = UserSettings(user_id=user.id)
                user.settings = preferences
            preferences.timezone = self.settings.timezone
            preferences.workout_days = ",".join(str(day) for day in sorted(set(days)))
            preferences.workout_time = workout_time
            preferences.workouts_per_week = workouts_per_week
            preferences.place = place
            preferences.goal = goal
            preferences.experience = experience
            preferences.monthly_target = self.settings.monthly_workout_target
            await session.flush()
            return user

    async def update_schedule(
        self, telegram_id: int, *, days: list[int], workout_time: str, workouts_per_week: int
    ) -> UserSettings:
        async with self.database.session() as session:
            settings = await session.scalar(
                select(UserSettings)
                .join(User)
                .where(User.telegram_id == telegram_id)
            )
            if settings is None:
                raise ValueError("Настройки пользователя не найдены")
            settings.workout_days = ",".join(str(day) for day in sorted(set(days)))
            settings.workout_time = workout_time
            settings.workouts_per_week = workouts_per_week
            settings.reminders_enabled = True
            settings.paused_until = None
            await session.flush()
            return settings

    async def pause_for_week(self, telegram_id: int) -> None:
        async with self.database.session() as session:
            settings = await session.scalar(
                select(UserSettings).join(User).where(User.telegram_id == telegram_id)
            )
            if settings:
                settings.paused_until = utc_now() + timedelta(days=7)

    async def set_reminders(self, telegram_id: int, enabled: bool) -> None:
        async with self.database.session() as session:
            settings = await session.scalar(
                select(UserSettings).join(User).where(User.telegram_id == telegram_id)
            )
            if settings:
                settings.reminders_enabled = enabled
                if enabled:
                    settings.paused_until = None
