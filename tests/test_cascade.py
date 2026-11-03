"""Cascada recursiva de completado, reversión y logros."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.task_node import TaskNode


def _toggle(
    client: TestClient,
    headers: dict[str, str],
    node_id: str,
    completed: bool = True,
) -> dict:
    response = client.post(
        f"/api/v1/nodes/{node_id}/toggle",
        headers=headers,
        json={"completed": completed},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tree(
    client: TestClient, headers: dict[str, str], module_type: str = "habits"
) -> list[dict]:
    response = client.get(
        f"/api/v1/nodes?module_type={module_type}", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["nodes"]


def _find(nodes: list[dict], node_id: str) -> dict | None:
    for node in nodes:
        if node["id"] == node_id:
            return node
        found = _find(node["children"], node_id)
        if found is not None:
            return found
    return None


def test_three_level_cascade_completes_and_reverses(
    client: TestClient, register, create_node
) -> None:
    user = register("cascade")
    headers = user["headers"]

    root = create_node(
        headers,
        module_type="habits",
        title="Raíz",
        workspace_id=user["workspace_id"],
    )
    child = create_node(
        headers, module_type="habits", title="Hijo", parent_id=root["id"]
    )
    leaf = create_node(
        headers, module_type="habits", title="Nieto", parent_id=child["id"]
    )

    # La casilla del padre está deshabilitada mientras tenga subtareas.
    response = client.post(
        f"/api/v1/nodes/{root['id']}/toggle",
        headers=headers,
        json={"completed": True},
    )
    assert response.status_code == 422
    assert "subtareas" in response.json()["detail"]

    # Completar la hoja completa toda la cadena.
    _toggle(client, headers, leaf["id"], True)
    nodes = _tree(client, headers)
    root_out = _find(nodes, root["id"])
    child_out = _find(nodes, child["id"])
    leaf_out = _find(nodes, leaf["id"])
    assert root_out is not None and child_out is not None and leaf_out is not None
    assert root_out["completed"] is True
    assert child_out["completed"] is True
    assert leaf_out["completed"] is True
    assert root_out["completed_at"] is not None
    assert child_out["completed_at"] is not None
    assert leaf_out["completed_at"] is not None
    assert root_out["has_children"] is True
    assert child_out["has_children"] is True

    # Desmarcar la hoja revierte a todos los ancestros.
    _toggle(client, headers, leaf["id"], False)
    nodes = _tree(client, headers)
    root_out = _find(nodes, root["id"])
    child_out = _find(nodes, child["id"])
    leaf_out = _find(nodes, leaf["id"])
    assert root_out["completed"] is False
    assert child_out["completed"] is False
    assert leaf_out["completed"] is False
    assert root_out["completed_at"] is None
    assert child_out["completed_at"] is None
    assert leaf_out["completed_at"] is None

    # Volver a completar restaura la cascada.
    _toggle(client, headers, leaf["id"], True)
    nodes = _tree(client, headers)
    assert _find(nodes, root["id"])["completed"] is True


def test_adding_subtask_uncompletes_parent_and_removes_achievement(
    client: TestClient, register, create_node, db
) -> None:
    user = register("cascade2")
    headers = user["headers"]

    root = create_node(
        headers,
        module_type="habits",
        title="Raíz",
        workspace_id=user["workspace_id"],
    )
    child = create_node(
        headers, module_type="habits", title="Hijo", parent_id=root["id"]
    )
    leaf = create_node(
        headers, module_type="habits", title="Nieto", parent_id=child["id"]
    )
    _toggle(client, headers, leaf["id"], True)

    # Archivar el hijo completado genera un logro definitivo.
    response = client.post(
        f"/api/v1/nodes/{child['id']}/archive", headers=headers
    )
    assert response.status_code == 200, response.text
    achievements = client.get("/api/v1/achievements", headers=headers)
    assert achievements.status_code == 200
    assert achievements.json()["total"] == 1

    # Añadir una subtarea nueva descompleta al padre y borra su logro.
    other_workspace = next(
        workspace
        for workspace in user["workspaces"]
        if workspace["name"] == "Trabajo"
    )
    new_child = create_node(
        headers,
        module_type="habits",
        title="Subtarea nueva",
        parent_id=child["id"],
        workspace_id=other_workspace["id"],
    )
    # El hijo hereda el espacio de trabajo del padre, no el enviado.
    assert new_child["workspace_id"] == root["workspace_id"]

    achievements = client.get("/api/v1/achievements", headers=headers)
    assert achievements.status_code == 200
    assert achievements.json()["total"] == 0

    nodes = _tree(client, headers)
    root_out = _find(nodes, root["id"])
    assert root_out is not None
    assert root_out["completed"] is False
    assert root_out["completed_at"] is None

    db.expire_all()
    child_row = db.get(TaskNode, child["id"])
    assert child_row is not None
    assert child_row.completed is False
    assert child_row.completed_at is None


def test_uncomplete_removes_achievement(
    client: TestClient, register, create_node
) -> None:
    user = register("cascade3")
    headers = user["headers"]

    node = create_node(
        headers,
        module_type="habits",
        title="Hábito suelto",
        workspace_id=user["workspace_id"],
    )
    _toggle(client, headers, node["id"], True)

    response = client.post(
        f"/api/v1/nodes/{node['id']}/archive", headers=headers
    )
    assert response.status_code == 200, response.text
    assert (
        client.get("/api/v1/achievements", headers=headers).json()["total"]
        == 1
    )

    _toggle(client, headers, node["id"], False)
    assert (
        client.get("/api/v1/achievements", headers=headers).json()["total"]
        == 0
    )
