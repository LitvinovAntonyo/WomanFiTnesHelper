from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from aiogram import Bot

from app.config import Settings
from app.database import Database
from app.llm import LLMService
from app.services.progress import ProgressService
from app.services.scheduler import ReminderService
from app.services.users import UserService
from app.services.workouts import WorkoutService


@dataclass(slots=True)
class AppContext:
    settings: Settings
    database: Database
    bot: Bot
    users: UserService
    workouts: WorkoutService
    progress: ProgressService
    reminders: ReminderService
    llm: LLMService
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: str | None = None
