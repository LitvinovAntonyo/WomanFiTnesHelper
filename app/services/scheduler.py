from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.database import Database
from app.models import Reminder, User, UserSettings, WorkoutSession, WorkoutTemplate, utc_now

logger = logging.getLogger(__name__)
UTC = ZoneInfo("UTC")
MORNING_MOTIVATION_TIME = time(9, 0)
PRIMARY_REMINDER_LEAD_MINUTES = 120
MORNING_MOTIVATIONS = (
    "Не откладывай то, что ты выбрала для себя. Вечером не нужен идеальный настрой — "
    "достаточно прийти и начать. Эта тренировка нужна не плану и не боту. Она нужна тебе.",
    "Сегодня у тебя есть встреча с собой — тренировка. Не переноси заботу о себе на "
    "«потом». Сделай сегодня то, за что завтра поблагодаришь себя.",
    "Тренировка сегодня — не наказание и не долг перед кем-то. Это время, которое ты "
    "вкладываешь в своё тело, силу и уверенность. Просто выполни сегодняшний шаг.",
    "Не жди идеального настроения к вечеру. Решение уже принято: сегодня ты идёшь "
    "тренироваться. Всё начинается с одного простого шага.",
    "То, что важно лично тебе, легко отложить ради чужих дел. Сегодня сохрани время для "
    "себя. Тренировка — часть этой заботы.",
    "Не нужно сделать всё идеально. Важно не оставить себя на потом. Сегодняшняя "
    "тренировка — маленькое обещание себе, которое стоит выполнить.",
    "Сила складывается не из редких рывков, а из дней, когда ты просто пришла и сделала "
    "своё. Сегодня один из таких дней.",
)
PRE_WORKOUT_MOTIVATIONS = (
    "Сегодня без отговорок. Собирайся — на тренировке будет лучше, чем дома с чувством вины.",
    "Не начинай торговаться с собой. Ты решила идти — значит, идёшь.",
    "Лень уже готовит убедительную речь. Не слушай. Собирай форму.",
    "Настроение можно не брать. Главное — принеси себя на тренировку.",
    "Пропустить легко. Но ты ведь пришла сюда не за лёгким путём?",
    "Не жди желания тренироваться. Сначала приходишь — желание появляется потом.",
    "Сегодня ты снова выбираешь себя. Не передумай.",
    "Оправдание займёт минуту. Сожаление о пропуске — весь вечер. Собирайся.",
    "Не отдавай тренировку усталости, погоде или плохому настроению. Это твоё время.",
    "Самая важная тренировка — та, которую ты сейчас пытаешься отменить.",
    "Просто надень форму. Дальше всё пойдёт гораздо легче.",
    "Ты обещала это не мне — ты обещала это себе. Приходи.",
    "Можешь идти без настроения, без энергии и без желания. Но иди.",
    "Сегодня не нужен подвиг. Нужно просто не слиться.",
    "Если в голове уже появилось «может, пропустить» — ответ нет. Увидимся на тренировке.",
    "Твоей цели всё равно, какой сегодня день. Сделай то, ради чего начинала.",
    "Хочешь результат — защищай свои тренировки от собственных оправданий.",
    "Я Ангелина, и сегодня я не разрешаю тебе снова отложить себя на потом.",
    "Не думай слишком долго. Форма, вода — и на тренировку.",
    "Вечером ты скажешь себе спасибо. Но сначала нужно встать и пойти.",
)


def local_to_utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def utc_naive_to_local(value: datetime, timezone: str) -> datetime:
    return value.replace(tzinfo=UTC).astimezone(ZoneInfo(timezone))


def parse_days(value: str) -> list[int]:
    return sorted({int(day) for day in value.split(",") if day.strip()})


def parse_clock(value: str) -> time:
    return time.fromisoformat(value)


def iter_workout_times(
    user_settings: UserSettings, *, start_utc: datetime, horizon_days: int = 35
):
    tz = ZoneInfo(user_settings.timezone)
    local_start = start_utc.replace(tzinfo=UTC).astimezone(tz)
    days = set(parse_days(user_settings.workout_days))
    clock = parse_clock(user_settings.workout_time)
    for offset in range(horizon_days + 1):
        date = (local_start + timedelta(days=offset)).date()
        if date.weekday() not in days:
            continue
        local_workout = datetime.combine(date, clock, tzinfo=tz)
        workout_at = local_to_utc_naive(local_workout)
        if workout_at > start_utc:
            yield workout_at


def is_quiet_hour(utc_value: datetime, timezone: str) -> bool:
    hour = utc_naive_to_local(utc_value, timezone).hour
    return hour < 8 or hour >= 22


def safe_notification_time(workout_at: datetime, lead_minutes: int, timezone: str) -> datetime | None:
    """Return a non-night reminder time, or None for an optional late reminder."""
    candidate = workout_at - timedelta(minutes=lead_minutes)
    if not is_quiet_hour(candidate, timezone):
        return candidate
    if lead_minutes == 10:
        return None
    tz = ZoneInfo(timezone)
    workout_local = utc_naive_to_local(workout_at, timezone)
    previous_evening = datetime.combine(
        workout_local.date() - timedelta(days=1), time(21, 0), tzinfo=tz
    )
    return local_to_utc_naive(previous_evening)


def morning_motivation_time(workout_at: datetime, timezone: str) -> datetime | None:
    """Schedule a separate message at 09:00 local, only when it precedes the workout."""
    tz = ZoneInfo(timezone)
    workout_local = utc_naive_to_local(workout_at, timezone)
    candidate = datetime.combine(
        workout_local.date(), MORNING_MOTIVATION_TIME, tzinfo=tz
    )
    if candidate >= workout_local:
        return None
    return local_to_utc_naive(candidate)


def morning_motivation_text(workout_at: datetime, timezone: str) -> str:
    workout_date = utc_naive_to_local(workout_at, timezone).date()
    message = MORNING_MOTIVATIONS[workout_date.toordinal() % len(MORNING_MOTIVATIONS)]
    return f"Доброе утро ☀️\nСегодня день тренировки.\n\n{message}"


def pre_workout_motivation_text(workout_at: datetime, timezone: str) -> str:
    workout_date = utc_naive_to_local(workout_at, timezone).date()
    return PRE_WORKOUT_MOTIVATIONS[workout_date.toordinal() % len(PRE_WORKOUT_MOTIVATIONS)]


class ReminderService:
    def __init__(self, database: Database, settings: Settings, bot: Bot | None = None):
        self.database = database
        self.settings = settings
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._tick_lock = asyncio.Lock()
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self.scheduler.running

    async def start(self) -> None:
        await self.ensure_all_users()
        self.scheduler.add_job(
            self.tick,
            "interval",
            seconds=self.settings.reminder_scan_seconds,
            id="reminder-scan",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self.scheduler.start()

    async def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def ensure_all_users(self) -> None:
        async with self.database.session() as session:
            ids = list(
                (
                    await session.scalars(
                        select(User.id).where(User.onboarding_complete.is_(True))
                    )
                ).all()
            )
        for user_id in ids:
            await self.ensure_user_reminders(user_id)

    async def ensure_user_reminders(self, user_id: int) -> int:
        async with self.database.session() as session:
            user_settings = await session.scalar(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            if user_settings is None:
                return 0
            now = utc_now()
            existing = set(
                (
                    await session.execute(
                        select(Reminder.workout_at, Reminder.kind).where(
                            Reminder.user_id == user_id,
                            Reminder.workout_at > now - timedelta(days=1),
                        )
                    )
                ).all()
            )
            created = 0
            for workout_at in iter_workout_times(user_settings, start_utc=now):
                schedule = (
                    (
                        "motivation",
                        morning_motivation_time(workout_at, user_settings.timezone),
                    ),
                    (
                        "pre90",
                        safe_notification_time(
                            workout_at,
                            PRIMARY_REMINDER_LEAD_MINUTES,
                            user_settings.timezone,
                        ),
                    ),
                    (
                        "pre10",
                        safe_notification_time(workout_at, 10, user_settings.timezone),
                    ),
                )
                for kind, scheduled_at in schedule:
                    if (
                        scheduled_at is None
                        or scheduled_at <= now
                        or (workout_at, kind) in existing
                    ):
                        continue
                    session.add(
                        Reminder(
                            user_id=user_id,
                            workout_at=workout_at,
                            scheduled_at=scheduled_at,
                            kind=kind,
                        )
                    )
                    existing.add((workout_at, kind))
                    created += 1
            return created

    async def rebuild_user_reminders(self, user_id: int) -> int:
        async with self.database.session() as session:
            await session.execute(
                delete(Reminder).where(
                    Reminder.user_id == user_id,
                    Reminder.status == "pending",
                    Reminder.scheduled_at > utc_now(),
                )
            )
        return await self.ensure_user_reminders(user_id)

    async def tick(self) -> None:
        if self.bot is None or self._tick_lock.locked():
            return
        async with self._tick_lock:
            try:
                await self.ensure_all_users()
                async with self.database.session() as session:
                    due = list(
                        (
                            await session.scalars(
                                select(Reminder)
                                .options(
                                    selectinload(Reminder.user).selectinload(User.settings)
                                )
                                .where(
                                    Reminder.status == "pending",
                                    Reminder.scheduled_at <= utc_now(),
                                )
                                .order_by(Reminder.scheduled_at)
                                .limit(20)
                            )
                        ).all()
                    )
                for reminder in due:
                    await self._deliver(reminder.id)
                self.last_error = None
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"[:500]
                logger.exception("Reminder scan failed")

    async def _deliver(self, reminder_id: int) -> None:
        assert self.bot is not None
        async with self.database.session() as session:
            reminder = await session.scalar(
                select(Reminder)
                .options(selectinload(Reminder.user).selectinload(User.settings))
                .where(Reminder.id == reminder_id)
            )
            if reminder is None or reminder.status != "pending":
                return
            if reminder.workout_at <= utc_now():
                reminder.status = "expired"
                return
            user = reminder.user
            prefs = user.settings
            if prefs is None or not prefs.reminders_enabled:
                reminder.status = "disabled"
                return
            if prefs.paused_until and prefs.paused_until > utc_now():
                reminder.status = "paused"
                return
            if is_quiet_hour(utc_now(), prefs.timezone):
                return
            if reminder.kind == "motivation":
                text = morning_motivation_text(reminder.workout_at, prefs.timezone)
                keyboard = None
            elif reminder.kind == "pre10":
                confirmed = await session.scalar(
                    select(WorkoutSession).where(
                        WorkoutSession.user_id == user.id,
                        WorkoutSession.scheduled_at == reminder.workout_at,
                        WorkoutSession.status.in_(("confirmed", "active")),
                    )
                )
                if confirmed is None:
                    reminder.status = "not_confirmed"
                    return
                text = "Через 10 минут тренировка. Программа уже готова — начинай, когда будешь на месте."
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🏋️ Начать тренировку",
                                callback_data=f"session:start:{confirmed.id}",
                            )
                        ]
                    ]
                )
            elif reminder.kind == "pre90":
                completed = await session.scalar(
                    select(func.count()).select_from(WorkoutSession).where(
                        WorkoutSession.user_id == user.id,
                        WorkoutSession.status == "completed",
                    )
                )
                templates = list(
                    (
                        await session.scalars(
                            select(WorkoutTemplate)
                            .where(WorkoutTemplate.active.is_(True))
                            .order_by(WorkoutTemplate.position)
                        )
                    ).all()
                )
                template = templates[int(completed or 0) % len(templates)]
                text = (
                    f"{pre_workout_motivation_text(reminder.workout_at, prefs.timezone)}\n\n"
                    f"Тренировка №{int(completed or 0) + 1}.\n"
                    f"Около 45 минут. Сегодня: {template.name.lower()}.\n\n"
                    "Ты сегодня идёшь?"
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Да, иду", callback_data=f"reminder:yes:{reminder.id}")],
                        [InlineKeyboardButton(text="Перенести", callback_data=f"reminder:move:{reminder.id}")],
                        [InlineKeyboardButton(text="Сегодня пропущу", callback_data=f"reminder:skip:{reminder.id}")],
                    ]
                )
            else:
                reminder.status = "unknown_kind"
                return
            try:
                await self.bot.send_message(user.telegram_id, text, reply_markup=keyboard)
            except Exception as exc:
                reminder.last_error = f"{type(exc).__name__}: {exc}"[:500]
                raise
            reminder.status = "sent"

    async def skip(self, reminder_id: int, telegram_id: int) -> datetime | None:
        async with self.database.session() as session:
            reminder = await session.scalar(
                select(Reminder).join(User).where(
                    Reminder.id == reminder_id, User.telegram_id == telegram_id
                )
            )
            if reminder is None:
                raise ValueError("Напоминание не найдено")
            await session.execute(
                Reminder.__table__.update()
                .where(
                    Reminder.user_id == reminder.user_id,
                    Reminder.workout_at == reminder.workout_at,
                )
                .values(status="skipped", responded_at=utc_now())
            )
            return await session.scalar(
                select(Reminder.workout_at)
                .where(
                    Reminder.user_id == reminder.user_id,
                    Reminder.kind == "pre90",
                    Reminder.status == "pending",
                    Reminder.workout_at > reminder.workout_at,
                )
                .order_by(Reminder.workout_at)
                .limit(1)
            )

    async def reschedule(
        self, reminder_id: int, telegram_id: int, new_workout_at: datetime
    ) -> None:
        async with self.database.session() as session:
            reminder = await session.scalar(
                select(Reminder)
                .join(User)
                .options(selectinload(Reminder.user).selectinload(User.settings))
                .where(Reminder.id == reminder_id, User.telegram_id == telegram_id)
            )
            if reminder is None:
                raise ValueError("Напоминание не найдено")
            if new_workout_at <= utc_now() + timedelta(minutes=15):
                raise ValueError("Выбери время хотя бы на 15 минут позже текущего")
            await session.execute(
                Reminder.__table__.update()
                .where(
                    Reminder.user_id == reminder.user_id,
                    Reminder.workout_at == reminder.workout_at,
                )
                .values(status="postponed", responded_at=utc_now())
            )
            timezone = reminder.user.settings.timezone if reminder.user.settings else "UTC"
            schedule = (
                ("motivation", morning_motivation_time(new_workout_at, timezone)),
                (
                    "pre90",
                    safe_notification_time(
                        new_workout_at,
                        PRIMARY_REMINDER_LEAD_MINUTES,
                        timezone,
                    ),
                ),
                ("pre10", safe_notification_time(new_workout_at, 10, timezone)),
            )
            for kind, scheduled_at in schedule:
                if scheduled_at is None or scheduled_at <= utc_now():
                    continue
                session.add(
                    Reminder(
                        user_id=reminder.user_id,
                        workout_at=new_workout_at,
                        scheduled_at=scheduled_at,
                        kind=kind,
                    )
                )
            try:
                await session.flush()
            except IntegrityError as exc:
                raise ValueError("На это время тренировка уже запланирована") from exc

    async def user_timezone(self, telegram_id: int) -> str:
        async with self.database.session() as session:
            timezone = await session.scalar(
                select(UserSettings.timezone).join(User).where(User.telegram_id == telegram_id)
            )
            return timezone or self.settings.timezone

    async def user_id(self, telegram_id: int) -> int:
        async with self.database.session() as session:
            user_id = await session.scalar(select(User.id).where(User.telegram_id == telegram_id))
            if user_id is None:
                raise ValueError("Пользователь не найден")
            return user_id
