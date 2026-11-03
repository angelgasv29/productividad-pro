"""Acceso a sesiones de enfoque y al estado del Timer Pro."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import TimerPhase
from app.models.timer import ActiveTimerState, TimerSession
from app.repositories.base import get_scoped


class TimerRepository:
    @staticmethod
    def get_session(
        db: Session,
        user_id: str,
        node_id: str,
        logical_date: str,
        used_timer: bool,
    ) -> TimerSession | None:
        return db.scalars(
            select(TimerSession).where(
                TimerSession.user_id == user_id,
                TimerSession.node_id == node_id,
                TimerSession.logical_date == logical_date,
                TimerSession.used_timer.is_(used_timer),
            )
        ).first()

    @staticmethod
    def record(
        db: Session,
        *,
        user_id: str,
        node_id: str,
        logical_date: str,
        seconds: int,
        cycles: int | None = None,
        used_timer: bool = True,
    ) -> TimerSession:
        session = TimerRepository.get_session(
            db, user_id, node_id, logical_date, used_timer
        )
        seconds = max(0, int(seconds))
        cycle_increment = (
            (1 if seconds > 0 else 0) if cycles is None else max(0, int(cycles))
        )
        if session is None:
            session = TimerSession(
                user_id=user_id,
                node_id=node_id,
                logical_date=logical_date,
                focus_secs=seconds,
                cycles=cycle_increment,
                used_timer=used_timer,
            )
            db.add(session)
        else:
            session.focus_secs = int(session.focus_secs or 0) + seconds
            session.cycles = int(session.cycles or 0) + cycle_increment
        db.flush()
        return session

    @staticmethod
    def list_for_node(db: Session, user_id: str, node_id: str) -> list[TimerSession]:
        return list(
            db.scalars(
                select(TimerSession).where(
                    TimerSession.user_id == user_id, TimerSession.node_id == node_id
                )
            )
        )

    @staticmethod
    def list_for_date(db: Session, user_id: str, logical_date: str) -> list[TimerSession]:
        return list(
            db.scalars(
                select(TimerSession).where(
                    TimerSession.user_id == user_id,
                    TimerSession.logical_date == logical_date,
                )
            )
        )

    @staticmethod
    def list_for_nodes_date(
        db: Session, user_id: str, node_ids: list[str], logical_date: str
    ) -> list[TimerSession]:
        if not node_ids:
            return []
        return list(
            db.scalars(
                select(TimerSession).where(
                    TimerSession.user_id == user_id,
                    TimerSession.node_id.in_(node_ids),
                    TimerSession.logical_date == logical_date,
                )
            )
        )

    @staticmethod
    def list_for_nodes(db: Session, user_id: str, node_ids: list[str]) -> list[TimerSession]:
        if not node_ids:
            return []
        return list(
            db.scalars(
                select(TimerSession).where(
                    TimerSession.user_id == user_id,
                    TimerSession.node_id.in_(node_ids),
                )
            )
        )

    @staticmethod
    def delete_for_node(db: Session, user_id: str, node_id: str) -> int:
        from sqlalchemy import delete

        result = db.execute(
            delete(TimerSession).where(
                TimerSession.user_id == user_id, TimerSession.node_id == node_id
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def delete_old_sessions(db: Session, user_id: str, cutoff_date: str) -> int:
        from sqlalchemy import delete

        result = db.execute(
            delete(TimerSession).where(
                TimerSession.user_id == user_id,
                TimerSession.logical_date < cutoff_date,
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def get_active_state(db: Session, user_id: str) -> ActiveTimerState | None:
        return db.scalars(
            select(ActiveTimerState).where(ActiveTimerState.user_id == user_id)
        ).first()

    @staticmethod
    def create_default_state(
        db: Session, user_id: str, logical_date: str
    ) -> ActiveTimerState:
        state = ActiveTimerState(
            user_id=user_id,
            phase=TimerPhase.WORK,
            total_secs=25 * 60,
            remaining_secs=25 * 60,
            running=False,
            work_min=25,
            break_min=5,
            logical_date=logical_date,
        )
        db.add(state)
        db.flush()
        return state

    @staticmethod
    def delete_state(db: Session, state: ActiveTimerState) -> None:
        db.delete(state)
        db.flush()

    @staticmethod
    def get_state_or_default(
        db: Session, user_id: str, logical_date: str
    ) -> ActiveTimerState:
        state = TimerRepository.get_active_state(db, user_id)
        if state is None:
            state = TimerRepository.create_default_state(db, user_id, logical_date)
        return state
