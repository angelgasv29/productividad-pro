"""Dashboard, métricas, historial e informes."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.schemas.analytics import (
    BootstrapResponse,
    CategoriesResponse,
    CorrelationResponse,
    GlobalStatsOut,
    HeatmapResponse,
    HistoryResponse,
    ObjectiveHistoryChartResponse,
    TimerImpactOut,
    TodayScoreOut,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

Period = Literal[
    "day", "week", "month", "quarter", "quadrimester", "semester", "year"
]


@router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap(user: CurrentUser, db: DbSession) -> BootstrapResponse:
    payload = analytics_service.bootstrap(db, user)
    db.commit()
    return payload


@router.get("/today-score", response_model=TodayScoreOut)
def today_score(user: CurrentUser, db: DbSession) -> TodayScoreOut:
    payload = analytics_service.today_score(db, user)
    db.commit()
    return payload


@router.get("/global-stats", response_model=GlobalStatsOut)
def global_stats(user: CurrentUser, db: DbSession) -> GlobalStatsOut:
    return analytics_service.global_stats(db, user)


@router.get("/heatmap", response_model=HeatmapResponse)
def heatmap(
    user: CurrentUser,
    db: DbSession,
    weeks: int = Query(default=16, ge=1, le=53),
) -> HeatmapResponse:
    return analytics_service.heatmap(db, user, weeks=weeks)


@router.get("/timer-impact", response_model=TimerImpactOut)
def timer_impact(
    user: CurrentUser, db: DbSession, workspace_id: str | None = None
) -> TimerImpactOut:
    return analytics_service.timer_impact(db, user, workspace_id=workspace_id)


@router.get("/correlation", response_model=CorrelationResponse)
def correlation(user: CurrentUser, db: DbSession) -> CorrelationResponse:
    return analytics_service.correlation(db, user)


@router.get("/categories", response_model=CategoriesResponse)
def categories(
    user: CurrentUser, db: DbSession, workspace_id: str | None = None
) -> CategoriesResponse:
    return analytics_service.categories(db, user, workspace_id=workspace_id)


@router.get("/objectives-history", response_model=ObjectiveHistoryChartResponse)
def objectives_history(
    user: CurrentUser, db: DbSession, workspace_id: str | None = None
) -> ObjectiveHistoryChartResponse:
    return analytics_service.objectives_history(
        db, user, workspace_id=workspace_id
    )


@router.get("/history", response_model=HistoryResponse)
def history(
    user: CurrentUser,
    db: DbSession,
    period: Period = "week",
    limit: int = Query(default=30, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    workspace_id: str | None = None,
) -> HistoryResponse:
    return analytics_service.history(
        db,
        user,
        period=period,
        limit=limit,
        offset=offset,
        workspace_id=workspace_id,
    )


@router.get("/history/export.csv")
def export_history_csv(
    user: CurrentUser,
    db: DbSession,
    period: Period = "week",
) -> StreamingResponse:
    payload = analytics_service.history(
        db, user, period=period, limit=100000, offset=0
    )
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "Período",
            "Desde",
            "Hasta",
            "Fecha",
            "Score",
            "Hábitos",
            "Rutinas",
            "Backlog",
            "Excepciones",
            "Minutos fuga",
            "Logros",
            "Fallback",
        ]
    )
    for bucket in payload.items:
        for day in bucket.days:
            writer.writerow(
                [
                    bucket.key,
                    bucket.title,
                    bucket.subtitle,
                    day.date,
                    day.score if day.score is not None else "",
                    f"{sum(1 for item in day.habits if item.completed)}/{len(day.habits)}",
                    f"{sum(1 for item in day.routines if item.completed)}/{len(day.routines)}",
                    f"{sum(1 for item in day.backlog if item.completed)}/{len(day.backlog)}",
                    len(day.exceptions),
                    round(
                        sum(
                            max(
                                0.0,
                                (
                                    item.end_time - item.start_time
                                ).total_seconds()
                                / 60,
                            )
                            for item in day.exceptions
                            if item.start_time and item.end_time
                        ),
                        1,
                    ),
                    len(day.achievements),
                    "sí" if day.fallback else "no",
                ]
            )
    filename = f"Historial_{period}_{datetime.now().date().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report.txt")
def report(user: CurrentUser, db: DbSession) -> StreamingResponse:
    content = analytics_service.txt_report(db, user)
    filename = f"Informe_Productividad_{datetime.now().date().isoformat()}.txt"
    return StreamingResponse(
        iter([content]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/year-countdown")
def year_countdown(user: CurrentUser) -> dict:
    return analytics_service.year_countdown(user)
