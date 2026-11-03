"""DTOs analíticos, historial, mapa de calor y bootstrap."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.enums import ModuleType, RoutineCategory
from app.schemas.achievement import AchievementOut
from app.schemas.auth import UserOut
from app.schemas.exception_log import ExceptionOut
from app.schemas.node import NodeOut
from app.schemas.objective import ObjectiveOut, ObjectivePointOut
from app.schemas.schedule import ScheduleSlotOut
from app.schemas.workspace import WorkspaceOut


class ScoreOut(BaseModel):
    h_total: int = 0
    h_comp: int = 0
    r_total: int = 0
    r_comp: int = 0
    b_total: int = 0
    b_comp: int = 0
    exc_mins: int = 0
    penalty: int = 0
    score: int = 0
    base_score: float = 0.0
    high_minutes: float = 0.0
    low_minutes: float = 0.0


class TodayScoreOut(BaseModel):
    logical_date: str
    workspace_id: str
    workspace_name: str
    score: int
    breakdown: ScoreOut
    global_score: ScoreOut


class GlobalStatsOut(BaseModel):
    dias_totales: int = 0
    fecha_inicio: str = ""
    score_promedio_global: int = 0
    score_prom_7d: int = 0
    score_prom_30d: int = 0
    total_habitos_comp: int = 0
    total_rutinas_comp: int = 0
    total_backlog_comp: int = 0
    total_minutos_fuga: int = 0
    racha_actual: int = 0
    racha_maxima: int = 0


class HeatmapCellOut(BaseModel):
    date: str
    score: float | None = None
    level: int = 0
    is_today: bool = False
    has_data: bool = False
    tooltip: str = ""


class HeatmapResponse(BaseModel):
    weeks: list[list[HeatmapCellOut]]
    month_labels: list[str]
    day_labels: list[str]
    start_date: str
    end_date: str
    current_date: str


class TimerImpactTaskOut(BaseModel):
    node_id: str
    title: str
    module_type: ModuleType
    timer_mins: int = 0
    completed_at: datetime | None = None


class TimerImpactOut(BaseModel):
    with_timer_count: int = 0
    without_timer_count: int = 0
    total_completed: int = 0
    adoption_pct: int = 0
    avg_focus_mins: int = 0
    last_with_timer: list[TimerImpactTaskOut] = Field(default_factory=list)


class CorrelationDayOut(BaseModel):
    date: str
    score: int = 0
    penalty: int = 0
    total_minutes: float = 0
    high_minutes: float = 0
    low_minutes: float = 0
    blocked_hours: int = 0
    exception_count: int = 0


class CorrelationResponse(BaseModel):
    days: list[CorrelationDayOut]
    suggestions: list[str]
    total_exceptions: int = 0
    high_impact_exceptions: int = 0


class CategoryOut(BaseModel):
    category: RoutineCategory
    total: int = 0
    completed: int = 0
    pct: int = 0
    css_var: str = ""


class CategoriesResponse(BaseModel):
    categories: list[CategoryOut]
    workspace_id: str


class ObjectiveHistoryDataset(BaseModel):
    label: str
    objective_id: str
    data: list[float | None]
    span_gaps: bool = True


class ObjectiveHistoryChartResponse(BaseModel):
    labels: list[str]
    datasets: list[ObjectiveHistoryDataset]


class HistoryTaskOut(BaseModel):
    id: str | None = None
    title: str
    completed: bool = False
    parent_title: str | None = None
    workspace: str | None = None


class HistoryExceptionOut(BaseModel):
    id: str | None = None
    title: str
    impact: str = "Leve"
    area: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class HistoryDayOut(BaseModel):
    date: str
    score: int | None = None
    habits: list[HistoryTaskOut] = Field(default_factory=list)
    routines: list[HistoryTaskOut] = Field(default_factory=list)
    backlog: list[HistoryTaskOut] = Field(default_factory=list)
    exceptions: list[HistoryExceptionOut] = Field(default_factory=list)
    achievements: list[HistoryTaskOut] = Field(default_factory=list)
    fallback: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)


class HistoryBucketOut(BaseModel):
    key: str
    period: str
    title: str
    subtitle: str
    score_avg: int | None = None
    days_active: int = 0
    days_total: int = 0
    completed: int = 0
    total: int = 0
    completion: int = 0
    fuga: int = 0
    exc_count: int = 0
    days: list[HistoryDayOut] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    items: list[HistoryBucketOut]
    total: int
    limit: int
    offset: int
    period: str
    has_more: bool = False


class BootstrapResponse(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceOut]
    current_workspace_id: str
    logical_date: str
    nodes: dict[str, list[NodeOut]]
    schedule: list[ScheduleSlotOut]
    exceptions: list[ExceptionOut]
    objectives: list[ObjectiveOut]
    achievements: list[AchievementOut]
    achievement_total: int = 0
    score_history: dict[str, ScoreOut]
    scores_by_workspace: dict[str, dict[str, ScoreOut]]
    objective_history: dict[str, list[ObjectivePointOut]]
    today_score: TodayScoreOut
    global_stats: GlobalStatsOut
    schema_version: int = 4
    year_countdown: dict[str, Any] = Field(default_factory=dict)


class ImportResultOut(BaseModel):
    ok: bool = True
    imported: dict[str, int]
    source_schema_version: int
    warnings: list[str] = Field(default_factory=list)
    message: str = "Importación completada"
