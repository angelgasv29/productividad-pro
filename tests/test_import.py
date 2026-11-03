"""Importación de backups legacy y reemplazo atómico de datos."""

from __future__ import annotations

import json
from datetime import timedelta

from fastapi.testclient import TestClient

from app.domain.logical_date import get_logical_date, parse_logical_date


def _legacy_payload() -> dict:
    today = get_logical_date()
    yesterday = (parse_logical_date(today) - timedelta(days=1)).isoformat()

    return {
        "schemaVersion": 3,
        "preferences": {
            "pomodoroWorkMin": 50,
            "pomodoroBreakMin": 10,
            "notificationsEnabled": True,
        },
        "workspaces": ["General", "Trabajo"],
        "currentWorkspace": "Trabajo",
        "lastAccessedDate": today,
        "habits": [
            {
                "id": "h1",
                "title": "Meditar",
                "completed": True,
                "workspace": "General",
                "completedAt": f"{yesterday}T08:00:00",
                "timerSessions": [
                    {
                        "date": yesterday,
                        "focusSecs": 600,
                        "cycles": 1,
                        "usedTimer": True,
                    }
                ],
            },
            {
                "id": "h2",
                "title": "Leer",
                "completed": False,
                "workspace": "Trabajo",
                "children": [
                    {
                        "id": "h2c",
                        "title": "Capítulo 1",
                        "completed": True,
                        "timerSessions": [
                            {
                                "date": today,
                                "focusSecs": 300,
                                "cycles": 1,
                                "usedTimer": True,
                            }
                        ],
                    }
                ],
            },
        ],
        "routines": [
            {
                "id": "r1",
                "title": "Cocinar",
                "completed": False,
                "workspace": "Trabajo",
                "category": "Comer",
            }
        ],
        "backlog": [
            {
                "id": "b1",
                "title": "Preparar informe",
                "completed": False,
                "workspace": "Trabajo",
                "priority": "Alta",
                "tag": "Trabajo",
            }
        ],
        "dailySchedule": {
            "04:00": [
                "h1",
                {
                    "id": "b1",
                    "recurring": False,
                    "assignedLogicalDate": today,
                },
            ],
            "05:00": [
                {
                    "id": "h2",
                    "recurring": True,
                    "scheduleDays": [1, 2, 3, 4, 5],
                }
            ],
        },
        "exceptions": [
            {
                "id": "e1",
                "title": "Corte de luz",
                "impact": "Alta",
                "area": "General",
                "note": "Sin electricidad",
                "startTime": f"{today}T10:00:00",
                "endTime": f"{today}T11:00:00",
                "date": today,
                "affectedHours": [10],
                "blockedTaskIds": ["b1"],
                "workspace": "Trabajo",
            }
        ],
        "objectives": [
            {
                "id": "o1",
                "title": "Aprender Python",
                "description": "Curso completo",
                "horizon": "Mensual",
                "startDate": (parse_logical_date(today) - timedelta(days=5)).isoformat(),
                "endDate": today,
                "workspace": "Trabajo",
                "linkedItems": ["h2c", "b1"],
            }
        ],
        "achievements": [
            {
                "id": "a1",
                "nodeId": "h1",
                "sourceId": f"h1_{yesterday}",
                "title": "Meditar",
                "moduleType": "habits",
                "completedAt": f"{yesterday}T08:00:00",
                "timerMins": 10,
                "workspace": "General",
                "objectiveId": "o1",
            }
        ],
        "scoreHistory": {
            today: {
                "hTotal": 2,
                "hComp": 1,
                "rTotal": 1,
                "rComp": 0,
                "bTotal": 1,
                "bComp": 0,
                "excMins": 60,
                "penalty": 10,
                "score": 40,
            }
        },
        "scoreHistoryByWs": {
            "Trabajo": {
                today: {
                    "hTotal": 1,
                    "hComp": 0,
                    "rTotal": 1,
                    "rComp": 0,
                    "bTotal": 1,
                    "bComp": 0,
                    "excMins": 60,
                    "penalty": 10,
                    "score": 0,
                }
            }
        },
        "dailyLog": {
            today: {
                "date": today,
                "score": 40,
                "habits": [
                    {"id": "h2c", "title": "Capítulo 1", "completed": True}
                ],
                "routines": [],
                "backlog": [],
                "exceptions": [
                    {
                        "id": "e1",
                        "title": "Corte de luz",
                        "impact": "Alta",
                        "start_time": f"{today}T10:00:00",
                        "end_time": f"{today}T11:00:00",
                    }
                ],
            }
        },
        "objectiveHistory": {
            "o1": [
                {
                    "date": (parse_logical_date(today) - timedelta(days=5)).isoformat(),
                    "pct": 0,
                    "done": 0,
                    "total": 2,
                },
                {"date": today, "pct": 50, "done": 1, "total": 2},
            ]
        },
    }


def _import(client: TestClient, headers: dict[str, str], payload) -> object:
    content = (
        payload
        if isinstance(payload, bytes)
        else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    return client.post(
        "/api/v1/backup/import",
        headers=headers,
        files={"file": ("legacy.json", content, "application/json")},
    )


def test_legacy_import_replaces_data_and_remaps_ids(
    client: TestClient, register, create_node
) -> None:
    user = register("importer")
    headers = user["headers"]

    # Dato previo que debe desaparecer tras importar.
    create_node(
        headers,
        module_type="backlog",
        title="Dato anterior",
        workspace_id=user["workspace_id"],
    )

    response = _import(client, headers, _legacy_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["source_schema_version"] == 3
    assert body["imported"] == {
        "workspaces": 2,
        "nodes": 5,
        "schedule_slots": 3,
        "exceptions": 1,
        "objectives": 1,
        "achievements": 1,
        "score_history": 2,
        "snapshots": 1,
        "timer_sessions": 2,
        "objective_snapshots": 2,
    }

    workspaces = client.get("/api/v1/workspaces", headers=headers)
    assert workspaces.status_code == 200
    by_name = {workspace["name"]: workspace for workspace in workspaces.json()}
    assert set(by_name) == {"General", "Trabajo"}

    habits_general = client.get(
        f"/api/v1/nodes?module_type=habits&workspace_id={by_name['General']['id']}",
        headers=headers,
    ).json()["nodes"]
    assert [node["title"] for node in habits_general] == ["Meditar"]
    assert habits_general[0]["completed"] is True

    habits_trabajo = client.get(
        f"/api/v1/nodes?module_type=habits&workspace_id={by_name['Trabajo']['id']}",
        headers=headers,
    ).json()["nodes"]
    assert len(habits_trabajo) == 1
    assert habits_trabajo[0]["title"] == "Leer"
    assert habits_trabajo[0]["completed"] is False
    assert [child["title"] for child in habits_trabajo[0]["children"]] == [
        "Capítulo 1"
    ]
    assert habits_trabajo[0]["children"][0]["completed"] is True
    # Los IDs legacy se remapearon a UUID nuevos.
    assert habits_trabajo[0]["id"] != "h2"
    assert habits_trabajo[0]["children"][0]["id"] != "h2c"

    backlog = client.get(
        f"/api/v1/nodes?module_type=backlog&workspace_id={by_name['Trabajo']['id']}",
        headers=headers,
    ).json()["nodes"]
    assert [node["title"] for node in backlog] == ["Preparar informe"]
    assert backlog[0]["priority"] == "Alta"
    assert backlog[0]["tag"] == "Trabajo"

    slots = client.get("/api/v1/schedule", headers=headers)
    assert slots.status_code == 200
    slot_rows = slots.json()
    assert len(slot_rows) == 3
    assert {slot["hour_slot"] for slot in slot_rows} == {"04:00", "05:00"}
    assert any(slot["recurring"] is False for slot in slot_rows)

    achievements = client.get("/api/v1/achievements", headers=headers)
    assert achievements.status_code == 200
    assert achievements.json()["total"] == 1
    achievement = achievements.json()["items"][0]
    assert achievement["title"] == "Meditar"
    assert achievement["source_id"].startswith(
        habits_general[0]["id"] + "_"
    )

    objectives = client.get(
        f"/api/v1/objectives?workspace_id={by_name['Trabajo']['id']}",
        headers=headers,
    )
    assert objectives.status_code == 200
    objective = objectives.json()[0]
    assert objective["title"] == "Aprender Python"
    assert objective["total"] == 2
    assert objective["done"] == 1
    assert objective["pct"] == 50

    stats = client.get("/api/v1/analytics/global-stats", headers=headers)
    assert stats.status_code == 200
    stats_body = stats.json()
    assert stats_body["dias_totales"] == 1
    assert stats_body["score_promedio_global"] == 40
    assert stats_body["total_minutos_fuga"] == 60

    today = get_logical_date()
    heatmap = client.get("/api/v1/analytics/heatmap?weeks=16", headers=headers)
    assert heatmap.status_code == 200
    cells = [
        cell
        for week in heatmap.json()["weeks"]
        for cell in week
        if cell["date"] == today
    ]
    assert len(cells) == 1
    assert cells[0]["score"] == 40
    assert cells[0]["level"] == 2
    assert cells[0]["has_data"] is True

    history = client.get(
        "/api/v1/analytics/history?period=day&limit=10", headers=headers
    )
    assert history.status_code == 200
    buckets = history.json()["items"]
    today_bucket = next(bucket for bucket in buckets if bucket["key"] == today)
    assert today_bucket["days"][0]["score"] == 40
    assert today_bucket["days"][0]["fallback"] is False
    assert today_bucket["fuga"] == 60


def test_invalid_import_rolls_back_and_keeps_existing_data(
    client: TestClient, register, create_node
) -> None:
    user = register("importer2")
    headers = user["headers"]
    create_node(
        headers,
        module_type="habits",
        title="Conservar",
        workspace_id=user["workspace_id"],
    )

    # JSON inválido: ni siquiera llega al savepoint.
    response = _import(client, headers, b"{esto no es json")
    assert response.status_code == 400

    # Error a mitad de la importación: el savepoint debe revertir el borrado.
    broken = _legacy_payload()
    broken["scoreHistory"] = [{"score": 10}]
    response = _import(client, headers, broken)
    assert response.status_code == 400

    nodes = client.get("/api/v1/nodes?module_type=habits", headers=headers)
    assert nodes.status_code == 200
    assert [node["title"] for node in nodes.json()["nodes"]] == ["Conservar"]

    workspaces = client.get("/api/v1/workspaces", headers=headers)
    assert {workspace["name"] for workspace in workspaces.json()} == {
        "General",
        "Trabajo",
        "Estudios",
    }
