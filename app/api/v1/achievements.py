"""Logros definitivos y exportación CSV."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.domain.enums import ModuleType
from app.repositories.achievements import AchievementRepository
from app.repositories.nodes import NodeRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.achievement import AchievementListResponse, AchievementOut

router = APIRouter(prefix="/achievements", tags=["achievements"])


def _out(db, user, achievement, names: dict[str, str]) -> AchievementOut:
    node = (
        NodeRepository.get(db, user.id, achievement.node_id)
        if achievement.node_id
        else None
    )
    return AchievementOut(
        id=achievement.id,
        source_id=achievement.source_id,
        node_id=achievement.node_id,
        module_type=achievement.module_type,
        title=achievement.title,
        completed_at=achievement.completed_at,
        timer_mins=achievement.timer_mins,
        objective_id=achievement.objective_id,
        workspace_id=achievement.workspace_id,
        workspace_name=names.get(achievement.workspace_id or ""),
        is_live=bool(node is not None and node.completed),
    )


@router.get("", response_model=AchievementListResponse)
def list_achievements(
    user: CurrentUser,
    db: DbSession,
    module_type: ModuleType | None = None,
    search: str | None = None,
    timer: str | None = None,
    workspace_id: str | None = None,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AchievementListResponse:
    names = {
        workspace.id: workspace.name
        for workspace in WorkspaceRepository.list_for_user(db, user.id)
    }
    items = AchievementRepository.list(
        db,
        user.id,
        workspace_id=workspace_id,
        module_type=module_type,
        search=search,
        timer_filter=timer,
        limit=limit,
        offset=offset,
    )
    total = AchievementRepository.count(
        db,
        user.id,
        workspace_id=workspace_id,
        module_type=module_type,
        search=search,
        timer_filter=timer,
    )
    return AchievementListResponse(
        items=[_out(db, user, item, names) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )


@router.get("/export.csv")
def export_csv(
    user: CurrentUser,
    db: DbSession,
    module_type: ModuleType | None = None,
    search: str | None = None,
    timer: str | None = None,
    workspace_id: str | None = None,
) -> StreamingResponse:
    names = {
        workspace.id: workspace.name
        for workspace in WorkspaceRepository.list_for_user(db, user.id)
    }
    items = AchievementRepository.list(
        db,
        user.id,
        workspace_id=workspace_id,
        module_type=module_type,
        search=search,
        timer_filter=timer,
        limit=10000,
        offset=0,
    )
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "ID",
            "Título",
            "Módulo",
            "Espacio",
            "Completado",
            "Minutos de enfoque",
            "Objetivo",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.id,
                item.title,
                item.module_type.value,
                names.get(item.workspace_id or "", ""),
                item.completed_at.isoformat(),
                item.timer_mins,
                item.objective_id or "",
            ]
        )
    filename = f"Logros_{datetime.now().date().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
