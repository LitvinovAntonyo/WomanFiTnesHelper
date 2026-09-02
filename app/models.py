from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return a naive UTC timestamp; SQLite stores all timestamps in UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    sessions: Mapped[list[WorkoutSession]] = relationship(back_populates="user")


class UserSettings(TimestampMixin, Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Yekaterinburg")
    workout_days: Mapped[str] = mapped_column(String(32), default="0,2,4")
    workout_time: Mapped[str] = mapped_column(String(5), default="19:00")
    workouts_per_week: Mapped[int] = mapped_column(Integer, default=3)
    place: Mapped[str] = mapped_column(String(20), default="gym")
    goal: Mapped[str] = mapped_column(String(40), default="regularity")
    experience: Mapped[str] = mapped_column(String(40), default="returning")
    monthly_target: Mapped[int] = mapped_column(Integer, default=10)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="settings")


class WorkoutTemplate(TimestampMixin, Base):
    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    focus: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list[WorkoutExercise]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="WorkoutExercise.position"
    )


class Exercise(TimestampMixin, Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    instructions: Mapped[str] = mapped_column(Text, default="")
    requires_weight: Mapped[bool] = mapped_column(Boolean, default=True)
    weight_step_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("2.5"))


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"
    __table_args__ = (UniqueConstraint("template_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer, default=3)
    reps: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)

    template: Mapped[WorkoutTemplate] = relationship(back_populates="items")
    exercise: Mapped[Exercise] = relationship()


class Reminder(TimestampMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint("user_id", "workout_at", "kind", name="uq_reminder_occurrence"),
        Index("ix_reminders_due", "status", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workout_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[User] = relationship()


class WorkoutSession(TimestampMixin, Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (Index("ix_sessions_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("workout_templates.id"))
    reminder_id: Mapped[int | None] = mapped_column(ForeignKey("reminders.id"), unique=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    current_position: Mapped[int] = mapped_column(Integer, default=1)

    user: Mapped[User] = relationship(back_populates="sessions")
    template: Mapped[WorkoutTemplate] = relationship()
    results: Mapped[list[ExerciseResult]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ExerciseResult(TimestampMixin, Base):
    __tablename__ = "exercise_results"
    __table_args__ = (UniqueConstraint("session_id", "workout_exercise_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True
    )
    workout_exercise_id: Mapped[int] = mapped_column(ForeignKey("workout_exercises.id"))
    sets_planned: Mapped[int] = mapped_column(Integer)
    completed_sets: Mapped[int] = mapped_column(Integer, default=0)
    reps: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped[WorkoutSession] = relationship(back_populates="results")
    workout_exercise: Mapped[WorkoutExercise] = relationship()
    outcome: Mapped[ExerciseOutcome | None] = relationship(
        back_populates="result", cascade="all, delete-orphan", uselist=False
    )


class ExerciseOutcome(TimestampMixin, Base):
    """Optional interaction data kept separately for additive SQLite upgrades."""

    __tablename__ = "exercise_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_result_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_results.id", ondelete="CASCADE"), unique=True, index=True
    )
    effective_exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercises.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    effort: Mapped[str | None] = mapped_column(String(20))

    result: Mapped[ExerciseResult] = relationship(back_populates="outcome")
    effective_exercise: Mapped[Exercise | None] = relationship()


class TelegramMediaCache(TimestampMixin, Base):
    __tablename__ = "telegram_media_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    file_id: Mapped[str] = mapped_column(String(255))


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    awarded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ConversationMessage(Base):
    __tablename__ = "conversation_history"
    __table_args__ = (Index("ix_conversation_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
