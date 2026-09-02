from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.exercise_library import (
    CARDIO_CODES,
    EXERCISE_ALTERNATIVES,
    EXERCISE_GUIDANCE,
    image_path_for,
    repetitions_text,
    rest_seconds_for,
)
from app.handlers.workout import (
    cardio_keyboard,
    parse_set_input,
    plan_text,
    step_caption,
    step_keyboard,
    step_text,
)
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


def test_plan_shows_whole_workout_and_requests_per_set_input():
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
    assert "запиши фактические вес и повторения" in text


def test_temporary_reset_button_is_available_from_main_menu():
    labels = [button.text for row in menu_keyboard().keyboard for button in row]
    assert RESET_TODAY_TEXT in labels


def test_reset_button_can_be_hidden_from_main_menu():
    labels = [
        button.text
        for row in menu_keyboard(show_reset_button=False).keyboard
        for button in row
    ]
    assert RESET_TODAY_TEXT not in labels


def test_machine_rep_ranges_are_shown_in_plan_language():
    assert repetitions_text("seated_leg_curl", 15) == "12–15 повторений"
    assert repetitions_text("hip_abduction", 20) == "15–20 повторений"
    assert repetitions_text("machine_shoulder_press", 12) == "10–12 повторений"
    assert (
        repetitions_text("glute_kickback", 15)
        == "12–15 повторений на каждую ногу"
    )


def make_strength_step(previous_weight: Decimal | None = None):
    return SimpleNamespace(
        exercise=SimpleNamespace(code="seated_row", name="Горизонтальная тяга"),
        item=SimpleNamespace(duration_minutes=None, position=2),
        result=SimpleNamespace(
            id=77,
            completed_sets=0,
            sets_planned=2,
            reps=12,
        ),
        previous_weight=previous_weight,
    )


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


def test_strength_card_has_log_repeat_skip_replace_and_pain_actions():
    step = make_strength_step(previous_weight=Decimal("25"))

    keyboard = step_keyboard(step, repeat_available=True)
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert f"exercise:log:{step.result.id}" in callbacks
    assert f"exercise:repeat:{step.result.id}" in callbacks
    assert f"exercise:pain:{step.result.id}" in callbacks
    assert f"exercise:skip:{step.result.id}" in callbacks
    assert f"exercise:replace:{step.result.id}" in callbacks
    assert any("25 кг × 12" in button.text for row in keyboard.inline_keyboard for button in row)


def test_repeat_button_supports_a_machine_without_weight_scale():
    step = make_strength_step()

    keyboard = step_keyboard(
        step,
        repeat_available=True,
        last_set=(None, 12),
    )

    assert any(
        button.text == "Повторить: без веса × 12"
        for row in keyboard.inline_keyboard
        for button in row
    )


def test_strength_card_contains_detailed_technique_and_fixed_rest():
    step = SimpleNamespace(
        exercise=SimpleNamespace(code="seated_row", name="Горизонтальная тяга"),
        item=SimpleNamespace(duration_minutes=None, position=2),
        result=SimpleNamespace(id=77, completed_sets=0, sets_planned=2, reps=12),
        previous_weight=Decimal("25"),
        session=SimpleNamespace(
            template=SimpleNamespace(items=[object(), object()])
        ),
    )

    text = step_text(step)
    caption = step_caption(step)

    assert "Исходное положение" in text
    assert "Движение" in text
    assert "Дыхание" in text
    assert "Главный ориентир" in text
    assert "Не делай так" in text
    assert "лопаток назад и вниз" in text
    assert "Отдых после подхода: 90 секунд" in caption
    assert "Прошлый рабочий вес: 25 кг" in caption


def test_cardio_choice_has_all_three_options():
    keyboard = cardio_keyboard(42)
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == [
        "cardio:select:42:cardio_treadmill",
        "cardio:select:42:cardio_elliptical",
        "cardio:select:42:cardio_bike",
        "session:light:42",
    ]
