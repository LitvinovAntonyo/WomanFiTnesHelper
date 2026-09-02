from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.context import AppContext
from app.exercise_library import (
    CARDIO_CODES,
    CARDIO_LABELS,
    alternative_code_for,
    guidance_for,
    image_path_for,
    repetitions_text,
    rest_seconds_for,
)
from app.keyboards import RESET_TODAY_TEXT, menu_keyboard
from app.models import WorkoutSession
from app.services.scheduler import local_to_utc_naive, utc_naive_to_local
from app.services.workouts import SetLogState, WorkoutStep
from app.states import RescheduleInput, WorkoutInput

SET_INPUT_HINT = (
    "Напиши вес и повторения через пробел, например: 25 12.\n"
    "Если у тренажёра нет понятной шкалы веса: - 12."
)


def format_decimal(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized.replace(".", ",")


def parse_set_input(value: str) -> tuple[Decimal | None, int]:
    parts = value.strip().split()
    if len(parts) != 2:
        raise ValueError(SET_INPUT_HINT)
    raw_weight, raw_reps = parts
    try:
        reps = int(raw_reps)
        weight = (
            None
            if raw_weight == "-"
            else Decimal(raw_weight.replace(",", "."))
        )
        if not 1 <= reps <= 100:
            raise ValueError
        if weight is not None and (
            not weight.is_finite() or not Decimal("0") <= weight <= Decimal("999")
        ):
            raise ValueError
    except (InvalidOperation, ValueError):
        raise ValueError(SET_INPUT_HINT) from None
    return weight, reps


def step_keyboard(
    step: WorkoutStep,
    *,
    repeat_available: bool = False,
    last_set: tuple[Decimal | None, int] | None = None,
) -> InlineKeyboardMarkup:
    if step.item.duration_minutes:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Кардио выполнено ✅",
                        callback_data=f"exercise:set:{step.result.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Пропустить",
                        callback_data=f"exercise:skip:{step.result.id}",
                    )
                ],
            ]
        )

    next_set = min(step.result.completed_sets + 1, step.result.sets_planned)
    rows = [
        [
            InlineKeyboardButton(
                text=f"Записать подход {next_set}/{step.result.sets_planned}",
                callback_data=f"exercise:log:{step.result.id}",
            )
        ]
    ]
    if repeat_available:
        values = last_set
        if values is None and step.result.reps is not None:
            values = (step.previous_weight, step.result.reps)
        if values is not None:
            weight, reps = values
            weight_text = (
                "без веса" if weight is None else f"{format_decimal(weight)} кг"
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Повторить: {weight_text} × {reps}",
                        callback_data=f"exercise:repeat:{step.result.id}",
                    )
                ]
            )
    actions = []
    if (
        step.result.completed_sets == 0
        and step.exercise.code not in CARDIO_CODES
        and alternative_code_for(step.exercise.code)
    ):
        actions.append(
            InlineKeyboardButton(
                text="Заменить",
                callback_data=f"exercise:replace:{step.result.id}",
            )
        )
    actions.append(
        InlineKeyboardButton(
            text="Пропустить",
            callback_data=f"exercise:skip:{step.result.id}",
        )
    )
    rows.append(actions)
    rows.append(
        [
            InlineKeyboardButton(
                text="Боль или дискомфорт",
                callback_data=f"exercise:pain:{step.result.id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cardio_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"cardio:select:{session_id}:{code}",
                )
            ]
            for code, label in CARDIO_LABELS.items()
        ]
        + [
            [
                InlineKeyboardButton(
                    text="Облегчённая тренировка",
                    callback_data=f"session:light:{session_id}",
                )
            ]
        ]
    )


def effort_keyboard(result_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Легко", callback_data=f"effort:{result_id}:easy"),
                InlineKeyboardButton(text="Нормально", callback_data=f"effort:{result_id}:ok"),
            ],
            [
                InlineKeyboardButton(text="Тяжело", callback_data=f"effort:{result_id}:hard"),
                InlineKeyboardButton(
                    text="Был дискомфорт", callback_data=f"effort:{result_id}:pain"
                ),
            ],
        ]
    )


def session_feedback_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Легко",
                    callback_data=f"session:feedback:{session_id}:easy",
                ),
                InlineKeyboardButton(
                    text="Нормально",
                    callback_data=f"session:feedback:{session_id}:ok",
                ),
                InlineKeyboardButton(
                    text="Тяжело",
                    callback_data=f"session:feedback:{session_id}:hard",
                ),
            ]
        ]
    )


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
    await message.answer(
        f"Отдых: {seconds} секунд. Я напомню, когда можно продолжать."
    )

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
                last_set = await context.workouts.last_set_values(
                    result_id, telegram_id
                )
                await message.answer(
                    "Отдых закончен. Можно начинать следующий подход.",
                    reply_markup=step_keyboard(
                        step,
                        repeat_available=last_set is not None,
                        last_set=last_set,
                    ),
                )
        except asyncio.CancelledError:
            return
        finally:
            if rest_tasks.get(key) is asyncio.current_task():
                rest_tasks.pop(key, None)

    rest_tasks[key] = asyncio.create_task(notify())


def dose_text(step: WorkoutStep) -> str:
    return (
        f"{step.item.duration_minutes} минут"
        if step.item.duration_minutes
        else f"{step.result.sets_planned} × "
        f"{repetitions_text(step.exercise.code, step.result.reps)}"
    )


def plan_text(workout: WorkoutSession) -> str:
    items = sorted(workout.template.items, key=lambda item: item.position)
    results = {result.workout_exercise_id: result for result in workout.results}
    lines = [
        f"🏋️ {workout.template.name}",
        workout.template.focus,
        "",
        "Полный план:",
    ]
    for item in items:
        result = results.get(item.id)
        dose = (
            f"{item.duration_minutes} минут"
            if item.duration_minutes
            else f"{result.sets_planned if result else item.sets} подхода × "
            f"{repetitions_text(item.exercise.code, result.reps if result else item.reps)}"
        )
        name = "Кардио на выбор" if item.position == 1 else item.exercise.name
        lines.append(f"{item.position}. {name} — {dose}")
    lines.extend(
        [
            "",
            "Сначала кардио, затем силовой блок. Заминка в программу не входит.",
            "После каждого силового подхода запиши фактические вес и повторения. "
            "Выбирай нагрузку с запасом примерно 2–3 технически чистых повтора.",
            "Дальше покажу каждое упражнение отдельно: картинку, технику и частые ошибки.",
        ]
    )
    return "\n".join(lines)


def step_caption(step: WorkoutStep) -> str:
    guidance = guidance_for(step.exercise.code)
    total_items = len(step.session.template.items)
    lines = [
        f"{step.item.position}/{total_items} · {step.exercise.name}\n"
        f"Объём: {dose_text(step)}\n"
        f"Нагрузка: {guidance.weight_label}"
    ]
    rest_seconds = rest_seconds_for(step.exercise.code)
    if rest_seconds is not None:
        lines.append(f"Отдых после подхода: {rest_seconds} секунд")
    if step.previous_weight is not None:
        lines.append(
            f"Прошлый рабочий вес: {format_decimal(step.previous_weight)} кг"
        )
    return "\n".join(lines)


def step_text(step: WorkoutStep) -> str:
    guidance = guidance_for(step.exercise.code)
    return (
        f"Техника — {step.exercise.name}\n\n"
        f"Исходное положение\n{guidance.setup}\n\n"
        f"Движение\n{guidance.movement}\n\n"
        f"Дыхание\n{guidance.breathing}\n\n"
        f"Главный ориентир\n{guidance.cues}\n\n"
        f"Не делай так\n{guidance.mistakes}"
    )


def build_workout_router(context: AppContext) -> Router:
    router = Router(name="workout")
    rest_tasks: dict[tuple[int, int], asyncio.Task[None]] = {}

    async def clear_pending_set_input(state: FSMContext) -> None:
        if await state.get_state() == WorkoutInput.set_result.state:
            await state.clear()

    async def send_current_step(
        message: Message, session_id: int, telegram_id: int
    ) -> None:
        step = await context.workouts.get_step(session_id, telegram_id)
        if step is None:
            completed = await context.workouts.finish_if_complete(session_id)
            if completed:
                progress = await context.progress.get(telegram_id)
                summary = await context.workouts.summary(session_id)
                skipped = (
                    f" · пропущено: {summary.skipped_exercises}"
                    if summary.skipped_exercises
                    else ""
                )
                weight_lines = [
                    f"{item.exercise_name}: {format_decimal(item.previous_kg)} → "
                    f"{format_decimal(item.current_kg)} кг"
                    for item in summary.weight_changes
                ]
                weight_block = (
                    "\n\nИзменения рабочих весов:\n" + "\n".join(weight_lines)
                    if weight_lines
                    else ""
                )
                await message.answer(
                    "Тренировка завершена ✅\n"
                    f"Выполнено упражнений: {summary.completed_exercises}{skipped}\n"
                    f"Время: около {summary.duration_minutes} минут\n"
                    f"Общий прогресс этого месяца: {progress.month_completed}/{progress.monthly_target}. "
                    "На сегодня всё — отдельной заминки в плане нет."
                    f"{weight_block}",
                    reply_markup=menu_keyboard(),
                )
                await message.answer(
                    "Насколько комфортной была нагрузка?",
                    reply_markup=session_feedback_keyboard(session_id),
                )
            return
        image_path = image_path_for(step.exercise.code)
        if image_path.is_file():
            cached_file_id = await context.workouts.media_file_id(step.exercise.code)
            sent = await message.answer_photo(
                cached_file_id or FSInputFile(image_path), caption=step_caption(step)
            )
            photos = getattr(sent, "photo", None)
            if not cached_file_id and photos:
                await context.workouts.remember_media_file_id(
                    step.exercise.code, photos[-1].file_id
                )
        else:
            await message.answer(step_caption(step))
        last_set = None
        if not step.item.duration_minutes:
            last_set = await context.workouts.last_set_values(
                step.result.id, telegram_id
            )
        await message.answer(
            step_text(step),
            reply_markup=step_keyboard(
                step,
                repeat_available=last_set is not None,
                last_set=last_set,
            ),
        )

    async def send_plan(message: Message, session_id: int, telegram_id: int) -> None:
        workout = await context.workouts.get_plan(session_id, telegram_id)
        await message.answer(plan_text(workout))

    async def ask_for_cardio(message: Message, session_id: int) -> None:
        await message.answer(
            "С чего начнём кардио-разогрев? Выбери один вариант на 10 минут. "
            "Темп спокойный: можно сказать короткую фразу без сильной одышки.",
            reply_markup=cardio_keyboard(session_id),
        )

    async def continue_after_logged_set(
        message: Message, telegram_id: int, logged_set: SetLogState
    ) -> None:
        result_id = logged_set.result_id
        if logged_set.exercise_complete:
            await context.workouts.record_effort(result_id, telegram_id, None)
            await send_current_step(
                message,
                logged_set.session_id,
                telegram_id,
            )
            return
        await start_rest_task(
            rest_tasks,
            context,
            message,
            telegram_id,
            result_id,
            logged_set.rest_seconds,
        )

    @router.message(F.text == "🏋️ Начать тренировку")
    async def start_from_menu(message: Message, state: FSMContext) -> None:
        assert message.from_user is not None
        await clear_pending_set_input(state)
        workout = await context.workouts.active_or_new(message.from_user.id)
        if workout.started_at:
            await message.answer("Продолжаем с того места, где остановились.")
            await send_current_step(message, workout.id, message.from_user.id)
        else:
            await ask_for_cardio(message, workout.id)

    @router.message(F.text == RESET_TODAY_TEXT)
    async def reset_current_day(message: Message, state: FSMContext) -> None:
        assert message.from_user is not None
        await clear_pending_set_input(state)
        for key, task in list(rest_tasks.items()):
            if key[0] == message.from_user.id:
                task.cancel()
                rest_tasks.pop(key, None)
        reset = await context.workouts.reset_current_day(message.from_user.id)
        if reset:
            await message.answer(
                "Текущий тренировочный день сброшен. Все тестовые отметки этого дня "
                "удалены — можно начать его заново.",
                reply_markup=menu_keyboard(),
            )
        else:
            await message.answer(
                "Сегодняшней тренировки для сброса пока нет.",
                reply_markup=menu_keyboard(),
            )

    @router.callback_query(F.data.startswith("reminder:yes:"))
    async def accept_reminder(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        reminder_id = int((callback.data or "").rsplit(":", 1)[1])
        workout = await context.workouts.confirm_from_reminder(
            reminder_id, callback.from_user.id
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Начать, когда буду готова",
                        callback_data=f"session:start:{workout.id}",
                    )
                ]
            ]
        )
        if callback.message:
            await callback.message.answer(
                "Отлично, договорились. Перед началом покажу весь комплекс, затем упражнения по порядку.",
                reply_markup=keyboard,
            )
        await callback.answer("Тренировка подтверждена")

    @router.callback_query(F.data.startswith("session:start:"))
    async def start_session(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        session_id = int((callback.data or "").rsplit(":", 1)[1])
        if callback.message:
            await ask_for_cardio(callback.message, session_id)
        await callback.answer()

    @router.callback_query(F.data.startswith("session:light:"))
    async def enable_light_session(
        callback: CallbackQuery, state: FSMContext
    ) -> None:
        await clear_pending_set_input(state)
        session_id = int((callback.data or "").rsplit(":", 1)[1])
        try:
            changed = await context.workouts.enable_light_mode(
                session_id, callback.from_user.id
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            message = (
                "Облегчённый режим включён: в ещё не начатых силовых "
                "упражнениях будет не больше двух подходов."
                if changed
                else "Облегчённый режим уже учтён для этой тренировки."
            )
            await callback.message.answer(message)
            await ask_for_cardio(callback.message, session_id)
        await callback.answer("Облегчённый режим включён")

    @router.callback_query(F.data.startswith("cardio:select:"))
    async def select_cardio(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        _, _, raw_session_id, cardio_code = (callback.data or "").split(":")
        session_id = int(raw_session_id)
        await context.workouts.choose_cardio(session_id, callback.from_user.id, cardio_code)
        await context.workouts.begin(session_id, callback.from_user.id)
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await send_plan(callback.message, session_id, callback.from_user.id)
            await send_current_step(callback.message, session_id, callback.from_user.id)
        await callback.answer(f"Выбрано: {CARDIO_LABELS[cardio_code]}")

    @router.callback_query(F.data.startswith("exercise:set:"))
    async def complete_set(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        task = rest_tasks.pop((callback.from_user.id, result_id), None)
        if task:
            task.cancel()
        try:
            _, _, _, completed, strength_exercise = (
                await context.workouts.result_state(result_id, callback.from_user.id)
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if completed:
            await callback.answer("Этот шаг уже завершён", show_alert=True)
            return
        if strength_exercise:
            await state.set_state(WorkoutInput.set_result)
            await state.update_data(result_id=result_id)
            if callback.message:
                with suppress(Exception):
                    await callback.message.edit_reply_markup(reply_markup=None)
                await callback.message.answer(SET_INPUT_HINT)
            await callback.answer()
            return

        session_id, _ = await context.workouts.complete_next_set(
            result_id, callback.from_user.id
        )
        await context.workouts.record_effort(result_id, callback.from_user.id, None)
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await send_current_step(
                callback.message, session_id, callback.from_user.id
            )
        await callback.answer("Записано")

    @router.callback_query(F.data.startswith("exercise:log:"))
    async def request_set_result(
        callback: CallbackQuery, state: FSMContext
    ) -> None:
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        try:
            _, _, _, completed, strength_exercise = (
                await context.workouts.result_state(result_id, callback.from_user.id)
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if completed or not strength_exercise:
            await callback.answer("Этот подход уже недоступен", show_alert=True)
            return
        await state.set_state(WorkoutInput.set_result)
        await state.update_data(result_id=result_id)
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(SET_INPUT_HINT)
        await callback.answer()

    @router.message(WorkoutInput.set_result, F.text)
    async def receive_set_result(message: Message, state: FSMContext) -> None:
        assert message.from_user is not None
        try:
            weight_kg, reps = parse_set_input(message.text or "")
        except ValueError:
            await message.answer(SET_INPUT_HINT)
            return
        data = await state.get_data()
        result_id = data.get("result_id")
        if not isinstance(result_id, int):
            await state.clear()
            await message.answer("Подход не найден. Открой текущую тренировку ещё раз.")
            return
        try:
            logged_set = await context.workouts.record_set(
                result_id,
                message.from_user.id,
                reps=reps,
                weight_kg=weight_kg,
            )
        except ValueError as exc:
            await state.clear()
            await message.answer(str(exc))
            return
        await state.clear()
        await continue_after_logged_set(
            message, message.from_user.id, logged_set
        )

    @router.callback_query(F.data.startswith("exercise:repeat:"))
    async def repeat_set(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        try:
            logged_set = await context.workouts.repeat_last_set(
                result_id, callback.from_user.id
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await continue_after_logged_set(
                callback.message, callback.from_user.id, logged_set
            )
        await callback.answer("Подход записан")

    @router.callback_query(F.data.startswith("exercise:pain:"))
    async def stop_for_pain(
        callback: CallbackQuery, state: FSMContext
    ) -> None:
        await clear_pending_set_input(state)
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        task = rest_tasks.pop((callback.from_user.id, result_id), None)
        if task:
            task.cancel()
        try:
            session_id = await context.workouts.stop_for_discomfort(
                result_id, callback.from_user.id
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                "Упражнение остановлено. Не продолжай через острую или "
                "сохраняющуюся боль; при необходимости обратись к специалисту."
            )
            await send_current_step(
                callback.message, session_id, callback.from_user.id
            )
        await callback.answer("Упражнение остановлено")

    @router.callback_query(F.data.startswith("effort:"))
    async def record_effort(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        _, raw_result_id, effort = (callback.data or "").split(":")
        result_id = int(raw_result_id)
        session_id = await context.workouts.record_effort(
            result_id, callback.from_user.id, effort
        )
        notes = {
            "easy": "Легко — если так будет два раза подряд, добавлю один повтор.",
            "ok": "Нормально — нагрузку оставляю без изменений.",
            "hard": "Тяжело — в следующем таком упражнении уберу один повтор.",
            "pain": "Дискомфорт записан: нагрузку не повышаю. При острой или сохраняющейся боли упражнение лучше прекратить и обсудить со специалистом.",
        }
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(notes[effort])
            await send_current_step(callback.message, session_id, callback.from_user.id)
        await callback.answer("Оценка сохранена")

    @router.callback_query(F.data.startswith("session:feedback:"))
    async def record_session_feedback(
        callback: CallbackQuery, state: FSMContext
    ) -> None:
        await clear_pending_set_input(state)
        _, _, raw_session_id, effort = (callback.data or "").split(":")
        try:
            await context.workouts.record_session_feedback(
                int(raw_session_id), callback.from_user.id, effort
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        labels = {"easy": "легко", "ok": "нормально", "hard": "тяжело"}
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                f"Записала: {labels[effort]}. Учту это в следующих тренировках.",
                reply_markup=menu_keyboard(),
            )
        await callback.answer("Оценка сохранена")

    @router.callback_query(F.data.startswith("exercise:replace:"))
    async def replace_exercise(
        callback: CallbackQuery, state: FSMContext
    ) -> None:
        await clear_pending_set_input(state)
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        try:
            session_id = await context.workouts.replace_exercise(
                result_id, callback.from_user.id
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("Показываю готовую замену из той же библиотеки.")
            await send_current_step(callback.message, session_id, callback.from_user.id)
        await callback.answer("Упражнение заменено")

    @router.callback_query(F.data.startswith("exercise:skip:"))
    async def skip_exercise(callback: CallbackQuery, state: FSMContext) -> None:
        await clear_pending_set_input(state)
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        task = rest_tasks.pop((callback.from_user.id, result_id), None)
        if task:
            task.cancel()
        session_id = await context.workouts.skip_exercise(
            result_id, callback.from_user.id
        )
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("Пропустили без штрафа и без обнуления серии.")
            await send_current_step(callback.message, session_id, callback.from_user.id)
        await callback.answer("Пропущено")

    # Compatibility for buttons already sent by the previous deployed version.
    @router.callback_query(F.data.startswith("exercise:done:"))
    async def complete_legacy_exercise(
        callback: CallbackQuery, state: FSMContext
    ) -> None:
        await clear_pending_set_input(state)
        result_id = int((callback.data or "").rsplit(":", 1)[1])
        session_id = await context.workouts.complete_exercise(result_id, callback.from_user.id)
        await context.workouts.record_effort(result_id, callback.from_user.id, None)
        if callback.message:
            with suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
            await send_current_step(callback.message, session_id, callback.from_user.id)
        await callback.answer("Готово")

    @router.callback_query(F.data.startswith("reminder:skip:"))
    async def skip_reminder(callback: CallbackQuery) -> None:
        reminder_id = int((callback.data or "").rsplit(":", 1)[1])
        next_workout = await context.reminders.skip(reminder_id, callback.from_user.id)
        progress = await context.progress.get(callback.from_user.id)
        timezone = await context.reminders.user_timezone(callback.from_user.id)
        next_text = (
            utc_naive_to_local(next_workout, timezone).strftime("%d.%m, %H:%M")
            if next_workout
            else "пока не запланирована"
        )
        if callback.message:
            await callback.message.answer(
                "Окей. Никаких упрёков — общий прогресс сохраняется: "
                f"{progress.month_completed}/{progress.monthly_target}. Следующая тренировка: {next_text}."
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("reminder:move:"))
    async def choose_move(callback: CallbackQuery) -> None:
        reminder_id = int((callback.data or "").rsplit(":", 1)[1])
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Завтра", callback_data=f"move:quick:{reminder_id}:1"
                    ),
                    InlineKeyboardButton(
                        text="Через 2 дня", callback_data=f"move:quick:{reminder_id}:2"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Выбрать дату и время", callback_data=f"move:manual:{reminder_id}"
                    )
                ],
            ]
        )
        if callback.message:
            await callback.message.answer("На когда перенести?", reply_markup=keyboard)
        await callback.answer()

    @router.callback_query(F.data.startswith("move:quick:"))
    async def quick_move(callback: CallbackQuery) -> None:
        _, _, raw_id, raw_days = (callback.data or "").split(":")
        user = await context.users.get_by_telegram_id(callback.from_user.id)
        if user is None or user.settings is None:
            await callback.answer("Настройки не найдены", show_alert=True)
            return
        tz = ZoneInfo(user.settings.timezone)
        clock = time.fromisoformat(user.settings.workout_time)
        local_date = (datetime.now(tz) + timedelta(days=int(raw_days))).date()
        local_value = datetime.combine(local_date, clock, tzinfo=tz)
        await context.reminders.reschedule(
            int(raw_id), callback.from_user.id, local_to_utc_naive(local_value)
        )
        if callback.message:
            await callback.message.answer(
                f"Перенесла на {local_value.strftime('%d.%m, %H:%M')}. Общий прогресс сохранён."
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("move:manual:"))
    async def manual_move(callback: CallbackQuery, state: FSMContext) -> None:
        reminder_id = int((callback.data or "").rsplit(":", 1)[1])
        await state.set_state(RescheduleInput.date_time)
        await state.update_data(reminder_id=reminder_id)
        if callback.message:
            await callback.message.answer("Напиши новую дату и время: ДД.ММ ЧЧ:ММ, например 05.09 19:30.")
        await callback.answer()

    @router.message(RescheduleInput.date_time, F.text)
    async def receive_manual_move(message: Message, state: FSMContext) -> None:
        assert message.from_user is not None
        timezone = await context.reminders.user_timezone(message.from_user.id)
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        try:
            parsed = datetime.strptime((message.text or "").strip(), "%d.%m %H:%M")
            local_value = parsed.replace(year=now.year, tzinfo=tz)
            if local_value <= now:
                local_value = local_value.replace(year=now.year + 1)
        except ValueError:
            await message.answer("Формат: ДД.ММ ЧЧ:ММ, например 05.09 19:30.")
            return
        data = await state.get_data()
        try:
            await context.reminders.reschedule(
                data["reminder_id"], message.from_user.id, local_to_utc_naive(local_value)
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await state.clear()
        await message.answer(
            f"Перенесла на {local_value.strftime('%d.%m.%Y, %H:%M')}. Прогресс сохранён.",
            reply_markup=menu_keyboard(),
        )

    return router
