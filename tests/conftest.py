"""Fixtures de prueba con una base SQLite temporal aislada."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

# Debe ejecutarse antes de importar app.core.config.
_TEST_DB = Path(tempfile.gettempdir()) / f"prodpro_test_{uuid.uuid4().hex}.db"
_TEST_BACKUPS = Path(tempfile.gettempdir()) / f"prodpro_test_backups_{uuid.uuid4().hex}"
_TEST_BACKUPS.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-for-productividad-pro"

import pytest
from fastapi.testclient import TestClient

import app.core.config as app_config

app_config.BACKUP_DIR = _TEST_BACKUPS

from app import models  # noqa: F401  (registra el metadata)
from app.core.database import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def register(client: TestClient) -> Callable[..., dict[str, Any]]:
    def _register(username: str = "alice", email: str | None = None) -> dict[str, Any]:
        payload = {
            "username": username,
            "email": email or f"{username}@example.com",
            "password": "Test12345",
        }
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        workspaces = client.get("/api/v1/workspaces", headers=headers)
        assert workspaces.status_code == 200, workspaces.text
        return {
            "token": token,
            "headers": headers,
            "user": data["user"],
            "workspaces": workspaces.json(),
            "workspace_id": workspaces.json()[0]["id"],
        }

    return _register


@pytest.fixture
def create_node(client: TestClient) -> Callable[..., dict[str, Any]]:
    def _create(
        headers: dict[str, str],
        *,
        module_type: str = "habits",
        title: str = "Tarea",
        workspace_id: str | None = None,
        parent_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "module_type": module_type,
            "title": title,
        }
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if parent_id:
            payload["parent_id"] = parent_id
        payload.update(extra)
        response = client.post("/api/v1/nodes", headers=headers, json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _create
