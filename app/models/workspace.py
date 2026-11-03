"""Espacios de trabajo aislados por usuario."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import new_uuid, now_local

if TYPE_CHECKING:
    from app.models.user import User


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_workspace_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)

    user: Mapped["User"] = relationship(back_populates="workspaces")
