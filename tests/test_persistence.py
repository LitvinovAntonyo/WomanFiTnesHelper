from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.database import Database
from app.models import ExerciseResult, ExerciseSetResult, User, WorkoutSessionFeedback


@pytest.mark.asyncio
async def test_sqlite_survives_database_reopen(app_services, onboarded_user):
    settings, database, _, _, _, _ = app_services
    await database.close()
    reopened = Database(settings)
    await reopened.initialize()
    async with reopened.session() as session:
        count = await session.scalar(select(func.count()).select_from(User))
    assert count == 1
    await reopened.close()


@pytest.mark.asyncio
async def test_v3_schema_persists_set_rows_and_session_feedback(
    app_services, onboarded_user
):
    settings, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    async with database.session() as session:
        result = await session.scalar(
            select(ExerciseResult)
            .where(ExerciseResult.session_id == workout.id)
            .order_by(ExerciseResult.id)
        )
        assert result is not None
        session.add(
            ExerciseSetResult(
                exercise_result_id=result.id,
                set_number=1,
                reps=12,
                weight_kg=Decimal("25.00"),
            )
        )
        session.add(WorkoutSessionFeedback(session_id=workout.id, effort="ok"))

    await database.close()
    reopened = Database(settings)
    await reopened.initialize()
    async with reopened.session() as session:
        saved_set = await session.scalar(select(ExerciseSetResult))
        feedback = await session.scalar(select(WorkoutSessionFeedback))
        version = await session.scalar(text("PRAGMA user_version"))
    assert saved_set is not None
    assert saved_set.reps == 12
    assert saved_set.weight_kg == Decimal("25.00")
    assert feedback is not None
    assert feedback.effort == "ok"
    assert version == 4
    await reopened.close()


@pytest.mark.asyncio
async def test_initialize_never_downgrades_a_newer_schema_version(app_services):
    settings, database, *_ = app_services
    async with database.engine.begin() as connection:
        await connection.execute(text("PRAGMA user_version=7"))
    await database.close()

    reopened = Database(settings)
    await reopened.initialize()
    async with reopened.session() as session:
        version = await session.scalar(text("PRAGMA user_version"))

    assert version == 7
    await reopened.close()
