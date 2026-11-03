"""Ponderación dinámica, penalizaciones y separación de scores por ámbito."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.scoring import (
    ModuleProgress,
    compute_score,
    compute_streaks,
    dynamic_weights,
    heatmap_level,
    penalty_for_minutes,
    score_from_stored_base,
    split_exception_penalty,
)
from app.models.history import DailyScoreHistory


def test_all_empty_modules_score_zero() -> None:
    result = compute_score(ModuleProgress(), ModuleProgress(), ModuleProgress())
    assert result.score == 0
    assert result.base_score == 0.0
    assert result.weights == {}
    assert dynamic_weights(
        {
            "habits": ModuleProgress(),
            "routines": ModuleProgress(),
            "backlog": ModuleProgress(),
        }
    ) == {}


def test_dynamic_weights_redistribute_empty_modules() -> None:
    result = compute_score(
        habits=ModuleProgress(total=1, completed=1),
        routines=ModuleProgress(total=2, completed=1),
        backlog=ModuleProgress(),
    )
    assert result.weights == {
        "habits": pytest.approx(0.5),
        "routines": pytest.approx(0.5),
    }
    assert result.base_score == pytest.approx(75.0)
    assert result.score == 75


def test_single_active_module_gets_full_weight() -> None:
    result = compute_score(
        habits=ModuleProgress(total=2, completed=1),
        routines=ModuleProgress(),
        backlog=ModuleProgress(),
    )
    assert result.weights == {"habits": pytest.approx(1.0)}
    assert result.score == 50


def test_exception_penalties_and_score_clamp() -> None:
    assert penalty_for_minutes(30, "Alta") == pytest.approx(5.0)
    assert penalty_for_minutes(30, "Leve") == pytest.approx(2.0)
    assert penalty_for_minutes(0, "Alta") == 0.0

    result = compute_score(
        ModuleProgress(total=1, completed=1),
        ModuleProgress(),
        ModuleProgress(),
        high_minutes=60,
        low_minutes=60,
    )
    assert result.penalty == 14
    assert result.score == 86

    crushed = compute_score(
        ModuleProgress(total=1, completed=0),
        ModuleProgress(),
        ModuleProgress(),
        high_minutes=600,
    )
    assert crushed.score == 0


def test_exception_split_across_logical_cutoff() -> None:
    splits = split_exception_penalty(
        datetime(2026, 1, 10, 3, 0),
        datetime(2026, 1, 10, 5, 0),
        "Alta",
        cutoff_hour=4,
    )
    by_date = {split.logical_date: split for split in splits}
    assert set(by_date) == {"2026-01-09", "2026-01-10"}
    assert by_date["2026-01-09"].minutes == pytest.approx(60.0)
    assert by_date["2026-01-10"].minutes == pytest.approx(60.0)
    assert by_date["2026-01-09"].penalty == pytest.approx(10.0)
    assert by_date["2026-01-10"].penalty == pytest.approx(10.0)


def test_heatmap_levels_and_streaks() -> None:
    assert heatmap_level(None) == 0
    assert heatmap_level(0) == 0
    assert heatmap_level(0.9) == 0
    assert heatmap_level(1) == 1
    assert heatmap_level(29.9) == 1
    assert heatmap_level(30) == 2
    assert heatmap_level(49.9) == 2
    assert heatmap_level(50) == 3
    assert heatmap_level(69.9) == 3
    assert heatmap_level(70) == 4
    assert heatmap_level(89.9) == 4
    assert heatmap_level(90) == 5

    current, maximum = compute_streaks(
        {
            "2026-01-01": 60,
            "2026-01-02": 59,
            "2026-01-03": 80,
            "2026-01-04": 90,
            "2026-01-05": 100,
        }
    )
    assert current == 3
    assert maximum == 3


def test_score_from_stored_base_reverses_penalty() -> None:
    score, penalty = score_from_stored_base(100.0, 30.0, 0.0)
    assert score == 95
    assert penalty == 5

    score, penalty = score_from_stored_base(10.0, 600.0, 600.0)
    assert score == 0
    assert penalty == 140


def test_workspace_and_global_scores_do_not_overwrite_each_other(
    client: TestClient, register, create_node, db
) -> None:
    user = register("scores")
    headers = user["headers"]
    general = user["workspace_id"]
    trabajo = next(
        workspace
        for workspace in user["workspaces"]
        if workspace["name"] == "Trabajo"
    )["id"]

    habit = create_node(
        headers,
        module_type="habits",
        title="Hábito de General",
        workspace_id=general,
    )
    routine = create_node(
        headers,
        module_type="routines",
        title="Rutina de Trabajo",
        workspace_id=trabajo,
    )

    response = client.post(
        f"/api/v1/nodes/{habit['id']}/toggle",
        headers=headers,
        json={"completed": True},
    )
    assert response.status_code == 200, response.text

    # General: solo su hábito activo (100). Global: hábito 1/1 + rutina 0/1.
    score = client.get("/api/v1/analytics/today-score", headers=headers)
    assert score.status_code == 200, score.text
    payload = score.json()
    assert payload["workspace_id"] == general
    assert payload["score"] == 100
    assert payload["breakdown"]["h_total"] == 1
    assert payload["breakdown"]["r_total"] == 0
    assert payload["global_score"]["score"] == 50
    assert payload["global_score"]["h_comp"] == 1
    assert payload["global_score"]["r_comp"] == 0

    # Cambiar de espacio no altera el score global.
    response = client.post(
        f"/api/v1/workspaces/{trabajo}/select", headers=headers
    )
    assert response.status_code == 200, response.text
    score = client.get("/api/v1/analytics/today-score", headers=headers)
    payload = score.json()
    assert payload["workspace_id"] == trabajo
    assert payload["score"] == 0
    assert payload["global_score"]["score"] == 50

    # Completar la rutina de Trabajo no pisa el score de General.
    response = client.post(
        f"/api/v1/nodes/{routine['id']}/toggle",
        headers=headers,
        json={"completed": True},
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    today = payload["logical_date"]
    rows = {
        row.scope_key: row
        for row in db.scalars(
            select(DailyScoreHistory).where(
                DailyScoreHistory.user_id == user["user"]["id"],
                DailyScoreHistory.logical_date == today,
            )
        )
    }
    assert rows[general].score == 100
    assert rows[trabajo].score == 100
    assert rows["global"].score == 100

    # Desmarcar el hábito solo afecta a General y al global.
    response = client.post(
        f"/api/v1/nodes/{habit['id']}/toggle",
        headers=headers,
        json={"completed": False},
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    rows = {
        row.scope_key: row
        for row in db.scalars(
            select(DailyScoreHistory).where(
                DailyScoreHistory.user_id == user["user"]["id"],
                DailyScoreHistory.logical_date == today,
            )
        )
    }
    assert rows[general].score == 0
    assert rows[trabajo].score == 100
    assert rows["global"].score == 50
