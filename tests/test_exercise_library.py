from __future__ import annotations

from types import SimpleNamespace

from app.exercise_library import (
    CARDIO_CODES,
    EXERCISE_ALTERNATIVES,
    EXERCISE_GUIDANCE,
    image_path_for,
    repetitions_text,
    rest_seconds_for,
)
from app.handlers.workout import cardio_keyboard, plan_text, step_keyboard, step_text
from app.keyboards import RESET_TODAY_TEXT, menu_keyboard
from app.services.workouts import DEFAULT_TEMPLATES


def test_every_template_exercise_has_guidance():
    exercise_codes = {
        raw[0]
        for template in DEFAULT_TEMPLATES
        for raw in template["items"]
    }
    assert "cooldown" not in exercise_codes
    assert exercise_codes <= set(EXERCISE_GUIDANCE)
    assert set(CARDIO_CODES) <= set(EXERCISE_GUIDANCE)


def test_machine_replacements_have_local_guidance():
    assert EXERCISE_ALTERNATIVES["leg_press"] == "hack_squat"
    assert EXERCISE_ALTERNATIVES["hack_squat"] == "leg_press"
    assert "goblet_squat" not in EXERCISE_ALTERNATIVES
    assert EXERCISE_GUIDANCE["hack_squat"].image_filename == "hack_squat.png"
    assert image_path_for("hack_squat").is_file()
    assert EXERCISE_ALTERNATIVES["chest_press"] == "pec_deck"
    assert EXERCISE_ALTERNATIVES["pec_deck"] == "chest_press"
    assert "dumbbell_press" not in EXERCISE_ALTERNATIVES
    assert EXERCISE_GUIDANCE["pec_deck"].image_filename == "pec_deck.png"
    assert image_path_for("pec_deck").is_file()


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
    active_codes = {code for codes in by_code.values() for code in codes[1:]}
    assert "romanian_deadlift" not in active_codes
    assert "hip_thrust" not in active_codes


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


def test_plan_shows_whole_workout_and_never_requests_weight_input():
    items = [
        SimpleNamespace(
            position=1,
            id=11,
            duration_minutes=10,
            sets=1,
            reps=None,
            exercise=SimpleNamespace(code="cardio_treadmill", name="Кардио на выбор"),
        ),
        SimpleNamespace(
            position=2,
            id=12,
            duration_minutes=None,
            sets=3,
            reps=12,
            exercise=SimpleNamespace(code="leg_press", name="Жим ногами"),
        ),
    ]
    workout = SimpleNamespace(
        results=[
            SimpleNamespace(workout_exercise_id=11, sets_planned=1, reps=None),
            SimpleNamespace(workout_exercise_id=12, sets_planned=2, reps=12),
        ],
        template=SimpleNamespace(
            name="Ноги + ягодицы",
            focus="Спокойная силовая тренировка",
            items=items,
        )
    )

    text = plan_text(workout)

    assert "Полный план:" in text
    assert "1. Кардио на выбор — 10 минут" in text
    assert "2. Жим ногами — 2 подхода × 12 повторений" in text
    assert "Заминка в программу не входит" in text
    assert "Рабочий вес вводить не нужно" in text


def test_temporary_reset_button_is_available_from_main_menu():
    labels = [button.text for row in menu_keyboard().keyboard for button in row]
    assert RESET_TODAY_TEXT in labels


def test_machine_rep_ranges_are_shown_in_plan_language():
    assert repetitions_text("seated_leg_curl", 15) == "12–15 повторений"
    assert repetitions_text("hip_abduction", 20) == "15–20 повторений"
    assert repetitions_text("machine_shoulder_press", 12) == "10–12 повторений"
    assert (
        repetitions_text("glute_kickback", 15)
        == "12–15 повторений на каждую ногу"
    )


def test_exercise_card_contains_detailed_technique_and_one_done_button():
    step = SimpleNamespace(
        exercise=SimpleNamespace(code="seated_row", name="Горизонтальная тяга"),
        item=SimpleNamespace(duration_minutes=None),
        result=SimpleNamespace(id=77, completed_sets=0, sets_planned=2),
    )

    text = step_text(step)
    keyboard = step_keyboard(step)

    assert "Исходное положение" in text
    assert "Движение" in text
    assert "Дыхание" in text
    assert "Главный ориентир" in text
    assert "Не делай так" in text
    assert "лопаток назад и вниз" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "exercise:set:77"
    assert "Подход 1/2" in keyboard.inline_keyboard[0][0].text
    assert keyboard.inline_keyboard[1][0].callback_data == "exercise:replace:77"
    assert keyboard.inline_keyboard[1][1].callback_data == "exercise:skip:77"
    assert "вес" not in keyboard.inline_keyboard[0][0].text.lower()


def test_cardio_choice_has_all_three_options():
    keyboard = cardio_keyboard(42)
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == [
        "cardio:select:42:cardio_treadmill",
        "cardio:select:42:cardio_elliptical",
        "cardio:select:42:cardio_bike",
    ]
