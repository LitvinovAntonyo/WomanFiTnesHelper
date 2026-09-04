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
MORNING_MOTIVATION_TIME = time(7, 0)
PRIMARY_REMINDER_LEAD_MINUTES = 60
MORNING_MOTIVATIONS = (
    "Сегодня тренировка — немного времени только для тебя. Не нужно делать всё идеально, достаточно начать.",
    "Сегодня встреча с собой — в спортивной форме 💛 Ты тоже заслуживаешь места в своём расписании.",
    "Сегодня можно немного отвлечься от дел и переключиться на себя 🌿 Остальное ненадолго подождёт.",
    "Сегодня тренировочный день 💪 Начнём спокойно, без гонки и лишних требований к себе.",
    "Новый день — ещё одна возможность позаботиться о себе. Маленькие регулярные шаги важнее редких подвигов.",
    "Давай заранее найдём время для сегодняшней тренировки 🗓 Когда время выбрано, собраться уже немного проще.",
    "Сегодня не нужно побеждать весь мир — достаточно выделить время себе. Сделаем столько, сколько будет комфортно.",
    "Спортивная форма сегодня ждёт своего выхода 😊 Можно начать без особого настроения и посмотреть, как пойдёт.",
    "Пусть сегодня среди всех дел будет и одно для себя 🌸 Забота о себе — тоже важное дело.",
    "Сегодня тренировка! Не сравниваем себя с тем, что было раньше: двигаемся из той точки, где ты сейчас.",
    "Давай оставим в сегодняшнем расписании немного места для движения. Твой темп — вполне подходящий темп.",
    "Сегодня продолжаем возвращать тренировки в привычную жизнь 🌿 Без спешки: привычка складывается из таких обычных дней.",
    "Сегодня можно на время отложить заботы и сосредоточиться на себе. Не ради чужих ожиданий — ради тебя.",
    "До тренировки пока только один маленький шаг — выбрать время 😊 Со всем остальным разберёмся по порядку.",
    "Сегодня день движения! Не обязательно выкладываться на максимум, чтобы занятие имело смысл.",
    "Давай сегодня поддержим себя не только добрыми словами, но и действием. Спокойная тренировка тоже считается.",
    "В планах на сегодня — тренировка и немного внимания к себе. Ты не обязана быть в идеальной форме, чтобы заботиться о ней.",
    "Сегодня ещё один шаг к привычке, которую ты создаёшь для себя 💛 Каждое занятие — отдельный маленький вклад.",
    "Если день обещает быть насыщенным, давай заранее выберем время для зала. Пусть твои планы на себя тоже будут в приоритете.",
    "Сегодня тренировка! Не проверяем, на что ты способна через силу, — просто продолжаем двигаться.",
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
    return hour < 7 or hour >= 22


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
    """Return the 07:00 local prompt time for the given training date."""
    tz = ZoneInfo(timezone)
    workout_local = utc_naive_to_local(workout_at, timezone)
    candidate = datetime.combine(
        workout_local.date(), MORNING_MOTIVATION_TIME, tzinfo=tz
    )
    if candidate >= workout_local:
        return None
    return local_to_utc_naive(candidate)


def morning_motivation_text(workout_at: datetime, timezone: str, name: str = "") -> str:
    workout_date = utc_naive_to_local(workout_at, timezone).date()
    message = MORNING_MOTIVATIONS[workout_date.toordinal() % len(MORNING_MOTIVATIONS)]
    greeting = f"Доброе утро, {name}!" if name else "Доброе утро!"
    return f"{greeting} ☀️\n\n{message}\n\nВо сколько сегодня пойдём на тренировку? Время — твоё местное."


def daily_time_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"В {hour}:00", callback_data=f"daily:time:{reminder_id}:{hour}00")
         for hour in (18, 19, 20)],
        [InlineKeyboardButton(text="Другое время", callback_data=f"daily:custom:{reminder_id}")],
        [InlineKeyboardButton(text="Сегодня не получится", callback_data=f"daily:skip:{reminder_id}")],
    ])


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
        self._choice_lock = asyncio.Lock()
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
            tz = ZoneInfo(user_settings.timezone)
            today = utc_naive_to_local(now, user_settings.timezone).date()
            selected_days = set(parse_days(user_settings.workout_days))
            booked_times = await session.scalars(select(Reminder.workout_at).where(
                Reminder.user_id == user_id, Reminder.kind == "pre90",
                Reminder.status.in_(("pending", "sent", "accepted")), Reminder.workout_at > now,
            ))
            booked_dates = {utc_naive_to_local(at, user_settings.timezone).date()
                            for at in booked_times}
            for offset in range(36):
                day = today + timedelta(days=offset)
                if day.weekday() not in selected_days or day in booked_dates:
                    continue
                # The end-of-day anchor is NOT a workout time; it gives the prompt
                # a stable per-user/date key and expires old buttons at midnight.
                anchor = local_to_utc_naive(datetime.combine(day, time(23, 59, 59), tzinfo=tz))
                scheduled_at = morning_motivation_time(anchor, user_settings.timezone)
                if scheduled_at is None or scheduled_at <= now or (anchor, "daily_time") in existing:
                    continue
                session.add(Reminder(user_id=user_id, workout_at=anchor,
                                     scheduled_at=scheduled_at, kind="daily_time"))
                existing.add((anchor, "daily_time"))
                created += 1
            return created

    async def rebuild_user_reminders(self, user_id: int) -> int:
        async with self.database.session() as session:
            await session.execute(
                delete(Reminder).where(
                    Reminder.user_id == user_id,
                    Reminder.kind == "daily_time",
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
        async with self._choice_lock, self.database.session() as session:
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
            if reminder.kind == "daily_time" and utc_now() - reminder.scheduled_at >= timedelta(hours=1):
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
            local_hour = utc_naive_to_local(utc_now(), prefs.timezone).hour
            if local_hour < 7 or local_hour >= 22:
                return
            if reminder.kind == "daily_time":
                text = morning_motivation_text(reminder.workout_at, prefs.timezone, user.display_name or "")
                keyboard = daily_time_keyboard(reminder.id)
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
                    f"Напоминаю: сегодня тренировка в {utc_naive_to_local(reminder.workout_at, prefs.timezone):%H:%M} по твоему местному времени.\n"
                    f"Тренировка №{int(completed or 0) + 1}.\n"
                    f"Около 50–60 минут. Сегодня: {template.name.lower()}.\n\n"
                    "Всё в силе?"
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

    async def choose_daily_time(
        self, reminder_id: int, telegram_id: int, clock: str | None
    ) -> tuple[datetime, datetime | None] | None:
        """Persist one owned, same-day choice; no reminder exists until this call."""
        async with self._choice_lock, self.database.session() as session:
            reminder = await session.scalar(
                select(Reminder).join(User)
                .options(selectinload(Reminder.user).selectinload(User.settings))
                .where(Reminder.id == reminder_id, User.telegram_id == telegram_id,
                       Reminder.kind == "daily_time")
            )
            if reminder is None or reminder.user.settings is None:
                raise ValueError("Вопрос о времени не найден.")
            prefs = reminder.user.settings
            now = utc_now()
            local_now = utc_naive_to_local(now, prefs.timezone)
            day = utc_naive_to_local(reminder.workout_at, prefs.timezone).date()
            if day != local_now.date():
                raise ValueError("Этот вопрос был на другой день. Выбери сегодняшнее сообщение.")
            if reminder.status not in ("pending", "sent"):
                raise ValueError("Ответ уже сохранён. Повторно выбирать время не нужно.")
            if not prefs.reminders_enabled or (prefs.paused_until and prefs.paused_until > now):
                raise ValueError("Напоминания на паузе или отключены. Сначала включи их в настройках.")
            if clock is None:
                reminder.status = "skipped"
                reminder.responded_at = now
                return None
            try:
                parsed = datetime.strptime(clock, "%H:%M").time()
            except ValueError as exc:
                raise ValueError("Напиши время как 19:00, с 08:00 до 22:00.") from exc
            if not time(8) <= parsed <= time(22):
                raise ValueError("Выбери время с 08:00 до 22:00.")
            workout_at = local_to_utc_naive(datetime.combine(day, parsed, tzinfo=ZoneInfo(prefs.timezone)))
            if workout_at <= now:
                raise ValueError("Это время уже прошло. Выбери более позднее время сегодня.")
            due = workout_at - timedelta(minutes=PRIMARY_REMINDER_LEAD_MINUTES)
            existing = await session.scalar(select(Reminder.id).where(
                Reminder.user_id == reminder.user_id, Reminder.workout_at == workout_at,
                Reminder.kind == "pre90",
            ))
            if existing is not None:
                raise ValueError("На это время тренировка уже запланирована.")
            session.add(Reminder(user_id=reminder.user_id, workout_at=workout_at,
                                 scheduled_at=due, kind="pre90",
                                 status="pending" if due > now else "sent"))
            reminder.status = "chosen"
            reminder.responded_at = now
            return workout_at, due if due > now else None

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
            local_clock = utc_naive_to_local(new_workout_at, timezone).time()
            if not time(8) <= local_clock <= time(22):
                raise ValueError("Выбери время с 08:00 до 22:00 по местному времени.")
            schedule = (("pre90", new_workout_at - timedelta(minutes=60)),)
            for kind, scheduled_at in schedule:
                session.add(
                    Reminder(
                        user_id=reminder.user_id,
                        workout_at=new_workout_at,
                        scheduled_at=scheduled_at,
                        kind=kind,
                        status="pending" if scheduled_at > utc_now() else "sent",
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

    async def reminder_local_time(self, reminder_id: int, telegram_id: int) -> datetime:
        async with self.database.session() as session:
            reminder = await session.scalar(select(Reminder).join(User)
                .options(selectinload(Reminder.user).selectinload(User.settings))
                .where(Reminder.id == reminder_id, User.telegram_id == telegram_id,
                       Reminder.kind == "pre90"))
            if reminder is None or reminder.user.settings is None:
                raise ValueError("Тренировка не найдена.")
            return utc_naive_to_local(reminder.workout_at, reminder.user.settings.timezone)

    async def user_id(self, telegram_id: int) -> int:
        async with self.database.session() as session:
            user_id = await session.scalar(select(User.id).where(User.telegram_id == telegram_id))
            if user_id is None:
                raise ValueError("Пользователь не найден")
            return user_id
