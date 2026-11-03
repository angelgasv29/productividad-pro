"""Acceso al historial de scores y a los snapshots de actividad."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.scoring import ScoreResult
from app.models.history import DailyActivitySnapshot, DailyScoreHistory
from app.repositories.base import scoped


class HistoryRepository:
    @staticmethod
    def get_score(
        db: Session, user_id: str, scope_key: str, logical_date: str
    ) -> DailyScoreHistory | None:
        return db.scalars(
            select(DailyScoreHistory).where(
                DailyScoreHistory.user_id == user_id,
                DailyScoreHistory.scope_key == scope_key,
                DailyScoreHistory.logical_date == logical_date,
            )
        ).first()

    @staticmethod
    def upsert_score(
        db: Session,
        *,
        user_id: str,
        workspace_id: str | None,
        scope_key: str,
        logical_date: str,
        result: ScoreResult,
    ) -> DailyScoreHistory:
        row = HistoryRepository.get_score(db, user_id, scope_key, logical_date)
        if row is None:
            row = DailyScoreHistory(
                user_id=user_id,
                workspace_id=workspace_id,
                scope_key=scope_key,
                logical_date=logical_date,
            )
            db.add(row)
        row.score = result.score
        row.base_score = result.base_score
        row.h_total = result.h_total
        row.h_comp = result.h_comp
        row.r_total = result.r_total
        row.r_comp = result.r_comp
        row.b_total = result.b_total
        row.b_comp = result.b_comp
        row.exc_mins = result.exc_mins
        row.penalty = result.penalty
        row.high_minutes = result.high_minutes
        row.low_minutes = result.low_minutes
        db.flush()
        return row

    @staticmethod
    def update_score_penalty(
        db: Session,
        row: DailyScoreHistory,
        *,
        score: int,
        penalty: int,
        exc_mins: int,
        high_minutes: float,
        low_minutes: float,
    ) -> DailyScoreHistory:
        row.score = score
        row.penalty = penalty
        row.exc_mins = exc_mins
        row.high_minutes = high_minutes
        row.low_minutes = low_minutes
        db.flush()
        return row

    @staticmethod
    def list_scores(
        db: Session,
        user_id: str,
        *,
        scope_key: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[DailyScoreHistory]:
        stmt = scoped(DailyScoreHistory, user_id)
        if scope_key:
            stmt = stmt.where(DailyScoreHistory.scope_key == scope_key)
        if start:
            stmt = stmt.where(DailyScoreHistory.logical_date >= start)
        if end:
            stmt = stmt.where(DailyScoreHistory.logical_date <= end)
        stmt = stmt.order_by(DailyScoreHistory.logical_date)
        return list(db.scalars(stmt))

    @staticmethod
    def get_snapshot(
        db: Session, user_id: str, scope_key: str, logical_date: str
    ) -> DailyActivitySnapshot | None:
        return db.scalars(
            select(DailyActivitySnapshot).where(
                DailyActivitySnapshot.user_id == user_id,
                DailyActivitySnapshot.scope_key == scope_key,
                DailyActivitySnapshot.logical_date == logical_date,
            )
        ).first()

    @staticmethod
    def upsert_snapshot(
        db: Session,
        *,
        user_id: str,
        workspace_id: str | None,
        scope_key: str,
        logical_date: str,
        score: int,
        habits: list[dict[str, Any]],
        routines: list[dict[str, Any]],
        backlog: list[dict[str, Any]],
        exceptions: list[dict[str, Any]],
    ) -> DailyActivitySnapshot:
        row = HistoryRepository.get_snapshot(db, user_id, scope_key, logical_date)
        if row is None:
            row = DailyActivitySnapshot(
                user_id=user_id,
                workspace_id=workspace_id,
                scope_key=scope_key,
                logical_date=logical_date,
            )
            db.add(row)
        row.score = score
        row.habits = habits
        row.routines = routines
        row.backlog = backlog
        row.exceptions = exceptions
        db.flush()
        return row

    @staticmethod
    def list_snapshots(
        db: Session,
        user_id: str,
        *,
        scope_key: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[DailyActivitySnapshot]:
        stmt = scoped(DailyActivitySnapshot, user_id)
        if scope_key:
            stmt = stmt.where(DailyActivitySnapshot.scope_key == scope_key)
        if start:
            stmt = stmt.where(DailyActivitySnapshot.logical_date >= start)
        if end:
            stmt = stmt.where(DailyActivitySnapshot.logical_date <= end)
        stmt = stmt.order_by(DailyActivitySnapshot.logical_date)
        return list(db.scalars(stmt))

    @staticmethod
    def get_snapshot_by_date(
        db: Session, user_id: str, scope_key: str, logical_date: str
    ) -> DailyActivitySnapshot | None:
        return HistoryRepository.get_snapshot(db, user_id, scope_key, logical_date)
