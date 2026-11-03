"""Objetivos a largo plazo y su histórico de progreso."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models.objective import Objective
from app.repositories.nodes import NodeRepository
from app.repositories.objectives import ObjectiveRepository
from app.schemas.analytics import ObjectiveHistoryChartResponse
from app.schemas.common import MessageResponse
from app.schemas.objective import (
    ObjectiveCreateRequest,
    ObjectiveLinkRequest,
    ObjectiveOut,
    ObjectiveUpdateRequest,
)
from app.services import analytics_service, tree_service

router = APIRouter(prefix="/objectives", tags=["objectives"])


@router.get("", response_model=list[ObjectiveOut])
def list_objectives(
    user: CurrentUser, db: DbSession, workspace_id: str | None = None
) -> list[ObjectiveOut]:
    workspace = tree_service.get_workspace(db, user, workspace_id)
    return [
        tree_service.compute_objective_progress(db, user, objective)
        for objective in ObjectiveRepository.list_for_user(
            db, user.id, workspace_id=workspace.id
        )
    ]


@router.get("/history", response_model=ObjectiveHistoryChartResponse)
def objectives_history(
    user: CurrentUser, db: DbSession, workspace_id: str | None = None
) -> ObjectiveHistoryChartResponse:
    return analytics_service.objectives_history(
        db, user, workspace_id=workspace_id
    )


@router.post("", response_model=ObjectiveOut, status_code=201)
def create_objective(
    payload: ObjectiveCreateRequest, user: CurrentUser, db: DbSession
) -> ObjectiveOut:
    workspace = tree_service.get_workspace(db, user, payload.workspace_id)
    objective = Objective(
        user_id=user.id,
        workspace_id=workspace.id,
        title=payload.title.strip(),
        description=payload.description,
        horizon=payload.horizon,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    ObjectiveRepository.create(db, objective)
    tree_service.snapshot_objective_progress(db, user, objective)
    db.commit()
    return tree_service.compute_objective_progress(db, user, objective)


@router.get("/{objective_id}", response_model=ObjectiveOut)
def get_objective(
    objective_id: str, user: CurrentUser, db: DbSession
) -> ObjectiveOut:
    objective = ObjectiveRepository.get(db, user.id, objective_id)
    if objective is None:
        raise NotFoundError("El objetivo no existe o no te pertenece.")
    return tree_service.compute_objective_progress(db, user, objective)


@router.patch("/{objective_id}", response_model=ObjectiveOut)
def update_objective(
    objective_id: str,
    payload: ObjectiveUpdateRequest,
    user: CurrentUser,
    db: DbSession,
) -> ObjectiveOut:
    objective = ObjectiveRepository.get(db, user.id, objective_id)
    if objective is None:
        raise NotFoundError("El objetivo no existe o no te pertenece.")
    if payload.title is not None:
        objective.title = payload.title.strip()
    if payload.horizon is not None:
        objective.horizon = payload.horizon
    if "description" in payload.model_fields_set:
        objective.description = payload.description
    if "start_date" in payload.model_fields_set:
        objective.start_date = payload.start_date
    if "end_date" in payload.model_fields_set:
        objective.end_date = payload.end_date
    if (
        objective.start_date
        and objective.end_date
        and objective.end_date < objective.start_date
    ):
        from app.core.exceptions import ValidationError

        raise ValidationError("La fecha límite es anterior al inicio.")
    tree_service.snapshot_objective_progress(db, user, objective)
    db.commit()
    return tree_service.compute_objective_progress(db, user, objective)


@router.delete("/{objective_id}", response_model=MessageResponse)
def delete_objective(
    objective_id: str, user: CurrentUser, db: DbSession
) -> MessageResponse:
    objective = ObjectiveRepository.get(db, user.id, objective_id)
    if objective is None:
        raise NotFoundError("El objetivo no existe o no te pertenece.")
    title = objective.title
    for node in NodeRepository.list_all(db, user.id, include_archived=True):
        if node.objective_id == objective.id:
            node.objective_id = None
    ObjectiveRepository.delete(db, objective)
    db.commit()
    return MessageResponse(message=f'Objetivo "{title}" eliminado.')


@router.post("/{objective_id}/link", response_model=ObjectiveOut)
def link_node(
    objective_id: str,
    payload: ObjectiveLinkRequest,
    user: CurrentUser,
    db: DbSession,
) -> ObjectiveOut:
    objective = ObjectiveRepository.get(db, user.id, objective_id)
    if objective is None:
        raise NotFoundError("El objetivo no existe o no te pertenece.")
    node = tree_service.find_node(db, user, payload.node_id)
    tree_service.link_node_to_objective(db, user, node, objective.id)
    tree_service.snapshot_objective_progress(db, user, objective)
    db.commit()
    return tree_service.compute_objective_progress(db, user, objective)


@router.delete("/{objective_id}/link/{node_id}", response_model=ObjectiveOut)
def unlink_node(
    objective_id: str, node_id: str, user: CurrentUser, db: DbSession
) -> ObjectiveOut:
    objective = ObjectiveRepository.get(db, user.id, objective_id)
    if objective is None:
        raise NotFoundError("El objetivo no existe o no te pertenece.")
    node = tree_service.find_node(db, user, node_id)
    tree_service.link_node_to_objective(db, user, node, None)
    tree_service.snapshot_objective_progress(db, user, objective)
    db.commit()
    return tree_service.compute_objective_progress(db, user, objective)
