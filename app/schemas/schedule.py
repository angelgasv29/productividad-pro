"""DTOs de la línea de tiempo 04:00 → 03:00."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import ImpactLevel, ModuleType


class ScheduleAssignRequest(BaseModel):
    node_id: str
    hour_slot: str = Field(pattern=r"^([01]\d|2[0-3]):00$")
    recurring: bool = True

    @field_validator("hour_slot")
    @classmethod
    def _validate_hour(cls, value: str) -> str:
        return value


class ScheduleSlotOut(BaseModel):
    id: str
    node_id: str
    hour_slot: str
    recurring: bool
    assigned_logical_date: str
    skip_logical_date: str | None = None
    schedule_days: list[int] = Field(default_factory=list)


class TimelineTaskOut(BaseModel):
    slot_id: str
    node_id: str
    title: str
    module_type: ModuleType
    workspace_id: str
    completed: bool
    has_children: bool
    recurring: bool
    skip_logical_date: str | None = None
    timer_secs_today: int = 0
    used_timer_today: bool = False


class TimelineExceptionOut(BaseModel):
    id: str
    title: str
    impact: ImpactLevel
    area: str | None = None


class TimelineHourOut(BaseModel):
    index: int
    real_hour: int
    hour_slot: str
    is_night: bool
    is_current: bool
    exception: TimelineExceptionOut | None = None
    tasks: list[TimelineTaskOut] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    logical_date: str
    workspace_id: str
    hours: list[TimelineHourOut]


class ScheduleSuggestionOut(BaseModel):
    node_id: str
    title: str
    module_type: ModuleType
    hour_slot: str
