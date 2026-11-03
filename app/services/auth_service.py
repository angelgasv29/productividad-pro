"""Registro, login, perfil y contraseñas."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password, verify_password
from app.domain.logical_date import get_logical_date
from app.models.user import User, UserPreferences
from app.models.workspace import Workspace
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.auth import PreferencesOut, ProfileUpdateRequest, RegisterRequest, UserOut

DEFAULT_WORKSPACES: tuple[str, ...] = ("General", "Trabajo", "Estudios")


def _initials(username: str) -> str:
    clean = username.strip()
    if not clean:
        return "PP"
    parts = [part for part in clean.replace("_", " ").replace(".", " ").split() if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return clean[:2].upper()


def serialize_user(user: User) -> UserOut:
    preferences = user.preferences
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        theme=user.theme,
        logical_cutoff_hour=user.logical_cutoff_hour,
        last_accessed_logical_date=user.last_accessed_logical_date,
        created_at=user.created_at,
        initials=_initials(user.username),
        preferences=(
            PreferencesOut.model_validate(preferences) if preferences is not None else None
        ),
    )


def create_default_workspaces(db: Session, user: User) -> list[Workspace]:
    existing = {workspace.name for workspace in WorkspaceRepository.list_for_user(db, user.id)}
    created: list[Workspace] = []
    for index, name in enumerate(DEFAULT_WORKSPACES):
        if name in existing:
            continue
        workspace = WorkspaceRepository.create(
            db, user_id=user.id, name=name, is_default=(index == 0)
        )
        created.append(workspace)
    if not created:
        return WorkspaceRepository.list_for_user(db, user.id)
    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        preferences = UserRepository.create_preferences(
            db, UserPreferences(user_id=user.id, current_workspace_id=created[0].id)
        )
    elif not preferences.current_workspace_id:
        preferences.current_workspace_id = created[0].id
    db.flush()
    return WorkspaceRepository.list_for_user(db, user.id)


def register_user(db: Session, data: RegisterRequest) -> User:
    username = data.username.strip()
    email = str(data.email).strip().lower()
    existing_username = db.scalars(
        select(User).where(func.lower(User.username) == username.lower())
    ).first()
    if existing_username is not None:
        raise ConflictError("Ese nombre de usuario ya está registrado.")
    existing_email = db.scalars(
        select(User).where(func.lower(User.email) == email)
    ).first()
    if existing_email is not None:
        raise ConflictError("Ese correo ya está registrado.")
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(data.password),
        theme="light",
        logical_cutoff_hour=settings.logical_cutoff_hour,
        last_accessed_logical_date=get_logical_date(),
    )
    UserRepository.create(db, user)
    UserRepository.create_preferences(
        db, UserPreferences(user_id=user.id, current_workspace_id=None)
    )
    create_default_workspaces(db, user)
    db.flush()
    db.refresh(user)
    return user


def authenticate_user(db: Session, identifier: str, password: str) -> User:
    normalized = identifier.strip()
    user = db.scalars(
        select(User).where(
            (func.lower(User.username) == normalized.lower())
            | (func.lower(User.email) == normalized.lower())
        )
    ).first()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Usuario o contraseña incorrectos.")
    return user


def change_password(
    db: Session, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("La contraseña actual no es correcta.")
    if verify_password(new_password, user.password_hash):
        raise ValidationError("La nueva contraseña debe ser diferente a la actual.")
    user.password_hash = hash_password(new_password)
    db.flush()


def update_profile(db: Session, user: User, data: ProfileUpdateRequest) -> User:
    if data.email is not None:
        email = str(data.email).strip().lower()
        duplicate = db.scalars(
            select(User).where(func.lower(User.email) == email, User.id != user.id)
        ).first()
        if duplicate is not None:
            raise ConflictError("Ese correo ya está registrado por otra cuenta.")
        user.email = email
    if data.theme is not None:
        user.theme = data.theme
    if data.logical_cutoff_hour is not None:
        user.logical_cutoff_hour = data.logical_cutoff_hour
    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        preferences = UserRepository.create_preferences(
            db, UserPreferences(user_id=user.id)
        )
    if data.current_workspace_id is not None:
        workspace = WorkspaceRepository.get(db, user.id, data.current_workspace_id)
        if workspace is None:
            raise NotFoundError("El espacio de trabajo no existe o no te pertenece.")
        preferences.current_workspace_id = workspace.id
    if data.pomodoro_work_min is not None:
        preferences.pomodoro_work_min = data.pomodoro_work_min
    if data.pomodoro_break_min is not None:
        preferences.pomodoro_break_min = data.pomodoro_break_min
    if data.notifications_enabled is not None:
        preferences.notifications_enabled = data.notifications_enabled
    db.flush()
    db.refresh(user)
    return user
