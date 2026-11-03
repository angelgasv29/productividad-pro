"""Aislamiento estricto entre usuarios."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_user_cannot_see_or_modify_another_users_data(
    client: TestClient, register, create_node
) -> None:
    alice = register("alice")
    bob = register("bob")

    alice_node = create_node(
        alice["headers"],
        module_type="habits",
        title="Hábito privado de Alice",
        workspace_id=alice["workspace_id"],
    )

    # Bob no ve el árbol de Alice.
    response = client.get(
        "/api/v1/nodes?module_type=habits", headers=bob["headers"]
    )
    assert response.status_code == 200
    assert response.json()["nodes"] == []

    # Bob no ve el espacio de trabajo de Alice.
    response = client.get("/api/v1/workspaces", headers=bob["headers"])
    assert response.status_code == 200
    assert alice["workspace_id"] not in {
        workspace["id"] for workspace in response.json()
    }

    # Bob no puede editar, completar ni borrar el nodo de Alice.
    response = client.patch(
        f"/api/v1/nodes/{alice_node['id']}",
        headers=bob["headers"],
        json={"title": "Hackeado"},
    )
    assert response.status_code == 404

    response = client.post(
        f"/api/v1/nodes/{alice_node['id']}/toggle",
        headers=bob["headers"],
        json={"completed": True},
    )
    assert response.status_code == 404

    response = client.delete(
        f"/api/v1/nodes/{alice_node['id']}", headers=bob["headers"]
    )
    assert response.status_code == 404

    # Alice sigue viendo su nodo intacto.
    response = client.get(
        "/api/v1/nodes?module_type=habits", headers=alice["headers"]
    )
    assert response.status_code == 200
    nodes = response.json()["nodes"]
    assert [node["title"] for node in nodes] == ["Hábito privado de Alice"]


def test_achievements_and_exceptions_are_user_scoped(
    client: TestClient, register, create_node
) -> None:
    alice = register("alice")
    bob = register("bob")

    create_node(
        alice["headers"],
        module_type="backlog",
        title="Tarea de Alice",
        workspace_id=alice["workspace_id"],
    )
    response = client.get("/api/v1/achievements", headers=bob["headers"])
    assert response.status_code == 200
    assert response.json()["total"] == 0

    response = client.get("/api/v1/exceptions", headers=bob["headers"])
    assert response.status_code == 200
    assert response.json()["items"] == []
