"""Sesiones de enfoque y estado persistente del Timer Pro."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import TimerPhase
from app.models.base import new_uuid, now_local

if TYPE_CHECKING:
    from app.models.task_node import TaskNode


class TimerSession(Base):
    __tablename__ = "timer_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "node_id", "logical_date", "used_timer", name="uq_timer_user_node_day_mode"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    focus_secs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cycles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_timer: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )

    node: Mapped["TaskNode"] = relationship()


class ActiveTimerState(Base):
    __tablename__ = "active_timer_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("task_nodes.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(20), default="pomodoro", nullable=False)
    phase: Mapped[TimerPhase] = mapped_column(
        SAEnum(
            TimerPhase,
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=10,
        ),
        default=TimerPhase.WORK,
        nullable=False,
    )
    total_secs: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    remaining_secs: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cycle_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    focused_secs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    work_min: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    break_min: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )
