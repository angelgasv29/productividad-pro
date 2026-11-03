"""DTOs del Timer Pro."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import TimerPhase


class TimerStartRequest(BaseModel):
    work_min: int = Field(default=25, gt=0, le=120)
    break_min: int = Field(default=5, gt=0, le=60)
    mode: Literal["pomodoro", "custom"] = "pomodoro"
    node_id: str | None = None
    resume: bool = False


class TimerRecordRequest(BaseModel):
    node_id: str
    seconds: int = Field(ge=0, le=86400)
    cycles: int | None = Field(default=None, ge=0, le=100)
    used_timer: bool = True


class TimerLinkRequest(BaseModel):
    node_id: str


class TimerStateOut(BaseModel):
    phase: TimerPhase
    total_secs: int
    remaining_secs: int
    running: bool
    cycle_count: int
    focused_secs: int
    work_min: int
    break_min: int
    mode: str
    node_id: str | None = None
    node_title: str | None = None
    started_at: datetime | None = None
    logical_date: str
    server_now: datetime
    elapsed_secs: int = 0


class TimerActionResponse(BaseModel):
    state: TimerStateOut
    recorded_secs: int = 0
    message: str = ""
    phase_finished: bool = False
