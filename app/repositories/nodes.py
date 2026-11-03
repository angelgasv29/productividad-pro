"""Acceso al árbol unificado de tareas."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ModuleType
from app.models.task_node import TaskNode
from app.repositories.base import get_scoped, scoped


class NodeRepository:
    @staticmethod
    def list_all(
        db: Session,
        user_id: str,
        *,
        workspace_id: str | None = None,
        module_type: ModuleType | None = None,
        include_archived: bool = True,
    ) -> list[TaskNode]:
        stmt = scoped(TaskNode, user_id)
        if workspace_id:
            stmt = stmt.where(TaskNode.workspace_id == workspace_id)
        if module_type:
            stmt = stmt.where(TaskNode.module_type == module_type)
        if not include_archived:
            stmt = stmt.where(TaskNode.is_archived.is_(False))
        stmt = stmt.order_by(TaskNode.sort_order, TaskNode.created_at, TaskNode.title)
        return list(db.scalars(stmt))

    @staticmethod
    def get(db: Session, user_id: str, node_id: str) -> TaskNode | None:
        return get_scoped(db, TaskNode, user_id, node_id)

    @staticmethod
    def create(db: Session, node: TaskNode) -> TaskNode:
        db.add(node)
        db.flush()
        return node

    @staticmethod
    def delete(db: Session, node: TaskNode) -> None:
        db.delete(node)
        db.flush()

    @staticmethod
    def children(db: Session, user_id: str, parent_id: str) -> list[TaskNode]:
        return list(
            db.scalars(
                select(TaskNode)
                .where(TaskNode.user_id == user_id, TaskNode.parent_id == parent_id)
                .order_by(TaskNode.sort_order, TaskNode.created_at)
            )
        )

    @staticmethod
    def pending_leaves(
        db: Session, user_id: str, *, workspace_id: str | None = None
    ) -> list[TaskNode]:
        nodes = NodeRepository.list_all(
            db, user_id, workspace_id=workspace_id, include_archived=False
        )
        parent_ids = {node.parent_id for node in nodes if node.parent_id}
        return [node for node in nodes if not node.completed and node.id not in parent_ids]

    @staticmethod
    def all_leaf_nodes(
        db: Session, user_id: str, *, workspace_id: str | None = None
    ) -> list[TaskNode]:
        nodes = NodeRepository.list_all(
            db, user_id, workspace_id=workspace_id, include_archived=False
        )
        parent_ids = {node.parent_id for node in nodes if node.parent_id}
        return [node for node in nodes if node.id not in parent_ids]

    @staticmethod
    def count(db: Session, user_id: str, *, include_archived: bool = False) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(TaskNode).where(TaskNode.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(TaskNode.is_archived.is_(False))
        return int(db.scalar(stmt) or 0)
