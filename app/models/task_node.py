"""Árbol unificado de Hábitos, Rutinas y Backlog."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import ModuleType, Priority, RoutineCategory, TaskTag
from app.models.base import new_uuid, now_local

if TYPE_CHECKING:
    from app.models.objective import Objective


def _enum_values(enum_cls: Any) -> list[str]:
    return [member.value for member in enum_cls]


class TaskNode(Base):
    __tablename__ = "task_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("task_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    module_type: Mapped[ModuleType] = mapped_column(
        SAEnum(
            ModuleType,
            native_enum=False,
            values_callable=_enum_values,
            length=20,
        ),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expanded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    routine_category: Mapped[RoutineCategory | None] = mapped_column(
        SAEnum(
            RoutineCategory,
            native_enum=False,
            values_callable=_enum_values,
            length=20,
        ),
        nullable=True,
    )
    priority: Mapped[Priority | None] = mapped_column(
        SAEnum(Priority, native_enum=False, values_callable=_enum_values, length=10),
        nullable=True,
    )
    tag: Mapped[TaskTag | None] = mapped_column(
        SAEnum(TaskTag, native_enum=False, values_callable=_enum_values, length=20),
        nullable=True,
    )

    schedule_days: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    objective_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("objectives.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )

    parent: Mapped["TaskNode | None"] = relationship(
        remote_side="TaskNode.id",
        back_populates="children",
    )
    children: Mapped[list["TaskNode"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
    )
    objective: Mapped["Objective | None"] = relationship(back_populates="nodes")
