"""Objetivos a largo plazo, vínculos únicos e histórico de progreso."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import Horizon, ModuleType
from app.models.base import new_uuid, now_local

if TYPE_CHECKING:
    from app.models.task_node import TaskNode


class Objective(Base):
    __tablename__ = "objectives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    horizon: Mapped[Horizon] = mapped_column(
        SAEnum(
            Horizon,
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=20,
        ),
        nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )

    nodes: Mapped[list["TaskNode"]] = relationship(back_populates="objective")
    links: Mapped[list["ObjectiveTaskLink"]] = relationship(
        back_populates="objective", cascade="all, delete-orphan", passive_deletes=True
    )
    snapshots: Mapped[list["ObjectiveHistorySnapshot"]] = relationship(
        back_populates="objective", cascade="all, delete-orphan", passive_deletes=True
    )


class ObjectiveTaskLink(Base):
    __tablename__ = "objective_task_links"
    __table_args__ = (
        UniqueConstraint("objective_id", "node_id", name="uq_objective_link"),
        UniqueConstraint("user_id", "node_id", name="uq_objective_single_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_type: Mapped[ModuleType] = mapped_column(
        SAEnum(
            ModuleType,
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=20,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)

    objective: Mapped[Objective] = relationship(back_populates="links")


class ObjectiveHistorySnapshot(Base):
    __tablename__ = "objective_history_snapshots"
    __table_args__ = (
        UniqueConstraint("objective_id", "logical_date", name="uq_objective_snapshot_day"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    logical_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)

    objective: Mapped[Objective] = relationship(back_populates="snapshots")
