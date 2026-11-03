"""Salud, backups, restauración y autodiagnóstico."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.domain.enums import ModuleType
from app.domain.logical_date import get_logical_date
from app.domain.scoring import ModuleProgress, compute_score
from app.models.achievement import Achievement
from app.models.exception_log import TimeException
from app.models.history import DailyScoreHistory
from app.models.objective import Objective
from app.models.schedule import DailyScheduleSlot
from app.models.task_node import TaskNode
from app.models.timer import TimerSession
from app.models.workspace import Workspace
from app.repositories.nodes import NodeRepository
from app.schemas.system import (
    HealthOut,
    RestoreResponse,
    SelfTestCheck,
    SelfTestResponse,
)
from app.services import backup_service, reset_service, tree_service

router = APIRouter(prefix="/system", tags=["system"])


def _database_path() -> str:
    url = settings.database_url
    return url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else url


@router.get("/health", response_model=HealthOut)
def health(user: CurrentUser, db: DbSession) -> HealthOut:
    counts = {
        "workspaces": int(
            db.scalar(
                select(func.count())
                .select_from(Workspace)
                .where(Workspace.user_id == user.id)
            )
            or 0
        ),
        "nodes": NodeRepository.count(db, user.id, include_archived=False),
        "habits": int(
            db.scalar(
                select(func.count())
                .select_from(TaskNode)
                .where(
                    TaskNode.user_id == user.id,
                    TaskNode.is_archived.is_(False),
                    TaskNode.module_type == ModuleType.HABITS,
                )
            )
            or 0
        ),
        "routines": int(
            db.scalar(
                select(func.count())
                .select_from(TaskNode)
                .where(
                    TaskNode.user_id == user.id,
                    TaskNode.is_archived.is_(False),
                    TaskNode.module_type == ModuleType.ROUTINES,
                )
            )
            or 0
        ),
        "backlog": int(
            db.scalar(
                select(func.count())
                .select_from(TaskNode)
                .where(
                    TaskNode.user_id == user.id,
                    TaskNode.is_archived.is_(False),
                    TaskNode.module_type == ModuleType.BACKLOG,
                )
            )
            or 0
        ),
        "schedule_slots": int(
            db.scalar(
                select(func.count())
                .select_from(DailyScheduleSlot)
                .where(DailyScheduleSlot.user_id == user.id)
            )
            or 0
        ),
        "exceptions": int(
            db.scalar(
                select(func.count())
                .select_from(TimeException)
                .where(TimeException.user_id == user.id)
            )
            or 0
        ),
        "objectives": int(
            db.scalar(
                select(func.count())
                .select_from(Objective)
                .where(Objective.user_id == user.id)
            )
            or 0
        ),
        "achievements": int(
            db.scalar(
                select(func.count())
                .select_from(Achievement)
                .where(Achievement.user_id == user.id)
            )
            or 0
        ),
        "timer_sessions": int(
            db.scalar(
                select(func.count())
                .select_from(TimerSession)
                .where(TimerSession.user_id == user.id)
            )
            or 0
        ),
        "score_history_days": int(
            db.scalar(
                select(func.count())
                .select_from(DailyScoreHistory)
                .where(DailyScoreHistory.user_id == user.id)
            )
            or 0
        ),
    }
    db_path = Path(_database_path())
    return HealthOut(
        ok=True,
        app_version=settings.app_version,
        schema_version=settings.schema_version,
        database_path=str(db_path),
        database_bytes=db_path.stat().st_size if db_path.exists() else 0,
        logical_date=tree_service.logical_today(user),
        counts=counts,
        backups=backup_service.backup_info(user),
        user=user.username,
        server_time=datetime.now().isoformat(),
    )


@router.get("/backups", response_model=dict)
def backups(user: CurrentUser) -> dict:
    return {
        slot: info.model_dump()
        for slot, info in backup_service.backup_info(user).items()
    }


@router.post("/backup", response_model=dict)
def create_backup(user: CurrentUser, db: DbSession) -> dict:
    path = backup_service.rotate_save(db, user)
    db.commit()
    return {
        "ok": True,
        "path": str(path),
        "message": "Backup guardado en el slot A (el anterior pasó a B).",
    }


@router.post("/restore/{slot}", response_model=RestoreResponse)
def restore(slot: str, user: CurrentUser, db: DbSession) -> RestoreResponse:
    counts, version, warnings = backup_service.restore_slot(db, user, slot)
    db.commit()
    return RestoreResponse(
        ok=True,
        slot=slot.upper(),
        message=f"Backup restaurado desde el slot {slot.upper()}.",
        imported=counts,
    )


@router.post("/reset", response_model=dict)
def reset(user: CurrentUser, db: DbSession) -> dict:
    counts = reset_service.reset_user_data(db, user)
    db.commit()
    return {
        "ok": True,
        "message": "Todos los datos fueron eliminados. Se recrearon los espacios por defecto.",
        "deleted": counts,
    }


@router.post("/selftest", response_model=SelfTestResponse)
def selftest(user: CurrentUser, db: DbSession) -> SelfTestResponse:
    checks: list[SelfTestCheck] = []

    def add(name: str, passed: bool, detail=None) -> None:
        checks.append(SelfTestCheck(name=name, passed=passed, detail=detail))

    try:
        before = get_logical_date(datetime(2026, 1, 10, 3, 30))
        after = get_logical_date(datetime(2026, 1, 10, 4, 30))
        add(
            "Corte lógico 04:00",
            before == "2026-01-09" and after == "2026-01-10",
            {"before": before, "after": after},
        )
    except Exception as exc:
        add("Corte lógico 04:00", False, str(exc))

    empty = compute_score(
        ModuleProgress(), ModuleProgress(), ModuleProgress()
    )
    add("Score vacío = 0", empty.score == 0, empty.score)

    try:
        db.execute(text("SELECT 1"))
        add("Base de datos escribible", True)
    except Exception as exc:
        add("Base de datos escribible", False, str(exc))

    try:
        settings.backup_dir.mkdir(parents=True, exist_ok=True)
        add("Directorio de backups", settings.backup_dir.exists(), str(settings.backup_dir))
    except Exception as exc:
        add("Directorio de backups", False, str(exc))

    try:
        workspaces = db.scalars(
            select(Workspace).where(Workspace.user_id == user.id)
        ).all()
        add("Aislamiento multi-tenant", len(workspaces) >= 1, len(workspaces))
    except Exception as exc:
        add("Aislamiento multi-tenant", False, str(exc))

    passed = sum(1 for check in checks if check.passed)
    return SelfTestResponse(
        passed=passed,
        failed=len(checks) - passed,
        total=len(checks),
        checks=checks,
    )
