"""Exportación, importación legacy y backups rotativos por usuario."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BackupError, ValidationError
from app.domain.enums import (
    ExceptionArea,
    Horizon,
    ImpactLevel,
    ModuleType,
    Priority,
    RoutineCategory,
    TaskTag,
    TimerPhase,
)
from app.domain.logical_date import (
    get_logical_date,
    iso_to_logical_date,
    split_interval_by_logical_date,
)
from app.domain.scoring import ScoreResult
from app.models.achievement import Achievement
from app.models.exception_log import TimeException
from app.models.history import DailyActivitySnapshot, DailyScoreHistory
from app.models.objective import Objective, ObjectiveHistorySnapshot, ObjectiveTaskLink
from app.models.schedule import DailyScheduleSlot, ScheduleSkip
from app.models.task_node import TaskNode
from app.models.timer import ActiveTimerState, TimerSession
from app.models.user import User, UserPreferences
from app.models.workspace import Workspace
from app.repositories.history import HistoryRepository
from app.repositories.objectives import ObjectiveRepository
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.system import BackupSlotInfo
from app.services.auth_service import DEFAULT_WORKSPACES


# ---------------------------------------------------------------------------
# Utilidades de serialización
# ---------------------------------------------------------------------------


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _slot_path(user: User, slot: str) -> Path:
    normalized = slot.upper()
    if normalized not in {"A", "B"}:
        raise ValidationError("El slot debe ser A o B.")
    return settings.backup_dir / f"user_{user.id}_slot{normalized}.json"


def _pre_reset_path(user: User) -> Path:
    return settings.backup_dir / f"user_{user.id}_pre_reset.json"


def export_payload(db: Session, user: User) -> dict[str, Any]:
    """Construye el JSON de exportación con TODO el estado del usuario."""

    from sqlalchemy import select

    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    nodes = list(
        db.scalars(
            select(TaskNode)
            .where(TaskNode.user_id == user.id)
            .order_by(TaskNode.sort_order, TaskNode.created_at)
        )
    )
    sessions = list(
        db.scalars(
            select(TimerSession).where(TimerSession.user_id == user.id)
        )
    )
    sessions_by_node: dict[str, list[TimerSession]] = {}
    for session in sessions:
        sessions_by_node.setdefault(session.node_id, []).append(session)
    slots = list(
        db.scalars(
            select(DailyScheduleSlot).where(DailyScheduleSlot.user_id == user.id)
        )
    )
    exceptions = list(
        db.scalars(
            select(TimeException).where(TimeException.user_id == user.id)
        )
    )
    objectives = list(
        db.scalars(select(Objective).where(Objective.user_id == user.id))
    )
    links = list(
        db.scalars(
            select(ObjectiveTaskLink).where(
                ObjectiveTaskLink.user_id == user.id
            )
        )
    )
    links_by_objective: dict[str, list[str]] = {}
    for link in links:
        links_by_objective.setdefault(link.objective_id, []).append(link.node_id)
    achievements = list(
        db.scalars(
            select(Achievement).where(Achievement.user_id == user.id)
        )
    )
    scores = list(
        db.scalars(
            select(DailyScoreHistory).where(
                DailyScoreHistory.user_id == user.id
            )
        )
    )
    snapshots = list(
        db.scalars(
            select(DailyActivitySnapshot).where(
                DailyActivitySnapshot.user_id == user.id
            )
        )
    )
    objective_snapshots = list(
        db.scalars(
            select(ObjectiveHistorySnapshot).where(
                ObjectiveHistorySnapshot.user_id == user.id
            )
        )
    )
    active = db.scalars(
        select(ActiveTimerState).where(ActiveTimerState.user_id == user.id)
    ).first()
    preferences = UserRepository.get_preferences(db, user.id)

    return {
        "app": settings.app_name,
        "schemaVersion": settings.schema_version,
        "exportedAt": datetime.now().isoformat(),
        "logicalDate": get_logical_date(
            cutoff_hour=user.logical_cutoff_hour
        ),
        "user": {
            "username": user.username,
            "email": user.email,
            "theme": user.theme,
            "logicalCutoffHour": user.logical_cutoff_hour,
            "lastAccessedDate": user.last_accessed_logical_date,
        },
        "preferences": {
            "currentWorkspaceId": preferences.current_workspace_id
            if preferences
            else None,
            "pomodoroWorkMin": preferences.pomodoro_work_min
            if preferences
            else 25,
            "pomodoroBreakMin": preferences.pomodoro_break_min
            if preferences
            else 5,
            "notificationsEnabled": preferences.notifications_enabled
            if preferences
            else False,
        },
        "workspaces": [
            {
                "id": workspace.id,
                "name": workspace.name,
                "isDefault": workspace.is_default,
                "createdAt": _iso(workspace.created_at),
            }
            for workspace in workspaces
        ],
        "nodes": [
            {
                "id": node.id,
                "workspaceId": node.workspace_id,
                "parentId": node.parent_id,
                "moduleType": node.module_type.value,
                "title": node.title,
                "completed": node.completed,
                "completedAt": _iso(node.completed_at),
                "expanded": node.expanded,
                "isArchived": node.is_archived,
                "routineCategory": _enum(node.routine_category),
                "priority": _enum(node.priority),
                "tag": _enum(node.tag),
                "scheduleDays": list(node.schedule_days or []),
                "periodStart": _iso(node.period_start),
                "periodEnd": _iso(node.period_end),
                "sortOrder": node.sort_order,
                "objectiveId": node.objective_id,
                "createdAt": _iso(node.created_at),
                "updatedAt": _iso(node.updated_at),
                "timerSessions": [
                    {
                        "logicalDate": session.logical_date,
                        "focusSecs": session.focus_secs,
                        "cycles": session.cycles,
                        "usedTimer": session.used_timer,
                    }
                    for session in sessions_by_node.get(node.id, [])
                ],
            }
            for node in nodes
        ],
        "schedule": [
            {
                "id": slot.id,
                "nodeId": slot.node_id,
                "hourSlot": slot.hour_slot,
                "recurring": slot.recurring,
                "assignedLogicalDate": slot.assigned_logical_date,
                "skipLogicalDate": slot.skip_logical_date,
                "scheduleDays": list(slot.schedule_days or []),
            }
            for slot in slots
        ],
        "exceptions": [
            {
                "id": exception.id,
                "workspaceId": exception.workspace_id,
                "title": exception.title,
                "impact": exception.impact.value,
                "area": _enum(exception.area),
                "note": exception.note,
                "startTime": _iso(exception.start_time),
                "endTime": _iso(exception.end_time),
                "logicalDate": exception.logical_date,
                "affectedHours": exception.affected_hours,
                "affectedHoursList": list(exception.affected_hours_list or []),
                "blockedTaskIds": list(exception.blocked_task_ids or []),
                "daySplits": dict(exception.day_splits or {}),
            }
            for exception in exceptions
        ],
        "objectives": [
            {
                "id": objective.id,
                "workspaceId": objective.workspace_id,
                "title": objective.title,
                "description": objective.description,
                "horizon": objective.horizon.value,
                "startDate": _iso(objective.start_date),
                "endDate": _iso(objective.end_date),
                "linkedItems": links_by_objective.get(objective.id, []),
                "createdAt": _iso(objective.created_at),
            }
            for objective in objectives
        ],
        "achievements": [
            {
                "id": achievement.id,
                "workspaceId": achievement.workspace_id,
                "nodeId": achievement.node_id,
                "sourceId": achievement.source_id,
                "moduleType": achievement.module_type.value,
                "title": achievement.title,
                "completedAt": _iso(achievement.completed_at),
                "timerMins": achievement.timer_mins,
                "objectiveId": achievement.objective_id,
            }
            for achievement in achievements
        ],
        "scoreHistory": [
            {
                "scopeKey": row.scope_key,
                "workspaceId": row.workspace_id,
                "logicalDate": row.logical_date,
                "score": row.score,
                "baseScore": row.base_score,
                "hTotal": row.h_total,
                "hComp": row.h_comp,
                "rTotal": row.r_total,
                "rComp": row.r_comp,
                "bTotal": row.b_total,
                "bComp": row.b_comp,
                "excMins": row.exc_mins,
                "penalty": row.penalty,
                "highMinutes": row.high_minutes,
                "lowMinutes": row.low_minutes,
            }
            for row in scores
        ],
        "activitySnapshots": [
            {
                "scopeKey": row.scope_key,
                "workspaceId": row.workspace_id,
                "logicalDate": row.logical_date,
                "score": row.score,
                "habits": row.habits,
                "routines": row.routines,
                "backlog": row.backlog,
                "exceptions": row.exceptions,
            }
            for row in snapshots
        ],
        "objectiveHistory": [
            {
                "objectiveId": row.objective_id,
                "logicalDate": row.logical_date,
                "pct": row.pct,
                "done": row.done,
                "total": row.total,
            }
            for row in objective_snapshots
        ],
        "activeTimer": {
            "nodeId": active.node_id,
            "mode": active.mode,
            "phase": active.phase.value,
            "totalSecs": active.total_secs,
            "remainingSecs": active.remaining_secs,
            "running": active.running,
            "cycleCount": active.cycle_count,
            "focusedSecs": active.focused_secs,
            "workMin": active.work_min,
            "breakMin": active.break_min,
            "logicalDate": active.logical_date,
        }
        if active
        else None,
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def rotate_save(db: Session, user: User) -> Path:
    """Guarda en slot A rotando el contenido anterior a slot B."""

    payload = export_payload(db, user)
    slot_a = _slot_path(user, "A")
    slot_b = _slot_path(user, "B")
    if slot_a.exists():
        shutil.copy2(slot_a, slot_b)
    return write_json(slot_a, payload)


def pre_reset_backup(db: Session, user: User) -> Path:
    payload = export_payload(db, user)
    write_json(_pre_reset_path(user), payload)
    return rotate_save(db, user)


def backup_info(user: User) -> dict[str, BackupSlotInfo]:
    result: dict[str, BackupSlotInfo] = {}
    for slot in ("A", "B"):
        path = _slot_path(user, slot)
        info = BackupSlotInfo(exists=False)
        if path.exists():
            stat = path.stat()
            logical_date = None
            exported_at = None
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
                logical_date = parsed.get("logicalDate") or parsed.get(
                    "lastAccessedDate"
                )
                exported_at = parsed.get("exportedAt")
            except Exception:
                pass
            info = BackupSlotInfo(
                exists=True,
                path=str(path),
                bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                logical_date=logical_date,
                exported_at=exported_at,
            )
        result[slot] = info
    return result


def read_slot(user: User, slot: str) -> dict[str, Any]:
    path = _slot_path(user, slot)
    if not path.exists():
        raise BackupError(f"No existe un backup en el slot {slot.upper()}.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupError("El backup está corrupto o no es JSON válido.") from exc


# ---------------------------------------------------------------------------
# Parseo de valores legacy
# ---------------------------------------------------------------------------


def _parse_dt(value: Any, default: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if value in (None, ""):
        if default is not None:
            return default
        raise BackupError("Falta una fecha obligatoria en el backup.")
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for fmt, size in (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d", 10),
    ):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    if default is not None:
        return default
    raise BackupError(f"Fecha inválida en el backup: {value!r}")


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_enum(enum_cls: Any, value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, enum_cls):
        return value
    for member in enum_cls:
        if str(value).lower() == member.value.lower():
            return member
    return default


def _coerce_module(value: Any) -> ModuleType:
    return _coerce_enum(ModuleType, value, ModuleType.BACKLOG)


# ---------------------------------------------------------------------------
# Limpieza e importación
# ---------------------------------------------------------------------------


def _wipe_user_data(db: Session, user: User) -> None:
    for model in (
        TimerSession,
        ActiveTimerState,
        DailyScheduleSlot,
        ScheduleSkip,
        TimeException,
        Achievement,
        ObjectiveTaskLink,
        ObjectiveHistorySnapshot,
        Objective,
        TaskNode,
        DailyActivitySnapshot,
        DailyScoreHistory,
        Workspace,
    ):
        db.execute(delete(model).where(model.user_id == user.id))
    db.flush()


def _ensure_workspace(
    db: Session,
    user: User,
    name: str | None,
    mapping: dict[str, str],
    *,
    fallback_name: str,
) -> str:
    clean = (name or fallback_name or "General").strip() or "General"
    if clean in mapping:
        return mapping[clean]
    workspace = Workspace(
        user_id=user.id,
        name=clean,
        is_default=not mapping,
    )
    db.add(workspace)
    db.flush()
    mapping[clean] = workspace.id
    return workspace.id


def _legacy_timer_sessions(
    db: Session, user: User, node_id: str, raw_sessions: Any
) -> int:
    if not isinstance(raw_sessions, list):
        return 0
    count = 0
    for raw in raw_sessions:
        if not isinstance(raw, dict):
            continue
        day = iso_to_logical_date(
            raw.get("date") or raw.get("logicalDate"), user.logical_cutoff_hour
        )
        if not day:
            continue
        session = TimerSession(
            user_id=user.id,
            node_id=node_id,
            logical_date=day,
            focus_secs=_safe_int(raw.get("focusSecs") or raw.get("seconds")),
            cycles=_safe_int(raw.get("cycles")),
            used_timer=bool(raw.get("usedTimer", True)),
        )
        db.add(session)
        count += 1
    return count


def _legacy_node(
    db: Session,
    user: User,
    item: dict[str, Any],
    *,
    module_type: ModuleType,
    workspace_id: str,
    parent_id: str | None,
    node_map: dict[str, str],
    timer_count: list[int],
    sort_order: int,
) -> str | None:
    old_id = str(item.get("id") or f"legacy_{uuid4().hex}")
    node = TaskNode(
        user_id=user.id,
        workspace_id=workspace_id,
        parent_id=parent_id,
        module_type=module_type,
        title=str(item.get("title") or "Sin título")[:500],
        completed=bool(item.get("completed")),
        completed_at=_parse_dt(item.get("completedAt"))
        if item.get("completedAt")
        else None,
        expanded=bool(item.get("expanded", True)),
        is_archived=bool(item.get("isArchived", False)),
        routine_category=_coerce_enum(
            RoutineCategory,
            item.get("category") or item.get("routineCategory"),
            RoutineCategory.COMER if module_type == ModuleType.ROUTINES else None,
        )
        if module_type == ModuleType.ROUTINES
        else None,
        priority=_coerce_enum(Priority, item.get("priority"))
        if module_type == ModuleType.BACKLOG
        else None,
        tag=_coerce_enum(TaskTag, item.get("tag"))
        if module_type == ModuleType.BACKLOG
        else None,
        schedule_days=[
            int(day)
            for day in (item.get("scheduleDays") or [])
            if isinstance(day, (int, float, str)) and str(day).isdigit()
        ],
        period_start=_parse_date(item.get("periodStart")),
        period_end=_parse_date(item.get("periodEnd")),
        sort_order=_safe_int(item.get("sortOrder"), sort_order),
    )
    db.add(node)
    db.flush()
    node_map[old_id] = node.id
    timer_count[0] += _legacy_timer_sessions(
        db, user, node.id, item.get("timerSessions")
    )
    for index, child in enumerate(item.get("children") or []):
        if isinstance(child, dict):
            _legacy_node(
                db,
                user,
                child,
                module_type=module_type,
                workspace_id=workspace_id,
                parent_id=node.id,
                node_map=node_map,
                timer_count=timer_count,
                sort_order=index,
            )
    return node.id


def _record_score_row(
    db: Session,
    user: User,
    *,
    workspace_id: str | None,
    scope_key: str,
    logical_date: str,
    data: dict[str, Any],
) -> None:
    result = ScoreResult(
        h_total=_safe_int(data.get("hTotal") or data.get("h_total")),
        h_comp=_safe_int(data.get("hComp") or data.get("h_comp")),
        r_total=_safe_int(data.get("rTotal") or data.get("r_total")),
        r_comp=_safe_int(data.get("rComp") or data.get("r_comp")),
        b_total=_safe_int(data.get("bTotal") or data.get("b_total")),
        b_comp=_safe_int(data.get("bComp") or data.get("b_comp")),
        exc_mins=_safe_int(data.get("excMins") or data.get("exc_mins")),
        penalty=_safe_int(data.get("penalty")),
        score=_safe_int(data.get("score")),
        base_score=_safe_float(
            data.get("baseScore") or data.get("base_score"),
            _safe_float(data.get("score")),
        ),
        high_minutes=_safe_float(
            data.get("highMinutes") or data.get("high_minutes")
        ),
        low_minutes=_safe_float(
            data.get("lowMinutes") or data.get("low_minutes")
        ),
    )
    HistoryRepository.upsert_score(
        db,
        user_id=user.id,
        workspace_id=workspace_id,
        scope_key=scope_key,
        logical_date=logical_date,
        result=result,
    )


def _record_snapshot(
    db: Session,
    user: User,
    *,
    workspace_id: str | None,
    scope_key: str,
    logical_date: str,
    data: dict[str, Any],
) -> None:
    HistoryRepository.upsert_snapshot(
        db,
        user_id=user.id,
        workspace_id=workspace_id,
        scope_key=scope_key,
        logical_date=logical_date,
        score=_safe_int(data.get("score")),
        habits=data.get("habits") if isinstance(data.get("habits"), list) else [],
        routines=data.get("routines")
        if isinstance(data.get("routines"), list)
        else [],
        backlog=data.get("backlog")
        if isinstance(data.get("backlog"), list)
        else [],
        exceptions=data.get("exceptions")
        if isinstance(data.get("exceptions"), list)
        else [],
    )


def _remap_source(source_id: str, node_map: dict[str, str]) -> str:
    text = str(source_id or "")
    for old_id, new_id in node_map.items():
        if text == old_id:
            return new_id
        if text.startswith(f"{old_id}_"):
            return f"{new_id}_{text[len(old_id) + 1:]}"
    return f"legacy_{uuid4().hex}" if not text else text


def _import_legacy(db: Session, user: User, payload: dict[str, Any]) -> dict[str, int]:
    counts = {
        "workspaces": 0,
        "nodes": 0,
        "schedule_slots": 0,
        "exceptions": 0,
        "objectives": 0,
        "achievements": 0,
        "score_history": 0,
        "snapshots": 0,
        "timer_sessions": 0,
        "objective_snapshots": 0,
    }
    warnings: list[str] = []
    today = get_logical_date(cutoff_hour=user.logical_cutoff_hour)
    current_name = (
        payload.get("currentWorkspace")
        or payload.get("current_workspace")
        or "General"
    )
    workspace_map: dict[str, str] = {}
    raw_workspaces = payload.get("workspaces") or list(DEFAULT_WORKSPACES)
    for raw in raw_workspaces:
        name = raw if isinstance(raw, str) else raw.get("name") if isinstance(raw, dict) else None
        if name:
            _ensure_workspace(
                db, user, str(name), workspace_map, fallback_name="General"
            )
    if not workspace_map:
        _ensure_workspace(
            db, user, "General", workspace_map, fallback_name="General"
        )
    counts["workspaces"] = len(workspace_map)
    fallback_ws = workspace_map.get(
        str(current_name), next(iter(workspace_map.values()))
    )

    node_map: dict[str, str] = {}
    timer_count = [0]
    for module_key, module_type in (
        ("habits", ModuleType.HABITS),
        ("routines", ModuleType.ROUTINES),
        ("backlog", ModuleType.BACKLOG),
    ):
        tree = payload.get(module_key) or []
        if not isinstance(tree, list):
            warnings.append(f"'{module_key}' no es una lista; se ignora.")
            continue
        for index, item in enumerate(tree):
            if not isinstance(item, dict):
                continue
            ws_name = item.get("workspace") or item.get("ws")
            workspace_id = (
                _ensure_workspace(
                    db, user, str(ws_name), workspace_map, fallback_name=current_name
                )
                if ws_name
                else fallback_ws
            )
            _legacy_node(
                db,
                user,
                item,
                module_type=module_type,
                workspace_id=workspace_id,
                parent_id=None,
                node_map=node_map,
                timer_count=timer_count,
                sort_order=index,
            )
    counts["nodes"] = len(node_map)
    counts["timer_sessions"] = timer_count[0]

    # Agenda legacy: hora -> [id | {id, recurring, scheduleDays}]
    schedule = payload.get("dailySchedule") or {}
    if isinstance(schedule, dict):
        for hour, entries in schedule.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                raw_id = entry if isinstance(entry, str) else entry.get("id") if isinstance(entry, dict) else None
                new_id = node_map.get(str(raw_id)) if raw_id else None
                if not new_id:
                    continue
                data = entry if isinstance(entry, dict) else {}
                db.add(
                    DailyScheduleSlot(
                        user_id=user.id,
                        node_id=new_id,
                        hour_slot=str(hour)[:5],
                        recurring=bool(data.get("recurring", True)),
                        assigned_logical_date=str(
                            data.get("assignedLogicalDate")
                            or payload.get("lastAccessedDate")
                            or today
                        )[:10],
                        skip_logical_date=(
                            str(data.get("skipLogicalDate"))[:10]
                            if data.get("skipLogicalDate")
                            else None
                        ),
                        schedule_days=[
                            int(day)
                            for day in (data.get("scheduleDays") or [])
                            if str(day).isdigit()
                        ],
                    )
                )
                counts["schedule_slots"] += 1

    # Excepciones
    for item in payload.get("exceptions") or []:
        if not isinstance(item, dict):
            continue
        start = _parse_dt(
            item.get("startTime") or item.get("start_time"),
            default=datetime.combine(_parse_date(item.get("date")) or date.today(), time.min),
        )
        end = _parse_dt(
            item.get("endTime") or item.get("end_time"),
            default=start,
        )
        if end <= start:
            continue
        ws_name = item.get("workspace") or item.get("ws") or current_name
        workspace_id = _ensure_workspace(
            db, user, str(ws_name), workspace_map, fallback_name=current_name
        )
        splits = split_interval_by_logical_date(
            start, end, user.logical_cutoff_hour
        )
        affected = item.get("affectedHours")
        if isinstance(affected, list):
            affected_hours = float(len(affected))
            affected_list = [str(value) for value in affected]
        else:
            affected_hours = _safe_float(affected)
            affected_list = sorted(splits)
        blocked = [
            node_map[str(node_id)]
            for node_id in (item.get("blockedTaskIds") or [])
            if str(node_id) in node_map
        ]
        db.add(
            TimeException(
                user_id=user.id,
                workspace_id=workspace_id,
                title=str(item.get("title") or "Excepción")[:300],
                impact=_coerce_enum(
                    ImpactLevel, item.get("impact"), ImpactLevel.LEVE
                ),
                area=_coerce_enum(ExceptionArea, item.get("area")),
                note=str(item.get("note") or "")[:2000],
                start_time=start,
                end_time=end,
                logical_date=str(
                    item.get("date")
                    or iso_to_logical_date(start, user.logical_cutoff_hour)
                )[:10],
                affected_hours=affected_hours,
                affected_hours_list=affected_list,
                blocked_task_ids=blocked,
                day_splits={
                    key: round(value, 2) for key, value in splits.items()
                },
            )
        )
        counts["exceptions"] += 1

    # Objetivos y vínculos
    objective_map: dict[str, str] = {}
    linked_nodes: set[str] = set()
    for item in payload.get("objectives") or []:
        if not isinstance(item, dict):
            continue
        ws_name = item.get("ws") or item.get("workspace") or current_name
        workspace_id = _ensure_workspace(
            db, user, str(ws_name), workspace_map, fallback_name=current_name
        )
        objective = Objective(
            user_id=user.id,
            workspace_id=workspace_id,
            title=str(item.get("title") or "Objetivo")[:300],
            description=(str(item.get("description"))[:2000] if item.get("description") else None),
            horizon=_coerce_enum(Horizon, item.get("horizon"), Horizon.SEMANAL),
            start_date=_parse_date(item.get("startDate")),
            end_date=_parse_date(item.get("endDate")),
        )
        db.add(objective)
        db.flush()
        old_id = str(item.get("id") or uuid4().hex)
        objective_map[old_id] = objective.id
        counts["objectives"] += 1
        raw_links = item.get("linkedItems") or []
        for raw_link in raw_links:
            raw_node = (
                raw_link.get("id")
                if isinstance(raw_link, dict)
                else raw_link
            )
            new_node = node_map.get(str(raw_node)) if raw_node else None
            if not new_node or new_node in linked_nodes:
                continue
            node = db.get(TaskNode, new_node)
            if node is None:
                continue
            db.add(
                ObjectiveTaskLink(
                    user_id=user.id,
                    objective_id=objective.id,
                    node_id=new_node,
                    module_type=node.module_type,
                )
            )
            node.objective_id = objective.id
            linked_nodes.add(new_node)

    # Logros
    for item in payload.get("achievements") or []:
        if not isinstance(item, dict):
            continue
        old_node = str(item.get("nodeId") or "")
        new_node = node_map.get(old_node)
        ws_name = item.get("workspace") or current_name
        workspace_id = (
            workspace_map.get(str(ws_name))
            if str(ws_name) in workspace_map
            else fallback_ws
        )
        objective_id = objective_map.get(str(item.get("objectiveId") or ""))
        module_type = _coerce_module(item.get("moduleType") or item.get("module"))
        db.add(
            Achievement(
                user_id=user.id,
                workspace_id=workspace_id,
                node_id=new_node,
                source_id=_remap_source(
                    str(item.get("sourceId") or item.get("id") or uuid4().hex),
                    node_map,
                )[:120],
                module_type=module_type,
                title=str(item.get("title") or "Logro")[:500],
                completed_at=_parse_dt(
                    item.get("completedAt"), default=datetime.now()
                ),
                timer_mins=_safe_int(item.get("timerMins")),
                objective_id=objective_id,
            )
        )
        counts["achievements"] += 1

    # Score global legacy
    for day, data in (payload.get("scoreHistory") or {}).items():
        if not isinstance(data, dict):
            continue
        _record_score_row(
            db,
            user,
            workspace_id=None,
            scope_key="global",
            logical_date=str(day)[:10],
            data=data,
        )
        counts["score_history"] += 1

    # Score por workspace legacy
    by_ws = payload.get("scoreHistoryByWs") or {}
    if isinstance(by_ws, dict):
        for ws_name, history in by_ws.items():
            if not isinstance(history, dict):
                continue
            workspace_id = workspace_map.get(str(ws_name))
            if not workspace_id:
                continue
            for day, data in history.items():
                if not isinstance(data, dict):
                    continue
                _record_score_row(
                    db,
                    user,
                    workspace_id=workspace_id,
                    scope_key=workspace_id,
                    logical_date=str(day)[:10],
                    data=data,
                )
                counts["score_history"] += 1

    # dailyLog legacy
    for day, data in (payload.get("dailyLog") or {}).items():
        if not isinstance(data, dict):
            continue
        _record_snapshot(
            db,
            user,
            workspace_id=None,
            scope_key="global",
            logical_date=str(day)[:10],
            data=data,
        )
        counts["snapshots"] += 1

    # objectiveHistory legacy
    for old_objective, points in (payload.get("objectiveHistory") or {}).items():
        new_objective = objective_map.get(str(old_objective))
        if not new_objective or not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, dict) or not point.get("date"):
                continue
            ObjectiveRepository.upsert_snapshot(
                db,
                user_id=user.id,
                objective_id=new_objective,
                logical_date=str(point.get("date"))[:10],
                pct=_safe_float(point.get("pct")),
                done=_safe_int(point.get("done")),
                total=_safe_int(point.get("total")),
            )
            counts["objective_snapshots"] += 1

    # Timer activo legacy
    timer = payload.get("activeTimer") or payload.get("timerState")
    if isinstance(timer, dict):
        node_id = node_map.get(str(timer.get("linkedNodeId") or timer.get("nodeId") or ""))
        phase = _coerce_enum(
            TimerPhase, timer.get("phase"), TimerPhase.WORK
        )
        work_min = _safe_int(timer.get("workMin"), 25) or 25
        break_min = _safe_int(timer.get("breakMin"), 5) or 5
        total = _safe_int(timer.get("totalSecs"), work_min * 60)
        remaining = _safe_int(timer.get("remaining"), total)
        db.add(
            ActiveTimerState(
                user_id=user.id,
                node_id=node_id,
                mode=str(timer.get("mode") or "pomodoro"),
                phase=phase,
                total_secs=total,
                remaining_secs=remaining,
                running=False,
                cycle_count=_safe_int(timer.get("cycleCount")),
                focused_secs=0,
                work_min=work_min,
                break_min=break_min,
                logical_date=today,
            )
        )

    # Preferencias
    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        preferences = UserPreferences(user_id=user.id)
        UserRepository.create_preferences(db, preferences)
    preferences.current_workspace_id = fallback_ws
    raw_preferences = payload.get("preferences") or {}
    if isinstance(raw_preferences, dict):
        preferences.pomodoro_work_min = _safe_int(
            raw_preferences.get("pomodoroWorkMin"), 25
        ) or 25
        preferences.pomodoro_break_min = _safe_int(
            raw_preferences.get("pomodoroBreakMin"), 5
        ) or 5
        preferences.notifications_enabled = bool(
            raw_preferences.get("notificationsEnabled", False)
        )
    theme = (payload.get("preferences") or {}).get("theme")
    if theme in {"light", "dark"}:
        user.theme = theme
    last_access = payload.get("lastAccessedDate")
    if last_access:
        user.last_accessed_logical_date = str(last_access)[:10]
    else:
        user.last_accessed_logical_date = today
    db.flush()
    return counts


def _import_new(db: Session, user: User, payload: dict[str, Any]) -> dict[str, int]:
    """Importa el formato nuevo (schemaVersion 4) remapeando IDs."""

    counts = {
        "workspaces": 0,
        "nodes": 0,
        "schedule_slots": 0,
        "exceptions": 0,
        "objectives": 0,
        "achievements": 0,
        "score_history": 0,
        "snapshots": 0,
        "timer_sessions": 0,
        "objective_snapshots": 0,
    }
    workspace_map: dict[str, str] = {}
    workspace_name_map: dict[str, str] = {}
    for item in payload.get("workspaces") or []:
        if not isinstance(item, dict):
            continue
        old_id = str(item.get("id") or uuid4().hex)
        workspace = Workspace(
            user_id=user.id,
            name=str(item.get("name") or "General")[:80],
            is_default=bool(item.get("isDefault", not workspace_map)),
        )
        db.add(workspace)
        db.flush()
        workspace_map[old_id] = workspace.id
        workspace_name_map[workspace.name] = workspace.id
        counts["workspaces"] += 1
    if not workspace_map:
        workspace = Workspace(user_id=user.id, name="General", is_default=True)
        db.add(workspace)
        db.flush()
        workspace_map["__default__"] = workspace.id
        workspace_name_map["General"] = workspace.id
        counts["workspaces"] = 1
    default_ws = next(iter(workspace_map.values()))

    node_map: dict[str, str] = {}
    pending_nodes: list[tuple[TaskNode, str | None]] = []
    for item in payload.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        old_id = str(item.get("id") or uuid4().hex)
        workspace_id = workspace_map.get(
            str(item.get("workspaceId") or ""), default_ws
        )
        node = TaskNode(
            user_id=user.id,
            workspace_id=workspace_id,
            parent_id=None,
            module_type=_coerce_module(item.get("moduleType")),
            title=str(item.get("title") or "Sin título")[:500],
            completed=bool(item.get("completed")),
            completed_at=_parse_dt(item.get("completedAt"))
            if item.get("completedAt")
            else None,
            expanded=bool(item.get("expanded", True)),
            is_archived=bool(item.get("isArchived", False)),
            routine_category=_coerce_enum(
                RoutineCategory, item.get("routineCategory")
            ),
            priority=_coerce_enum(Priority, item.get("priority")),
            tag=_coerce_enum(TaskTag, item.get("tag")),
            schedule_days=[
                int(day)
                for day in (item.get("scheduleDays") or [])
                if str(day).isdigit()
            ],
            period_start=_parse_date(item.get("periodStart")),
            period_end=_parse_date(item.get("periodEnd")),
            sort_order=_safe_int(item.get("sortOrder")),
        )
        db.add(node)
        db.flush()
        node_map[old_id] = node.id
        pending_nodes.append((node, str(item.get("parentId") or "") or None))
        counts["nodes"] += 1
        counts["timer_sessions"] += _legacy_timer_sessions(
            db, user, node.id, item.get("timerSessions")
        )
    for node, old_parent in pending_nodes:
        if old_parent and old_parent in node_map:
            node.parent_id = node_map[old_parent]
    db.flush()

    for item in payload.get("schedule") or []:
        if not isinstance(item, dict):
            continue
        new_node = node_map.get(str(item.get("nodeId") or ""))
        if not new_node:
            continue
        db.add(
            DailyScheduleSlot(
                user_id=user.id,
                node_id=new_node,
                hour_slot=str(item.get("hourSlot") or "04:00")[:5],
                recurring=bool(item.get("recurring", True)),
                assigned_logical_date=str(
                    item.get("assignedLogicalDate") or today_for(user)
                )[:10],
                skip_logical_date=(
                    str(item.get("skipLogicalDate"))[:10]
                    if item.get("skipLogicalDate")
                    else None
                ),
                schedule_days=[
                    int(day)
                    for day in (item.get("scheduleDays") or [])
                    if str(day).isdigit()
                ],
            )
        )
        counts["schedule_slots"] += 1

    for item in payload.get("exceptions") or []:
        if not isinstance(item, dict):
            continue
        start = _parse_dt(item.get("startTime"))
        end = _parse_dt(item.get("endTime"))
        if end <= start:
            continue
        workspace_id = workspace_map.get(
            str(item.get("workspaceId") or ""), default_ws
        )
        splits = split_interval_by_logical_date(
            start, end, user.logical_cutoff_hour
        )
        db.add(
            TimeException(
                user_id=user.id,
                workspace_id=workspace_id,
                title=str(item.get("title") or "Excepción")[:300],
                impact=_coerce_enum(
                    ImpactLevel, item.get("impact"), ImpactLevel.LEVE
                ),
                area=_coerce_enum(ExceptionArea, item.get("area")),
                note=str(item.get("note") or "")[:2000],
                start_time=start,
                end_time=end,
                logical_date=str(
                    item.get("logicalDate")
                    or iso_to_logical_date(start, user.logical_cutoff_hour)
                )[:10],
                affected_hours=_safe_float(item.get("affectedHours")),
                affected_hours_list=[
                    str(value)
                    for value in (item.get("affectedHoursList") or [])
                ],
                blocked_task_ids=[
                    node_map[str(node_id)]
                    for node_id in (item.get("blockedTaskIds") or [])
                    if str(node_id) in node_map
                ],
                day_splits={
                    key: round(value, 2) for key, value in splits.items()
                },
            )
        )
        counts["exceptions"] += 1

    objective_map: dict[str, str] = {}
    linked_nodes: set[str] = set()
    for item in payload.get("objectives") or []:
        if not isinstance(item, dict):
            continue
        old_id = str(item.get("id") or uuid4().hex)
        workspace_id = workspace_map.get(
            str(item.get("workspaceId") or ""), default_ws
        )
        objective = Objective(
            user_id=user.id,
            workspace_id=workspace_id,
            title=str(item.get("title") or "Objetivo")[:300],
            description=(str(item.get("description"))[:2000] if item.get("description") else None),
            horizon=_coerce_enum(Horizon, item.get("horizon"), Horizon.SEMANAL),
            start_date=_parse_date(item.get("startDate")),
            end_date=_parse_date(item.get("endDate")),
        )
        db.add(objective)
        db.flush()
        objective_map[old_id] = objective.id
        counts["objectives"] += 1
        for raw_node in item.get("linkedItems") or []:
            new_node = node_map.get(str(raw_node))
            if not new_node or new_node in linked_nodes:
                continue
            node = db.get(TaskNode, new_node)
            if node is None:
                continue
            db.add(
                ObjectiveTaskLink(
                    user_id=user.id,
                    objective_id=objective.id,
                    node_id=new_node,
                    module_type=node.module_type,
                )
            )
            node.objective_id = objective.id
            linked_nodes.add(new_node)

    for item in payload.get("achievements") or []:
        if not isinstance(item, dict):
            continue
        new_node = node_map.get(str(item.get("nodeId") or ""))
        workspace_id = workspace_map.get(str(item.get("workspaceId") or ""))
        objective_id = objective_map.get(str(item.get("objectiveId") or ""))
        db.add(
            Achievement(
                user_id=user.id,
                workspace_id=workspace_id,
                node_id=new_node,
                source_id=_remap_source(
                    str(item.get("sourceId") or uuid4().hex), node_map
                )[:120],
                module_type=_coerce_module(item.get("moduleType")),
                title=str(item.get("title") or "Logro")[:500],
                completed_at=_parse_dt(
                    item.get("completedAt"), default=datetime.now()
                ),
                timer_mins=_safe_int(item.get("timerMins")),
                objective_id=objective_id,
            )
        )
        counts["achievements"] += 1

    for item in payload.get("scoreHistory") or []:
        if not isinstance(item, dict):
            continue
        scope_key = str(item.get("scopeKey") or "global")
        workspace_id: str | None
        if scope_key == "global":
            workspace_id = None
        else:
            workspace_id = workspace_map.get(
                str(item.get("workspaceId") or scope_key)
            ) or workspace_name_map.get(scope_key)
            if workspace_id is None:
                continue
            scope_key = workspace_id
        _record_score_row(
            db,
            user,
            workspace_id=workspace_id,
            scope_key=scope_key,
            logical_date=str(item.get("logicalDate"))[:10],
            data=item,
        )
        counts["score_history"] += 1

    for item in payload.get("activitySnapshots") or []:
        if not isinstance(item, dict):
            continue
        scope_key = str(item.get("scopeKey") or "global")
        workspace_id = (
            None
            if scope_key == "global"
            else workspace_map.get(str(item.get("workspaceId") or scope_key))
        )
        if scope_key != "global" and workspace_id is None:
            continue
        _record_snapshot(
            db,
            user,
            workspace_id=workspace_id,
            scope_key=workspace_id or "global",
            logical_date=str(item.get("logicalDate"))[:10],
            data=item,
        )
        counts["snapshots"] += 1

    for item in payload.get("objectiveHistory") or []:
        if not isinstance(item, dict):
            continue
        objective_id = objective_map.get(str(item.get("objectiveId") or ""))
        if not objective_id:
            continue
        ObjectiveRepository.upsert_snapshot(
            db,
            user_id=user.id,
            objective_id=objective_id,
            logical_date=str(item.get("logicalDate"))[:10],
            pct=_safe_float(item.get("pct")),
            done=_safe_int(item.get("done")),
            total=_safe_int(item.get("total")),
        )
        counts["objective_snapshots"] += 1

    timer = payload.get("activeTimer")
    if isinstance(timer, dict):
        db.add(
            ActiveTimerState(
                user_id=user.id,
                node_id=node_map.get(str(timer.get("nodeId") or "")),
                mode=str(timer.get("mode") or "pomodoro"),
                phase=_coerce_enum(
                    TimerPhase, timer.get("phase"), TimerPhase.WORK
                ),
                total_secs=_safe_int(timer.get("totalSecs"), 1500),
                remaining_secs=_safe_int(timer.get("remainingSecs"), 1500),
                running=False,
                cycle_count=_safe_int(timer.get("cycleCount")),
                focused_secs=0,
                work_min=_safe_int(timer.get("workMin"), 25) or 25,
                break_min=_safe_int(timer.get("breakMin"), 5) or 5,
                logical_date=today_for(user),
            )
        )

    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        preferences = UserPreferences(user_id=user.id)
        UserRepository.create_preferences(db, preferences)
    preferences.current_workspace_id = default_ws
    raw_preferences = payload.get("preferences") or {}
    if isinstance(raw_preferences, dict):
        preferences.pomodoro_work_min = _safe_int(
            raw_preferences.get("pomodoroWorkMin"), 25
        ) or 25
        preferences.pomodoro_break_min = _safe_int(
            raw_preferences.get("pomodoroBreakMin"), 5
        ) or 5
        preferences.notifications_enabled = bool(
            raw_preferences.get("notificationsEnabled", False)
        )
    user_data = payload.get("user") or {}
    if isinstance(user_data, dict):
        theme = user_data.get("theme")
        if theme in {"light", "dark"}:
            user.theme = theme
        cutoff = user_data.get("logicalCutoffHour")
        if isinstance(cutoff, int) and 0 <= cutoff <= 12:
            user.logical_cutoff_hour = cutoff
    user.last_accessed_logical_date = str(
        payload.get("logicalDate") or today_for(user)
    )[:10]
    db.flush()
    return counts


def today_for(user: User) -> str:
    return get_logical_date(cutoff_hour=user.logical_cutoff_hour)


def import_payload(
    db: Session, user: User, payload: dict[str, Any]
) -> tuple[dict[str, int], int, list[str]]:
    """Importa JSON legacy o nuevo de forma atómica (savepoint)."""

    if not isinstance(payload, dict):
        raise BackupError("El archivo no contiene un objeto JSON válido.")
    source_version = _safe_int(
        payload.get("schemaVersion") or payload.get("schema_version") or 1,
        1,
    )
    warnings: list[str] = []
    savepoint = db.begin_nested()
    try:
        _wipe_user_data(db, user)
        if source_version >= 4 and isinstance(payload.get("nodes"), list):
            counts = _import_new(db, user, payload)
        else:
            counts = _import_legacy(db, user, payload)
        savepoint.commit()
    except Exception as exc:
        savepoint.rollback()
        if isinstance(exc, (BackupError, ValidationError)):
            raise
        raise BackupError(
            f"No se pudo importar el backup: {exc}"
        ) from exc
    db.flush()
    return counts, source_version, warnings


def restore_slot(
    db: Session, user: User, slot: str
) -> tuple[dict[str, int], int, list[str]]:
    payload = read_slot(user, slot)
    # Backup del estado actual antes de restaurar.
    try:
        pre_reset_backup(db, user)
    except Exception:
        pass
    return import_payload(db, user, payload)
