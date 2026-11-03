"""Acceso a espacios de trabajo, siempre filtrado por usuario."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.repositories.base import get_scoped, scoped


class WorkspaceRepository:
    @staticmethod
    def list_for_user(db: Session, user_id: str) -> list[Workspace]:
        return list(
            db.scalars(scoped(Workspace, user_id).order_by(Workspace.created_at, Workspace.name))
        )

    @staticmethod
    def get(db: Session, user_id: str, workspace_id: str) -> Workspace | None:
        return get_scoped(db, Workspace, user_id, workspace_id)

    @staticmethod
    def get_by_name(db: Session, user_id: str, name: str) -> Workspace | None:
        return db.scalars(
            select(Workspace).where(
                Workspace.user_id == user_id, Workspace.name == name
            )
        ).first()

    @staticmethod
    def create(
        db: Session,
        *,
        user_id: str,
        name: str,
        is_default: bool = False,
    ) -> Workspace:
        workspace = Workspace(user_id=user_id, name=name.strip(), is_default=is_default)
        db.add(workspace)
        db.flush()
        return workspace

    @staticmethod
    def delete(db: Session, workspace: Workspace) -> None:
        db.delete(workspace)
        db.flush()
