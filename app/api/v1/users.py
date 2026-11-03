"""Perfil, preferencias, contraseña y baja de cuenta."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser, DbSession
from app.core.security import clear_auth_cookie
from app.repositories.users import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    ProfileUpdateRequest,
    UserOut,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return auth_service.serialize_user(user)


@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: ProfileUpdateRequest, user: CurrentUser, db: DbSession
) -> UserOut:
    updated = auth_service.update_profile(db, user, payload)
    db.commit()
    return auth_service.serialize_user(updated)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, db: DbSession
) -> MessageResponse:
    auth_service.change_password(
        db, user, payload.current_password, payload.new_password
    )
    db.commit()
    return MessageResponse(message="Contraseña actualizada correctamente.")


@router.delete("/account", response_model=MessageResponse)
def delete_account(
    user: CurrentUser, db: DbSession, response: Response
) -> MessageResponse:
    UserRepository.delete(db, user)
    db.commit()
    clear_auth_cookie(response)
    return MessageResponse(message="Cuenta eliminada definitivamente.")
