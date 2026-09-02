from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
RESET_TODAY_TEXT = "🔄 Сбросить текущий день"


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Начать тренировку")],
            [KeyboardButton(text="📊 Мой прогресс"), KeyboardButton(text="🥗 Небольшой шаг")],
            [KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text=RESET_TODAY_TEXT)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Напиши, если нужна поддержка",
    )


def days_keyboard(selected: list[int], prefix: str = "onboarding") -> InlineKeyboardMarkup:
    selected_set = set(selected)
    rows = []
    for start in (0, 3, 6):
        row = []
        for day in range(start, min(start + 3, 7)):
            mark = "✅ " if day in selected_set else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{mark}{DAY_NAMES[day]}", callback_data=f"{prefix}:day:{day}"
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Готово", callback_data=f"{prefix}:days_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def frequency_keyboard(prefix: str = "onboarding") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=str(value), callback_data=f"{prefix}:frequency:{value}")
                for value in range(1, 5)
            ],
            [
                InlineKeyboardButton(text=str(value), callback_data=f"{prefix}:frequency:{value}")
                for value in range(5, 8)
            ],
        ]
    )


def choices_keyboard(prefix: str, choices: tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{value}")]
            for label, value in choices
        ]
    )


def settings_keyboard(reminders_enabled: bool = True) -> InlineKeyboardMarkup:
    toggle_text = "🔕 Отключить напоминания" if reminders_enabled else "🔔 Включить напоминания"
    toggle_value = "off" if reminders_enabled else "on"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏸ Пауза на 7 дней", callback_data="settings:pause")],
            [InlineKeyboardButton(text=toggle_text, callback_data=f"settings:reminders:{toggle_value}")],
            [InlineKeyboardButton(text="🗓 Изменить расписание", callback_data="settings:schedule")],
        ]
    )
