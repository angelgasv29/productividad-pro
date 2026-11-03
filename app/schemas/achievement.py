"""DTOs de logros históricos."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import ModuleType


class AchievementOut(BaseModel):
    id: str
    source_id: str
    node_id: str | None = None
    module_type: ModuleType
    title: str
    completed_at: datetime
    timer_mins: int = 0
    objective_id: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    is_live: bool = False


class AchievementListResponse(BaseModel):
    items: list[AchievementOut]
    total: int
    limit: int
    offset: int
    has_more: bool = False


class AchievementFilters(BaseModel):
    module_type: ModuleType | None = None
    search: str | None = None
    timer: str | None = None
    workspace_id: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
