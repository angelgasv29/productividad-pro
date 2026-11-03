"""Línea de tiempo 04:00 → 03:00 y asignaciones de tareas."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import delete

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.logical_date import iter_timeline_hours, logical_hour_datetime
from app.models.schedule import DailyScheduleSlot, ScheduleSkip
from app.repositories.exceptions import ExceptionRepository
from app.repositories.nodes import NodeRepository
from app.repositories.schedules import ScheduleRepository
from app.repositories.timers import TimerRepository
from app.schemas.common import MessageResponse
from app.schemas.schedule import (
    ScheduleAssignRequest,
    ScheduleSlotOut,
    ScheduleSuggestionOut,
    TimelineExceptionOut,
    TimelineHourOut,
    TimelineResponse,
    TimelineTaskOut,
)
from app.services import analytics_service, tree_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _slot_visible(slot, node, logical_date: str, skipped: set[str]) -> bool:
    if node is None or node.is_archived:
        return False
    if slot.skip_logical_date == logical_date or node.id in skipped:
        return False
    if slot.recurring:
        if not tree_service.node_schedule_active(node, logical_date):
            return False
        days = slot.schedule_days or node.schedule_days or []
        if days and tree_service.weekday_js(logical_date) not in days:
            return False
        return True
    return slot.assigned_logical_date == logical_date


@router.get("/timeline", response_model=TimelineResponse)
def timeline(
    user: CurrentUser,
    db: DbSession,
    workspace_id: str | None = None,
    logical_date: str | None = None,
) -> TimelineResponse:
    workspace = tree_service.get_workspace(db, user, workspace_id)
    today = tree_service.logical_today(user)
    day = logical_date or today
    nodes = {
        node.id: node
        for node in NodeRepository.list_all(
            db, user.id, workspace_id=workspace.id, include_archived=True
        )
    }
    skipped = ScheduleRepository.skipped_node_ids(db, user.id, day)
    slots_by_hour: dict[str, list] = {}
    for slot in ScheduleRepository.list_for_user(db, user.id):
        node = nodes.get(slot.node_id)
        if not _slot_visible(slot, node, day, skipped):
            continue
        slots_by_hour.setdefault(slot.hour_slot, []).append(slot)
    sessions = TimerRepository.list_for_date(db, user.id, day)
    secs_by_node: dict[str, int] = {}
    used_by_node: set[str] = set()
    for session in sessions:
        secs_by_node[session.node_id] = secs_by_node.get(
            session.node_id, 0
        ) + int(session.focus_secs or 0)
        if session.used_timer:
            used_by_node.add(session.node_id)
    exceptions = ExceptionRepository.list_for_user(
        db, user.id, workspace_id=workspace.id
    )
    now = datetime.now()
    hours: list[TimelineHourOut] = []
    for index, real_hour, hour_slot in iter_timeline_hours():
        start = logical_hour_datetime(day, real_hour, user.logical_cutoff_hour)
        end = start + timedelta(hours=1)
        exception_out: TimelineExceptionOut | None = None
        for exception in exceptions:
            if exception.start_time < end and exception.end_time > start:
                exception_out = TimelineExceptionOut(
                    id=exception.id,
                    title=exception.title,
                    impact=exception.impact,
                    area=exception.area.value if exception.area else None,
                )
                break
        tasks: list[TimelineTaskOut] = []
        for slot in slots_by_hour.get(hour_slot, []):
            node = nodes[slot.node_id]
            tasks.append(
                TimelineTaskOut(
                    slot_id=slot.id,
                    node_id=node.id,
                    title=node.title,
                    module_type=node.module_type,
                    workspace_id=node.workspace_id,
                    completed=node.completed,
                    has_children=bool(
                        NodeRepository.children(db, user.id, node.id)
                    ),
                    recurring=slot.recurring,
                    skip_logical_date=slot.skip_logical_date,
                    timer_secs_today=secs_by_node.get(node.id, 0),
                    used_timer_today=node.id in used_by_node,
                )
            )
        is_current = day == today and now.hour == real_hour
        hours.append(
            TimelineHourOut(
                index=index,
                real_hour=real_hour,
                hour_slot=hour_slot,
                is_night=index >= 24,
                is_current=is_current,
                exception=exception_out,
                tasks=tasks,
            )
        )
    return TimelineResponse(
        logical_date=day, workspace_id=workspace.id, hours=hours
    )


@router.get("", response_model=list[ScheduleSlotOut])
def list_slots(user: CurrentUser, db: DbSession) -> list[ScheduleSlotOut]:
    return [
        ScheduleSlotOut(
            id=slot.id,
            node_id=slot.node_id,
            hour_slot=slot.hour_slot,
            recurring=slot.recurring,
            assigned_logical_date=slot.assigned_logical_date,
            skip_logical_date=slot.skip_logical_date,
            schedule_days=list(slot.schedule_days or []),
        )
        for slot in ScheduleRepository.list_for_user(db, user.id)
    ]


@router.get("/suggestion", response_model=ScheduleSuggestionOut | None)
def suggestion(
    user: CurrentUser, db: DbSession, workspace_id: str | None = None
) -> ScheduleSuggestionOut | None:
    workspace = tree_service.get_workspace(db, user, workspace_id)
    now_hour = f"{datetime.now().hour:02d}:00"
    for slot in ScheduleRepository.list_for_hour(db, user.id, now_hour):
        node = NodeRepository.get(db, user.id, slot.node_id)
        if (
            node is None
            or node.workspace_id != workspace.id
            or node.completed
            or node.is_archived
        ):
            continue
        if NodeRepository.children(db, user.id, node.id):
            continue
        return ScheduleSuggestionOut(
            node_id=node.id,
            title=node.title,
            module_type=node.module_type,
            hour_slot=now_hour,
        )
    return None


@router.post("/assign", response_model=ScheduleSlotOut)
def assign(
    payload: ScheduleAssignRequest, user: CurrentUser, db: DbSession
) -> ScheduleSlotOut:
    node = NodeRepository.get(db, user.id, payload.node_id)
    if node is None:
        raise NotFoundError("La tarea no existe o no te pertenece.")
    if node.is_archived:
        raise ValidationError("No puedes agendar una tarea archivada.")
    today = tree_service.logical_today(user)
    slot = ScheduleRepository.get_for_node_hour(
        db, user.id, node.id, payload.hour_slot
    )
    if slot is None:
        slot = ScheduleRepository.create(
            db,
            DailyScheduleSlot(
                user_id=user.id,
                node_id=node.id,
                hour_slot=payload.hour_slot,
                recurring=payload.recurring,
                assigned_logical_date=today,
                schedule_days=list(node.schedule_days or []),
            ),
        )
    else:
        slot.recurring = payload.recurring
        slot.skip_logical_date = None
        if not payload.recurring:
            slot.assigned_logical_date = today
        if payload.recurring and not slot.schedule_days:
            slot.schedule_days = list(node.schedule_days or [])
    db.execute(
        delete(ScheduleSkip).where(
            ScheduleSkip.user_id == user.id,
            ScheduleSkip.node_id == node.id,
            ScheduleSkip.hour_slot == payload.hour_slot,
            ScheduleSkip.logical_date == today,
        )
    )
    analytics_service.persist_scores(db, user, today)
    db.commit()
    return ScheduleSlotOut(
        id=slot.id,
        node_id=slot.node_id,
        hour_slot=slot.hour_slot,
        recurring=slot.recurring,
        assigned_logical_date=slot.assigned_logical_date,
        skip_logical_date=slot.skip_logical_date,
        schedule_days=list(slot.schedule_days or []),
    )


@router.delete("/{slot_id}", response_model=MessageResponse)
def unassign(
    slot_id: str, user: CurrentUser, db: DbSession
) -> MessageResponse:
    slot = ScheduleRepository.get(db, user.id, slot_id)
    if slot is None:
        raise NotFoundError("La asignación no existe o no te pertenece.")
    today = tree_service.logical_today(user)
    if slot.recurring:
        ScheduleRepository.create_skip(
            db,
            user_id=user.id,
            node_id=slot.node_id,
            hour_slot=slot.hour_slot,
            logical_date=today,
        )
        slot.skip_logical_date = today
        message = "Tarea omitida solo por hoy."
    else:
        ScheduleRepository.delete(db, slot)
        message = "Asignación única eliminada."
    analytics_service.persist_scores(db, user, today)
    db.commit()
    return MessageResponse(message=message)
