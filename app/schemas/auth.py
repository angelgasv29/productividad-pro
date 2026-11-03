"""DTOs de autenticación, perfil y cuenta."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import validate_password_strength


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        validate_password_strength(value)
        return value

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255, description="Usuario o email")
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        validate_password_strength(value)
        return value


class PreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_workspace_id: str | None = None
    pomodoro_work_min: int = 25
    pomodoro_break_min: int = 5
    notifications_enabled: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    theme: str
    logical_cutoff_hour: int
    last_accessed_logical_date: str
    created_at: datetime
    initials: str = ""
    preferences: PreferencesOut | None = None


class ProfileUpdateRequest(BaseModel):
    email: EmailStr | None = None
    theme: str | None = Field(default=None, pattern="^(light|dark)$")
    logical_cutoff_hour: int | None = Field(default=None, ge=0, le=12)
    current_workspace_id: str | None = None
    pomodoro_work_min: int | None = Field(default=None, gt=0, le=120)
    pomodoro_break_min: int | None = Field(default=None, gt=0, le=60)
    notifications_enabled: bool | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    message: str = "Sesión iniciada"
