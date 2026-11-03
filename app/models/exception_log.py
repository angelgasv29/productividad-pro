"""Rompe-rutinas: fugas de tiempo registradas por el usuario."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.enums import ExceptionArea, ImpactLevel
from app.models.base import new_uuid, now_local


class TimeException(Base):
    __tablename__ = "time_exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    impact: Mapped[ImpactLevel] = mapped_column(
        SAEnum(
            ImpactLevel,
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=10,
        ),
        nullable=False,
    )
    area: Mapped[ExceptionArea | None] = mapped_column(
        SAEnum(
            ExceptionArea,
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=20,
        ),
        nullable=True,
    )
    note: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    affected_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    affected_hours_list: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocked_task_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    day_splits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
