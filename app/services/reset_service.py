"""Reset diario lógico, archivado de logros y purga de Backlog."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums import ModuleType, TimerPhase
from app.domain.logical_date import get_logical_date
from app.models.achievement import Achievement
from app.models.exception_log import TimeException
from app.models.history import DailyActivitySnapshot, DailyScoreHistory
from app.models.objective import Objective, ObjectiveHistorySnapshot, ObjectiveTaskLink
from app.models.schedule import DailyScheduleSlot, ScheduleSkip
from app.models.task_node import TaskNode
from app.models.timer import ActiveTimerState, TimerSession
from app.models.user import User, UserPreferences
from app.models.workspace import Workspace
from app.repositories.schedules import ScheduleRepository
from app.repositories.timers import TimerRepository
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services import analytics_service, tree_service


def logical_today(user: User) -> str:
    return get_logical_date(cutoff_hour=user.logical_cutoff_hour)


def _reset_active_timer(db: Session, user: User, today: str) -> None:
    state = TimerRepository.get_active_state(db, user.id)
    if state is None:
        return
    preferences = UserRepository.get_preferences(db, user.id)
    work_min = (
        preferences.pomodoro_work_min if preferences is not None else state.work_min
    ) or 25
    break_min = (
        preferences.pomodoro_break_min
        if preferences is not None
        else state.break_min
    ) or 5
    state.phase = TimerPhase.WORK
    state.total_secs = work_min * 60
    state.remaining_secs = work_min * 60
    state.running = False
    state.started_at = None
    state.cycle_count = 0
    state.focused_secs = 0
    state.work_min = work_min
    state.break_min = break_min
    state.logical_date = today
    db.flush()


def _delete_old_skips(db: Session, user: User, today: str) -> int:
    result = db.execute(
        delete(ScheduleSkip).where(
            ScheduleSkip.user_id == user.id,
            ScheduleSkip.logical_date < today,
        )
    )
    return int(result.rowcount or 0)


def ensure_daily_reset(db: Session, user: User, *, backup: bool = True) -> dict[str, object]:
    """Ejecuta el cambio de día lógico de forma idempotente y atómica.

    El llamador decide cuándo hacer ``commit``. La función solo hace ``flush``
    para que bootstrap y los tests puedan inspeccionar el resultado.
    """

    today = logical_today(user)
    last = user.last_accessed_logical_date
    if last == today:
        return {"reset": False, "logical_date": today}
    if last and last > today:
        # El reloj retrocedió (cambio de zona horaria o ajuste manual). No se
        # destruyen datos: simplemente se realinea el puntero.
        user.last_accessed_logical_date = today
        db.flush()
        return {"reset": False, "logical_date": today, "clock_moved_back": True}

    # 1. Rescatar el tiempo del timer si cruzó la frontera de las 04:00.
    from app.services import timer_service

    timer_service.rescue_running_timer(db, user)

    # 2. Backup de emergencia ANTES de modificar el estado.
    backup_path: str | None = None
    if backup:
        try:
            from app.services import backup_service

            backup_path = str(backup_service.pre_reset_backup(db, user))
        except Exception:  # El backup nunca debe bloquear el reset.
            backup_path = None

    # 3. Cerrar el día anterior: score, detalle y logros definitivos.
    analytics_service.persist_scores(db, user, last)
    analytics_service.persist_activity_snapshots(db, user, last)
    archived = tree_service.archive_completed_achievements(
        db, user, logical_date=last
    )

    # 4. Reiniciar hábitos/rutinas y purgar raíces completas de Backlog.
    reset_count = tree_service.reset_habit_routine_trees(db, user)
    purged_ids = tree_service.archive_and_purge_backlog(db, user)

    # 5. Limpiar agenda: una sola vez y skips viejos.
    ScheduleRepository.delete_non_recurring(db, user.id)
    _delete_old_skips(db, user, today)

    # 6. Rellenar huecos entre el último acceso y hoy (días intermedios).
    filled = analytics_service.infill_missing_days(db, user, last, today)

    # 7. Reiniciar el timer (sin auto-start) y avanzar el puntero.
    _reset_active_timer(db, user, today)
    user.last_accessed_logical_date = today

    # 8. Persistir el día nuevo y snapshots de objetivos.
    tree_service.snapshot_all_objectives(db, user, logical_date=today)
    analytics_service.persist_scores(db, user, today)
    analytics_service.persist_activity_snapshots(db, user, today)
    tree_service.prune_old_timer_sessions(db, user, days=30)
    db.flush()

    return {
        "reset": True,
        "logical_date": today,
        "previous_logical_date": last,
        "archived_achievements": archived,
        "reset_habit_routine_nodes": reset_count,
        "purged_backlog_nodes": len(purged_ids),
        "infilled_days": len(filled),
        "backup_path": backup_path,
    }


def reset_user_data(db: Session, user: User) -> dict[str, int]:
    """Borrado completo de los datos del usuario (botón Reset).

    Mantiene la cuenta y las preferencias, pero recrea los espacios de trabajo
    por defecto. El backup de emergencia se genera antes de tocar nada.
    """

    from app.services import backup_service
    from app.services.auth_service import DEFAULT_WORKSPACES

    backup_service.pre_reset_backup(db, user)

    counts: dict[str, int] = {}
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
        result = db.execute(delete(model).where(model.user_id == user.id))
        counts[model.__tablename__] = int(result.rowcount or 0)
    db.flush()

    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        preferences = UserPreferences(user_id=user.id)
        UserRepository.create_preferences(db, preferences)
    preferences.current_workspace_id = None

    created: list[Workspace] = []
    for index, name in enumerate(DEFAULT_WORKSPACES):
        created.append(
            WorkspaceRepository.create(
                db, user_id=user.id, name=name, is_default=(index == 0)
            )
        )
    preferences.current_workspace_id = created[0].id
    user.last_accessed_logical_date = logical_today(user)
    db.flush()
    counts["workspaces_recreated"] = len(created)
    return counts
