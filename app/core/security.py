"""Hashing de contraseñas, JWT y dependencias de autenticación."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, ValidationError
from app.models.user import User

_password_hash = PasswordHash.recommended()
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValidationError("La contraseña debe tener al menos 8 caracteres.")
    if password.lower() == password or password.upper() == password:
        # Se permite igualmente, pero se exige al menos una letra y un número.
        pass
    if not any(char.isalpha() for char in password) or not any(
        char.isdigit() for char in password
    ):
        raise ValidationError("La contraseña debe incluir letras y números.")


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user.id,
        "username": user.username,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()
        ),
        "iss": settings.app_name,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("La sesión ha expirado. Inicia sesión de nuevo.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Token de autenticación inválido.") from exc
    if not payload.get("sub"):
        raise AuthenticationError("Token de autenticación inválido.")
    return payload


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.cookie_name, path="/")


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.cookie_name)


def resolve_user_from_request(request: Request, db: Session) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except AuthenticationError:
        return None
    user = db.get(User, payload["sub"])
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    token = _extract_token(request, credentials)
    if not token:
        raise AuthenticationError("No autenticado. Inicia sesión para continuar.")
    payload = decode_access_token(token)
    user = db.get(User, payload["sub"])
    if user is None:
        raise AuthenticationError("El usuario de la sesión ya no existe.")
    return user
