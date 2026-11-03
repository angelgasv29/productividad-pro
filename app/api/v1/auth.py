"""Registro, login y logout."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import DbSession
from app.core.security import (
    clear_auth_cookie,
    create_access_token,
    set_auth_cookie,
)
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    payload: RegisterRequest, response: Response, db: DbSession
) -> AuthResponse:
    user = auth_service.register_user(db, payload)
    token = create_access_token(user)
    set_auth_cookie(response, token)
    db.commit()
    return AuthResponse(
        access_token=token,
        user=auth_service.serialize_user(user),
        message="Cuenta creada correctamente.",
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = auth_service.authenticate_user(db, payload.identifier, payload.password)
    token = create_access_token(user)
    set_auth_cookie(response, token)
    db.commit()
    return AuthResponse(
        access_token=token,
        user=auth_service.serialize_user(user),
        message="Sesión iniciada.",
    )


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response) -> MessageResponse:
    clear_auth_cookie(response)
    return MessageResponse(message="Sesión cerrada.")
