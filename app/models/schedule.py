"""Asignaciones de tareas a bloques horarios y skips diarios."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import new_uuid, now_local

if TYPE_CHECKING:
    from app.models.task_node import TaskNode


class DailyScheduleSlot(Base):
    __tablename__ = "daily_schedule_slots"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", "hour_slot", name="uq_schedule_user_node_hour"),
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
    hour_slot: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    skip_logical_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    schedule_days: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)

    node: Mapped["TaskNode"] = relationship()


class ScheduleSkip(Base):
    __tablename__ = "schedule_skips"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "node_id", "hour_slot", "logical_date", name="uq_skip_user_node_hour_day"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hour_slot: Mapped[str] = mapped_column(String(5), nullable=False)
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
