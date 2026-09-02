from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    name = State()
    days = State()
    workout_time = State()
    frequency = State()
    place = State()
    goal = State()
    experience = State()


class ScheduleEdit(StatesGroup):
    days = State()
    workout_time = State()
    frequency = State()


class RescheduleInput(StatesGroup):
    date_time = State()


class WorkoutInput(StatesGroup):
    weight = State()
