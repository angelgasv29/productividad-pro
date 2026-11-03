"""DTOs de objetivos e histórico."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import Horizon, ModuleType  # noqa: F401


class ObjectiveCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    horizon: Horizon = Horizon.SEMANAL
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    workspace_id: str | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "ObjectiveCreateRequest":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("La fecha límite es anterior al inicio.")
        return self


class ObjectiveUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    horizon: Horizon | None = None
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "ObjectiveUpdateRequest":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("La fecha límite es anterior al inicio.")
        return self


class ObjectiveLinkRequest(BaseModel):
    node_id: str


class LinkedItemOut(BaseModel):
    node_id: str
    title: str
    module_type: ModuleType | None = None
    done: bool = False
    archived: bool = False
    missing: bool = False


class ObjectiveOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None
    horizon: Horizon
    start_date: date | None
    end_date: date | None
    created_at: datetime
    total: int = 0
    done: int = 0
    pct: int = 0
    links: list[LinkedItemOut] = Field(default_factory=list)


class ObjectivePointOut(BaseModel):
    date: str
    pct: float
    done: int
    total: int


class ObjectiveHistorySeriesOut(BaseModel):
    objective_id: str
    title: str
    points: list[ObjectivePointOut]


class ObjectiveHistoryResponse(BaseModel):
    labels: list[str]
    datasets: list[dict]
