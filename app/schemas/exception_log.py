"""DTOs de Rompe-Rutinas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import ExceptionArea, ImpactLevel


class ExceptionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    impact: ImpactLevel = ImpactLevel.LEVE
    area: ExceptionArea | None = None
    note: str = Field(default="", max_length=2000)
    start_time: datetime
    end_time: datetime
    workspace_id: str | None = None

    @model_validator(mode="after")
    def _validate_times(self) -> "ExceptionCreateRequest":
        if self.end_time <= self.start_time:
            raise ValueError("La fecha final debe ser posterior a la inicial.")
        return self


class ExceptionOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    impact: ImpactLevel
    area: ExceptionArea | None = None
    note: str
    start_time: datetime
    end_time: datetime
    logical_date: str
    affected_hours: float
    affected_hours_list: list[str] = Field(default_factory=list)
    blocked_task_ids: list[str] = Field(default_factory=list)
    day_splits: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    workspace_name: str | None = None


class ExceptionAreaSummary(BaseModel):
    area: str
    count: int
    minutes: float


class ExceptionListResponse(BaseModel):
    items: list[ExceptionOut]
    areas: list[ExceptionAreaSummary]
