"""Rompe-rutinas: registro de fugas de tiempo."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.domain.logical_date import iso_to_logical_date, split_interval_by_logical_date
from app.models.exception_log import TimeException
from app.repositories.exceptions import ExceptionRepository
from app.repositories.nodes import NodeRepository
from app.repositories.schedules import ScheduleRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.common import MessageResponse
from app.schemas.exception_log import (
    ExceptionAreaSummary,
    ExceptionCreateRequest,
    ExceptionListResponse,
    ExceptionOut,
)
from app.services import analytics_service, tree_service

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


def _workspace_names(db, user) -> dict[str, str]:
    return {
        workspace.id: workspace.name
        for workspace in WorkspaceRepository.list_for_user(db, user.id)
    }


def _out(db, user, exception: TimeException) -> ExceptionOut:
    names = _workspace_names(db, user)
    return ExceptionOut(
        id=exception.id,
        workspace_id=exception.workspace_id,
        title=exception.title,
        impact=exception.impact,
        area=exception.area,
        note=exception.note,
        start_time=exception.start_time,
        end_time=exception.end_time,
        logical_date=exception.logical_date,
        affected_hours=exception.affected_hours,
        affected_hours_list=list(exception.affected_hours_list or []),
        blocked_task_ids=list(exception.blocked_task_ids or []),
        day_splits=dict(exception.day_splits or {}),
        created_at=exception.created_at,
        workspace_name=names.get(exception.workspace_id),
    )


def _affected_labels(start: datetime, end: datetime) -> list[str]:
    cursor = start.replace(minute=0, second=0, microsecond=0)
    labels: list[str] = []
    guard = 0
    while cursor < end and guard < 500:
        guard += 1
        labels.append(f"{cursor.hour:02d}:00")
        cursor += timedelta(hours=1)
    return list(dict.fromkeys(labels))


def _blocked_tasks(db, user, workspace_id: str, labels: list[str]) -> list[str]:
    blocked: list[str] = []
    label_set = set(labels)
    for slot in ScheduleRepository.list_for_user(db, user.id):
        if slot.hour_slot not in label_set:
            continue
        node = NodeRepository.get(db, user.id, slot.node_id)
        if (
            node is not None
            and node.workspace_id == workspace_id
            and not node.completed
            and not node.is_archived
        ):
            blocked.append(node.id)
    return list(dict.fromkeys(blocked))


@router.get("", response_model=ExceptionListResponse)
def list_exceptions(
    user: CurrentUser,
    db: DbSession,
    workspace_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> ExceptionListResponse:
    if start and end:
        items = ExceptionRepository.list_between(db, user.id, start, end)
        if workspace_id:
            items = [item for item in items if item.workspace_id == workspace_id]
    else:
        items = ExceptionRepository.list_for_user(
            db, user.id, workspace_id=workspace_id
        )
    areas: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item.area.value if item.area else "General"
        bucket = areas.setdefault(key, {"count": 0, "minutes": 0.0})
        bucket["count"] += 1
        if item.start_time and item.end_time:
            minutes = (item.end_time - item.start_time).total_seconds() / 60
            if minutes > 0:
                bucket["minutes"] += minutes
    return ExceptionListResponse(
        items=[_out(db, user, item) for item in items],
        areas=[
            ExceptionAreaSummary(
                area=key,
                count=value["count"],
                minutes=round(value["minutes"], 1),
            )
            for key, value in sorted(areas.items())
        ],
    )


@router.post("", response_model=ExceptionOut, status_code=201)
def create_exception(
    payload: ExceptionCreateRequest, user: CurrentUser, db: DbSession
) -> ExceptionOut:
    workspace = tree_service.get_workspace(db, user, payload.workspace_id)
    labels = _affected_labels(payload.start_time, payload.end_time)
    splits = split_interval_by_logical_date(
        payload.start_time, payload.end_time, user.logical_cutoff_hour
    )
    logical_date = iso_to_logical_date(
        payload.start_time, user.logical_cutoff_hour
    ) or tree_service.logical_today(user)
    exception = TimeException(
        user_id=user.id,
        workspace_id=workspace.id,
        title=payload.title.strip(),
        impact=payload.impact,
        area=payload.area,
        note=payload.note,
        start_time=payload.start_time,
        end_time=payload.end_time,
        logical_date=logical_date,
        affected_hours=float(len(labels)),
        affected_hours_list=labels,
        blocked_task_ids=_blocked_tasks(db, user, workspace.id, labels),
        day_splits={key: round(value, 2) for key, value in splits.items()},
    )
    ExceptionRepository.create(db, exception)
    today = tree_service.logical_today(user)
    for day in splits:
        if day == today:
            analytics_service.persist_scores(db, user, day)
            analytics_service.persist_activity_snapshots(db, user, day)
        else:
            analytics_service.recalculate_day_score(db, user, day)
    if today not in splits:
        analytics_service.persist_scores(db, user, today)
    db.commit()
    return _out(db, user, exception)


@router.delete("/{exception_id}", response_model=MessageResponse)
def delete_exception(
    exception_id: str, user: CurrentUser, db: DbSession
) -> MessageResponse:
    exception = ExceptionRepository.get(db, user.id, exception_id)
    if exception is None:
        raise NotFoundError("La excepción no existe o no te pertenece.")
    days = set((exception.day_splits or {}).keys())
    if not days and exception.start_time and exception.end_time:
        days = set(
            split_interval_by_logical_date(
                exception.start_time,
                exception.end_time,
                user.logical_cutoff_hour,
            )
        )
    title = exception.title
    ExceptionRepository.delete(db, exception)
    today = tree_service.logical_today(user)
    for day in days:
        if day == today:
            analytics_service.persist_scores(db, user, day)
            analytics_service.persist_activity_snapshots(db, user, day)
        else:
            analytics_service.recalculate_day_score(db, user, day)
    db.commit()
    return MessageResponse(message=f'Excepción "{title}" eliminada.')
