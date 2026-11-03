"""Acceso a usuarios y preferencias."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserPreferences


class UserRepository:
    @staticmethod
    def get_by_id(db: Session, user_id: str) -> User | None:
        return db.get(User, user_id)

    @staticmethod
    def get_by_username(db: Session, username: str) -> User | None:
        return db.scalars(select(User).where(User.username == username)).first()

    @staticmethod
    def get_by_email(db: Session, email: str) -> User | None:
        return db.scalars(select(User).where(User.email == email)).first()

    @staticmethod
    def get_by_username_or_email(db: Session, identifier: str) -> User | None:
        return db.scalars(
            select(User).where(
                (User.username == identifier) | (User.email == identifier)
            )
        ).first()

    @staticmethod
    def create(db: Session, user: User) -> User:
        db.add(user)
        db.flush()
        return user

    @staticmethod
    def get_preferences(db: Session, user_id: str) -> UserPreferences | None:
        return db.scalars(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        ).first()

    @staticmethod
    def create_preferences(db: Session, preferences: UserPreferences) -> UserPreferences:
        db.add(preferences)
        db.flush()
        return preferences

    @staticmethod
    def delete(db: Session, user: User) -> None:
        db.delete(user)
        db.flush()
