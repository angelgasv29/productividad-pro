"""Acceso a objetivos, vínculos únicos y snapshots de progreso."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.objective import Objective, ObjectiveHistorySnapshot, ObjectiveTaskLink
from app.repositories.base import get_scoped, scoped


class ObjectiveRepository:
    @staticmethod
    def list_for_user(
        db: Session, user_id: str, *, workspace_id: str | None = None
    ) -> list[Objective]:
        stmt = scoped(Objective, user_id)
        if workspace_id:
            stmt = stmt.where(Objective.workspace_id == workspace_id)
        stmt = stmt.order_by(Objective.created_at)
        return list(db.scalars(stmt))

    @staticmethod
    def get(db: Session, user_id: str, objective_id: str) -> Objective | None:
        return get_scoped(db, Objective, user_id, objective_id)

    @staticmethod
    def create(db: Session, objective: Objective) -> Objective:
        db.add(objective)
        db.flush()
        return objective

    @staticmethod
    def delete(db: Session, objective: Objective) -> None:
        db.delete(objective)
        db.flush()

    @staticmethod
    def list_links(db: Session, user_id: str, objective_id: str) -> list[ObjectiveTaskLink]:
        return list(
            db.scalars(
                select(ObjectiveTaskLink)
                .where(
                    ObjectiveTaskLink.user_id == user_id,
                    ObjectiveTaskLink.objective_id == objective_id,
                )
                .order_by(ObjectiveTaskLink.created_at)
            )
        )

    @staticmethod
    def get_link_for_node(
        db: Session, user_id: str, node_id: str
    ) -> ObjectiveTaskLink | None:
        return db.scalars(
            select(ObjectiveTaskLink).where(
                ObjectiveTaskLink.user_id == user_id,
                ObjectiveTaskLink.node_id == node_id,
            )
        ).first()

    @staticmethod
    def create_link(db: Session, link: ObjectiveTaskLink) -> ObjectiveTaskLink:
        db.add(link)
        db.flush()
        return link

    @staticmethod
    def delete_link(db: Session, link: ObjectiveTaskLink) -> None:
        db.delete(link)
        db.flush()

    @staticmethod
    def delete_links_for_node(db: Session, user_id: str, node_id: str) -> int:
        from sqlalchemy import delete

        result = db.execute(
            delete(ObjectiveTaskLink).where(
                ObjectiveTaskLink.user_id == user_id,
                ObjectiveTaskLink.node_id == node_id,
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def list_snapshots(
        db: Session, user_id: str, objective_id: str
    ) -> list[ObjectiveHistorySnapshot]:
        return list(
            db.scalars(
                select(ObjectiveHistorySnapshot)
                .where(
                    ObjectiveHistorySnapshot.user_id == user_id,
                    ObjectiveHistorySnapshot.objective_id == objective_id,
                )
                .order_by(ObjectiveHistorySnapshot.logical_date)
            )
        )

    @staticmethod
    def get_snapshot(
        db: Session, user_id: str, objective_id: str, logical_date: str
    ) -> ObjectiveHistorySnapshot | None:
        return db.scalars(
            select(ObjectiveHistorySnapshot).where(
                ObjectiveHistorySnapshot.user_id == user_id,
                ObjectiveHistorySnapshot.objective_id == objective_id,
                ObjectiveHistorySnapshot.logical_date == logical_date,
            )
        ).first()

    @staticmethod
    def upsert_snapshot(
        db: Session,
        *,
        user_id: str,
        objective_id: str,
        logical_date: str,
        pct: float,
        done: int,
        total: int,
    ) -> ObjectiveHistorySnapshot:
        snapshot = ObjectiveRepository.get_snapshot(
            db, user_id, objective_id, logical_date
        )
        if snapshot is None:
            snapshot = ObjectiveHistorySnapshot(
                user_id=user_id,
                objective_id=objective_id,
                logical_date=logical_date,
                pct=pct,
                done=done,
                total=total,
            )
            db.add(snapshot)
        else:
            snapshot.pct = pct
            snapshot.done = done
            snapshot.total = total
        db.flush()
        return snapshot
