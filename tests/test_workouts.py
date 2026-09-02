from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.exercise_library import rest_seconds_for
from app.models import (
    ExerciseOutcome,
    ExerciseResult,
    ExerciseSetResult,
    WorkoutExercise,
    WorkoutSession,
    WorkoutSessionFeedback,
    WorkoutTemplate,
)
from app.services.workouts import WeightChange


async def complete_workout(workouts, telegram_id: int):
    workout = await workouts.active_or_new(telegram_id)
    await workouts.begin(workout.id, telegram_id)
    while True:
        step = await workouts.get_step(workout.id, telegram_id)
        if step is None:
            break
        await workouts.complete_exercise(step.result.id, telegram_id)
        if step.exercise.requires_weight:
            await workouts.record_effort(step.result.id, telegram_id, "ok")
    assert await workouts.finish_if_complete(workout.id)
    return workout.id


async def complete_workout_with_efforts(workouts, telegram_id: int, efforts: dict[str, str]):
    workout = await workouts.active_or_new(telegram_id)
    await workouts.begin(workout.id, telegram_id)
    while True:
        step = await workouts.get_step(workout.id, telegram_id)
        if step is None:
            break
        await workouts.complete_exercise(step.result.id, telegram_id)
        if step.exercise.requires_weight:
            await workouts.record_effort(
                step.result.id,
                telegram_id,
                efforts.get(step.exercise.code, "ok"),
            )
    assert await workouts.finish_if_complete(workout.id)
    return workout.id


async def complete_workout_with_weighted_sets(
    workouts,
    telegram_id: int,
    exercise_code: str,
    weights: tuple[Decimal, ...],
) -> int:
    workout = await workouts.active_or_new(telegram_id)
    await workouts.begin(workout.id, telegram_id)
    while True:
        step = await workouts.get_step(workout.id, telegram_id)
        if step is None:
            break
        if step.exercise.code == exercise_code:
            for weight in weights:
                await workouts.record_set(
                    step.result.id,
                    telegram_id,
                    reps=12,
                    weight_kg=weight,
                )
            await workouts.record_effort(step.result.id, telegram_id, "ok")
        else:
            await workouts.complete_exercise(step.result.id, telegram_id)
            if step.exercise.requires_weight:
                await workouts.record_effort(step.result.id, telegram_id, "ok")
    assert await workouts.finish_if_complete(workout.id)
    return workout.id


@pytest.mark.asyncio
async def test_full_workout_needs_no_weight_and_increments_progress(
    app_services, onboarded_user
):
    _, database, _, workouts, progress, _ = app_services
    workout_id = await complete_workout(workouts, 10001)
    async with database.session() as session:
        results = list(
            (
                await session.scalars(
                    select(ExerciseResult).where(ExerciseResult.session_id == workout_id)
                )
            ).all()
        )
    assert results
    assert all(result.weight_kg is None for result in results)
    assert all(result.completed_sets == result.sets_planned for result in results)
    assert all(result.completed for result in results)
    result = await progress.get(10001)
    assert result.total_completed == 1
    assert result.month_completed == 1


@pytest.mark.asyncio
async def test_ten_workouts_award_all_milestones(app_services, onboarded_user):
    _, _, _, workouts, progress, _ = app_services
    for _ in range(10):
        await complete_workout(workouts, 10001)
    result = await progress.get(10001)
    assert result.total_completed == 10
    assert result.month_completed == 10
    assert result.achievements == ["bronze_3", "silver_5", "gold_10"]
    assert result.recent_weeks[-1] == 10


@pytest.mark.asyncio
async def test_plan_contains_all_exercises_in_prescribed_order(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    plan = await workouts.get_plan(workout.id, 10001)
    items = sorted(plan.template.items, key=lambda item: item.position)
    assert [item.exercise.code for item in items] == [
        "cardio_treadmill",
        "seated_leg_curl",
        "glute_kickback",
        "hip_abduction",
        "lat_pulldown",
        "chest_press",
    ]
    assert all(result.sets_planned == 2 for result in plan.results[1:])


@pytest.mark.asyncio
async def test_cardio_choice_replaces_default_cardio_in_current_step(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.choose_cardio(workout.id, 10001, "cardio_elliptical")
    await workouts.begin(workout.id, 10001)

    step = await workouts.get_step(workout.id, 10001)

    assert step is not None
    assert step.exercise.code == "cardio_elliptical"
    assert step.item.position == 1


@pytest.mark.asyncio
async def test_leg_press_can_be_replaced_with_hack_squat(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    await complete_workout(workouts, 10001)
    await complete_workout(workouts, 10001)
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)

    leg_press = await workouts.get_step(workout.id, 10001)
    assert leg_press is not None
    assert leg_press.exercise.code == "leg_press"
    await workouts.replace_exercise(leg_press.result.id, 10001)

    replacement = await workouts.get_step(workout.id, 10001)
    assert replacement is not None
    assert replacement.exercise.code == "hack_squat"
    assert replacement.exercise.name == "Гакк-присед"


@pytest.mark.asyncio
async def test_chest_press_can_be_replaced_with_pec_deck(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    await complete_workout(workouts, 10001)
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)

    while True:
        step = await workouts.get_step(workout.id, 10001)
        assert step is not None
        if step.exercise.code == "chest_press":
            break
        await workouts.complete_exercise(step.result.id, 10001)
        if step.exercise.requires_weight:
            await workouts.record_effort(step.result.id, 10001, "ok")

    await workouts.replace_exercise(step.result.id, 10001)
    replacement = await workouts.get_step(workout.id, 10001)
    assert replacement is not None
    assert replacement.exercise.code == "pec_deck"
    assert replacement.exercise.name == "Сведение рук в тренажёре"


@pytest.mark.asyncio
async def test_strength_sets_are_persisted_one_by_one(app_services, onboarded_user):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_next_set(cardio.result.id, 10001)

    strength = await workouts.get_step(workout.id, 10001)
    assert strength is not None
    session_id, completed = await workouts.complete_next_set(strength.result.id, 10001)
    state = await workouts.result_state(strength.result.id, 10001)

    assert session_id == workout.id
    assert not completed
    assert state[1:3] == (1, 2)


@pytest.mark.asyncio
async def test_record_set_is_idempotent_and_completes_only_planned_sets(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None

    first = await workouts.record_set(
        step.result.id, 10001, reps=12, weight_kg=Decimal("25")
    )
    assert first.completed_sets == 1
    assert first.set_number == 1
    assert not first.exercise_complete
    assert first.rest_seconds == rest_seconds_for(step.exercise.code)

    second = await workouts.record_set(
        step.result.id, 10001, reps=12, weight_kg=Decimal("25")
    )
    assert second.completed_sets == 2
    assert second.exercise_complete

    with pytest.raises(ValueError, match="уже завершено"):
        await workouts.record_set(
            step.result.id, 10001, reps=12, weight_kg=Decimal("25")
        )

    async with database.session() as session:
        rows = list(
            (
                await session.scalars(
                    select(ExerciseSetResult)
                    .where(ExerciseSetResult.exercise_result_id == step.result.id)
                    .order_by(ExerciseSetResult.set_number)
                )
            ).all()
        )
    assert [(row.set_number, row.reps, row.weight_kg) for row in rows] == [
        (1, 12, Decimal("25.00")),
        (2, 12, Decimal("25.00")),
    ]


@pytest.mark.parametrize("reps", [0, 101])
@pytest.mark.asyncio
async def test_record_set_rejects_invalid_repetitions(
    app_services, onboarded_user, reps
):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None
    with pytest.raises(ValueError, match="повтор"):
        await workouts.record_set(step.result.id, 10001, reps=reps, weight_kg=None)


@pytest.mark.parametrize("weight", [Decimal("-0.01"), Decimal("999.01")])
@pytest.mark.asyncio
async def test_record_set_rejects_invalid_weight(
    app_services, onboarded_user, weight
):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None
    with pytest.raises(ValueError, match="вес"):
        await workouts.record_set(
            step.result.id, 10001, reps=12, weight_kg=weight
        )


@pytest.mark.asyncio
async def test_record_set_rejects_stale_callback_after_skip(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None
    await workouts.skip_exercise(step.result.id, 10001)

    with pytest.raises(ValueError, match="уже завершено"):
        await workouts.record_set(
            step.result.id,
            10001,
            reps=12,
            weight_kg=Decimal("25"),
        )

    async with database.session() as session:
        stored = await session.get(ExerciseResult, step.result.id)
        set_count = await session.scalar(
            select(func.count()).select_from(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id == step.result.id
            )
        )
        outcome_status = await session.scalar(
            select(ExerciseOutcome.status).where(
                ExerciseOutcome.exercise_result_id == step.result.id
            )
        )
    assert stored is not None
    assert stored.completed
    assert stored.completed_sets == 0
    assert set_count == 0
    assert outcome_status == "skipped"


@pytest.mark.asyncio
async def test_record_set_rejects_an_older_session_card(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    completed_session_id = await complete_workout(workouts, 10001)
    async with database.session() as session:
        old_strength_id = await session.scalar(
            select(ExerciseResult.id)
            .where(
                ExerciseResult.session_id == completed_session_id,
                ExerciseResult.reps.is_not(None),
            )
            .limit(1)
        )
    assert old_strength_id is not None

    current_workout = await workouts.active_or_new(10001)
    await workouts.begin(current_workout.id, 10001)
    with pytest.raises(ValueError, match="текущ"):
        await workouts.record_set(
            old_strength_id,
            10001,
            reps=12,
            weight_kg=Decimal("25"),
        )

    async with database.session() as session:
        row_count = await session.scalar(
            select(func.count()).select_from(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id == old_strength_id
            )
        )
    assert row_count == 0


@pytest.mark.asyncio
async def test_record_set_rejects_a_future_result_in_the_active_session(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    current = await workouts.get_step(workout.id, 10001)
    assert current is not None
    async with database.session() as session:
        future_result_id = await session.scalar(
            select(ExerciseResult.id)
            .join(WorkoutExercise)
            .where(
                ExerciseResult.session_id == workout.id,
                WorkoutExercise.position > current.item.position,
            )
            .order_by(WorkoutExercise.position)
            .limit(1)
        )
    assert future_result_id is not None

    with pytest.raises(ValueError, match="текущ"):
        await workouts.record_set(
            future_result_id,
            10001,
            reps=12,
            weight_kg=Decimal("25"),
        )

    async with database.session() as session:
        row_count = await session.scalar(
            select(func.count()).select_from(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id == future_result_id
            )
        )
    assert row_count == 0


@pytest.mark.asyncio
async def test_repeat_last_set_copies_weight_and_reps(app_services, onboarded_user):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None
    await workouts.record_set(step.result.id, 10001, reps=12, weight_kg=Decimal("25"))
    repeated = await workouts.repeat_last_set(step.result.id, 10001)
    assert repeated.completed_sets == 2
    assert await workouts.last_set_values(step.result.id, 10001) == (
        Decimal("25.00"),
        12,
    )


@pytest.mark.asyncio
async def test_previous_values_come_from_last_completed_occurrence(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    await complete_workout_with_weighted_sets(
        workouts,
        10001,
        "seated_leg_curl",
        (Decimal("22.5"), Decimal("25")),
    )
    await complete_workout(workouts, 10001)
    await complete_workout(workouts, 10001)

    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None

    assert step.exercise.code == "seated_leg_curl"
    assert step.previous_weight == Decimal("25.00")
    assert await workouts.last_set_values(step.result.id, 10001) == (
        Decimal("25.00"),
        12,
    )
    repeated = await workouts.repeat_last_set(step.result.id, 10001)
    assert repeated.completed_sets == 1


@pytest.mark.asyncio
async def test_summary_reports_change_from_final_logged_set(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    await complete_workout(workouts, 10001)
    await complete_workout(workouts, 10001)
    await complete_workout_with_weighted_sets(
        workouts,
        10001,
        "leg_press",
        (Decimal("22.5"), Decimal("25")),
    )
    await complete_workout(workouts, 10001)
    await complete_workout(workouts, 10001)
    current_id = await complete_workout_with_weighted_sets(
        workouts,
        10001,
        "leg_press",
        (Decimal("25"), Decimal("27.5")),
    )

    summary = await workouts.summary(current_id)

    assert summary.weight_changes == (
        WeightChange(
            exercise_name="Жим ногами",
            previous_kg=Decimal("25.00"),
            current_kg=Decimal("27.50"),
        ),
    )


@pytest.mark.asyncio
async def test_summary_of_older_session_ignores_newer_workout(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    await complete_workout(workouts, 10001)
    await complete_workout(workouts, 10001)
    older_id = await complete_workout_with_weighted_sets(
        workouts,
        10001,
        "leg_press",
        (Decimal("22.5"), Decimal("25")),
    )
    await complete_workout(workouts, 10001)
    await complete_workout(workouts, 10001)
    await complete_workout_with_weighted_sets(
        workouts,
        10001,
        "leg_press",
        (Decimal("25"), Decimal("27.5")),
    )

    summary = await workouts.summary(older_id)

    assert summary.weight_changes == ()


@pytest.mark.asyncio
async def test_two_easy_repeats_add_only_one_rep_next_time(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    await complete_workout_with_efforts(workouts, 10001, {"chest_press": "easy"})
    await complete_workout_with_efforts(workouts, 10001, {"chest_press": "easy"})
    await complete_workout_with_efforts(workouts, 10001, {})

    next_workout = await workouts.active_or_new(10001)
    plan = await workouts.get_plan(next_workout.id, 10001)
    items = {item.id: item.exercise.code for item in plan.template.items}
    chest_press_result = next(
        result
        for result in plan.results
        if items[result.workout_exercise_id] == "chest_press"
    )

    assert chest_press_result.reps == 11
    assert chest_press_result.sets_planned == 2


@pytest.mark.asyncio
async def test_two_easy_results_at_ceiling_suggest_minimum_machine_increment(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    for _ in range(2):
        workout_id = await complete_workout_with_efforts(
            workouts, 10001, {"chest_press": "easy"}
        )
        async with database.session() as session:
            stored = await session.scalar(
                select(ExerciseResult)
                .join(WorkoutExercise)
                .join(WorkoutExercise.exercise)
                .where(
                    ExerciseResult.session_id == workout_id,
                    WorkoutExercise.exercise.has(code="chest_press"),
                )
            )
            assert stored is not None
            stored.reps = 12

    await complete_workout(workouts, 10001)

    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    while (step := await workouts.get_step(workout.id, 10001)) is not None:
        if step.exercise.code == "chest_press":
            assert step.result.reps == 12
            assert step.minimum_weight_increase_suggested is True
            break
        await workouts.complete_exercise(step.result.id, 10001)
        if step.exercise.requires_weight:
            await workouts.record_effort(step.result.id, 10001, "ok")
    else:
        pytest.fail("chest_press step was not reached")


@pytest.mark.asyncio
async def test_stale_mutation_callbacks_cannot_change_pain_or_completed_results(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    painful = await workouts.get_step(workout.id, 10001)
    assert painful is not None
    await workouts.stop_for_discomfort(painful.result.id, 10001)

    stale_calls = (
        lambda: workouts.replace_exercise(painful.result.id, 10001),
        lambda: workouts.skip_exercise(painful.result.id, 10001),
        lambda: workouts.complete_exercise(painful.result.id, 10001),
        lambda: workouts.record_effort(painful.result.id, 10001, "easy"),
    )
    for call in stale_calls:
        with pytest.raises(ValueError):
            await call()

    async with database.session() as session:
        painful_outcome = await session.scalar(
            select(ExerciseOutcome).where(
                ExerciseOutcome.exercise_result_id == painful.result.id
            )
        )
    assert painful_outcome is not None
    assert (painful_outcome.status, painful_outcome.effort) == ("pain", "pain")

    current = await workouts.get_step(workout.id, 10001)
    assert current is not None
    await workouts.complete_exercise(current.result.id, 10001)
    await workouts.record_effort(current.result.id, 10001, "easy")
    with pytest.raises(ValueError):
        await workouts.record_effort(current.result.id, 10001, "hard")
    with pytest.raises(ValueError):
        await workouts.skip_exercise(current.result.id, 10001)


@pytest.mark.asyncio
async def test_concurrent_effort_callbacks_save_exactly_one_value(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    strength = await workouts.get_step(workout.id, 10001)
    assert strength is not None
    await workouts.complete_exercise(strength.result.id, 10001)

    outcomes = await asyncio.gather(
        workouts.record_effort(strength.result.id, 10001, "easy"),
        workouts.record_effort(strength.result.id, 10001, "hard"),
        return_exceptions=True,
    )

    assert sum(value == workout.id for value in outcomes) == 1
    assert sum(isinstance(value, ValueError) for value in outcomes) == 1
    async with database.session() as session:
        saved = await session.scalar(
            select(ExerciseOutcome).where(
                ExerciseOutcome.exercise_result_id == strength.result.id
            )
        )
    assert saved is not None
    assert saved.status == "completed"
    assert saved.effort in {"easy", "hard"}


@pytest.mark.asyncio
async def test_summary_excludes_pain_stops_from_completed_count(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    painful = await workouts.get_step(workout.id, 10001)
    assert painful is not None
    await workouts.stop_for_discomfort(painful.result.id, 10001)
    while (step := await workouts.get_step(workout.id, 10001)) is not None:
        await workouts.complete_exercise(step.result.id, 10001)
        if step.exercise.requires_weight:
            await workouts.record_effort(step.result.id, 10001, "ok")
    assert await workouts.finish_if_complete(workout.id)

    summary = await workouts.summary(workout.id)

    assert summary.completed_exercises == 5
    assert summary.pain_stopped_exercises == 1


@pytest.mark.asyncio
async def test_first_six_sessions_plan_two_strength_sets_and_seventh_plans_three(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services

    for session_number in range(1, 8):
        workout = await workouts.active_or_new(10001)
        plan = await workouts.get_plan(workout.id, 10001)
        expected_sets = 2 if session_number <= 6 else 3
        expected_reserve = "3–4" if session_number <= 6 else "2–3"

        assert all(
            result.sets_planned == expected_sets
            for result in plan.results
            if result.reps is not None
        )
        assert plan.reserve_reps == expected_reserve

        if session_number < 7:
            assert await complete_workout(workouts, 10001) == workout.id


@pytest.mark.asyncio
async def test_legacy_history_does_not_skip_return_program_ramp_up(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    async with database.session() as session:
        legacy = WorkoutTemplate(
            code="legacy_program",
            name="Старая программа",
            focus="Архив",
            position=99,
            active=False,
        )
        session.add(legacy)
        await session.flush()
        for _ in range(5):
            session.add(
                WorkoutSession(
                    user_id=onboarded_user.id,
                    template_id=legacy.id,
                    status="completed",
                )
            )

    workout = await workouts.active_or_new(10001)
    plan = await workouts.get_plan(workout.id, 10001)

    assert plan.template.code == "return_full_body_a_v4"
    assert all(result.sets_planned == 2 for result in plan.results if result.reps)


@pytest.mark.asyncio
async def test_incomplete_session_is_not_counted(app_services, onboarded_user):
    _, database, _, workouts, progress, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    result = await progress.get(10001)
    assert result.total_completed == 0
    async with database.session() as session:
        status = await session.scalar(
            select(WorkoutSession.status).where(WorkoutSession.id == workout.id)
        )
        assert status == "active"


@pytest.mark.asyncio
async def test_reset_current_day_removes_active_progress_and_reopens_same_day(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    original_template_id = workout.template_id
    await workouts.begin(workout.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None
    await workouts.complete_next_set(step.result.id, 10001)

    assert await workouts.reset_current_day(10001) is True
    async with database.session() as session:
        assert await session.get(WorkoutSession, workout.id) is None
        remaining_results = await session.scalar(
            select(func.count()).select_from(ExerciseResult).where(
                ExerciseResult.session_id == workout.id
            )
        )
        assert remaining_results == 0

    reopened = await workouts.active_or_new(10001)
    assert reopened.template_id == original_template_id


@pytest.mark.asyncio
async def test_reset_current_day_removes_completed_test_workout_from_progress(
    app_services, onboarded_user
):
    _, _, _, workouts, progress, _ = app_services
    await complete_workout(workouts, 10001)
    assert (await progress.get(10001)).total_completed == 1

    assert await workouts.reset_current_day(10001) is True
    assert (await progress.get(10001)).total_completed == 0


@pytest.mark.asyncio
async def test_reset_current_day_returns_false_when_nothing_was_started(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    assert await workouts.reset_current_day(10001) is False


@pytest.mark.asyncio
async def test_light_mode_reduces_only_unstarted_strength_results(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    for _ in range(6):
        await complete_workout(workouts, 10001)
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    first_strength = await workouts.get_step(workout.id, 10001)
    assert first_strength is not None
    await workouts.record_set(first_strength.result.id, 10001, reps=12, weight_kg=None)

    changed = await workouts.enable_light_mode(workout.id, 10001)
    plan = await workouts.get_plan(workout.id, 10001)
    by_id = {result.id: result for result in plan.results}

    assert changed == 4
    assert by_id[first_strength.result.id].sets_planned == 3
    assert all(
        result.sets_planned == 2
        for result in plan.results
        if result.id != first_strength.result.id and result.reps is not None
    )


@pytest.mark.asyncio
async def test_discomfort_stops_current_exercise_immediately(app_services, onboarded_user):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    assert step is not None

    session_id = await workouts.stop_for_discomfort(step.result.id, 10001)

    assert session_id == workout.id
    next_step = await workouts.get_step(workout.id, 10001)
    assert next_step is not None
    assert next_step.result.id != step.result.id
    async with database.session() as session:
        result = await session.get(ExerciseResult, step.result.id)
        outcome = await session.scalar(
            select(ExerciseOutcome).where(
                ExerciseOutcome.exercise_result_id == step.result.id
            )
        )
    assert result is not None
    assert result.completed
    assert result.completed_sets == 0
    assert outcome is not None
    assert outcome.status == outcome.effort == "pain"


@pytest.mark.asyncio
async def test_session_feedback_is_one_validated_row(app_services, onboarded_user):
    _, database, _, workouts, _, _ = app_services
    workout_id = await complete_workout(workouts, 10001)

    await workouts.record_session_feedback(workout_id, 10001, "ok")
    await workouts.record_session_feedback(workout_id, 10001, "hard")
    with pytest.raises(ValueError, match="оцен"):
        await workouts.record_session_feedback(workout_id, 10001, "pain")

    async with database.session() as session:
        rows = list((await session.scalars(select(WorkoutSessionFeedback))).all())
    assert len(rows) == 1
    assert rows[0].effort == "hard"


@pytest.mark.asyncio
async def test_discomfort_rejects_future_and_stale_callbacks_and_keeps_logged_sets(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    current = await workouts.get_step(workout.id, 10001)
    assert current is not None

    async with database.session() as session:
        future_id = await session.scalar(
            select(ExerciseResult.id)
            .join(WorkoutExercise)
            .where(
                ExerciseResult.session_id == workout.id,
                ExerciseResult.completed.is_(False),
                WorkoutExercise.position > current.item.position,
            )
            .order_by(WorkoutExercise.position)
            .limit(1)
        )
    assert future_id is not None
    with pytest.raises(ValueError, match="текущее"):
        await workouts.stop_for_discomfort(future_id, 10001)
    still_current = await workouts.get_step(workout.id, 10001)
    assert still_current is not None
    assert still_current.result.id == current.result.id

    await workouts.record_set(current.result.id, 10001, reps=12, weight_kg=None)
    await workouts.stop_for_discomfort(current.result.id, 10001)
    async with database.session() as session:
        stored = await session.get(ExerciseResult, current.result.id)
        set_count = await session.scalar(
            select(func.count()).select_from(ExerciseSetResult).where(
                ExerciseSetResult.exercise_result_id == current.result.id
            )
        )
    assert stored is not None
    assert stored.completed_sets == 1
    assert set_count == 1

    completed = await workouts.get_step(workout.id, 10001)
    assert completed is not None
    await workouts.complete_exercise(completed.result.id, 10001)
    await workouts.record_effort(completed.result.id, 10001, "easy")
    with pytest.raises(ValueError, match="текущее"):
        await workouts.stop_for_discomfort(completed.result.id, 10001)
    async with database.session() as session:
        outcome = await session.scalar(
            select(ExerciseOutcome).where(
                ExerciseOutcome.exercise_result_id == completed.result.id
            )
        )
    assert outcome is not None
    assert (outcome.status, outcome.effort) == ("completed", "easy")


@pytest.mark.asyncio
async def test_concurrent_discomfort_is_idempotent_without_raw_database_errors(
    app_services, onboarded_user
):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    assert cardio is not None
    await workouts.complete_exercise(cardio.result.id, 10001)
    current = await workouts.get_step(workout.id, 10001)
    assert current is not None

    results = await asyncio.gather(
        workouts.stop_for_discomfort(current.result.id, 10001),
        workouts.stop_for_discomfort(current.result.id, 10001),
        return_exceptions=True,
    )

    assert all(result == workout.id or isinstance(result, ValueError) for result in results)


@pytest.mark.asyncio
async def test_concurrent_feedback_upserts_one_row_without_database_errors(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout_id = await complete_workout(workouts, 10001)

    results = await asyncio.gather(
        workouts.record_session_feedback(workout_id, 10001, "ok"),
        workouts.record_session_feedback(workout_id, 10001, "hard"),
        return_exceptions=True,
    )

    assert results == [None, None]
    async with database.session() as session:
        rows = list((await session.scalars(select(WorkoutSessionFeedback))).all())
    assert len(rows) == 1
    assert rows[0].effort in {"ok", "hard"}
