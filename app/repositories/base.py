"""Helpers de consulta multi-tenant.

Regla de oro: *toda* consulta de datos de usuario recibe ``user_id`` y lo aplica
en el WHERE. Los repositorios nunca exponen listados globales de entidades
privadas.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

T = TypeVar("T")


def scoped(model: type[T], user_id: str) -> Select[tuple[T]]:
    return select(model).where(model.user_id == user_id)  # type: ignore[attr-defined]


def get_scoped(db: Session, model: type[T], user_id: str, entity_id: str) -> T | None:
    return db.scalars(
        select(model).where(
            model.id == entity_id,  # type: ignore[attr-defined]
            model.user_id == user_id,  # type: ignore[attr-defined]
        )
    ).first()


def count_scoped(db: Session, model: type[T], user_id: str, *conditions: Any) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(model).where(
        model.user_id == user_id,  # type: ignore[attr-defined]
        *conditions,
    )
    return int(db.scalar(stmt) or 0)
