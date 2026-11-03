"""Acceso a las excepciones (rompe-rutinas)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.exception_log import TimeException
from app.repositories.base import get_scoped, scoped


class ExceptionRepository:
    @staticmethod
    def list_for_user(
        db: Session, user_id: str, *, workspace_id: str | None = None
    ) -> list[TimeException]:
        stmt = scoped(TimeException, user_id)
        if workspace_id:
            stmt = stmt.where(TimeException.workspace_id == workspace_id)
        stmt = stmt.order_by(TimeException.start_time.desc())
        return list(db.scalars(stmt))

    @staticmethod
    def list_for_date(db: Session, user_id: str, logical_date: str) -> list[TimeException]:
        return list(
            db.scalars(
                select(TimeException)
                .where(
                    TimeException.user_id == user_id,
                    TimeException.logical_date == logical_date,
                )
                .order_by(TimeException.start_time)
            )
        )

    @staticmethod
    def list_between(
        db: Session, user_id: str, start: str, end: str
    ) -> list[TimeException]:
        return list(
            db.scalars(
                select(TimeException)
                .where(
                    TimeException.user_id == user_id,
                    TimeException.logical_date >= start,
                    TimeException.logical_date <= end,
                )
                .order_by(TimeException.start_time)
            )
        )

    @staticmethod
    def get(db: Session, user_id: str, exception_id: str) -> TimeException | None:
        return get_scoped(db, TimeException, user_id, exception_id)

    @staticmethod
    def create(db: Session, exception: TimeException) -> TimeException:
        db.add(exception)
        db.flush()
        return exception

    @staticmethod
    def delete(db: Session, exception: TimeException) -> None:
        db.delete(exception)
        db.flush()

    @staticmethod
    def count(db: Session, user_id: str) -> int:
        from sqlalchemy import func

        return int(
            db.scalar(
                select(func.count())
                .select_from(TimeException)
                .where(TimeException.user_id == user_id)
            )
            or 0
        )
