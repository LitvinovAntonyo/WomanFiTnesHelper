from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExerciseGuidance:
    image_filename: str
    weight_label: str
    setup: str
    movement: str
    breathing: str
    cues: str
    mistakes: str


CARDIO_CODES = ("cardio_treadmill", "cardio_elliptical", "cardio_bike")
CARDIO_LABELS = {
    "cardio_treadmill": "Дорожка",
    "cardio_elliptical": "Эллипс",
    "cardio_bike": "Велотренажёр",
}


# All alternatives already belong to the local library and have matching-style imagery.
# This keeps replacement deterministic and avoids introducing unreviewed exercises mid-session.
EXERCISE_ALTERNATIVES: dict[str, str] = {
    "leg_press": "hack_squat",
    "hack_squat": "leg_press",
    "leg_extension": "leg_press",
    "glute_kickback": "hip_abduction",
    "hip_abduction": "glute_kickback",
    "lat_pulldown": "seated_row",
    "seated_row": "lat_pulldown",
    "chest_press": "pec_deck",
    "pec_deck": "chest_press",
}

REP_RANGE_WIDTH: dict[str, int] = {
    "hack_squat": 2,
    "leg_press": 2,
    "machine_shoulder_press": 2,
    "seated_leg_curl": 3,
    "glute_kickback": 3,
    "leg_extension": 3,
    "hip_abduction": 5,
    "hip_adduction": 5,
    "lat_pulldown": 2,
    "seated_row": 2,
    "chest_press": 2,
    "pec_deck": 2,
}

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
    "pec_deck": 90,
}


EXERCISE_GUIDANCE: dict[str, ExerciseGuidance] = {
    "cardio_treadmill": ExerciseGuidance(
        image_filename="cardio_treadmill.png",
        weight_label="10 минут; можно говорить короткими фразами",
        setup="Встань по центру дорожки. Начни с медленной ходьбы и потом прибавь скорость.",
        movement="Иди быстро или легко беги. Двигайся естественно и не держись за поручни.",
        breathing="Дыши спокойно. Темп подходит, если можешь сказать короткую фразу.",
        cues="Смотри вперёд и расслабь плечи. Это разминка — уставать до предела не нужно.",
        mistakes="Не начинай резко. Остановись, если кружится голова или появилась боль.",
    ),
    "cardio_elliptical": ExerciseGuidance(
        image_filename="cardio_elliptical.png",
        weight_label="10 минут; можно говорить короткими фразами",
        setup="Поставь стопы целиком на педали и спокойно возьмись за рукояти. Спину держи прямо.",
        movement="Двигай руками и ногами плавно, как при ходьбе на лыжах. Выбери лёгкое сопротивление.",
        breathing="Дыши спокойно. Темп подходит, если можешь сказать короткую фразу.",
        cues="Дави на педали всей стопой и не переноси вес на руки.",
        mistakes="Не сутулься, не своди колени внутрь и не ставь тяжёлое сопротивление.",
    ),
    "cardio_bike": ExerciseGuidance(
        image_filename="cardio_bike.png",
        weight_label="10 минут; можно говорить короткими фразами",
        setup="Настрой седло так, чтобы внизу колено оставалось немного согнутым. Стопы поставь на педали.",
        movement="Крути педали плавно и не раскачивай таз. Сопротивление выбери лёгкое.",
        breathing="Дыши спокойно. Темп подходит, если можешь сказать короткую фразу.",
        cues="Расслабь плечи и кисти. Колени направляй вперёд.",
        mistakes="Не ставь седло слишком низко или высоко, не сутулься и не зажимай руль.",
    ),
    "seated_leg_curl": ExerciseGuidance(
        image_filename="seated_leg_curl.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Прижми спину и таз к сиденью. Нижний валик должен быть чуть выше пяток.",
        movement="Согни ноги и потяни валик вниз, будто убираешь пятки под сиденье. Медленно верни ноги.",
        breathing="Сгибаешь ноги — выдох. Возвращаешь — вдох.",
        cues="Представь, что таз приклеен к сиденью: он не двигается.",
        mistakes="Не дёргай вес, не отрывай таз и не бросай валик обратно.",
    ),
    "glute_kickback": ExerciseGuidance(
        image_filename="glute_kickback.png",
        weight_label="удобный вес; запиши результат после обеих ног",
        setup="Возьмись за рукояти и немного наклонись вперёд. Одну стопу поставь на платформу тренажёра.",
        movement="Толкни платформу назад пяткой, будто закрываешь дверь. Медленно верни ногу и потом поменяй сторону.",
        breathing="Толкаешь назад — выдох. Возвращаешь ногу — вдох.",
        cues="Двигай ногой, а корпус и таз оставляй на месте.",
        mistakes="Не раскачивайся, не разворачивай таз и не прогибай поясницу.",
    ),
    "leg_extension": ExerciseGuidance(
        image_filename="leg_extension.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Прижми спину и таз к сиденью. Валик положи на голени чуть выше стоп.",
        movement="Плавно выпрями ноги почти до конца. На секунду задержись и медленно опусти их.",
        breathing="Выпрямляешь ноги — выдох. Опускаешь — вдох.",
        cues="Таз держи на сиденье, обе ноги двигай одинаково.",
        mistakes="Не подбрасывай валик, не выпрямляй колени до щелчка и не бросай вес вниз.",
    ),
    "hip_abduction": ExerciseGuidance(
        image_filename="hip_abduction.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Сядь глубоко и прижми спину. Колени поставь наружной стороной к подушкам.",
        movement="Плавно разведи колени, на секунду задержись и медленно сведи их обратно.",
        breathing="Разводишь колени — выдох. Сводишь — вдох.",
        cues="Представь, что раскрываешь коленями тяжёлую книгу. Корпус не двигается.",
        mistakes="Не делай рывок, не разводи ноги через боль и не бросай вес обратно.",
    ),
    "hip_adduction": ExerciseGuidance(
        image_filename="hip_adduction.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Сядь глубоко и прижми спину. Колени поставь внутренней стороной к подушкам.",
        movement="Плавно сведи колени, на секунду задержись и медленно разведи их обратно.",
        breathing="Сводишь колени — выдох. Разводишь — вдох.",
        cues="Представь, что коленями сжимаешь большой мяч. Корпус не двигается.",
        mistakes="Не начинай слишком широко, не делай рывок и не бросай вес обратно.",
    ),
    "leg_press": ExerciseGuidance(
        image_filename="leg_press.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Прижми спину и таз. Стопы поставь на платформу на ширине плеч. Ноги почти прямые, но колени не запирай.",
        movement="Согни колени и опусти платформу до удобной глубины. Затем выжми её всей стопой.",
        breathing="Опускаешь платформу — вдох. Выжимаешь — выдох.",
        cues="Представь, что стопы приклеены к платформе. Колени направляй туда же, куда носки.",
        mistakes="Не своди колени, не отрывай пятки и таз, не выпрямляй ноги до щелчка.",
    ),
    "lat_pulldown": ExerciseGuidance(
        image_filename="lat_pulldown.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Зафиксируй бёдра валиком и возьмись за гриф двумя руками. Слегка отклонись назад.",
        movement="Потяни гриф к верхней части груди. Медленно выпрями руки и верни гриф вверх.",
        breathing="Тянешь вниз — выдох. Возвращаешь вверх — вдох.",
        cues="Тяни локти вниз, будто направляешь их к карманам. Плечи не поднимай.",
        mistakes="Не тяни гриф за голову, не раскачивайся и не дёргай вес.",
    ),
    "chest_press": ExerciseGuidance(
        image_filename="chest_press.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Настрой сиденье: рукояти должны быть на уровне груди. Прижми спину и поставь стопы на пол.",
        movement="Толкни рукояти вперёд, но не выпрямляй локти до щелчка. Медленно верни руки.",
        breathing="Толкаешь вперёд — выдох. Возвращаешь — вдох.",
        cues="Представь, что отталкиваешь от себя тяжёлую дверь. Плечи держи опущенными.",
        mistakes="Не отрывай спину, не заламывай кисти и не бросай вес назад.",
    ),
    "machine_shoulder_press": ExerciseGuidance(
        image_filename="machine_shoulder_press.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Настрой сиденье: рукояти должны быть на уровне плеч. Прижми спину и поставь стопы на пол.",
        movement="Выжми рукояти вверх, но не выпрямляй локти до щелчка. Медленно опусти руки к плечам.",
        breathing="Жмёшь вверх — выдох. Опускаешь руки — вдох.",
        cues="Представь, что толкаешь потолок вверх. Спину не отрывай.",
        mistakes="Не прогибай поясницу, не поднимай плечи к ушам и не бросай вес вниз.",
    ),
    "pec_deck": ExerciseGuidance(
        image_filename="pec_deck.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Настрой сиденье: рукояти должны быть на уровне груди. Прижми спину, локти немного согни.",
        movement="Плавно сведи руки перед грудью и медленно разведи их обратно.",
        breathing="Сводишь руки — выдох. Разводишь — вдох.",
        cues="Представь, что обнимаешь большой мяч. Угол в локтях не меняй.",
        mistakes="Не заводи руки далеко назад, не поднимай плечи и не бросай вес.",
    ),
    "seated_row": ExerciseGuidance(
        image_filename="seated_row.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Сядь лицом к блоку, упрись стопами и возьми рукоять. Выпрями спину и опусти плечи.",
        movement="Потяни рукоять к животу, ведя локти назад. Медленно выпрями руки.",
        breathing="Тянешь к себе — выдох. Возвращаешь руки — вдох.",
        cues="Представь, что локтями задвигаешь два ящика назад. Корпус почти не двигается.",
        mistakes="Не сутулься, не раскачивайся и не поднимай плечи.",
    ),
    "hack_squat": ExerciseGuidance(
        image_filename="hack_squat.png",
        weight_label="удобный вес; запиши вес и повторы после подхода",
        setup="Прижми спину и таз к тренажёру. Стопы поставь на платформу на ширине плеч.",
        movement="Согни колени и опустись, будто садишься на стул. Затем встань, толкая платформу всей стопой.",
        breathing="Опускаешься — вдох. Встаёшь — выдох.",
        cues="Колени направляй туда же, куда носки. Пятки держи на платформе.",
        mistakes="Не своди колени, не отрывай пятки и не выпрямляй ноги до щелчка.",
    ),
}


def guidance_for(code: str) -> ExerciseGuidance:
    return EXERCISE_GUIDANCE[code]


def alternative_code_for(code: str) -> str | None:
    return EXERCISE_ALTERNATIVES.get(code)


def rest_seconds_for(code: str) -> int | None:
    return REST_SECONDS_BY_EXERCISE.get(code)


def repetitions_text(code: str, upper_reps: int | None) -> str:
    if upper_reps is None:
        return ""
    width = REP_RANGE_WIDTH.get(code)
    if width is None:
        return f"{upper_reps} повторений"
    lower_reps = max(1, upper_reps - width)
    suffix = " на каждую ногу" if code == "glute_kickback" else ""
    return f"{lower_reps}–{upper_reps} повторений{suffix}"
