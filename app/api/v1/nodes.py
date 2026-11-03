"""Árbol de Hábitos, Rutinas y Backlog."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.domain.enums import ModuleType
from app.repositories.nodes import NodeRepository
from app.schemas.common import MessageResponse
from app.schemas.node import (
    NodeCreate,
    NodeOut,
    NodeToggleRequest,
    NodeTreeResponse,
    NodeUpdate,
    PendingNodeOut,
)
from app.services import analytics_service, timer_service, tree_service

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _refresh(db, user) -> None:
    today = tree_service.logical_today(user)
    analytics_service.persist_scores(db, user, today)
    analytics_service.persist_activity_snapshots(db, user, today)
    tree_service.snapshot_all_objectives(db, user, logical_date=today)


def _single_out(db, user, node) -> NodeOut:
    children = NodeRepository.children(db, user.id, node.id)
    return NodeOut(
        id=node.id,
        user_id=node.user_id,
        workspace_id=node.workspace_id,
        parent_id=node.parent_id,
        module_type=node.module_type,
        title=node.title,
        completed=node.completed,
        completed_at=node.completed_at,
        expanded=node.expanded,
        is_archived=node.is_archived,
        routine_category=node.routine_category,
        priority=node.priority,
        tag=node.tag,
        schedule_days=list(node.schedule_days or []),
        period_start=node.period_start,
        period_end=node.period_end,
        objective_id=node.objective_id,
        sort_order=node.sort_order,
        created_at=node.created_at,
        updated_at=node.updated_at,
        has_children=bool(children),
        children=[],
    )


@router.get("", response_model=dict[str, list[NodeOut]] | NodeTreeResponse)
def list_nodes(
    user: CurrentUser,
    db: DbSession,
    module_type: ModuleType | None = None,
    workspace_id: str | None = None,
):
    today = tree_service.logical_today(user)
    if module_type is not None:
        nodes = tree_service.serialize_forest(
            db,
            user,
            logical_date=today,
            workspace_id=workspace_id,
            module_type=module_type,
        )
        return NodeTreeResponse(
            module_type=module_type,
            workspace_id=workspace_id,
            logical_date=today,
            nodes=nodes,
        )
    return {
        module.value: tree_service.serialize_forest(
            db,
            user,
            logical_date=today,
            workspace_id=workspace_id,
            module_type=module,
        )
        for module in ModuleType
    }


@router.get("/pending", response_model=list[PendingNodeOut])
def pending_nodes(
    user: CurrentUser,
    db: DbSession,
    workspace_id: str | None = None,
) -> list[PendingNodeOut]:
    nodes = NodeRepository.pending_leaves(
        db, user.id, workspace_id=workspace_id
    )
    parent_ids = {
        node.parent_id
        for node in NodeRepository.list_all(
            db, user.id, workspace_id=workspace_id, include_archived=False
        )
        if node.parent_id
    }
    return [
        PendingNodeOut(
            id=node.id,
            title=node.title,
            module_type=node.module_type,
            workspace_id=node.workspace_id,
            has_children=node.id in parent_ids,
        )
        for node in nodes
    ]


@router.post("", response_model=NodeOut, status_code=201)
def create_node(
    payload: NodeCreate, user: CurrentUser, db: DbSession
) -> NodeOut:
    node = tree_service.create_node(db, user, payload)
    _refresh(db, user)
    db.commit()
    return _single_out(db, user, node)


@router.patch("/{node_id}", response_model=NodeOut)
def update_node(
    node_id: str, payload: NodeUpdate, user: CurrentUser, db: DbSession
) -> NodeOut:
    node = tree_service.find_node(db, user, node_id)
    tree_service.update_node(db, user, node, payload)
    _refresh(db, user)
    db.commit()
    return _single_out(db, user, node)


@router.post("/{node_id}/toggle", response_model=NodeOut)
def toggle_node(
    node_id: str,
    payload: NodeToggleRequest,
    user: CurrentUser,
    db: DbSession,
) -> NodeOut:
    node = tree_service.find_node(db, user, node_id)
    tree_service.toggle_node(db, user, node, payload.completed)
    timer_service.sync_after_task_change(db, user)
    _refresh(db, user)
    db.commit()
    return _single_out(db, user, node)


@router.post("/{node_id}/archive", response_model=MessageResponse)
def archive_node(node_id: str, user: CurrentUser, db: DbSession) -> MessageResponse:
    node = tree_service.find_node(db, user, node_id)
    achievement = tree_service.archive_node(db, user, node)
    _refresh(db, user)
    db.commit()
    if achievement is None:
        return MessageResponse(message="La tarea debe estar completada para archivarse.")
    return MessageResponse(message=f'Logro guardado: "{achievement.title}".')


@router.delete("/{node_id}", response_model=MessageResponse)
def delete_node(node_id: str, user: CurrentUser, db: DbSession) -> MessageResponse:
    node = tree_service.find_node(db, user, node_id)
    title = node.title
    tree_service.delete_node(db, user, node)
    timer_service.sync_after_task_change(db, user)
    _refresh(db, user)
    db.commit()
    return MessageResponse(message=f'"{title}" eliminada.')
