from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.database import Database
from app.exercise_library import CARDIO_CODES, alternative_code_for, rest_seconds_for
from app.models import (
    Achievement,
    Exercise,
    ExerciseOutcome,
    ExerciseResult,
    ExerciseSetResult,
    Reminder,
    TelegramMediaCache,
    User,
    WorkoutExercise,
    WorkoutSession,
    WorkoutSessionFeedback,
    WorkoutTemplate,
    utc_now,
)


@dataclass(slots=True)
class WorkoutStep:
    session: WorkoutSession
    result: ExerciseResult
    item: WorkoutExercise
    exercise: Exercise
    previous_weight: Decimal | None


@dataclass(frozen=True, slots=True)
class WeightChange:
    exercise_name: str
    previous_kg: Decimal
    current_kg: Decimal


@dataclass(slots=True)
class WorkoutSummary:
    duration_minutes: int
    completed_exercises: int
    skipped_exercises: int
    weight_changes: tuple[WeightChange, ...] = ()


@dataclass(frozen=True, slots=True)
class SetLogState:
    session_id: int
    result_id: int
    set_number: int
    completed_sets: int
    sets_planned: int
    exercise_complete: bool
    rest_seconds: int


DEFAULT_TEMPLATES: tuple[dict[str, object], ...] = (
    {
        "code": "return_full_body_a_v4",
        "name": "A · всё тело — ягодицы и задняя поверхность бедра",
        "focus": "Всё тело: акцент на ягодицы и заднюю поверхность бедра.",
        "items": (
            ("cardio_treadmill", "Кардио на выбор", False, 1, None, 10, "Разогрев в разговорном темпе."),
            ("seated_leg_curl", "Сгибание ног сидя", True, 3, 15, None, "Прижимай таз и возвращай вес медленно."),
            ("glute_kickback", "Отведение ноги назад в тренажёре", True, 3, 15, None, "Работай ягодицей без прогиба в пояснице."),
            ("hip_abduction", "Разведение бёдер в тренажёре", True, 3, 20, None, "Разводи колени без рывка и контролируй возврат."),
            ("lat_pulldown", "Тяга верхнего блока", True, 3, 12, None, "Тяни лопатками, без раскачки."),
            ("chest_press", "Жим в тренажёре", True, 3, 12, None, "Оставляй движение контролируемым."),
        ),
    },
    {
        "code": "return_full_body_b_v4",
        "name": "B · всё тело — квадрицепс и внутренняя поверхность бедра",
        "focus": "Всё тело: акцент на квадрицепс и внутреннюю поверхность бедра.",
        "items": (
            ("cardio_treadmill", "Кардио на выбор", False, 1, None, 10, "Разогрев в разговорном темпе."),
            ("hack_squat", "Гакк-присед", True, 3, 12, None, "Держи спину и таз прижатыми к опоре."),
            ("leg_extension", "Разгибание ног в тренажёре", True, 3, 15, None, "Разгибай колени плавно, без жёсткой блокировки."),
            ("hip_adduction", "Сведение бёдер в тренажёре", True, 3, 20, None, "Своди колени плавно и удерживай таз неподвижно."),
            ("seated_row", "Горизонтальная тяга", True, 3, 12, None, "Не округляй поясницу."),
            ("chest_press", "Жим в тренажёре", True, 3, 12, None, "Оставляй движение контролируемым."),
        ),
    },
    {
        "code": "return_full_body_c_v4",
        "name": "C · всё тело — ноги и ягодицы",
        "focus": "Всё тело: сбалансированный акцент на ноги и ягодицы.",
        "items": (
            ("cardio_treadmill", "Кардио на выбор", False, 1, None, 10, "Разогрев в разговорном темпе."),
            ("leg_press", "Жим ногами", True, 3, 12, None, "Работай без боли и не блокируй колени."),
            ("seated_leg_curl", "Сгибание ног сидя", True, 3, 15, None, "Прижимай таз и возвращай вес медленно."),
            ("glute_kickback", "Отведение ноги назад в тренажёре", True, 3, 15, None, "Работай ягодицей без прогиба в пояснице."),
            ("lat_pulldown", "Тяга верхнего блока", True, 3, 12, None, "Тяни лопатками, без раскачки."),
            ("machine_shoulder_press", "Жим вверх в тренажёре", True, 3, 12, None, "Не поднимай плечи к ушам и не блокируй локти."),
        ),
    },
)


EXTRA_EXERCISES: tuple[tuple[str, str, bool, str], ...] = (
    ("cardio_elliptical", "Кардио на эллипсе", False, "Разогрев в разговорном темпе."),
    ("cardio_bike", "Кардио на велотренажёре", False, "Разогрев в разговорном темпе."),
    ("hack_squat", "Гакк-присед", True, "Держи спину и таз прижатыми к опоре."),
    ("pec_deck", "Сведение рук в тренажёре", True, "Держи спину на опоре и не заводи локти далеко назад."),
    ("machine_shoulder_press", "Жим вверх в тренажёре", True, "Не поднимай плечи к ушам и не блокируй локти."),
)


class WorkoutService:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    async def _last_logged_set_for_exercise(
        session: AsyncSession,
        *,
        user_id: int,
        exercise_id: int,
        excluded_session_id: int,
        require_weight: bool = False,
        completed_before: datetime | None = None,
    ) -> ExerciseSetResult | None:
        statement = (
            select(ExerciseSetResult)
            .join(ExerciseResult)
            .join(WorkoutSession)
            .join(
                WorkoutExercise,
                ExerciseResult.workout_exercise_id == WorkoutExercise.id,
            )
            .outerjoin(
                ExerciseOutcome,
                ExerciseOutcome.exercise_result_id == ExerciseResult.id,
            )
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status == "completed",
                WorkoutSession.id != excluded_session_id,
                func.coalesce(
                    ExerciseOutcome.effective_exercise_id,
                    WorkoutExercise.exercise_id,
                )
                == exercise_id,
            )
            .order_by(
                WorkoutSession.completed_at.desc(),
                ExerciseSetResult.set_number.desc(),
            )
            .limit(1)
        )
        if require_weight:
            statement = statement.where(ExerciseSetResult.weight_kg.is_not(None))
        if completed_before is not None:
            statement = statement.where(
                WorkoutSession.completed_at < completed_before
            )
        return await session.scalar(statement)

    async def seed_templates(self) -> None:
        async with self.database.session() as session:
            exercises = {
                exercise.code: exercise
                for exercise in (await session.scalars(select(Exercise))).all()
            }
            for code, name, weighted, instructions in EXTRA_EXERCISES:
                if code not in exercises:
                    exercise = Exercise(
                        code=code,
                        name=name,
                        requires_weight=weighted,
                        instructions=instructions,
                    )
                    session.add(exercise)
                    await session.flush()
                    exercises[code] = exercise
            desired_codes = {str(definition["code"]) for definition in DEFAULT_TEMPLATES}
            for template_position, definition in enumerate(DEFAULT_TEMPLATES, start=1):
                existing_template = await session.scalar(
                    select(WorkoutTemplate).where(
                        WorkoutTemplate.code == str(definition["code"])
                    )
                )
                if existing_template is not None:
                    existing_template.active = True
                    existing_template.position = template_position
                    continue
                template = WorkoutTemplate(
                    code=str(definition["code"]),
                    name=str(definition["name"]),
                    focus=str(definition["focus"]),
                    position=template_position,
                )
                session.add(template)
                await session.flush()
                for position, raw in enumerate(definition["items"], start=1):  # type: ignore[arg-type]
                    code, name, weighted, sets, reps, duration, instructions = raw
                    exercise = exercises.get(code)
                    if exercise is None:
                        exercise = Exercise(
                            code=code,
                            name=name,
                            requires_weight=weighted,
                            instructions=instructions,
                        )
                        session.add(exercise)
                        await session.flush()
                        exercises[code] = exercise
                    session.add(
                        WorkoutExercise(
                            template_id=template.id,
                            exercise_id=exercise.id,
                            position=position,
                            sets=sets,
                            reps=reps,
                            duration_minutes=duration,
                        )
                    )
            await session.execute(
                update(WorkoutTemplate)
                .where(WorkoutTemplate.code.not_in(desired_codes))
                .values(active=False)
            )

    async def _pick_template_id(self, session: object, user_id: int) -> int:
        completed = await session.scalar(  # type: ignore[attr-defined]
            select(func.count()).select_from(WorkoutSession).join(WorkoutTemplate).where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status == "completed",
                WorkoutTemplate.active.is_(True),
            )
        )
        templates = list(
            (
                await session.scalars(  # type: ignore[attr-defined]
                    select(WorkoutTemplate)
                    .where(WorkoutTemplate.active.is_(True))
                    .order_by(WorkoutTemplate.position)
                )
            ).all()
        )
        if not templates:
            raise RuntimeError("Нет активных шаблонов тренировок")
        return templates[int(completed or 0) % len(templates)].id

    async def create_session(
        self,
        user_id: int,
        *,
        scheduled_at: datetime | None = None,
        reminder_id: int | None = None,
        status: str = "confirmed",
    ) -> WorkoutSession:
        async with self.database.session() as session:
            if reminder_id is not None:
                existing = await session.scalar(
                    select(WorkoutSession)
                    .options(selectinload(WorkoutSession.results))
                    .where(WorkoutSession.reminder_id == reminder_id)
                )
                if existing:
                    return existing
            template_id = await self._pick_template_id(session, user_id)
            completed_count = int(
                await session.scalar(
                    select(func.count()).select_from(WorkoutSession).join(WorkoutTemplate).where(
                        WorkoutSession.user_id == user_id,
                        WorkoutSession.status == "completed",
                        WorkoutTemplate.active.is_(True),
                    )
                )
                or 0
            )
            workout = WorkoutSession(
                user_id=user_id,
                template_id=template_id,
                reminder_id=reminder_id,
                scheduled_at=scheduled_at,
                status=status,
            )
            session.add(workout)
            await session.flush()
            items = list(
                (
                    await session.scalars(
                        select(WorkoutExercise)
                        .where(WorkoutExercise.template_id == template_id)
                        .order_by(WorkoutExercise.position)
                    )
                ).all()
            )
            for item in items:
                reps = await self._adapted_reps(session, user_id, item)
                sets_planned = (
                    min(item.sets, 2)
                    if completed_count < 6 and item.reps is not None
                    else item.sets
                )
                session.add(
                    ExerciseResult(
                        session_id=workout.id,
                        workout_exercise_id=item.id,
                        sets_planned=sets_planned,
                        reps=reps,
                    )
                )
            await session.flush()
            return workout

    async def _adapted_reps(
        self, session: object, user_id: int, item: WorkoutExercise
    ) -> int | None:
        """Apply a deliberately small, explainable adjustment to the next session."""
        if item.reps is None:
            return None
        efforts = list(
            (
                await session.scalars(  # type: ignore[attr-defined]
                    select(ExerciseOutcome.effort)
                    .join(ExerciseResult)
                    .join(WorkoutSession)
                    .join(WorkoutExercise, ExerciseResult.workout_exercise_id == WorkoutExercise.id)
                    .where(
                        WorkoutSession.user_id == user_id,
                        WorkoutSession.status == "completed",
                        WorkoutExercise.exercise_id == item.exercise_id,
                        ExerciseOutcome.status == "completed",
                        ExerciseOutcome.effort.is_not(None),
                    )
                    .order_by(ExerciseOutcome.updated_at.desc())
                    .limit(2)
                )
            ).all()
        )
        if len(efforts) == 2 and efforts == ["easy", "easy"]:
            return item.reps + 1
        if efforts and efforts[0] == "hard":
            return max(6, item.reps - 1)
        return item.reps

    async def confirm_from_reminder(self, reminder_id: int, telegram_id: int) -> WorkoutSession:
        async with self.database.session() as session:
            reminder = await session.scalar(
                select(Reminder).join(User).where(
                    Reminder.id == reminder_id,
                    User.telegram_id == telegram_id,
                )
            )
            if reminder is None:
                raise ValueError("Напоминание не найдено")
            reminder.status = "accepted"
            reminder.responded_at = utc_now()
            user_id = reminder.user_id
            workout_at = reminder.workout_at
        return await self.create_session(
            user_id, scheduled_at=workout_at, reminder_id=reminder_id, status="confirmed"
        )

    async def active_or_new(self, telegram_id: int) -> WorkoutSession:
        async with self.database.session() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user is None:
                raise ValueError("Сначала пройди настройку через /start")
            active = await session.scalar(
                select(WorkoutSession)
                .where(
                    WorkoutSession.user_id == user.id,
                    WorkoutSession.status.in_(("confirmed", "active")),
                )
                .order_by(WorkoutSession.created_at.desc())
            )
            if active:
                return active
            user_id = user.id
        return await self.create_session(user_id, status="active")

    async def reset_current_day(self, telegram_id: int) -> bool:
        """Remove the current test workout without touching earlier training days."""
        async with self.database.session() as session:
            user = await session.scalar(
                select(User)
                .options(joinedload(User.settings))
                .where(User.telegram_id == telegram_id)
            )
            if user is None:
                raise ValueError("Сначала пройди настройку через /start")

            workout = await session.scalar(
                select(WorkoutSession)
                .where(
                    WorkoutSession.user_id == user.id,
                    WorkoutSession.status.in_(("confirmed", "active")),
                )
                .order_by(WorkoutSession.created_at.desc())
            )
            if workout is None:
                timezone = ZoneInfo(
                    user.settings.timezone if user.settings else "Asia/Yekaterinburg"
                )
                local_now = datetime.now(timezone)
                local_start = datetime.combine(local_now.date(), time.min, tzinfo=timezone)
                day_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                day_end = (local_start + timedelta(days=1)).astimezone(
                    ZoneInfo("UTC")
                ).replace(tzinfo=None)
                workout = await session.scalar(
                    select(WorkoutSession)
                    .where(
                        WorkoutSession.user_id == user.id,
                        WorkoutSession.status == "completed",
                        WorkoutSession.completed_at >= day_start,
                        WorkoutSession.completed_at < day_end,
                    )
                    .order_by(WorkoutSession.completed_at.desc())
                )
            if workout is None:
                return False

            await session.delete(workout)
            await session.flush()
            completed_count = int(
                await session.scalar(
                    select(func.count()).select_from(WorkoutSession).where(
                        WorkoutSession.user_id == user.id,
                        WorkoutSession.status == "completed",
                    )
                )
                or 0
            )
            for threshold, code in ((3, "bronze_3"), (5, "silver_5"), (10, "gold_10")):
                if completed_count < threshold:
                    achievement = await session.scalar(
                        select(Achievement).where(
                            Achievement.user_id == user.id,
                            Achievement.code == code,
                        )
                    )
                    if achievement is not None:
                        await session.delete(achievement)
            return True

    async def begin(self, session_id: int, telegram_id: int) -> WorkoutSession:
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .join(User)
                .where(WorkoutSession.id == session_id, User.telegram_id == telegram_id)
            )
            if workout is None:
                raise ValueError("Тренировка не найдена")
            if workout.status == "completed":
                return workout
            workout.status = "active"
            workout.started_at = workout.started_at or utc_now()
            return workout

    async def choose_cardio(
        self, session_id: int, telegram_id: int, cardio_code: str
    ) -> None:
        if cardio_code not in CARDIO_CODES:
            raise ValueError("Неизвестный вариант кардио")
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .join(User)
                .where(WorkoutSession.id == session_id, User.telegram_id == telegram_id)
            )
            if workout is None:
                raise ValueError("Тренировка не найдена")
            first_result = await session.scalar(
                select(ExerciseResult)
                .options(joinedload(ExerciseResult.outcome))
                .join(WorkoutExercise)
                .where(ExerciseResult.session_id == session_id)
                .order_by(WorkoutExercise.position)
                .limit(1)
            )
            selected = await session.scalar(select(Exercise).where(Exercise.code == cardio_code))
            if first_result is None or selected is None:
                raise ValueError("Кардио пока недоступно")
            outcome = first_result.outcome
            if outcome is None:
                outcome = ExerciseOutcome(exercise_result_id=first_result.id)
                session.add(outcome)
            outcome.effective_exercise = selected
            outcome.status = "pending"
            outcome.effort = None

    async def get_plan(self, session_id: int, telegram_id: int) -> WorkoutSession:
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .options(
                    selectinload(WorkoutSession.template)
                    .selectinload(WorkoutTemplate.items)
                    .selectinload(WorkoutExercise.exercise),
                    selectinload(WorkoutSession.results),
                )
                .join(User)
                .where(WorkoutSession.id == session_id, User.telegram_id == telegram_id)
            )
            if workout is None:
                raise ValueError("Тренировка не найдена")
            return workout

    async def get_step(self, session_id: int, telegram_id: int) -> WorkoutStep | None:
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .options(
                    selectinload(WorkoutSession.template).selectinload(
                        WorkoutTemplate.items
                    )
                )
                .join(User)
                .where(WorkoutSession.id == session_id, User.telegram_id == telegram_id)
            )
            if workout is None:
                raise ValueError("Тренировка не найдена")
            result = await session.scalar(
                select(ExerciseResult)
                .options(
                    joinedload(ExerciseResult.workout_exercise).joinedload(WorkoutExercise.exercise),
                    joinedload(ExerciseResult.outcome).joinedload(
                        ExerciseOutcome.effective_exercise
                    ),
                )
                .join(WorkoutExercise)
                .where(
                    ExerciseResult.session_id == session_id,
                    ExerciseResult.completed.is_(False),
                )
                .order_by(WorkoutExercise.position)
            )
            if result is None:
                return None
            item = result.workout_exercise
            exercise = (
                result.outcome.effective_exercise
                if result.outcome and result.outcome.effective_exercise
                else item.exercise
            )
            previous_set = await self._last_logged_set_for_exercise(
                session,
                user_id=workout.user_id,
                exercise_id=exercise.id,
                excluded_session_id=workout.id,
                require_weight=True,
            )
            return WorkoutStep(
                session=workout,
                result=result,
                item=item,
                exercise=exercise,
                previous_weight=previous_set.weight_kg if previous_set else None,
            )

    async def replace_exercise(self, result_id: int, telegram_id: int) -> int:
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .options(
                    joinedload(ExerciseResult.workout_exercise).joinedload(WorkoutExercise.exercise),
                    joinedload(ExerciseResult.outcome).joinedload(
                        ExerciseOutcome.effective_exercise
                    ),
                )
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            if result.completed_sets:
                raise ValueError("Замену можно выбрать до первого подхода")
            item = result.workout_exercise
            current = (
                result.outcome.effective_exercise
                if result.outcome and result.outcome.effective_exercise
                else item.exercise
            )
            alternative_code = alternative_code_for(current.code)
            if alternative_code is None:
                raise ValueError("Для этого шага нет готовой безопасной замены")
            alternative = await session.scalar(
                select(Exercise).where(Exercise.code == alternative_code)
            )
            if alternative is None:
                raise ValueError("Замена пока недоступна")
            outcome = result.outcome
            if outcome is None:
                outcome = ExerciseOutcome(exercise_result_id=result.id)
                session.add(outcome)
                result.outcome = outcome
            outcome.effective_exercise = alternative
            outcome.status = "pending"
            outcome.effort = None
            await session.flush()
            return result.session_id

    async def skip_exercise(self, result_id: int, telegram_id: int) -> int:
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .options(joinedload(ExerciseResult.outcome))
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            outcome = result.outcome
            if outcome is None:
                outcome = ExerciseOutcome(exercise_result_id=result.id)
                session.add(outcome)
            outcome.status = "skipped"
            outcome.effort = None
            result.completed = True
            return result.session_id

    async def enable_light_mode(self, session_id: int, telegram_id: int) -> int:
        """Reduce only untouched strength exercises to two planned sets."""
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .join(User)
                .where(WorkoutSession.id == session_id, User.telegram_id == telegram_id)
            )
            if workout is None:
                raise ValueError("Тренировка не найдена")

            results = list(
                (
                    await session.scalars(
                        select(ExerciseResult).where(
                            ExerciseResult.session_id == workout.id,
                            ExerciseResult.reps.is_not(None),
                            ExerciseResult.completed_sets == 0,
                            ExerciseResult.completed.is_(False),
                        )
                    )
                ).all()
            )
            changed = 0
            for result in results:
                reduced_sets = min(result.sets_planned, 2)
                if reduced_sets != result.sets_planned:
                    result.sets_planned = reduced_sets
                    changed += 1
            return changed

    async def stop_for_discomfort(self, result_id: int, telegram_id: int) -> int:
        """Stop the current exercise without inventing completed sets."""
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            workout = await session.get(WorkoutSession, result.session_id)
            if workout is None or workout.status != "active":
                raise ValueError("Остановить можно только текущее упражнение")
            current_result_id = await session.scalar(
                select(ExerciseResult.id)
                .join(WorkoutExercise)
                .where(
                    ExerciseResult.session_id == workout.id,
                    ExerciseResult.completed.is_(False),
                )
                .order_by(WorkoutExercise.position)
                .limit(1)
            )
            if current_result_id != result.id:
                raise ValueError("Остановить можно только текущее упражнение")
            stopped = await session.execute(
                update(ExerciseResult)
                .where(
                    ExerciseResult.id == result.id,
                    ExerciseResult.completed.is_(False),
                )
                .values(completed=True)
            )
            if stopped.rowcount != 1:
                raise ValueError("Остановить можно только текущее упражнение")
            pain_outcome = sqlite_insert(ExerciseOutcome).values(
                exercise_result_id=result.id,
                status="pain",
                effort="pain",
            )
            await session.execute(
                pain_outcome.on_conflict_do_update(
                    index_elements=[ExerciseOutcome.exercise_result_id],
                    set_={
                        "status": "pain",
                        "effort": "pain",
                        "updated_at": utc_now(),
                    },
                )
            )
            return result.session_id

    async def record_session_feedback(
        self, session_id: int, telegram_id: int, effort: str
    ) -> None:
        if effort not in {"easy", "ok", "hard"}:
            raise ValueError("Выбери оценку тренировки: легко, нормально или тяжело")
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .join(User)
                .where(
                    WorkoutSession.id == session_id,
                    WorkoutSession.status == "completed",
                    User.telegram_id == telegram_id,
                )
            )
            if workout is None:
                raise ValueError("Завершённая тренировка не найдена")
            feedback_upsert = sqlite_insert(WorkoutSessionFeedback).values(
                session_id=workout.id,
                effort=effort,
            )
            await session.execute(
                feedback_upsert.on_conflict_do_update(
                    index_elements=[WorkoutSessionFeedback.session_id],
                    set_={"effort": effort, "updated_at": utc_now()},
                )
            )

    async def record_effort(
        self, result_id: int, telegram_id: int, effort: str | None
    ) -> int:
        if effort not in {None, "easy", "ok", "hard", "pain"}:
            raise ValueError("Неизвестная оценка нагрузки")
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .options(joinedload(ExerciseResult.outcome))
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            outcome = result.outcome
            if outcome is None:
                outcome = ExerciseOutcome(exercise_result_id=result.id)
                session.add(outcome)
            outcome.status = "completed"
            outcome.effort = effort
            return result.session_id

    async def result_state(
        self, result_id: int, telegram_id: int
    ) -> tuple[int, int, int, bool, bool]:
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .options(joinedload(ExerciseResult.workout_exercise).joinedload(WorkoutExercise.exercise))
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            return (
                result.session_id,
                result.completed_sets,
                result.sets_planned,
                result.completed,
                result.workout_exercise.exercise.requires_weight,
            )

    async def media_file_id(self, asset_key: str) -> str | None:
        async with self.database.session() as session:
            return await session.scalar(
                select(TelegramMediaCache.file_id).where(
                    TelegramMediaCache.asset_key == asset_key
                )
            )

    async def remember_media_file_id(self, asset_key: str, file_id: str) -> None:
        async with self.database.session() as session:
            cached = await session.scalar(
                select(TelegramMediaCache).where(TelegramMediaCache.asset_key == asset_key)
            )
            if cached is None:
                session.add(TelegramMediaCache(asset_key=asset_key, file_id=file_id))
            else:
                cached.file_id = file_id

    async def set_weight(
        self, result_id: int, telegram_id: int, weight: Decimal
    ) -> ExerciseResult:
        if weight < 0 or weight > Decimal("1000"):
            raise ValueError("Укажи вес от 0 до 1000 кг")
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            result.weight_kg = weight.quantize(Decimal("0.01"))
            return result

    async def record_set(
        self,
        result_id: int,
        telegram_id: int,
        reps: int,
        weight_kg: Decimal | None,
    ) -> SetLogState:
        if not 1 <= reps <= 100:
            raise ValueError("Укажи от 1 до 100 повторений")
        if weight_kg is not None and not Decimal("0") <= weight_kg <= Decimal("999"):
            raise ValueError("Укажи вес от 0 до 999 кг")
        normalized_weight = (
            weight_kg.quantize(Decimal("0.01")) if weight_kg is not None else None
        )

        try:
            async with self.database.session() as session:
                result = await session.scalar(
                    select(ExerciseResult)
                    .options(
                        joinedload(ExerciseResult.workout_exercise).joinedload(
                            WorkoutExercise.exercise
                        ),
                        joinedload(ExerciseResult.outcome).joinedload(
                            ExerciseOutcome.effective_exercise
                        ),
                    )
                    .join(WorkoutSession)
                    .join(User)
                    .where(
                        ExerciseResult.id == result_id,
                        User.telegram_id == telegram_id,
                    )
                )
                if result is None:
                    raise ValueError("Упражнение не найдено")
                if result.completed or result.completed_sets >= result.sets_planned:
                    raise ValueError("Упражнение уже завершено")

                next_number = result.completed_sets + 1
                session.add(
                    ExerciseSetResult(
                        exercise_result_id=result.id,
                        set_number=next_number,
                        reps=reps,
                        weight_kg=normalized_weight,
                    )
                )
                await session.flush()

                result.completed_sets = next_number
                result.reps = reps
                result.weight_kg = normalized_weight
                result.completed = next_number >= result.sets_planned
                exercise = (
                    result.outcome.effective_exercise
                    if result.outcome and result.outcome.effective_exercise
                    else result.workout_exercise.exercise
                )
                return SetLogState(
                    session_id=result.session_id,
                    result_id=result.id,
                    set_number=next_number,
                    completed_sets=result.completed_sets,
                    sets_planned=result.sets_planned,
                    exercise_complete=result.completed,
                    rest_seconds=rest_seconds_for(exercise.code) or 0,
                )
        except IntegrityError as exc:
            raise ValueError("Этот подход уже записан") from exc

    async def repeat_last_set(
        self, result_id: int, telegram_id: int
    ) -> SetLogState:
        values = await self.last_set_values(result_id, telegram_id)
        if values is None:
            raise ValueError("Нет предыдущего подхода для повтора")
        weight_kg, reps = values
        return await self.record_set(result_id, telegram_id, reps, weight_kg)

    async def last_set_values(
        self, result_id: int, telegram_id: int
    ) -> tuple[Decimal | None, int] | None:
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .options(
                    joinedload(ExerciseResult.session),
                    joinedload(ExerciseResult.workout_exercise).joinedload(
                        WorkoutExercise.exercise
                    ),
                    joinedload(ExerciseResult.outcome).joinedload(
                        ExerciseOutcome.effective_exercise
                    ),
                )
                .join(WorkoutSession)
                .join(User)
                .where(
                    ExerciseResult.id == result_id,
                    User.telegram_id == telegram_id,
                )
            )
            if result is None:
                raise ValueError("Упражнение не найдено")

            previous = await session.scalar(
                select(ExerciseSetResult)
                .where(ExerciseSetResult.exercise_result_id == result.id)
                .order_by(ExerciseSetResult.set_number.desc())
                .limit(1)
            )
            if previous is None:
                exercise = (
                    result.outcome.effective_exercise
                    if result.outcome and result.outcome.effective_exercise
                    else result.workout_exercise.exercise
                )
                previous = await self._last_logged_set_for_exercise(
                    session,
                    user_id=result.session.user_id,
                    exercise_id=exercise.id,
                    excluded_session_id=result.session_id,
                )
            if previous is None:
                return None
            return previous.weight_kg, previous.reps

    async def complete_next_set(self, result_id: int, telegram_id: int) -> tuple[int, bool]:
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .options(joinedload(ExerciseResult.workout_exercise))
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            if result.completed_sets < result.sets_planned:
                result.completed_sets += 1
            if result.completed_sets >= result.sets_planned:
                result.completed = True
            return result.session_id, result.completed

    async def complete_exercise(self, result_id: int, telegram_id: int) -> int:
        """Mark the whole prescribed exercise complete without collecting set/weight data."""
        async with self.database.session() as session:
            result = await session.scalar(
                select(ExerciseResult)
                .join(WorkoutSession)
                .join(User)
                .where(ExerciseResult.id == result_id, User.telegram_id == telegram_id)
            )
            if result is None:
                raise ValueError("Упражнение не найдено")
            result.completed_sets = result.sets_planned
            result.completed = True
            return result.session_id

    async def finish_if_complete(self, session_id: int) -> bool:
        async with self.database.session() as session:
            remaining = await session.scalar(
                select(func.count()).select_from(ExerciseResult).where(
                    ExerciseResult.session_id == session_id,
                    ExerciseResult.completed.is_(False),
                )
            )
            if remaining:
                return False
            workout = await session.get(WorkoutSession, session_id)
            if workout is None:
                return False
            workout.status = "completed"
            workout.completed_at = workout.completed_at or utc_now()
            total = await session.scalar(
                select(func.count()).select_from(WorkoutSession).where(
                    WorkoutSession.user_id == workout.user_id,
                    WorkoutSession.status == "completed",
                )
            )
            for threshold, code in ((3, "bronze_3"), (5, "silver_5"), (10, "gold_10")):
                if int(total or 0) >= threshold:
                    exists = await session.scalar(
                        select(Achievement).where(
                            Achievement.user_id == workout.user_id,
                            Achievement.code == code,
                        )
                    )
                    if exists is None:
                        session.add(Achievement(user_id=workout.user_id, code=code))
            return True

    async def summary(self, session_id: int) -> WorkoutSummary:
        async with self.database.session() as session:
            workout = await session.scalar(
                select(WorkoutSession)
                .options(
                    selectinload(WorkoutSession.results).selectinload(
                        ExerciseResult.sets_log
                    ),
                    selectinload(WorkoutSession.results)
                    .joinedload(ExerciseResult.workout_exercise)
                    .joinedload(WorkoutExercise.exercise),
                    selectinload(WorkoutSession.results)
                    .joinedload(ExerciseResult.outcome)
                    .joinedload(ExerciseOutcome.effective_exercise),
                )
                .where(WorkoutSession.id == session_id)
            )
            if workout is None:
                raise ValueError("Тренировка не найдена")
            elapsed = 0
            if workout.started_at and workout.completed_at:
                elapsed = max(1, round((workout.completed_at - workout.started_at).total_seconds() / 60))
            skipped = sum(
                1 for result in workout.results if result.outcome and result.outcome.status == "skipped"
            )
            weight_changes: list[WeightChange] = []
            results = sorted(
                workout.results,
                key=lambda result: result.workout_exercise.position,
            )
            for result in results:
                if not result.completed:
                    continue
                exercise = (
                    result.outcome.effective_exercise
                    if result.outcome and result.outcome.effective_exercise
                    else result.workout_exercise.exercise
                )
                if not exercise.requires_weight:
                    continue
                current_weight = next(
                    (
                        logged_set.weight_kg
                        for logged_set in reversed(result.sets_log)
                        if logged_set.weight_kg is not None
                    ),
                    None,
                )
                if current_weight is None:
                    continue
                previous_set = await self._last_logged_set_for_exercise(
                    session,
                    user_id=workout.user_id,
                    exercise_id=exercise.id,
                    excluded_session_id=workout.id,
                    require_weight=True,
                    completed_before=workout.completed_at,
                )
                if (
                    previous_set is not None
                    and previous_set.weight_kg is not None
                    and previous_set.weight_kg != current_weight
                ):
                    weight_changes.append(
                        WeightChange(
                            exercise_name=exercise.name,
                            previous_kg=previous_set.weight_kg,
                            current_kg=current_weight,
                        )
                    )
            return WorkoutSummary(
                duration_minutes=elapsed,
                completed_exercises=len(workout.results) - skipped,
                skipped_exercises=skipped,
                weight_changes=tuple(weight_changes),
            )
