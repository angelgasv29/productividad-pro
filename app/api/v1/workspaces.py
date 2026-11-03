"""CRUD de espacios de trabajo."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.common import MessageResponse
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.services import auth_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceOut]:
    return [
        WorkspaceOut.model_validate(workspace)
        for workspace in WorkspaceRepository.list_for_user(db, user.id)
    ]


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    payload: WorkspaceCreate, user: CurrentUser, db: DbSession
) -> WorkspaceOut:
    name = payload.name.strip()
    if not name:
        raise ValidationError("El nombre no puede estar vacío.")
    if WorkspaceRepository.get_by_name(db, user.id, name) is not None:
        raise ConflictError("Ya existe un espacio de trabajo con ese nombre.")
    workspace = WorkspaceRepository.create(db, user_id=user.id, name=name)
    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is not None and not preferences.current_workspace_id:
        preferences.current_workspace_id = workspace.id
    db.commit()
    return WorkspaceOut.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceOut:
    workspace = WorkspaceRepository.get(db, user.id, workspace_id)
    if workspace is None:
        raise NotFoundError("El espacio de trabajo no existe o no te pertenece.")
    name = payload.name.strip()
    duplicate = WorkspaceRepository.get_by_name(db, user.id, name)
    if duplicate is not None and duplicate.id != workspace.id:
        raise ConflictError("Ya existe un espacio de trabajo con ese nombre.")
    workspace.name = name
    db.commit()
    return WorkspaceOut.model_validate(workspace)


@router.post("/{workspace_id}/select", response_model=MessageResponse)
def select_workspace(
    workspace_id: str, user: CurrentUser, db: DbSession
) -> MessageResponse:
    workspace = WorkspaceRepository.get(db, user.id, workspace_id)
    if workspace is None:
        raise NotFoundError("El espacio de trabajo no existe o no te pertenece.")
    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        from app.models.user import UserPreferences

        preferences = UserRepository.create_preferences(
            db, UserPreferences(user_id=user.id)
        )
    preferences.current_workspace_id = workspace.id
    db.commit()
    return MessageResponse(message=f'Espacio de trabajo "{workspace.name}" seleccionado.')


@router.delete("/{workspace_id}", response_model=MessageResponse)
def delete_workspace(
    workspace_id: str, user: CurrentUser, db: DbSession
) -> MessageResponse:
    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    workspace = next((item for item in workspaces if item.id == workspace_id), None)
    if workspace is None:
        raise NotFoundError("El espacio de trabajo no existe o no te pertenece.")
    if len(workspaces) <= 1:
        raise ValidationError("No puedes eliminar tu único espacio de trabajo.")
    preferences = UserRepository.get_preferences(db, user.id)
    replacement = next(item for item in workspaces if item.id != workspace.id)
    if preferences is not None and preferences.current_workspace_id == workspace.id:
        preferences.current_workspace_id = replacement.id
    WorkspaceRepository.delete(db, workspace)
    db.commit()
    return MessageResponse(
        message=f'Espacio de trabajo "{workspace.name}" eliminado con sus datos.'
    )
