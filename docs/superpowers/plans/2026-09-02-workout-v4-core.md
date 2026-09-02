# Workout v4 Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current split program with the approved three-day full-body v4 program, fixed per-exercise rest, per-set logging, light mode, immediate discomfort handling, and session feedback.

**Architecture:** Keep the existing aiogram handlers, SQLAlchemy services, and versioned-template strategy. Add only additive SQLite tables for set logs and session feedback, keep fixed rest in the exercise library, and expose small service methods consumed by the Telegram handlers.

**Tech Stack:** Python 3.10–3.14, aiogram 3.31, SQLAlchemy 2.0 async, SQLite, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-02-return-to-training-v4-design.md`

## Global Constraints

- Three workouts per week, each 50–60 minutes.
- Every workout begins with 8–10 minutes of treadmill, elliptical, or stationary bike cardio.
- No cooldown step.
- Every day is full body with three lower-body and two upper-body exercises.
- First six completed v4 workouts use two strength sets; the seventh and later use three.
- Rest is fixed by exercise: 120, 90, 75, or 60 seconds as specified below.
- The bot does not ask for or calculate from body weight.
- Exercise sets stop before failure with 3–4 repetitions in reserve initially and 2–3 later.
- Existing users, settings, reminders, and old historical templates must remain readable.
- The current project directory has no `.git`; conditional commit steps run only if execution happens inside a real Git checkout.
- Do not touch VPS state in this plan; deployment is in the release plan.

---

### Task 1: Versioned v4 templates, shoulder press, and fixed rest library

**Files:**
- Modify: `app/services/workouts.py:44-94`
- Modify: `app/exercise_library.py:8-254`
- Test: `tests/test_workouts.py`
- Test: `tests/test_exercise_library.py`

**Interfaces:**
- Produces: `REST_SECONDS_BY_EXERCISE: dict[str, int]`
- Produces: `rest_seconds_for(code: str) -> int | None`
- Produces: `EXERCISE_GUIDANCE["machine_shoulder_press"]`
- Produces: three active template codes ending in `_v4`

- [ ] **Step 1: Replace the template-order test with the exact v4 contract**

```python
def test_templates_are_full_body_v4_with_lower_body_priority():
    by_code = {
        template["code"]: [raw[0] for raw in template["items"]]
        for template in DEFAULT_TEMPLATES
    }
    assert by_code == {
        "return_full_body_a_v4": [
            "cardio_treadmill",
            "seated_leg_curl",
            "glute_kickback",
            "hip_abduction",
            "lat_pulldown",
            "chest_press",
        ],
        "return_full_body_b_v4": [
            "cardio_treadmill",
            "hack_squat",
            "leg_extension",
            "hip_adduction",
            "seated_row",
            "chest_press",
        ],
        "return_full_body_c_v4": [
            "cardio_treadmill",
            "leg_press",
            "seated_leg_curl",
            "glute_kickback",
            "lat_pulldown",
            "machine_shoulder_press",
        ],
    }
```

- [ ] **Step 2: Add failing rest and guidance tests**

```python
def test_rest_is_fixed_per_exercise():
    assert rest_seconds_for("hack_squat") == 120
    assert rest_seconds_for("leg_press") == 120
    assert rest_seconds_for("seated_leg_curl") == 75
    assert rest_seconds_for("leg_extension") == 75
    assert rest_seconds_for("glute_kickback") == 60
    assert rest_seconds_for("hip_abduction") == 60
    assert rest_seconds_for("hip_adduction") == 60
    assert rest_seconds_for("lat_pulldown") == 90
    assert rest_seconds_for("seated_row") == 90
    assert rest_seconds_for("chest_press") == 90
    assert rest_seconds_for("machine_shoulder_press") == 90
    assert rest_seconds_for("cardio_treadmill") is None


def test_machine_shoulder_press_has_complete_guidance():
    guidance = EXERCISE_GUIDANCE["machine_shoulder_press"]
    assert guidance.image_filename == "machine_shoulder_press.png"
    assert "сидень" in guidance.setup.lower()
    assert guidance.movement
    assert guidance.breathing
    assert guidance.cues
    assert guidance.mistakes
```

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run: `python3 -m pytest tests/test_workouts.py tests/test_exercise_library.py -q`

Expected: failures mention the old `_v3` template codes, missing `rest_seconds_for`, and missing `machine_shoulder_press`.

- [ ] **Step 4: Define the fixed rest mapping**

```python
REST_SECONDS_BY_EXERCISE: dict[str, int] = {
    "hack_squat": 120,
    "leg_press": 120,
    "seated_leg_curl": 75,
    "leg_extension": 75,
    "glute_kickback": 60,
    "hip_abduction": 60,
    "hip_adduction": 60,
    "lat_pulldown": 90,
    "seated_row": 90,
    "chest_press": 90,
    "machine_shoulder_press": 90,
}


def rest_seconds_for(code: str) -> int | None:
    return REST_SECONDS_BY_EXERCISE.get(code)
```

- [ ] **Step 5: Replace `DEFAULT_TEMPLATES` with the exact v4 days**

Use the exercise order and upper repetition values from the tests. Cardio uses one set, no reps, and `duration_minutes=10`; strength exercises use three template sets. Set the names to:

```python
"A · всё тело — ягодицы и задняя поверхность бедра"
"B · всё тело — квадрицепс и внутренняя поверхность бедра"
"C · всё тело — ноги и ягодицы"
```

Each `focus` must state that the day is full body and identify its lower-body emphasis. Add `machine_shoulder_press` to `EXTRA_EXERCISES` with `requires_weight=True`.

- [ ] **Step 6: Add shoulder-press guidance and repetition ranges**

```python
"machine_shoulder_press": ExerciseGuidance(
    image_filename="machine_shoulder_press.png",
    weight_label="оставь 2–3 технически чистых повтора в запасе",
    setup="Отрегулируй сиденье так, чтобы рукояти находились примерно на уровне плеч. Прижми таз и спину к опоре, поставь стопы полностью на пол и возьмись за рукояти нейтральным или прямым хватом.",
    movement="Выжми рукояти вверх по траектории тренажёра, не поднимая плечи к ушам. Остановись до жёсткой блокировки локтей и плавно верни рукояти к уровню плеч.",
    breathing="Выдох во время жима вверх, вдох при контролируемом возвращении.",
    cues="Корпус остаётся на спинке, рёбра не выталкиваются вперёд, предплечья следуют за рукоятями.",
    mistakes="Не прогибай поясницу, не опускай рукояти ниже комфортного диапазона плеч, не бросай вес и не блокируй локти.",
),
```

- [ ] **Step 7: Run focused tests**

Run: `python3 -m pytest tests/test_workouts.py tests/test_exercise_library.py -q`

Expected: the v4 sequence and rest tests pass. The image-existence assertion may remain red until the media plan supplies `machine_shoulder_press.png`; change that assertion in this task to require guidance for every template exercise and require an image only when its manifest status is `approved` after the media plan lands.

- [ ] **Step 8: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/services/workouts.py app/exercise_library.py tests/test_workouts.py tests/test_exercise_library.py
  git commit -m "feat: define full-body workout v4"
fi
```

---

### Task 2: Additive persistence for individual sets and session feedback

**Files:**
- Modify: `app/models.py`
- Modify: `app/database.py:38-45`
- Modify: `tests/test_persistence.py`

**Interfaces:**
- Produces: `ExerciseSetResult`
- Produces: `WorkoutSessionFeedback`
- Produces: SQLite schema version `3`

- [ ] **Step 1: Write schema persistence tests**

```python
from decimal import Decimal

from app.models import ExerciseResult, ExerciseSetResult, WorkoutSessionFeedback


@pytest.mark.asyncio
async def test_v3_schema_persists_set_rows_and_session_feedback(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    async with database.session() as session:
        result = await session.scalar(
            select(ExerciseResult)
            .where(ExerciseResult.session_id == workout.id)
            .order_by(ExerciseResult.id)
        )
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
    reopened = Database(app_services[0])
    await reopened.initialize()
    async with reopened.session() as session:
        saved_set = await session.scalar(select(ExerciseSetResult))
        feedback = await session.scalar(select(WorkoutSessionFeedback))
        version = await session.scalar(text("PRAGMA user_version"))
    assert saved_set.reps == 12
    assert saved_set.weight_kg == Decimal("25.00")
    assert feedback.effort == "ok"
    assert version == 3
    await reopened.close()
```

- [ ] **Step 2: Run the persistence test and confirm it fails**

Run: `python3 -m pytest tests/test_persistence.py::test_v3_schema_persists_set_rows_and_session_feedback -q`

Expected: import failure for the two new models.

- [ ] **Step 3: Add `ExerciseSetResult`**

```python
class ExerciseSetResult(TimestampMixin, Base):
    __tablename__ = "exercise_set_results"
    __table_args__ = (
        UniqueConstraint("exercise_result_id", "set_number"),
        Index("ix_set_results_result", "exercise_result_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_result_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_results.id", ondelete="CASCADE"), nullable=False
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
```

Add `sets_log: Mapped[list[ExerciseSetResult]]` to `ExerciseResult` with cascade delete and `order_by="ExerciseSetResult.set_number"`, plus the matching `result` relationship.

- [ ] **Step 4: Add `WorkoutSessionFeedback`**

```python
class WorkoutSessionFeedback(TimestampMixin, Base):
    __tablename__ = "workout_session_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    effort: Mapped[str] = mapped_column(String(20), nullable=False)
```

Add the one-to-one `feedback` relationship to `WorkoutSession`.

- [ ] **Step 5: Raise the additive schema version**

Change `PRAGMA user_version=2` to `PRAGMA user_version=3`. Keep `Base.metadata.create_all()` so both new tables are created on existing databases without modifying existing columns.

- [ ] **Step 6: Run persistence tests**

Run: `python3 -m pytest tests/test_persistence.py -q`

Expected: all persistence tests pass and reopen the database successfully.

- [ ] **Step 7: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/models.py app/database.py tests/test_persistence.py
  git commit -m "feat: persist individual workout sets"
fi
```

---

### Task 3: Workout service APIs for set logging and progression

**Files:**
- Modify: `app/services/workouts.py`
- Test: `tests/test_workouts.py`

**Interfaces:**
- Consumes: `ExerciseSetResult`
- Consumes: `rest_seconds_for(code: str) -> int | None`
- Produces: `SetLogState`
- Produces: `record_set(result_id: int, telegram_id: int, reps: int, weight_kg: Decimal | None) -> SetLogState`
- Produces: `repeat_last_set(result_id: int, telegram_id: int) -> SetLogState`
- Produces: `last_set_values(result_id: int, telegram_id: int) -> tuple[Decimal | None, int] | None`
- Produces: `WeightChange` rows in `WorkoutSummary.weight_changes`

- [ ] **Step 1: Add failing tests for individual set recording**

```python
@pytest.mark.asyncio
async def test_record_set_is_idempotent_and_completes_only_planned_sets(
    app_services, onboarded_user
):
    _, database, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)

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
            (await session.scalars(
                select(ExerciseSetResult)
                .where(ExerciseSetResult.exercise_result_id == step.result.id)
                .order_by(ExerciseSetResult.set_number)
            )).all()
        )
    assert [(row.set_number, row.reps, row.weight_kg) for row in rows] == [
        (1, 12, Decimal("25.00")),
        (2, 12, Decimal("25.00")),
    ]
```

- [ ] **Step 2: Add failing tests for validation and repeat**

```python
@pytest.mark.parametrize("reps", [0, 101])
@pytest.mark.asyncio
async def test_record_set_rejects_invalid_repetitions(app_services, onboarded_user, reps):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    step = await workouts.get_step(workout.id, 10001)
    with pytest.raises(ValueError, match="повтор"):
        await workouts.record_set(step.result.id, 10001, reps=reps, weight_kg=None)


@pytest.mark.asyncio
async def test_repeat_last_set_copies_weight_and_reps(app_services, onboarded_user):
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    await workouts.record_set(step.result.id, 10001, reps=12, weight_kg=Decimal("25"))
    repeated = await workouts.repeat_last_set(step.result.id, 10001)
    assert repeated.completed_sets == 2
    assert await workouts.last_set_values(step.result.id, 10001) == (
        Decimal("25.00"),
        12,
    )
```

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run: `python3 -m pytest tests/test_workouts.py -q`

Expected: missing `record_set`, `repeat_last_set`, and `last_set_values`.

- [ ] **Step 4: Add the service result type**

```python
@dataclass(frozen=True, slots=True)
class SetLogState:
    session_id: int
    result_id: int
    set_number: int
    completed_sets: int
    sets_planned: int
    exercise_complete: bool
    rest_seconds: int
```

- [ ] **Step 5: Implement `record_set` atomically**

Validate `1 <= reps <= 100`, `weight_kg is None or Decimal("0") <= weight_kg <= Decimal("999")`, ownership through `WorkoutSession -> User`, and `completed_sets < sets_planned`. Use `next_number = completed_sets + 1`, insert one `ExerciseSetResult`, then update `completed_sets`, `reps`, `weight_kg`, and `completed`. Return `SetLogState` with `rest_seconds_for(effective_exercise.code) or 0`.

The unique constraint on `(exercise_result_id, set_number)` is the final duplicate-write guard. Convert `IntegrityError` into `ValueError("Этот подход уже записан")`.

- [ ] **Step 6: Implement repeat and previous-value queries**

`repeat_last_set` loads the newest row for the result; if none exists, it falls back to the newest set row for the same effective exercise in a completed earlier session. It then calls `record_set`. `last_set_values` follows the same lookup but returns only `(weight_kg, reps)`.

Update `get_step().previous_weight` to query `ExerciseSetResult.weight_kg` instead of the legacy aggregate field.

- [ ] **Step 7: Change the adaptation threshold from four to six completed v4 sessions**

Change the set-ramp condition from `completed_count < 4` to `completed_count < 6`. Keep the count joined to active templates so deactivated v3 history does not skip the v4 adaptation period.

- [ ] **Step 8: Run service tests**

Before running the suite, add a summary regression test that completes the same weighted exercise twice with a higher final-set weight on the second occurrence and asserts:

```python
assert summary.weight_changes == (
    WeightChange(
        exercise_name="Жим ногами",
        previous_kg=Decimal("25.00"),
        current_kg=Decimal("27.50"),
    ),
)
```

Extend the service types with:

```python
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
```

For each completed strength result, compare the last non-null set weight in the current session with the last non-null set weight for the same effective exercise in an earlier completed session. Include only actual changes; do not invent a change when either value is absent.

Run: `python3 -m pytest tests/test_workouts.py -q`

Expected: all workout service tests pass, including six two-set workouts followed by a three-set seventh workout.

- [ ] **Step 9: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/services/workouts.py tests/test_workouts.py
  git commit -m "feat: log workout sets and progression"
fi
```

---

### Task 4: Light mode, immediate discomfort, and session feedback services

**Files:**
- Modify: `app/services/workouts.py`
- Test: `tests/test_workouts.py`

**Interfaces:**
- Consumes: `WorkoutSessionFeedback`
- Produces: `enable_light_mode(session_id: int, telegram_id: int) -> int`
- Produces: `stop_for_discomfort(result_id: int, telegram_id: int) -> int`
- Produces: `record_session_feedback(session_id: int, telegram_id: int, effort: str) -> None`

- [ ] **Step 1: Write failing behavior tests**

```python
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
    await workouts.complete_exercise(cardio.result.id, 10001)
    first_strength = await workouts.get_step(workout.id, 10001)
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
    _, _, _, workouts, _, _ = app_services
    workout = await workouts.active_or_new(10001)
    await workouts.begin(workout.id, 10001)
    cardio = await workouts.get_step(workout.id, 10001)
    await workouts.complete_exercise(cardio.result.id, 10001)
    step = await workouts.get_step(workout.id, 10001)
    session_id = await workouts.stop_for_discomfort(step.result.id, 10001)
    assert session_id == workout.id
    next_step = await workouts.get_step(workout.id, 10001)
    assert next_step.result.id != step.result.id
```

- [ ] **Step 2: Write failing feedback validation test**

```python
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
```

- [ ] **Step 3: Run tests and confirm missing APIs**

Run: `python3 -m pytest tests/test_workouts.py -q`

- [ ] **Step 4: Implement the three service methods**

`enable_light_mode` changes only strength results with `completed_sets == 0` and `completed is False`, using `sets_planned = min(sets_planned, 2)`. `stop_for_discomfort` upserts `ExerciseOutcome(status="pain", effort="pain")`, marks the result complete without fabricating sets, and advances. `record_session_feedback` accepts only `easy`, `ok`, or `hard` and upserts one feedback row for an owned completed session.

- [ ] **Step 5: Run workout tests**

Run: `python3 -m pytest tests/test_workouts.py -q`

Expected: light mode, discomfort, feedback, reset, replacement, and progress tests all pass.

- [ ] **Step 6: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/services/workouts.py tests/test_workouts.py
  git commit -m "feat: add adaptive workout controls"
fi
```

---

### Task 5: Telegram set input and automatic fixed rest

**Files:**
- Modify: `app/states.py`
- Modify: `app/handlers/workout.py`
- Modify: `tests/test_exercise_library.py`
- Modify: `tests/test_handlers.py`

**Interfaces:**
- Consumes: `record_set`, `repeat_last_set`, `last_set_values`, `rest_seconds_for`
- Produces: `parse_set_input(value: str) -> tuple[Decimal | None, int]`
- Produces: callback prefixes `exercise:log:`, `exercise:repeat:`, `exercise:pain:`, `session:light:`, `session:feedback:`

- [ ] **Step 1: Add parser tests**

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("25 12", (Decimal("25"), 12)),
        ("25,5 12", (Decimal("25.5"), 12)),
        ("- 15", (None, 15)),
    ],
)
def test_parse_set_input(raw, expected):
    assert parse_set_input(raw) == expected


@pytest.mark.parametrize("raw", ["", "25", "abc 12", "25 0", "1000 12"])
def test_parse_set_input_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        parse_set_input(raw)
```

- [ ] **Step 2: Replace keyboard expectations**

```python
def test_strength_card_has_log_repeat_skip_replace_and_pain_actions():
    step = make_strength_step(previous_weight=Decimal("25"))
    keyboard = step_keyboard(step, repeat_available=True)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert f"exercise:log:{step.result.id}" in callbacks
    assert f"exercise:repeat:{step.result.id}" in callbacks
    assert f"exercise:pain:{step.result.id}" in callbacks
    assert f"exercise:skip:{step.result.id}" in callbacks
```

- [ ] **Step 3: Add an integration test for automatic 75-second rest**

Use a monkeypatched async timer launcher instead of waiting:

```python
started: list[tuple[int, int]] = []

async def fake_start_rest(message, telegram_id, result_id, seconds):
    started.append((result_id, seconds))

monkeypatch.setattr(workout_module, "start_rest_task", fake_start_rest)
```

Feed `exercise:log:<id>`, then a message `"20 12"` for `seated_leg_curl`; assert the set row exists and `started == [(result_id, 75)]`.

- [ ] **Step 4: Run handler tests and confirm they fail**

Run: `python3 -m pytest tests/test_handlers.py tests/test_exercise_library.py -q`

- [ ] **Step 5: Replace `WorkoutInput.weight` with one set-result state**

```python
class WorkoutInput(StatesGroup):
    set_result = State()
```

Implement `parse_set_input` exactly for `"вес повторы"`; comma decimals normalize to a dot and `-` maps to `None`. Reuse the service validation limits.

- [ ] **Step 6: Change the strength keyboard and captions**

The primary button becomes `Записать подход N/M` with `exercise:log:<result_id>`. When `last_set_values` is available, add `Повторить: 25 кг × 12`; use `без веса × 12` for `None`. Add a separate `Боль или дискомфорт` row. Cardio keeps a one-tap completion button and never asks for weight.

`step_caption` must include:

```text
Отдых после подхода: 75 секунд
Прошлый рабочий вес: 25 кг
```

Omit the second line when history is absent.

- [ ] **Step 7: Add the FSM handlers**

`exercise:log:` stores `result_id` in FSM state and asks:

```text
Напиши вес и повторения через пробел, например: 25 12.
Если у тренажёра нет понятной шкалы веса: - 12.
```

On valid input, call `record_set`, clear FSM state, and automatically start the fixed rest task if the exercise is not complete. On invalid input, keep the state and return the exact format hint.

`exercise:repeat:` calls `repeat_last_set` and follows the same rest/finish path. `exercise:pain:` calls `stop_for_discomfort`, cancels any timer for that result, sends the approved safety copy, and advances. When the session finishes, render each `WorkoutSummary.weight_changes` item as `Название: 25 → 27,5 кг`; omit the entire block when the tuple is empty.

- [ ] **Step 8: Replace selectable rest buttons with one automatic timer**

Delete `rest_keyboard` and `rest:timer:` callbacks. Keep a single top-level helper so dispatcher tests can substitute it without sleeping:

```python
async def start_rest_task(
    rest_tasks: dict[tuple[int, int], asyncio.Task[None]],
    context: AppContext,
    message: Message,
    telegram_id: int,
    result_id: int,
    seconds: int,
) -> None:
    key = (telegram_id, result_id)
    previous = rest_tasks.pop(key, None)
    if previous:
        previous.cancel()
    await message.answer(f"Отдых: {seconds} секунд. Я напомню, когда можно продолжать.")

    async def notify() -> None:
        try:
            await asyncio.sleep(seconds)
            session_id, _, _, completed, _ = await context.workouts.result_state(
                result_id, telegram_id
            )
            if completed:
                return
            step = await context.workouts.get_step(session_id, telegram_id)
            if step and step.result.id == result_id:
                repeat_available = (
                    await context.workouts.last_set_values(result_id, telegram_id)
                    is not None
                )
                await message.answer(
                    "Отдых закончен. Можно начинать следующий подход.",
                    reply_markup=step_keyboard(step, repeat_available=repeat_available),
                )
        except asyncio.CancelledError:
            return
        finally:
            rest_tasks.pop(key, None)

    rest_tasks[key] = asyncio.create_task(notify())
```

It cancels the existing `(telegram_id, result_id)` task, sends `Отдых: N секунд. Я напомню, когда можно продолжать.`, sleeps, rechecks result state, and sends the next-set keyboard only if the same result is still current.

- [ ] **Step 9: Add light-mode and final-feedback callbacks**

Show `Облегчённая тренировка` before cardio and route it to `session:light:<session_id>`. After `finish_if_complete`, send `session_feedback_keyboard(session_id)` with `Легко`, `Нормально`, and `Тяжело`; the callback records feedback and removes the keyboard.

- [ ] **Step 10: Run handler tests**

Run: `python3 -m pytest tests/test_handlers.py tests/test_exercise_library.py -q`

Expected: the dispatcher flow records a strength set through text input and starts only the exercise-defined rest timer.

- [ ] **Step 11: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/states.py app/handlers/workout.py tests/test_handlers.py tests/test_exercise_library.py
  git commit -m "feat: add guided set logging and rest"
fi
```

---

### Task 6: Non-consecutive-day warning and reset-button feature flag

**Files:**
- Modify: `app/config.py`
- Modify: `app/keyboards.py`
- Modify: `app/handlers/start.py`
- Modify: `app/handlers/menu.py`
- Modify: `app/handlers/workout.py`
- Modify: `deploy/fitness-bot.env.example`
- Test: `tests/test_config.py`
- Test: `tests/test_handlers.py`
- Test: `tests/test_exercise_library.py`

**Interfaces:**
- Produces: `Settings.show_reset_button: bool = True`
- Produces: `has_consecutive_days(days: list[int]) -> bool`
- Produces: `menu_keyboard(show_reset_button: bool = True)`

- [ ] **Step 1: Add exact utility and configuration tests**

```python
def test_consecutive_day_detection_wraps_across_week():
    assert not has_consecutive_days([0, 2, 4])
    assert has_consecutive_days([0, 1, 4])
    assert has_consecutive_days([0, 6])


def test_reset_button_can_be_hidden():
    labels = [
        button.text
        for row in menu_keyboard(show_reset_button=False).keyboard
        for button in row
    ]
    assert RESET_TODAY_TEXT not in labels
```

- [ ] **Step 2: Run tests and confirm missing signatures**

Run: `python3 -m pytest tests/test_config.py tests/test_handlers.py tests/test_exercise_library.py -q`

- [ ] **Step 3: Implement the warning utility**

```python
def has_consecutive_days(days: list[int]) -> bool:
    selected = set(days)
    return any((day + 1) % 7 in selected for day in selected)
```

After `days_done` in onboarding and schedule editing, send this warning without blocking progression when true:

```text
Все три тренировки нагружают ноги и ягодицы. Лучше оставить между ними день восстановления, например Пн–Ср–Пт.
```

- [ ] **Step 4: Add the reset-button feature flag**

Add `show_reset_button: bool = True` to `Settings`, `SHOW_RESET_BUTTON=true` to the example env, and a boolean parameter to `menu_keyboard`. Pass `context.settings.show_reset_button` from start, menu, and workout handlers. Keep the reset callback available even when the button is hidden so old messages remain compatible.

- [ ] **Step 5: Run focused tests**

Run: `python3 -m pytest tests/test_config.py tests/test_handlers.py tests/test_exercise_library.py -q`

Expected: warning and visible/hidden menu behavior pass.

- [ ] **Step 6: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add app/config.py app/keyboards.py app/handlers/start.py app/handlers/menu.py app/handlers/workout.py deploy/fitness-bot.env.example tests
  git commit -m "feat: add workout schedule safeguards"
fi
```

---

### Task 7: Core regression suite and documentation alignment

**Files:**
- Modify: `README.md`
- Modify: `docs/EXERCISE_IMAGE_STYLE.md`
- Modify: `DEPLOYMENT_STATUS.md` only after deployment in the release plan
- Test: all files under `tests/`

**Interfaces:**
- Consumes: all core interfaces from Tasks 1–6
- Produces: a locally verified core ready for media integration

- [ ] **Step 1: Update README facts**

Replace the v3 split, four-workout ramp, selectable timer, generated heroine, and no-weight claims with:

- three full-body v4 days;
- lower-body priority;
- six-workout two-set ramp;
- fixed automatic rest;
- per-set weight/repetition logging;
- immediate discomfort action;
- 50–60 minute duration;
- real licensed exercise cards;
- no cooldown.

- [ ] **Step 2: Replace the stale image-style document**

Remove all requirements for a generated heroine, outfit, tattoo, or visual likeness. Make `docs/EXERCISE_IMAGE_STYLE.md` point to the media manifest and require real licensed start/end photos, fixed layout, manual phase review, and cardio labels `Настройка` / `Рабочее положение`.

- [ ] **Step 3: Run the complete local verification**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check app tests
python3 -m compileall -q app
```

Expected: all commands exit 0. Do not report success if any command is interrupted or lacks its final exit status.

- [ ] **Step 4: Scan for stale behavior**

Run:

```bash
rg -n "четыре заверш|45 минут|таймер на 60 или 90|одна и та же героиня|татуиров|вес вводить.*не нужно|return_.*_v3" README.md docs app tests
```

Expected: no active-behavior matches. Historical text in the dated deployment log may remain, but it must be clearly labeled as historical.

- [ ] **Step 5: Conditional checkpoint commit**

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add README.md docs/EXERCISE_IMAGE_STYLE.md app tests
  git commit -m "docs: align workout v4 behavior"
fi
```
