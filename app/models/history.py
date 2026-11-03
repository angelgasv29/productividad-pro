"""Historial de scores por workspace/global y snapshots diarios."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import new_uuid, now_local


class DailyScoreHistory(Base):
    __tablename__ = "daily_score_history"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "scope_key", "logical_date", name="uq_score_user_scope_day"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    h_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    h_comp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    r_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    r_comp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    b_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    b_comp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exc_mins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_minutes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    low_minutes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )


class DailyActivitySnapshot(Base):
    __tablename__ = "daily_activity_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "scope_key", "logical_date", name="uq_snapshot_user_scope_day"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    habits: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    routines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    backlog: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    exceptions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )
