"""Logros definitivos (archivo histórico de tareas completadas)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import ModuleType
from app.models.base import new_uuid, now_local

if TYPE_CHECKING:
    from app.models.task_node import TaskNode


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "source_id", name="uq_achievement_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("task_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    module_type: Mapped[ModuleType] = mapped_column(
        SAEnum(
            ModuleType,
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            length=20,
        ),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    timer_mins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    objective_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)

    node: Mapped["TaskNode | None"] = relationship()
