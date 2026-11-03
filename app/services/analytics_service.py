"""Cálculo de scores, estadísticas, historial y datos del dashboard.

Toda función recibe un ``User`` ya autenticado y filtra por ``user_id`` en cada
consulta. El módulo concentra la lógica de lectura; la escritura de historial se
hace mediante ``persist_scores`` y ``persist_activity_snapshots``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import ModuleType, RoutineCategory
from app.domain.logical_date import (
    get_logical_date,
    iso_to_logical_date,
    logical_day_bounds,
    missing_dates,
    parse_logical_date,
    period_key_for_date,
    period_label,
)
from app.domain.scoring import (
    ModuleProgress,
    ScoreResult,
    average,
    compute_score,
    compute_streaks,
    heatmap_level,
    last_n_average,
    score_from_stored_base,
    split_exception_penalty,
)
from app.models.achievement import Achievement
from app.models.exception_log import TimeException
from app.models.history import DailyActivitySnapshot, DailyScoreHistory
from app.models.schedule import ScheduleSkip
from app.models.task_node import TaskNode
from app.models.timer import TimerSession
from app.models.user import User
from app.repositories.achievements import AchievementRepository
from app.repositories.exceptions import ExceptionRepository
from app.repositories.history import HistoryRepository
from app.repositories.nodes import NodeRepository
from app.repositories.objectives import ObjectiveRepository
from app.repositories.schedules import ScheduleRepository
from app.repositories.timers import TimerRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.achievement import AchievementOut
from app.schemas.analytics import (
    BootstrapResponse,
    CategoriesResponse,
    CategoryOut,
    CorrelationDayOut,
    CorrelationResponse,
    GlobalStatsOut,
    HeatmapCellOut,
    HeatmapResponse,
    HistoryBucketOut,
    HistoryDayOut,
    HistoryExceptionOut,
    HistoryResponse,
    HistoryTaskOut,
    ObjectiveHistoryChartResponse,
    ObjectiveHistoryDataset,
    ScoreOut,
    TimerImpactOut,
    TimerImpactTaskOut,
    TodayScoreOut,
)
from app.schemas.exception_log import ExceptionOut
from app.schemas.node import NodeOut
from app.schemas.objective import ObjectiveOut, ObjectivePointOut
from app.schemas.schedule import ScheduleSlotOut
from app.schemas.workspace import WorkspaceOut
from app.services import tree_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def logical_today(user: User) -> str:
    return get_logical_date(cutoff_hour=user.logical_cutoff_hour)


def _workspace_name_map(db: Session, user: User) -> dict[str, str]:
    return {workspace.id: workspace.name for workspace in WorkspaceRepository.list_for_user(db, user.id)}


def _children_map(nodes: Iterable[TaskNode]) -> dict[str | None, list[TaskNode]]:
    mapping: dict[str | None, list[TaskNode]] = defaultdict(list)
    for node in nodes:
        mapping[node.parent_id].append(node)
    for children in mapping.values():
        children.sort(key=lambda n: (n.sort_order, n.created_at, n.title.lower()))
    return mapping


def _logical_completed(node: TaskNode, cutoff: int) -> str | None:
    if node.completed_at is None:
        return None
    return iso_to_logical_date(node.completed_at, cutoff)


class _ActivityContext:
    """Estado de actividad de un día lógico concreto."""

    def __init__(
        self,
        *,
        nodes: list[TaskNode],
        scheduled: set[str],
        timer_nodes: set[str],
        completed_today: set[str],
        active: set[str],
        children: dict[str | None, list[TaskNode]],
    ) -> None:
        self.nodes = nodes
        self.scheduled = scheduled
        self.timer_nodes = timer_nodes
        self.completed_today = completed_today
        self.active = active
        self.children = children


def _activity_context(
    db: Session,
    user: User,
    logical_date: str,
    *,
    workspace_id: str | None = None,
    nodes: list[TaskNode] | None = None,
) -> _ActivityContext:
    if nodes is None:
        nodes = NodeRepository.list_all(
            db,
            user.id,
            workspace_id=workspace_id,
            include_archived=False,
        )
    children = _children_map(nodes)
    by_id = {node.id: node for node in nodes}
    scheduled = tree_service.active_scheduled_node_ids(
        db, user, logical_date, workspace_id=workspace_id, nodes_by_id=by_id
    )
    sessions = TimerRepository.list_for_nodes_date(
        db, user.id, list(by_id.keys()), logical_date
    )
    timer_nodes = {session.node_id for session in sessions}
    completed_today = {
        node.id
        for node in nodes
        if node.completed_at is not None
        and iso_to_logical_date(node.completed_at, user.logical_cutoff_hour) == logical_date
    }

    active: set[str] = set()

    def walk(node: TaskNode) -> bool:
        is_active = (
            node.id in scheduled
            or node.id in timer_nodes
            or node.id in completed_today
        )
        for child in children.get(node.id, []):
            if walk(child):
                is_active = True
        if is_active:
            active.add(node.id)
        return is_active

    for node in nodes:
        if not node.parent_id or node.parent_id not in by_id:
            walk(node)
    return _ActivityContext(
        nodes=nodes,
        scheduled=scheduled,
        timer_nodes=timer_nodes,
        completed_today=completed_today,
        active=active,
        children=children,
    )


def _scope_nodes(
    db: Session, user: User, workspace_id: str | None
) -> list[TaskNode]:
    return NodeRepository.list_all(
        db,
        user.id,
        workspace_id=workspace_id,
        include_archived=False,
    )


def _exception_minutes_for_date(
    db: Session,
    user: User,
    logical_date: str,
    *,
    workspace_id: str | None = None,
) -> tuple[float, float, list[TimeException]]:
    """Minutos Alta/Leve que caen en ``logical_date`` (split a las 04:00)."""

    exceptions = ExceptionRepository.list_for_user(
        db, user.id, workspace_id=workspace_id
    )
    high = 0.0
    low = 0.0
    relevant: list[TimeException] = []
    for exception in exceptions:
        if not exception.start_time or not exception.end_time:
            continue
        for split in split_exception_penalty(
            exception.start_time,
            exception.end_time,
            exception.impact.value,
            user.logical_cutoff_hour,
        ):
            if split.logical_date != logical_date:
                continue
            relevant.append(exception)
            if exception.impact.value == "Alta":
                high += split.minutes
            else:
                low += split.minutes
            break
    return high, low, relevant


def compute_scope_score(
    db: Session,
    user: User,
    *,
    logical_date: str,
    workspace_id: str | None = None,
) -> ScoreResult:
    """Score de un workspace (``workspace_id``) o global (``None``).

    Solo las raíces cuentan para Hábitos/Rutinas (igual que el frontend
    original); en Backlog cuenta una raíz si ella o alguna subtarea tuvo
    actividad ese día.
    """

    nodes = _scope_nodes(db, user, workspace_id)
    context = _activity_context(
        db, user, logical_date, workspace_id=workspace_id, nodes=nodes
    )
    habits = ModuleProgress()
    routines = ModuleProgress()
    backlog = ModuleProgress()

    for node in nodes:
        if node.parent_id is not None:
            continue
        if node.module_type == ModuleType.HABITS:
            active = (
                node.id in context.active
                or tree_service.node_schedule_active(node, logical_date)
            )
            if active:
                habits = ModuleProgress(
                    total=habits.total + 1,
                    completed=habits.completed + (1 if node.completed else 0),
                )
        elif node.module_type == ModuleType.ROUTINES:
            active = (
                node.id in context.active
                or tree_service.node_schedule_active(node, logical_date)
            )
            if active:
                routines = ModuleProgress(
                    total=routines.total + 1,
                    completed=routines.completed + (1 if node.completed else 0),
                )
        elif node.module_type == ModuleType.BACKLOG:
            if node.id in context.active:
                backlog = ModuleProgress(
                    total=backlog.total + 1,
                    completed=backlog.completed + (1 if node.completed else 0),
                )

    high, low, _ = _exception_minutes_for_date(
        db, user, logical_date, workspace_id=workspace_id
    )
    return compute_score(habits, routines, backlog, high, low)


def score_to_out(result: ScoreResult) -> ScoreOut:
    return ScoreOut(
        h_total=result.h_total,
        h_comp=result.h_comp,
        r_total=result.r_total,
        r_comp=result.r_comp,
        b_total=result.b_total,
        b_comp=result.b_comp,
        exc_mins=result.exc_mins,
        penalty=result.penalty,
        score=result.score,
        base_score=result.base_score,
        high_minutes=result.high_minutes,
        low_minutes=result.low_minutes,
    )


def _row_to_score_out(row: DailyScoreHistory) -> ScoreOut:
    return ScoreOut(
        h_total=row.h_total,
        h_comp=row.h_comp,
        r_total=row.r_total,
        r_comp=row.r_comp,
        b_total=row.b_total,
        b_comp=row.b_comp,
        exc_mins=row.exc_mins,
        penalty=row.penalty,
        score=row.score,
        base_score=row.base_score,
        high_minutes=row.high_minutes,
        low_minutes=row.low_minutes,
    )


# ---------------------------------------------------------------------------
# Persistencia de historial
# ---------------------------------------------------------------------------


def persist_scores(
    db: Session, user: User, logical_date: str
) -> dict[str, ScoreResult]:
    """Guarda el score de cada workspace y el global sin pisarse entre sí."""

    results: dict[str, ScoreResult] = {}
    for workspace in WorkspaceRepository.list_for_user(db, user.id):
        result = compute_scope_score(
            db, user, logical_date=logical_date, workspace_id=workspace.id
        )
        results[workspace.id] = result
        HistoryRepository.upsert_score(
            db,
            user_id=user.id,
            workspace_id=workspace.id,
            scope_key=workspace.id,
            logical_date=logical_date,
            result=result,
        )
    global_result = compute_scope_score(
        db, user, logical_date=logical_date, workspace_id=None
    )
    results["global"] = global_result
    HistoryRepository.upsert_score(
        db,
        user_id=user.id,
        workspace_id=None,
        scope_key="global",
        logical_date=logical_date,
        result=global_result,
    )
    return results


def _snapshot_tasks(
    nodes: list[TaskNode],
    context: _ActivityContext,
    *,
    module_type: ModuleType,
    workspace_names: dict[str, str],
    today: str,
    cutoff: int,
) -> list[dict[str, Any]]:
    """Aplana el subárbol activo de un módulo para el log diario."""

    result: list[dict[str, Any]] = []
    by_id = {node.id: node for node in nodes}
    roots = [
        node
        for node in nodes
        if node.module_type == module_type
        and (not node.parent_id or node.parent_id not in by_id)
    ]

    def include_root(node: TaskNode) -> bool:
        if module_type in (ModuleType.HABITS, ModuleType.ROUTINES):
            return (
                node.id in context.active
                or tree_service.node_schedule_active(node, today)
            )
        return node.id in context.active

    def append(node: TaskNode, parent_title: str | None) -> None:
        result.append(
            {
                "id": node.id,
                "title": node.title,
                "completed": bool(node.completed),
                "completed_at": node.completed_at.isoformat()
                if node.completed_at
                else None,
                "workspace": workspace_names.get(node.workspace_id, "General"),
                "parent_title": parent_title,
                "module": module_type.value,
            }
        )

    def walk(node: TaskNode, parent_title: str | None) -> None:
        append(node, parent_title)
        for child in context.children.get(node.id, []):
            walk(child, node.title)

    for root in roots:
        if not include_root(root):
            continue
        walk(root, None)
        # Los hijos de un hábito/rutina se incluyen siempre que el padre esté
        # activo; en Backlog solo se incluyen subárboles con actividad.
        if module_type == ModuleType.BACKLOG:
            # ``walk`` ya añadió todo; se conserva por compatibilidad.
            pass
    return result


def persist_activity_snapshots(
    db: Session, user: User, logical_date: str
) -> None:
    """Guarda el detalle de tareas/excepciones por ámbito."""

    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    names = {workspace.id: workspace.name for workspace in workspaces}
    all_nodes = NodeRepository.list_all(db, user.id, include_archived=False)
    global_context = _activity_context(
        db, user, logical_date, workspace_id=None, nodes=all_nodes
    )
    for workspace in [*workspaces, None]:
        scope_key = workspace.id if workspace else "global"
        workspace_id = workspace.id if workspace else None
        nodes = [
            node
            for node in all_nodes
            if workspace_id is None or node.workspace_id == workspace_id
        ]
        context = (
            global_context
            if workspace_id is None
            else _activity_context(
                db, user, logical_date, workspace_id=workspace_id, nodes=nodes
            )
        )
        score = compute_scope_score(
            db, user, logical_date=logical_date, workspace_id=workspace_id
        )
        high, low, relevant = _exception_minutes_for_date(
            db, user, logical_date, workspace_id=workspace_id
        )
        exceptions = [
            {
                "id": exception.id,
                "title": exception.title,
                "impact": exception.impact.value,
                "area": exception.area.value if exception.area else None,
                "start_time": exception.start_time.isoformat(),
                "end_time": exception.end_time.isoformat(),
                "workspace": names.get(exception.workspace_id),
                "affected_hours": exception.affected_hours,
            }
            for exception in relevant
        ]
        HistoryRepository.upsert_snapshot(
            db,
            user_id=user.id,
            workspace_id=workspace_id,
            scope_key=scope_key,
            logical_date=logical_date,
            score=score.score,
            habits=_snapshot_tasks(
                nodes,
                context,
                module_type=ModuleType.HABITS,
                workspace_names=names,
                today=logical_date,
                cutoff=user.logical_cutoff_hour,
            ),
            routines=_snapshot_tasks(
                nodes,
                context,
                module_type=ModuleType.ROUTINES,
                workspace_names=names,
                today=logical_date,
                cutoff=user.logical_cutoff_hour,
            ),
            backlog=_snapshot_tasks(
                nodes,
                context,
                module_type=ModuleType.BACKLOG,
                workspace_names=names,
                today=logical_date,
                cutoff=user.logical_cutoff_hour,
            ),
            exceptions=exceptions,
        )


def recalculate_day_score(
    db: Session, user: User, logical_date: str
) -> None:
    """Revierte/aplica penalizaciones de excepciones en un día ya cerrado.

    Usa ``base_score`` persistido para no depender del estado actual del árbol.
    """

    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    scopes: list[tuple[str, str | None]] = [
        (workspace.id, workspace.id) for workspace in workspaces
    ]
    scopes.append(("global", None))
    for scope_key, workspace_id in scopes:
        row = HistoryRepository.get_score(
            db, user.id, scope_key, logical_date
        )
        if row is None:
            continue
        high, low, _ = _exception_minutes_for_date(
            db, user, logical_date, workspace_id=workspace_id
        )
        score, penalty = score_from_stored_base(row.base_score, high, low)
        HistoryRepository.update_score_penalty(
            db,
            row,
            score=score,
            penalty=penalty,
            exc_mins=round(high + low),
            high_minutes=high,
            low_minutes=low,
        )
        snapshot = HistoryRepository.get_snapshot(
            db, user.id, scope_key, logical_date
        )
        if snapshot is not None:
            snapshot.score = score
            snapshot.exceptions = _snapshot_exception_list(
                db, user, logical_date, workspace_id
            )
    db.flush()


def _snapshot_exception_list(
    db: Session,
    user: User,
    logical_date: str,
    workspace_id: str | None,
) -> list[dict[str, Any]]:
    _, _, relevant = _exception_minutes_for_date(
        db, user, logical_date, workspace_id=workspace_id
    )
    names = _workspace_name_map(db, user)
    return [
        {
            "id": exception.id,
            "title": exception.title,
            "impact": exception.impact.value,
            "area": exception.area.value if exception.area else None,
            "start_time": exception.start_time.isoformat(),
            "end_time": exception.end_time.isoformat(),
            "workspace": names.get(exception.workspace_id),
            "affected_hours": exception.affected_hours,
        }
        for exception in relevant
    ]


def infill_missing_days(db: Session, user: User, last_date: str, today: str) -> list[str]:
    """Crea filas en cero para los huecos entre dos fechas lógicas."""

    filled: list[str] = []
    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    for gap in missing_dates(last_date, today):
        filled.append(gap)
        for workspace in workspaces:
            if HistoryRepository.get_score(db, user.id, workspace.id, gap) is None:
                HistoryRepository.upsert_score(
                    db,
                    user_id=user.id,
                    workspace_id=workspace.id,
                    scope_key=workspace.id,
                    logical_date=gap,
                    result=compute_score(ModuleProgress(), ModuleProgress(), ModuleProgress()),
                )
        if HistoryRepository.get_score(db, user.id, "global", gap) is None:
            HistoryRepository.upsert_score(
                db,
                user_id=user.id,
                workspace_id=None,
                scope_key="global",
                logical_date=gap,
                result=compute_score(ModuleProgress(), ModuleProgress(), ModuleProgress()),
            )
        if HistoryRepository.get_snapshot(db, user.id, "global", gap) is None:
            HistoryRepository.upsert_snapshot(
                db,
                user_id=user.id,
                workspace_id=None,
                scope_key="global",
                logical_date=gap,
                score=0,
                habits=[],
                routines=[],
                backlog=[],
                exceptions=[],
            )
    return filled


# ---------------------------------------------------------------------------
# Consultas del dashboard
# ---------------------------------------------------------------------------


def today_score(db: Session, user: User) -> TodayScoreOut:
    workspace = tree_service.get_current_workspace(db, user)
    today = logical_today(user)
    workspace_result = compute_scope_score(
        db, user, logical_date=today, workspace_id=workspace.id
    )
    global_result = compute_scope_score(
        db, user, logical_date=today, workspace_id=None
    )
    return TodayScoreOut(
        logical_date=today,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        score=workspace_result.score,
        breakdown=score_to_out(workspace_result),
        global_score=score_to_out(global_result),
    )


def _global_score_rows(db: Session, user: User) -> list[DailyScoreHistory]:
    rows = HistoryRepository.list_scores(db, user.id, scope_key="global")
    if rows:
        return rows
    # Compatibilidad con datos importados de versiones antiguas.
    all_rows = HistoryRepository.list_scores(db, user.id)
    by_date: dict[str, DailyScoreHistory] = {}
    for row in all_rows:
        current = by_date.get(row.logical_date)
        if current is None or (row.scope_key == "global"):
            by_date[row.logical_date] = row
    return [by_date[key] for key in sorted(by_date)]


def global_stats(db: Session, user: User) -> GlobalStatsOut:
    rows = _global_score_rows(db, user)
    scores = {row.logical_date: float(row.score) for row in rows}
    dates = sorted(scores)
    exceptions = ExceptionRepository.list_for_user(db, user.id)
    total_minutes = 0.0
    for exception in exceptions:
        if exception.start_time and exception.end_time:
            delta = (exception.end_time - exception.start_time).total_seconds() / 60
            if delta > 0:
                total_minutes += delta
    current_streak, max_streak = compute_streaks(scores)
    return GlobalStatsOut(
        dias_totales=len(dates),
        fecha_inicio=dates[0] if dates else logical_today(user),
        score_promedio_global=average(list(scores.values())),
        score_prom_7d=last_n_average(scores, 7),
        score_prom_30d=last_n_average(scores, 30),
        total_habitos_comp=sum(row.h_comp for row in rows),
        total_rutinas_comp=sum(row.r_comp for row in rows),
        total_backlog_comp=sum(row.b_comp for row in rows),
        total_minutos_fuga=round(total_minutes),
        racha_actual=current_streak,
        racha_maxima=max_streak,
    )


def heatmap(db: Session, user: User, *, weeks: int = 16) -> HeatmapResponse:
    today = parse_logical_date(logical_today(user))
    dow = (today.weekday() + 1) % 7  # Domingo = 0
    pad_end = 6 - dow
    start_offset = weeks * 7 - 1 - pad_end
    start = today - timedelta(days=start_offset)
    dates = [start + timedelta(days=index) for index in range(weeks * 7)]

    rows = _global_score_rows(db, user)
    by_date = {row.logical_date: row for row in rows}
    month_names = [
        "Ene",
        "Feb",
        "Mar",
        "Abr",
        "May",
        "Jun",
        "Jul",
        "Ago",
        "Sep",
        "Oct",
        "Nov",
        "Dic",
    ]
    week_cells: list[list[HeatmapCellOut]] = []
    month_labels: list[str] = []
    last_month = -1
    for week_index in range(weeks):
        cells: list[HeatmapCellOut] = []
        week_dates = dates[week_index * 7 : week_index * 7 + 7]
        for day in week_dates:
            key = day.isoformat()
            row = by_date.get(key)
            score = float(row.score) if row is not None else None
            tooltip = (
                f"{key}: Score {row.score} | Hábitos {row.h_comp}/{row.h_total} | "
                f"Rutinas {row.r_comp}/{row.r_total}"
                if row is not None
                else f"{key}: Sin datos"
            )
            if row is not None and row.exc_mins > 0:
                tooltip += f" | Fuga {row.exc_mins}min"
            cells.append(
                HeatmapCellOut(
                    date=key,
                    score=score,
                    level=heatmap_level(score) if score is not None else 0,
                    is_today=day == today,
                    has_data=row is not None,
                    tooltip=tooltip,
                )
            )
        week_cells.append(cells)
        first_month = week_dates[0].month
        month_labels.append(
            month_names[first_month - 1] if first_month != last_month else ""
        )
        last_month = first_month
    return HeatmapResponse(
        weeks=week_cells,
        month_labels=month_labels,
        day_labels=["D", "L", "M", "X", "J", "V", "S"],
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
        current_date=today.isoformat(),
    )


def timer_impact(db: Session, user: User, *, workspace_id: str | None = None) -> TimerImpactOut:
    today = logical_today(user)
    nodes = _scope_nodes(db, user, workspace_id)
    if not nodes:
        return TimerImpactOut()
    node_ids = [node.id for node in nodes]
    all_sessions = TimerRepository.list_for_nodes(db, user.id, node_ids)
    today_sessions = [session for session in all_sessions if session.logical_date == today]
    with_timer_ids = {
        session.node_id for session in today_sessions if session.used_timer
    }
    completed = [node for node in nodes if node.completed]
    with_timer = [node for node in completed if node.id in with_timer_ids]
    without_timer = [node for node in completed if node.id not in with_timer_ids]
    focus_by_node: dict[str, int] = defaultdict(int)
    for session in today_sessions:
        focus_by_node[session.node_id] += int(session.focus_secs or 0)
    avg_focus = (
        round(
            sum(focus_by_node.get(node.id, 0) for node in with_timer)
            / len(with_timer)
            / 60
        )
        if with_timer
        else 0
    )
    last_with = sorted(
        with_timer,
        key=lambda node: node.completed_at or datetime.min,
        reverse=True,
    )[:5]
    total_completed = len(with_timer) + len(without_timer)
    return TimerImpactOut(
        with_timer_count=len(with_timer),
        without_timer_count=len(without_timer),
        total_completed=total_completed,
        adoption_pct=round(len(with_timer) / total_completed * 100)
        if total_completed
        else 0,
        avg_focus_mins=avg_focus,
        last_with_timer=[
            TimerImpactTaskOut(
                node_id=node.id,
                title=node.title,
                module_type=node.module_type,
                timer_mins=round(focus_by_node.get(node.id, 0) / 60),
                completed_at=node.completed_at,
            )
            for node in last_with
        ],
    )


def correlation(db: Session, user: User) -> CorrelationResponse:
    exceptions = ExceptionRepository.list_for_user(db, user.id)
    scores = {
        row.logical_date: row for row in _global_score_rows(db, user)
    }
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "total": 0.0,
            "high": 0.0,
            "low": 0.0,
            "blocked": 0.0,
            "count": 0.0,
        }
    )
    for exception in exceptions:
        day = exception.logical_date
        bucket = grouped[day]
        bucket["count"] += 1
        if exception.start_time and exception.end_time:
            minutes = (exception.end_time - exception.start_time).total_seconds() / 60
            if minutes > 0:
                bucket["total"] += minutes
                if exception.impact.value == "Alta":
                    bucket["high"] += minutes
                else:
                    bucket["low"] += minutes
        bucket["blocked"] += float(exception.affected_hours or 0)

    days: list[CorrelationDayOut] = []
    for day in sorted(grouped):
        row = scores.get(day)
        bucket = grouped[day]
        days.append(
            CorrelationDayOut(
                date=day,
                score=row.score if row else 0,
                penalty=row.penalty if row else 0,
                total_minutes=round(bucket["total"], 1),
                high_minutes=round(bucket["high"], 1),
                low_minutes=round(bucket["low"], 1),
                blocked_hours=round(bucket["blocked"], 1),
                exception_count=int(bucket["count"]),
            )
        )

    suggestions: list[str] = []
    high_count = sum(1 for exception in exceptions if exception.impact.value == "Alta")
    if high_count > 0 and len(exceptions) > 3:
        suggestions.append(
            "⚠️ Tienes varias excepciones de alto impacto. Considera bloquear "
            "distracciones durante tus bloques de enfoque."
        )
    area_counts: dict[str, int] = defaultdict(int)
    for exception in exceptions:
        area_counts[exception.area.value if exception.area else "General"] += 1
    if area_counts:
        area, count = max(area_counts.items(), key=lambda item: item[1])
        if count >= 3:
            suggestions.append(
                f'📌 El área "{area}" concentra varias excepciones. Enfoca tus '
                "rutinas en reducir distracciones relacionadas."
            )
    if not exceptions:
        suggestions.append(
            "Aún no hay excepciones registradas. Sigue así y protege tus bloques "
            "de enfoque."
        )
    return CorrelationResponse(
        days=days,
        suggestions=suggestions,
        total_exceptions=len(exceptions),
        high_impact_exceptions=high_count,
    )


def categories(db: Session, user: User, *, workspace_id: str | None = None) -> CategoriesResponse:
    workspace = tree_service.get_workspace(db, user, workspace_id)
    nodes = NodeRepository.list_all(
        db,
        user.id,
        workspace_id=workspace.id,
        module_type=ModuleType.ROUTINES,
        include_archived=False,
    )
    roots = [node for node in nodes if node.parent_id is None]
    result: list[CategoryOut] = []
    for category in RoutineCategory:
        group = [node for node in roots if node.routine_category == category]
        total = len(group)
        completed = sum(1 for node in group if node.completed)
        result.append(
            CategoryOut(
                category=category,
                total=total,
                completed=completed,
                pct=round(completed / total * 100) if total else 0,
                css_var=f"--cat-{category.value.lower()}",
            )
        )
    return CategoriesResponse(categories=result, workspace_id=workspace.id)


def objectives_history(
    db: Session, user: User, *, workspace_id: str | None = None
) -> ObjectiveHistoryChartResponse:
    workspace = tree_service.get_workspace(db, user, workspace_id)
    objectives = ObjectiveRepository.list_for_user(
        db, user.id, workspace_id=workspace.id
    )
    all_dates: set[str] = set()
    snapshots_by_objective: dict[str, list[Any]] = {}
    for objective in objectives:
        snapshots = ObjectiveRepository.list_snapshots(db, user.id, objective.id)
        snapshots_by_objective[objective.id] = snapshots
        all_dates.update(snapshot.logical_date for snapshot in snapshots)
    labels = sorted(all_dates)
    colors = ["#4f46e5", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6"]
    datasets: list[ObjectiveHistoryDataset] = []
    for index, objective in enumerate(objectives):
        snapshots = snapshots_by_objective[objective.id]
        if not snapshots:
            continue
        data: list[float | None] = []
        for label in labels:
            past = [snapshot for snapshot in snapshots if snapshot.logical_date <= label]
            data.append(float(past[-1].pct) if past else None)
        datasets.append(
            ObjectiveHistoryDataset(
                label=objective.title,
                objective_id=objective.id,
                data=data,
                span_gaps=True,
            )
        )
    # El color no forma parte del DTO, se expone en un atributo extra para el JS.
    return ObjectiveHistoryChartResponse(labels=labels, datasets=datasets)


def objective_history_map(
    db: Session, user: User, *, workspace_id: str | None = None
) -> dict[str, list[ObjectivePointOut]]:
    workspace = tree_service.get_workspace(db, user, workspace_id)
    objectives = ObjectiveRepository.list_for_user(
        db, user.id, workspace_id=workspace.id
    )
    result: dict[str, list[ObjectivePointOut]] = {}
    for objective in objectives:
        result[objective.id] = [
            ObjectivePointOut(
                date=snapshot.logical_date,
                pct=float(snapshot.pct),
                done=snapshot.done,
                total=snapshot.total,
            )
            for snapshot in ObjectiveRepository.list_snapshots(
                db, user.id, objective.id
            )
        ]
    return result


def _history_tasks(raw: list[dict[str, Any]]) -> list[HistoryTaskOut]:
    return [
        HistoryTaskOut(
            id=item.get("id"),
            title=item.get("title", ""),
            completed=bool(item.get("completed")),
            parent_title=item.get("parent_title"),
            workspace=item.get("workspace"),
        )
        for item in raw
        if isinstance(item, dict)
    ]


def _history_exceptions(raw: list[dict[str, Any]]) -> list[HistoryExceptionOut]:
    result: list[HistoryExceptionOut] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = item.get("start_time") or item.get("startTime")
        end = item.get("end_time") or item.get("endTime")
        result.append(
            HistoryExceptionOut(
                id=item.get("id"),
                title=item.get("title", ""),
                impact=item.get("impact", "Leve"),
                area=item.get("area"),
                start_time=datetime.fromisoformat(start) if start else None,
                end_time=datetime.fromisoformat(end) if end else None,
            )
        )
    return result


def history(
    db: Session,
    user: User,
    *,
    period: str = "week",
    limit: int = 30,
    offset: int = 0,
    workspace_id: str | None = None,
) -> HistoryResponse:
    """Historial detallado con fallback a datos legacy (solo scores/logros)."""

    score_rows = _global_score_rows(db, user)
    scores = {row.logical_date: row for row in score_rows}
    snapshots = {
        snapshot.logical_date: snapshot
        for snapshot in HistoryRepository.list_snapshots(
            db, user.id, scope_key="global"
        )
    }
    exceptions = ExceptionRepository.list_for_user(db, user.id)
    achievements = AchievementRepository.all_for_user(db, user.id)
    exception_days = {exception.logical_date for exception in exceptions}
    dates = sorted(set(scores) | set(snapshots) | exception_days)
    if not dates:
        return HistoryResponse(
            items=[], total=0, limit=limit, offset=offset, period=period
        )

    achievements_by_day: dict[str, list[Achievement]] = defaultdict(list)
    for achievement in achievements:
        day = iso_to_logical_date(
            achievement.completed_at, user.logical_cutoff_hour
        )
        if day:
            achievements_by_day[day].append(achievement)

    days: list[HistoryDayOut] = []
    for day in dates:
        snapshot = snapshots.get(day)
        score_row = scores.get(day)
        if snapshot is not None:
            day_out = HistoryDayOut(
                date=day,
                score=snapshot.score,
                habits=_history_tasks(snapshot.habits),
                routines=_history_tasks(snapshot.routines),
                backlog=_history_tasks(snapshot.backlog),
                exceptions=_history_exceptions(snapshot.exceptions),
                achievements=[
                    HistoryTaskOut(
                        id=item.id,
                        title=item.title,
                        completed=True,
                        workspace=None,
                    )
                    for item in achievements_by_day.get(day, [])
                ],
                fallback=False,
            )
        else:
            day_out = HistoryDayOut(
                date=day,
                score=score_row.score if score_row else None,
                habits=[],
                routines=[],
                backlog=[],
                exceptions=[
                    HistoryExceptionOut(
                        id=exception.id,
                        title=exception.title,
                        impact=exception.impact.value,
                        area=exception.area.value if exception.area else None,
                        start_time=exception.start_time,
                        end_time=exception.end_time,
                    )
                    for exception in exceptions
                    if exception.logical_date == day
                ],
                achievements=[
                    HistoryTaskOut(
                        id=item.id,
                        title=item.title,
                        completed=True,
                        workspace=None,
                    )
                    for item in achievements_by_day.get(day, [])
                ],
                fallback=True,
            )
        total_tasks = (
            len(day_out.habits) + len(day_out.routines) + len(day_out.backlog)
        )
        completed_tasks = sum(
            1
            for item in [*day_out.habits, *day_out.routines, *day_out.backlog]
            if item.completed
        )
        day_out.summary = {
            "total": total_tasks,
            "completed": completed_tasks,
            "exceptions": len(day_out.exceptions),
        }
        days.append(day_out)

    buckets: dict[str, list[HistoryDayOut]] = defaultdict(list)
    for day in days:
        buckets[period_key_for_date(day.date, period)].append(day)

    items: list[HistoryBucketOut] = []
    for key in sorted(buckets, reverse=True):
        group = sorted(buckets[key], key=lambda item: item.date)
        title, subtitle = period_label(key, period)
        score_values = [
            float(item.score) for item in group if item.score is not None
        ]
        completed = sum(item.summary.get("completed", 0) for item in group)
        total = sum(item.summary.get("total", 0) for item in group)
        fuga = 0
        exc_count = 0
        for item in group:
            exc_count += len(item.exceptions)
            for exception in item.exceptions:
                if exception.start_time and exception.end_time:
                    delta = (
                        exception.end_time - exception.start_time
                    ).total_seconds() / 60
                    if delta > 0:
                        fuga += delta
        items.append(
            HistoryBucketOut(
                key=key,
                period=period,
                title=title,
                subtitle=subtitle,
                score_avg=round(average(score_values)) if score_values else None,
                days_active=len(score_values),
                days_total=len(group),
                completed=completed,
                total=total,
                completion=round(completed / total * 100) if total else 0,
                fuga=round(fuga),
                exc_count=exc_count,
                days=group,
            )
        )

    total_items = len(items)
    page = items[offset : offset + limit]
    return HistoryResponse(
        items=page,
        total=total_items,
        limit=limit,
        offset=offset,
        period=period,
        has_more=offset + limit < total_items,
    )


def txt_report(db: Session, user: User) -> str:
    today = logical_today(user)
    stats = global_stats(db, user)
    achievements = AchievementRepository.all_for_user(db, user.id)
    exceptions = ExceptionRepository.list_for_user(db, user.id)
    lines = [f"INFORME DE PRODUCTIVIDAD - {today}", ""]
    if stats.dias_totales:
        lines.append(f"Score promedio: {stats.score_promedio_global}/100")
        lines.append(f"Días registrados: {stats.dias_totales}")
    else:
        lines.append("Aún no hay datos de score.")
    lines.append("")
    if achievements:
        lines.append(f"LOGROS DEFINITIVOS ({len(achievements)}):")
        for achievement in achievements[:10]:
            day = iso_to_logical_date(
                achievement.completed_at, user.logical_cutoff_hour
            )
            timer = (
                f" - {achievement.timer_mins}min enfoque"
                if achievement.timer_mins
                else ""
            )
            lines.append(f"- {achievement.title} ({day or 'sin fecha'}){timer}")
    else:
        lines.append("Sin logros definitivos.")
    lines.append("")
    if exceptions:
        lines.append(f"EXCEPCIONES ({len(exceptions)} en total):")
        grouped: dict[str, dict[str, Any]] = {}
        for exception in exceptions:
            item = grouped.setdefault(
                exception.title,
                {"count": 0, "mins": 0.0, "impact": exception.impact.value},
            )
            item["count"] += 1
            if exception.start_time and exception.end_time:
                minutes = (
                    exception.end_time - exception.start_time
                ).total_seconds() / 60
                if minutes > 0:
                    item["mins"] += minutes
        for title, data in sorted(
            grouped.items(), key=lambda pair: pair[1]["mins"], reverse=True
        ):
            lines.append(
                f"- {title}: {data['count']} veces, "
                f"{round(data['mins'])}min perdidos (Impacto {data['impact']})"
            )
    else:
        lines.append("Sin excepciones registradas.")
    lines.append("")
    lines.append("SUGERENCIAS:")
    if stats.score_promedio_global >= 80:
        lines.append("- ¡Excelente productividad! Mantén tus rutinas.")
    elif stats.score_promedio_global >= 50:
        lines.append(
            "- Buen progreso. Identifica y reduce excepciones de alto impacto."
        )
    elif stats.dias_totales:
        lines.append(
            "- Tu score es bajo. Considera revisar tus hábitos y bloquear "
            "distracciones."
        )
    high = sum(1 for exception in exceptions if exception.impact.value == "Alta")
    if high:
        lines.append(
            f"- Tienes {high} excepción(es) de alto impacto. Prioriza eliminar "
            "esas fugas."
        )
    return "\n".join(lines) + "\n"


def year_countdown(user: User) -> dict[str, Any]:
    now = datetime.now()
    year = now.year
    start = datetime.combine(date(year, 1, 1), time.min)
    end = datetime.combine(date(year + 1, 1, 1), time.min)
    total = (end - start).total_seconds()
    passed = max(0.0, min((now - start).total_seconds(), total))
    percent = passed / total * 100 if total else 0.0
    remaining = max(0, int(-(-(total - passed) // 86400)))
    return {
        "year": year,
        "percent": round(percent, 1),
        "days_remaining": remaining,
        "label": f"⏳ {year}: {percent:.1f}% ({remaining} días rest.)",
    }


def bootstrap(db: Session, user: User) -> BootstrapResponse:
    from app.services.reset_service import ensure_daily_reset

    ensure_daily_reset(db, user)
    workspace = tree_service.get_current_workspace(db, user)
    today = logical_today(user)
    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    nodes = {
        module.value: tree_service.serialize_forest(
            db,
            user,
            logical_date=today,
            workspace_id=workspace.id,
            module_type=module,
        )
        for module in ModuleType
    }
    schedule = [
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
    exceptions = [
        _exception_out(db, user, exception)
        for exception in ExceptionRepository.list_for_date(db, user.id, today)
        if exception.workspace_id == workspace.id
    ]
    objectives = [
        tree_service.compute_objective_progress(db, user, objective)
        for objective in ObjectiveRepository.list_for_user(
            db, user.id, workspace_id=workspace.id
        )
    ]
    achievements = AchievementRepository.list(db, user.id, limit=25)
    achievement_total = AchievementRepository.count(db, user.id)
    names = {item.id: item.name for item in workspaces}
    score_history = {
        row.logical_date: _row_to_score_out(row)
        for row in HistoryRepository.list_scores(
            db, user.id, scope_key=workspace.id
        )
    }
    scores_by_workspace: dict[str, dict[str, ScoreOut]] = {}
    for item in workspaces:
        scores_by_workspace[item.id] = {
            row.logical_date: _row_to_score_out(row)
            for row in HistoryRepository.list_scores(
                db, user.id, scope_key=item.id
            )
        }
    scores_by_workspace["global"] = {
        row.logical_date: _row_to_score_out(row)
        for row in HistoryRepository.list_scores(db, user.id, scope_key="global")
    }
    from app.services.auth_service import serialize_user

    return BootstrapResponse(
        user=serialize_user(user),
        workspaces=[
            WorkspaceOut(
                id=item.id,
                name=item.name,
                is_default=item.is_default,
                created_at=item.created_at,
            )
            for item in workspaces
        ],
        current_workspace_id=workspace.id,
        logical_date=today,
        nodes=nodes,
        schedule=schedule,
        exceptions=exceptions,
        objectives=objectives,
        achievements=[
            AchievementOut(
                id=item.id,
                source_id=item.source_id,
                node_id=item.node_id,
                module_type=item.module_type,
                title=item.title,
                completed_at=item.completed_at,
                timer_mins=item.timer_mins,
                objective_id=item.objective_id,
                workspace_id=item.workspace_id,
                workspace_name=names.get(item.workspace_id or ""),
                is_live=False,
            )
            for item in achievements
        ],
        achievement_total=achievement_total,
        score_history=score_history,
        scores_by_workspace=scores_by_workspace,
        objective_history=objective_history_map(
            db, user, workspace_id=workspace.id
        ),
        today_score=today_score(db, user),
        global_stats=global_stats(db, user),
        schema_version=settings.schema_version,
        year_countdown=year_countdown(user),
    )


def _exception_out(db: Session, user: User, exception: TimeException) -> ExceptionOut:
    names = _workspace_name_map(db, user)
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
