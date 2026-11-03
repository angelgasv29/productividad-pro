"""Timer Pro: máquina de estados persistente y guardado parcial resiliente."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.domain.enums import TimerPhase
from app.domain.logical_date import (
    get_logical_date,
    split_interval_by_logical_date,
)
from app.models.task_node import TaskNode
from app.models.timer import ActiveTimerState
from app.models.user import User
from app.repositories.nodes import NodeRepository
from app.repositories.timers import TimerRepository
from app.repositories.users import UserRepository
from app.schemas.timer import TimerRecordRequest, TimerStartRequest, TimerStateOut
from app.services import tree_service


def logical_today(user: User) -> str:
    return get_logical_date(cutoff_hour=user.logical_cutoff_hour)


def _preferences(db: Session, user: User) -> tuple[int, int]:
    preferences = UserRepository.get_preferences(db, user.id)
    if preferences is None:
        return 25, 5
    return preferences.pomodoro_work_min, preferences.pomodoro_break_min


def _get_or_create(db: Session, user: User) -> ActiveTimerState:
    today = logical_today(user)
    state = TimerRepository.get_active_state(db, user.id)
    if state is None:
        work_min, break_min = _preferences(db, user)
        state = ActiveTimerState(
            user_id=user.id,
            phase=TimerPhase.WORK,
            total_secs=work_min * 60,
            remaining_secs=work_min * 60,
            running=False,
            work_min=work_min,
            break_min=break_min,
            logical_date=today,
        )
        db.add(state)
        db.flush()
    return state


def _node_title(db: Session, user: User, node_id: str | None) -> str | None:
    if not node_id:
        return None
    node = NodeRepository.get(db, user.id, node_id)
    return node.title if node is not None else None


def _remaining_now(state: ActiveTimerState, now: datetime | None = None) -> int:
    if not state.running or state.started_at is None:
        return max(0, int(state.remaining_secs))
    current = now or datetime.now()
    elapsed = max(0, int((current - state.started_at).total_seconds()))
    return max(0, int(state.remaining_secs) - elapsed)


def state_out(
    db: Session, user: User, state: ActiveTimerState
) -> TimerStateOut:
    now = datetime.now()
    elapsed = 0
    if state.running and state.started_at is not None:
        elapsed = max(0, int((now - state.started_at).total_seconds()))
    return TimerStateOut(
        phase=state.phase,
        total_secs=int(state.total_secs),
        remaining_secs=_remaining_now(state, now),
        running=bool(state.running),
        cycle_count=int(state.cycle_count),
        focused_secs=int(state.focused_secs),
        work_min=int(state.work_min),
        break_min=int(state.break_min),
        mode=state.mode,
        node_id=state.node_id,
        node_title=_node_title(db, user, state.node_id),
        started_at=state.started_at,
        logical_date=state.logical_date,
        server_now=now,
        elapsed_secs=elapsed,
    )


def _record_interval(
    db: Session,
    user: User,
    node_id: str | None,
    start: datetime,
    end: datetime,
    *,
    cycles: int = 0,
    used_timer: bool = True,
) -> int:
    """Registra un intervalo repartiéndolo entre días lógicos si cruza 04:00."""

    if node_id is None or end <= start:
        return 0
    splits = split_interval_by_logical_date(
        start, end, user.logical_cutoff_hour
    )
    total = 0
    for logical_date, minutes in sorted(splits.items()):
        seconds = int(round(minutes * 60))
        if seconds <= 0:
            continue
        TimerRepository.record(
            db,
            user_id=user.id,
            node_id=node_id,
            logical_date=logical_date,
            seconds=seconds,
            cycles=cycles,
            used_timer=used_timer,
        )
        total += seconds
    return total


def _account_elapsed(
    db: Session,
    user: User,
    state: ActiveTimerState,
    *,
    complete_phase: bool = False,
) -> tuple[int, bool]:
    """Contabiliza el tiempo transcurrido desde ``started_at``.

    Devuelve ``(segundos_registrados, fase_terminada)``. El tiempo se recorta
    al ``remaining_secs`` para que una pestaña olvidada no regale horas.
    """

    if not state.running or state.started_at is None:
        return 0, False
    now = datetime.now()
    elapsed = max(0, int((now - state.started_at).total_seconds()))
    if elapsed <= 0:
        return 0, False
    capped = min(elapsed, max(0, int(state.remaining_secs)))
    phase_finished = capped >= int(state.remaining_secs)
    recorded = 0
    if state.phase == TimerPhase.WORK and state.node_id:
        end = state.started_at + timedelta(seconds=capped)
        recorded = _record_interval(
            db,
            user,
            state.node_id,
            state.started_at,
            end,
            cycles=1 if phase_finished else 0,
        )
    if state.phase == TimerPhase.WORK:
        state.focused_secs = int(state.focused_secs or 0) + capped
    state.remaining_secs = max(0, int(state.remaining_secs) - capped)
    state.started_at = now
    if phase_finished:
        _advance_phase(state)
    db.flush()
    return recorded, phase_finished


def _advance_phase(state: ActiveTimerState) -> None:
    """Pasa a la siguiente fase SIN arrancarla automáticamente."""

    if state.phase == TimerPhase.WORK:
        state.phase = TimerPhase.BREAK
        state.total_secs = max(1, int(state.break_min)) * 60
        state.remaining_secs = state.total_secs
        state.cycle_count = int(state.cycle_count or 0) + 1
    else:
        state.phase = TimerPhase.WORK
        state.total_secs = max(1, int(state.work_min)) * 60
        state.remaining_secs = state.total_secs
    state.running = False
    state.started_at = None
    state.focused_secs = 0


def _advance_if_finished(
    db: Session, user: User, state: ActiveTimerState
) -> bool:
    if not state.running or state.started_at is None:
        return False
    now = datetime.now()
    elapsed = (now - state.started_at).total_seconds()
    if elapsed < int(state.remaining_secs):
        return False
    _account_elapsed(db, user, state, complete_phase=True)
    return True


def _validate_node(db: Session, user: User, node_id: str | None) -> TaskNode | None:
    if node_id is None:
        return None
    node = NodeRepository.get(db, user.id, node_id)
    if node is None:
        raise NotFoundError("La tarea no existe o no te pertenece.")
    children = NodeRepository.children(db, user.id, node.id)
    if children:
        raise ValidationError(
            "Solo puedes vincular tareas hoja (sin subtareas) al temporizador."
        )
    if node.completed:
        raise ValidationError("No puedes vincular una tarea ya completada.")
    return node


def get_state(db: Session, user: User) -> TimerStateOut:
    state = _get_or_create(db, user)
    _advance_if_finished(db, user, state)
    return state_out(db, user, state)


def start(
    db: Session, user: User, data: TimerStartRequest
) -> tuple[TimerStateOut, str]:
    state = _get_or_create(db, user)
    _advance_if_finished(db, user, state)
    if state.running:
        return state_out(db, user, state), "El temporizador ya está en marcha."

    break_ready = (
        data.resume
        and state.phase == TimerPhase.BREAK
        and not state.running
        and int(state.remaining_secs) == int(state.total_secs)
    )
    node = None if break_ready else _validate_node(db, user, data.node_id)

    if break_ready:
        state.running = True
        state.started_at = datetime.now()
        state.mode = data.mode
        state.work_min = data.work_min
        state.break_min = data.break_min
        state.logical_date = logical_today(user)
        db.flush()
        return state_out(db, user, state), "Descanso iniciado."

    can_resume = (
        data.resume
        and state.remaining_secs > 0
        and state.remaining_secs < state.total_secs
    )
    if can_resume:
        state.running = True
        state.started_at = datetime.now()
        state.mode = data.mode
        state.work_min = data.work_min
        state.break_min = data.break_min
        if node is not None:
            state.node_id = node.id
        state.logical_date = logical_today(user)
        db.flush()
        return state_out(db, user, state), "Temporizador reanudado."

    state.mode = data.mode
    state.work_min = data.work_min
    state.break_min = data.break_min
    state.phase = TimerPhase.WORK
    state.total_secs = data.work_min * 60
    state.remaining_secs = state.total_secs
    state.cycle_count = 0
    state.focused_secs = 0
    state.node_id = node.id if node is not None else None
    state.running = True
    state.started_at = datetime.now()
    state.logical_date = logical_today(user)
    db.flush()
    return state_out(db, user, state), "Temporizador iniciado."


def pause(db: Session, user: User) -> tuple[TimerStateOut, str, bool]:
    state = _get_or_create(db, user)
    if not state.running:
        return state_out(db, user, state), "El temporizador ya está pausado.", False
    _, finished = _account_elapsed(db, user, state, complete_phase=True)
    if finished:
        message = (
            "¡Tiempo! Tómate un descanso."
            if state.phase == TimerPhase.BREAK
            else "¡Descanso terminado! Vuelve al trabajo."
        )
        return state_out(db, user, state), message, True
    state.running = False
    state.started_at = None
    db.flush()
    return state_out(db, user, state), "Temporizador pausado.", False


def reset(db: Session, user: User) -> tuple[TimerStateOut, str]:
    state = _get_or_create(db, user)
    if state.running:
        _account_elapsed(db, user, state, complete_phase=False)
    state.phase = TimerPhase.WORK
    state.total_secs = max(1, int(state.work_min)) * 60
    state.remaining_secs = state.total_secs
    state.running = False
    state.started_at = None
    state.cycle_count = 0
    state.focused_secs = 0
    state.logical_date = logical_today(user)
    db.flush()
    return state_out(db, user, state), "Temporizador reiniciado."


def skip(db: Session, user: User) -> tuple[TimerStateOut, str]:
    state = _get_or_create(db, user)
    if state.running:
        _account_elapsed(db, user, state, complete_phase=False)
    _advance_phase(state)
    db.flush()
    return state_out(db, user, state), "Fase saltada. La siguiente no se inicia sola."


def link(db: Session, user: User, node_id: str) -> TimerStateOut:
    node = _validate_node(db, user, node_id)
    state = _get_or_create(db, user)
    state.node_id = node.id if node else None
    db.flush()
    return state_out(db, user, state)


def unlink(db: Session, user: User) -> TimerStateOut:
    state = _get_or_create(db, user)
    if state.running:
        _account_elapsed(db, user, state, complete_phase=False)
        state.running = False
        state.started_at = None
    state.node_id = None
    state.focused_secs = 0
    db.flush()
    return state_out(db, user, state)


def record(
    db: Session, user: User, data: TimerRecordRequest
) -> int:
    node = _validate_node(db, user, data.node_id)
    if node is None:
        raise ValidationError("Debes indicar una tarea válida.")
    today = logical_today(user)
    TimerRepository.record(
        db,
        user_id=user.id,
        node_id=node.id,
        logical_date=today,
        seconds=data.seconds,
        cycles=data.cycles,
        used_timer=data.used_timer,
    )
    return data.seconds


def complete_linked_task(db: Session, user: User) -> tuple[TimerStateOut, str]:
    state = _get_or_create(db, user)
    if state.node_id is None:
        raise ValidationError("No hay una tarea vinculada al temporizador.")
    if state.running:
        _account_elapsed(db, user, state, complete_phase=False)
        state.running = False
        state.started_at = None
    node = NodeRepository.get(db, user.id, state.node_id)
    if node is None:
        raise NotFoundError("La tarea vinculada ya no existe.")
    if node.completed:
        return state_out(db, user, state), "La tarea ya estaba completada."
    tree_service.toggle_node(db, user, node, True)
    title = node.title
    state.node_id = None
    state.focused_secs = 0
    db.flush()
    return state_out(db, user, state), f'"{title}" marcada como completada.'


def rescue_running_timer(db: Session, user: User) -> int:
    """Guarda el tiempo parcial antes de un cambio de día lógico."""

    state = TimerRepository.get_active_state(db, user.id)
    if state is None or not state.running or state.started_at is None:
        return 0
    recorded, _ = _account_elapsed(db, user, state, complete_phase=False)
    state.running = False
    state.started_at = None
    state.focused_secs = 0
    db.flush()
    return recorded


def sync_after_task_change(db: Session, user: User) -> None:
    """Si la tarea vinculada desaparece o se completa, se desvincula."""

    state = TimerRepository.get_active_state(db, user.id)
    if state is None or not state.node_id:
        return
    node = NodeRepository.get(db, user.id, state.node_id)
    if node is None or node.completed:
        state.node_id = None
        db.flush()
