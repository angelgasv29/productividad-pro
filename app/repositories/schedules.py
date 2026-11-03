"""Acceso a la línea de tiempo y a los skips de tareas recurrentes."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.schedule import DailyScheduleSlot, ScheduleSkip
from app.repositories.base import get_scoped, scoped


class ScheduleRepository:
    @staticmethod
    def list_for_user(db: Session, user_id: str) -> list[DailyScheduleSlot]:
        return list(
            db.scalars(
                scoped(DailyScheduleSlot, user_id).order_by(
                    DailyScheduleSlot.hour_slot, DailyScheduleSlot.created_at
                )
            )
        )

    @staticmethod
    def list_for_hour(
        db: Session, user_id: str, hour_slot: str
    ) -> list[DailyScheduleSlot]:
        return list(
            db.scalars(
                select(DailyScheduleSlot)
                .where(
                    DailyScheduleSlot.user_id == user_id,
                    DailyScheduleSlot.hour_slot == hour_slot,
                )
                .order_by(DailyScheduleSlot.created_at)
            )
        )

    @staticmethod
    def get(db: Session, user_id: str, slot_id: str) -> DailyScheduleSlot | None:
        return get_scoped(db, DailyScheduleSlot, user_id, slot_id)

    @staticmethod
    def get_for_node_hour(
        db: Session, user_id: str, node_id: str, hour_slot: str
    ) -> DailyScheduleSlot | None:
        return db.scalars(
            select(DailyScheduleSlot).where(
                DailyScheduleSlot.user_id == user_id,
                DailyScheduleSlot.node_id == node_id,
                DailyScheduleSlot.hour_slot == hour_slot,
            )
        ).first()

    @staticmethod
    def create(db: Session, slot: DailyScheduleSlot) -> DailyScheduleSlot:
        db.add(slot)
        db.flush()
        return slot

    @staticmethod
    def delete(db: Session, slot: DailyScheduleSlot) -> None:
        db.delete(slot)
        db.flush()

    @staticmethod
    def delete_for_nodes(db: Session, user_id: str, node_ids: list[str]) -> int:
        if not node_ids:
            return 0
        result = db.execute(
            delete(DailyScheduleSlot).where(
                DailyScheduleSlot.user_id == user_id,
                DailyScheduleSlot.node_id.in_(node_ids),
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def delete_for_node(db: Session, user_id: str, node_id: str) -> int:
        result = db.execute(
            delete(DailyScheduleSlot).where(
                DailyScheduleSlot.user_id == user_id,
                DailyScheduleSlot.node_id == node_id,
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def delete_non_recurring(db: Session, user_id: str) -> int:
        result = db.execute(
            delete(DailyScheduleSlot).where(
                DailyScheduleSlot.user_id == user_id,
                DailyScheduleSlot.recurring.is_(False),
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def create_skip(
        db: Session,
        *,
        user_id: str,
        node_id: str,
        hour_slot: str,
        logical_date: str,
    ) -> ScheduleSkip:
        existing = db.scalars(
            select(ScheduleSkip).where(
                ScheduleSkip.user_id == user_id,
                ScheduleSkip.node_id == node_id,
                ScheduleSkip.hour_slot == hour_slot,
                ScheduleSkip.logical_date == logical_date,
            )
        ).first()
        if existing:
            return existing
        skip = ScheduleSkip(
            user_id=user_id,
            node_id=node_id,
            hour_slot=hour_slot,
            logical_date=logical_date,
        )
        db.add(skip)
        db.flush()
        return skip

    @staticmethod
    def skipped_node_ids(db: Session, user_id: str, logical_date: str) -> set[str]:
        return set(
            db.scalars(
                select(ScheduleSkip.node_id).where(
                    ScheduleSkip.user_id == user_id,
                    ScheduleSkip.logical_date == logical_date,
                )
            )
        )
