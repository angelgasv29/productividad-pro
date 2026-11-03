"""Acceso a logros definitivos."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import ModuleType
from app.models.achievement import Achievement
from app.repositories.base import get_scoped, scoped


class AchievementRepository:
    @staticmethod
    def _filters(
        user_id: str,
        *,
        workspace_id: str | None,
        module_type: ModuleType | None,
        search: str | None,
        timer_filter: str | None,
    ) -> list:
        conditions = [Achievement.user_id == user_id]
        if workspace_id:
            conditions.append(Achievement.workspace_id == workspace_id)
        if module_type:
            conditions.append(Achievement.module_type == module_type)
        if search:
            conditions.append(Achievement.title.ilike(f"%{search}%"))
        if timer_filter == "with":
            conditions.append(Achievement.timer_mins > 0)
        elif timer_filter == "without":
            conditions.append(Achievement.timer_mins <= 0)
        return conditions

    @staticmethod
    def list(
        db: Session,
        user_id: str,
        *,
        workspace_id: str | None = None,
        module_type: ModuleType | None = None,
        search: str | None = None,
        timer_filter: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[Achievement]:
        stmt = (
            select(Achievement)
            .where(
                *AchievementRepository._filters(
                    user_id,
                    workspace_id=workspace_id,
                    module_type=module_type,
                    search=search,
                    timer_filter=timer_filter,
                )
            )
            .order_by(Achievement.completed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(db.scalars(stmt))

    @staticmethod
    def count(
        db: Session,
        user_id: str,
        *,
        workspace_id: str | None = None,
        module_type: ModuleType | None = None,
        search: str | None = None,
        timer_filter: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Achievement)
            .where(
                *AchievementRepository._filters(
                    user_id,
                    workspace_id=workspace_id,
                    module_type=module_type,
                    search=search,
                    timer_filter=timer_filter,
                )
            )
        )
        return int(db.scalar(stmt) or 0)

    @staticmethod
    def get(db: Session, user_id: str, achievement_id: str) -> Achievement | None:
        return get_scoped(db, Achievement, user_id, achievement_id)

    @staticmethod
    def get_by_source(db: Session, user_id: str, source_id: str) -> Achievement | None:
        return db.scalars(
            select(Achievement).where(
                Achievement.user_id == user_id, Achievement.source_id == source_id
            )
        ).first()

    @staticmethod
    def create(db: Session, achievement: Achievement) -> Achievement:
        db.add(achievement)
        db.flush()
        return achievement

    @staticmethod
    def delete(db: Session, achievement: Achievement) -> None:
        db.delete(achievement)
        db.flush()

    @staticmethod
    def exists_for_node(db: Session, user_id: str, node_id: str) -> bool:
        return (
            db.scalars(
                select(Achievement.id).where(
                    Achievement.user_id == user_id,
                    or_(
                        Achievement.source_id == node_id,
                        Achievement.source_id.like(f"{node_id}_%"),
                    ),
                )
            ).first()
            is not None
        )

    @staticmethod
    def find_for_node(db: Session, user_id: str, node_id: str) -> Achievement | None:
        return db.scalars(
            select(Achievement)
            .where(
                Achievement.user_id == user_id,
                or_(
                    Achievement.source_id == node_id,
                    Achievement.source_id.like(f"{node_id}_%"),
                ),
            )
            .order_by(Achievement.completed_at.desc())
        ).first()

    @staticmethod
    def delete_for_node_sources(db: Session, user_id: str, node_id: str) -> int:
        from sqlalchemy import delete

        result = db.execute(
            delete(Achievement).where(
                Achievement.user_id == user_id,
                or_(
                    Achievement.source_id == node_id,
                    Achievement.source_id.like(f"{node_id}_%"),
                ),
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def list_for_date(
        db: Session, user_id: str, start, end
    ) -> list[Achievement]:
        return list(
            db.scalars(
                select(Achievement)
                .where(
                    Achievement.user_id == user_id,
                    Achievement.completed_at >= start,
                    Achievement.completed_at < end,
                )
                .order_by(Achievement.completed_at)
            )
        )

    @staticmethod
    def all_for_user(db: Session, user_id: str) -> list[Achievement]:
        return list(
            db.scalars(
                scoped(Achievement, user_id).order_by(Achievement.completed_at.desc())
            )
        )
