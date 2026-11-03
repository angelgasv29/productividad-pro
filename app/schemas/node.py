"""DTOs de Hábitos, Rutinas y Backlog."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import ModuleType, Priority, RoutineCategory, TaskTag


class NodeCreate(BaseModel):
    module_type: ModuleType
    title: str = Field(min_length=1, max_length=500)
    workspace_id: str | None = None
    parent_id: str | None = None
    routine_category: RoutineCategory | None = None
    priority: Priority | None = None
    tag: TaskTag | None = None
    schedule_days: list[int] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    objective_id: str | None = None
    expanded: bool = True
    sort_order: int | None = None

    @field_validator("schedule_days")
    @classmethod
    def _valid_days(cls, value: list[int]) -> list[int]:
        unique = sorted({int(day) for day in value})
        if any(day < 0 or day > 6 for day in unique):
            raise ValueError("Los días deben estar entre 0 (domingo) y 6 (sábado).")
        return unique

    @model_validator(mode="after")
    def _validate_period(self) -> "NodeCreate":
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("La fecha final del periodo es anterior a la inicial.")
        return self


class NodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    expanded: bool | None = None
    schedule_days: list[int] | None = None
    period_start: date | None = None
    period_end: date | None = None
    routine_category: RoutineCategory | None = None
    priority: Priority | None = None
    tag: TaskTag | None = None
    objective_id: str | None = None
    sort_order: int | None = None

    @field_validator("schedule_days")
    @classmethod
    def _valid_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        unique = sorted({int(day) for day in value})
        if any(day < 0 or day > 6 for day in unique):
            raise ValueError("Los días deben estar entre 0 y 6.")
        return unique


class NodeToggleRequest(BaseModel):
    completed: bool


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    workspace_id: str
    parent_id: str | None
    module_type: ModuleType
    title: str
    completed: bool
    completed_at: datetime | None
    expanded: bool
    is_archived: bool
    routine_category: RoutineCategory | None = None
    priority: Priority | None = None
    tag: TaskTag | None = None
    schedule_days: list[int] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    objective_id: str | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
    has_children: bool = False
    timer_secs_today: int = 0
    used_timer_today: bool = False
    focus_mins_today: int = 0
    active_today: bool = False
    children: list["NodeOut"] = Field(default_factory=list)


NodeOut.model_rebuild()


class NodeTreeResponse(BaseModel):
    module_type: ModuleType
    workspace_id: str | None
    logical_date: str
    nodes: list[NodeOut]


class PendingNodeOut(BaseModel):
    id: str
    title: str
    module_type: ModuleType
    workspace_id: str
    has_children: bool = False
