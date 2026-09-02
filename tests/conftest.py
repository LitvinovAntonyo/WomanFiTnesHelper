from __future__ import annotations

import pytest_asyncio

from app.config import Settings
from app.database import Database
from app.services.progress import ProgressService
from app.services.scheduler import ReminderService
from app.services.users import UserService
from app.services.workouts import WorkoutService


@pytest_asyncio.fixture
async def app_services(tmp_path):
    settings = Settings(
        telegram_bot_token="123456:TEST_TOKEN",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'fitness.sqlite3'}",
        timezone="UTC",
        llm_provider="template",
        reminder_scan_seconds=3600,
    )
    database = Database(settings)
    await database.initialize()
    users = UserService(database, settings)
    workouts = WorkoutService(database)
    await workouts.seed_templates()
    progress = ProgressService(database)
    reminders = ReminderService(database, settings)
    yield settings, database, users, workouts, progress, reminders
    await database.close()


@pytest_asyncio.fixture
async def onboarded_user(app_services):
    _, _, users, _, _, _ = app_services
    return await users.complete_onboarding(
        10001,
        name="Тест",
        days=[0, 2, 4],
        workout_time="19:00",
        workouts_per_week=3,
        place="gym",
        goal="regularity",
        experience="returning",
    )
