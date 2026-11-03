"""Endpoints del Timer Pro."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.timer import (
    TimerActionResponse,
    TimerLinkRequest,
    TimerRecordRequest,
    TimerStartRequest,
    TimerStateOut,
)
from app.services import analytics_service, timer_service, tree_service

router = APIRouter(prefix="/timer", tags=["timer"])


def _refresh(db, user) -> None:
    today = tree_service.logical_today(user)
    analytics_service.persist_scores(db, user, today)
    analytics_service.persist_activity_snapshots(db, user, today)


@router.get("/state", response_model=TimerStateOut)
def state(user: CurrentUser, db: DbSession) -> TimerStateOut:
    result = timer_service.get_state(db, user)
    db.commit()
    return result


@router.post("/start", response_model=TimerActionResponse)
def start(
    payload: TimerStartRequest, user: CurrentUser, db: DbSession
) -> TimerActionResponse:
    result, message = timer_service.start(db, user, payload)
    _refresh(db, user)
    db.commit()
    return TimerActionResponse(state=result, message=message)


@router.post("/pause", response_model=TimerActionResponse)
def pause(user: CurrentUser, db: DbSession) -> TimerActionResponse:
    result, message, finished = timer_service.pause(db, user)
    _refresh(db, user)
    db.commit()
    return TimerActionResponse(
        state=result, message=message, phase_finished=finished
    )


@router.post("/reset", response_model=TimerActionResponse)
def reset(user: CurrentUser, db: DbSession) -> TimerActionResponse:
    result, message = timer_service.reset(db, user)
    _refresh(db, user)
    db.commit()
    return TimerActionResponse(state=result, message=message)


@router.post("/skip", response_model=TimerActionResponse)
def skip(user: CurrentUser, db: DbSession) -> TimerActionResponse:
    result, message = timer_service.skip(db, user)
    _refresh(db, user)
    db.commit()
    return TimerActionResponse(state=result, message=message)


@router.post("/record", response_model=TimerActionResponse)
def record(
    payload: TimerRecordRequest, user: CurrentUser, db: DbSession
) -> TimerActionResponse:
    seconds = timer_service.record(db, user, payload)
    _refresh(db, user)
    db.commit()
    state = timer_service.get_state(db, user)
    return TimerActionResponse(
        state=state,
        recorded_secs=seconds,
        message=f"{seconds} segundos registrados.",
    )


@router.post("/link", response_model=TimerStateOut)
def link(
    payload: TimerLinkRequest, user: CurrentUser, db: DbSession
) -> TimerStateOut:
    result = timer_service.link(db, user, payload.node_id)
    db.commit()
    return result


@router.post("/unlink", response_model=TimerStateOut)
def unlink(user: CurrentUser, db: DbSession) -> TimerStateOut:
    result = timer_service.unlink(db, user)
    db.commit()
    return result


@router.post("/complete-task", response_model=TimerActionResponse)
def complete_task(user: CurrentUser, db: DbSession) -> TimerActionResponse:
    result, message = timer_service.complete_linked_task(db, user)
    _refresh(db, user)
    db.commit()
    return TimerActionResponse(state=result, message=message)
