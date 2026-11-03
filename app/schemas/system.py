"""DTOs de salud, diagnóstico y restauración."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BackupSlotInfo(BaseModel):
    exists: bool = False
    path: str | None = None
    bytes: int = 0
    modified_at: str | None = None
    logical_date: str | None = None
    exported_at: str | None = None


class HealthOut(BaseModel):
    ok: bool = True
    app_version: str
    schema_version: int
    database_path: str
    database_bytes: int
    logical_date: str
    counts: dict[str, int]
    backups: dict[str, BackupSlotInfo]
    user: str
    server_time: str


class RestoreResponse(BaseModel):
    ok: bool = True
    slot: str
    message: str
    imported: dict[str, int] = Field(default_factory=dict)


class SelfTestCheck(BaseModel):
    name: str
    passed: bool
    detail: Any = None


class SelfTestResponse(BaseModel):
    passed: int
    failed: int
    total: int
    checks: list[SelfTestCheck]
