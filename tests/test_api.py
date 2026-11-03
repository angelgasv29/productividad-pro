"""Smoke tests de páginas, autenticación, sistema, analítica y exportaciones."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

PERIODS = ["day", "week", "month", "quarter", "quadrimester", "semester", "year"]


def test_public_pages_and_static_assets(client: TestClient) -> None:
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    index = client.get("/", follow_redirects=False)
    assert index.status_code == 302
    assert index.headers["location"] == "/login"

    login = client.get("/login")
    assert login.status_code == 200
    assert "Productividad Pro" in login.text

    css = client.get("/static/css/styles.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]

    main_js = client.get("/static/js/main.js")
    assert main_js.status_code == 200
    assert "javascript" in main_js.headers["content-type"]

    chart = client.get("/static/vendor/chart.umd.min.js")
    assert chart.status_code == 200
    assert len(chart.content) > 100_000

    missing = client.get("/static/js/no-existe.js")
    assert missing.status_code == 404


def test_register_login_cookie_bearer_and_logout(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "Test12345",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    assert token
    assert client.cookies.get("prodpro_access_token")

    index = client.get("/")
    assert index.status_code == 200
    assert "alice" in index.text
    assert "headerUsername" in index.text

    me = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert me.json()["initials"] == "AL"

    profile = client.patch(
        "/api/v1/users/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "nueva@example.com", "theme": "dark"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["email"] == "nueva@example.com"
    assert profile.json()["theme"] == "dark"

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert client.cookies.get("prodpro_access_token") is None
    assert client.get("/", follow_redirects=False).status_code == 302

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "alice", "password": "Test12345"},
    )
    assert login.status_code == 200, login.text
    assert client.get("/").status_code == 200

    changed = client.post(
        "/api/v1/users/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "Test12345",
            "new_password": "NuevaClave9876",
        },
    )
    assert changed.status_code == 200, changed.text

    old_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "alice", "password": "Test12345"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "alice", "password": "NuevaClave9876"},
    )
    assert new_login.status_code == 200


def test_health_selftest_bootstrap_and_analytics(
    client: TestClient, register, create_node
) -> None:
    user = register("smoke")
    headers = user["headers"]

    create_node(
        headers,
        module_type="routines",
        title="Cocinar",
        workspace_id=user["workspace_id"],
        routine_category="Comer",
    )

    health = client.get("/api/v1/system/health", headers=headers)
    assert health.status_code == 200, health.text
    health_body = health.json()
    assert health_body["ok"] is True
    assert health_body["schema_version"] == 4
    assert health_body["counts"]["nodes"] == 1
    assert health_body["counts"]["workspaces"] == 3
    assert health_body["database_bytes"] > 0
    assert health_body["user"] == "smoke"
    assert set(health_body["backups"]) == {"A", "B"}

    selftest = client.post("/api/v1/system/selftest", headers=headers)
    assert selftest.status_code == 200, selftest.text
    selftest_body = selftest.json()
    assert selftest_body["failed"] == 0
    assert selftest_body["passed"] == selftest_body["total"]
    assert selftest_body["total"] >= 5

    bootstrap = client.get("/api/v1/analytics/bootstrap", headers=headers)
    assert bootstrap.status_code == 200, bootstrap.text
    bootstrap_body = bootstrap.json()
    assert bootstrap_body["user"]["username"] == "smoke"
    assert len(bootstrap_body["workspaces"]) == 3
    assert bootstrap_body["current_workspace_id"] == user["workspace_id"]
    assert set(bootstrap_body["nodes"]) == {"habits", "routines", "backlog"}
    assert bootstrap_body["schema_version"] == 4
    assert "today_score" in bootstrap_body
    assert "global_stats" in bootstrap_body
    assert bootstrap_body["year_countdown"]["year"] > 2000

    countdown = client.get("/api/v1/analytics/year-countdown", headers=headers)
    assert countdown.status_code == 200
    assert 0 <= countdown.json()["percent"] <= 100
    assert countdown.json()["days_remaining"] >= 0

    heatmap = client.get("/api/v1/analytics/heatmap?weeks=16", headers=headers)
    assert heatmap.status_code == 200
    assert len(heatmap.json()["weeks"]) == 16
    assert all(len(week) == 7 for week in heatmap.json()["weeks"])

    for path in (
        "/api/v1/analytics/global-stats",
        "/api/v1/analytics/timer-impact",
        "/api/v1/analytics/correlation",
        "/api/v1/analytics/categories",
        "/api/v1/analytics/objectives-history",
        "/api/v1/analytics/today-score",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)

    for period in PERIODS:
        response = client.get(
            f"/api/v1/analytics/history?period={period}", headers=headers
        )
        assert response.status_code == 200, (period, response.text)
        assert response.json()["period"] == period


def test_exports_and_backup_restore(
    client: TestClient, register, create_node
) -> None:
    user = register("exporter")
    headers = user["headers"]

    node = create_node(
        headers,
        module_type="backlog",
        title="Original",
        workspace_id=user["workspace_id"],
    )
    response = client.post(
        f"/api/v1/nodes/{node['id']}/toggle",
        headers=headers,
        json={"completed": True},
    )
    assert response.status_code == 200
    response = client.post(
        f"/api/v1/nodes/{node['id']}/archive", headers=headers
    )
    assert response.status_code == 200

    achievements_csv = client.get(
        "/api/v1/achievements/export.csv", headers=headers
    )
    assert achievements_csv.status_code == 200
    assert "text/csv" in achievements_csv.headers["content-type"]
    assert "attachment" in achievements_csv.headers["content-disposition"]
    assert achievements_csv.text.startswith("\ufeff")
    assert '"ID","Título","Módulo"' in achievements_csv.text

    history_csv = client.get(
        "/api/v1/analytics/history/export.csv?period=week", headers=headers
    )
    assert history_csv.status_code == 200
    assert '"Período","Desde","Hasta"' in history_csv.text
    assert '"Minutos fuga"' in history_csv.text

    report = client.get("/api/v1/analytics/report.txt", headers=headers)
    assert report.status_code == 200
    assert "text/plain" in report.headers["content-type"]
    assert "INFORME DE PRODUCTIVIDAD" in report.text

    exported = client.get("/api/v1/backup/export", headers=headers)
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    payload = json.loads(exported.text)
    assert payload["schemaVersion"] == 4
    assert payload["user"]["username"] == "exporter"
    assert len(payload["nodes"]) == 1

    # Backup rotativo y restauración del slot A.
    create_node(
        headers,
        module_type="backlog",
        title="Antes del backup",
        workspace_id=user["workspace_id"],
    )
    saved = client.post("/api/v1/system/backup", headers=headers)
    assert saved.status_code == 200, saved.text
    slots = client.get("/api/v1/system/backups", headers=headers)
    assert slots.status_code == 200
    assert slots.json()["A"]["exists"] is True

    create_node(
        headers,
        module_type="backlog",
        title="Extra posterior",
        workspace_id=user["workspace_id"],
    )
    before = client.get("/api/v1/nodes?module_type=backlog", headers=headers)
    assert {item["title"] for item in before.json()["nodes"]} == {
        "Antes del backup",
        "Extra posterior",
    }

    restored = client.post("/api/v1/system/restore/A", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["slot"] == "A"

    after = client.get("/api/v1/nodes?module_type=backlog", headers=headers)
    assert after.status_code == 200
    assert {item["title"] for item in after.json()["nodes"]} == {
        "Antes del backup"
    }
