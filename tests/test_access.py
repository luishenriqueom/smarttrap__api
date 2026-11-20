from tests.helpers import GATEWAY, JPEG, login, login_demo


def _device(client, headers, code: str, owner_id: str | None = None) -> dict:
    payload = {"code": code, "name": code, "location": "CTT"}
    if owner_id is not None:
        payload["owner_id"] = owner_id
    response = client.post("/api/v1/devices", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_common_user_cannot_see_another_users_trap(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    common = login(client, "usuario@smarttrap.local", "usuario123")
    private = _device(client, admin, "trap-admin")
    own = _device(client, common, "trap-comum")

    visible = client.get("/api/v1/devices", headers=common).json()
    codes = {item["code"] for item in visible["items"]}
    assert codes == {"trap-comum"}
    assert client.get(f"/api/v1/devices/{private['id']}", headers=common).status_code == 404
    assert client.get("/api/v1/users", headers=common).status_code == 403
    assert client.get(f"/api/v1/devices/{own['id']}", headers=admin).status_code == 200


def test_demo_is_read_only(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    users = client.get("/api/v1/users", headers=admin).json()
    demo_user = next(user for user in users if user["is_demo"])
    device = _device(client, admin, "trap-demo", owner_id=demo_user["id"])

    uploaded = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-demo", "captured_at": "2026-11-10T15:00:00Z"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert uploaded.status_code == 201, uploaded.text
    capture_id = uploaded.json()["id"]

    demo = login_demo(client)
    listed = client.get("/api/v1/devices", headers=demo).json()
    assert [item["code"] for item in listed["items"]] == ["trap-demo"]

    forbidden = client.patch(
        f"/api/v1/captures/{capture_id}",
        json={"manual_count": 3, "label": "with_pest"},
        headers=demo,
    )
    assert forbidden.status_code == 403
    assert client.post("/api/v1/devices", json={"code": "trap-x", "name": "X"}, headers=demo).status_code == 403
    assert client.patch(f"/api/v1/devices/{device['id']}", json={"name": "Alterada"}, headers=demo).status_code == 403

    updated = client.patch(
        f"/api/v1/captures/{capture_id}",
        json={"manual_count": 3, "label": "with_pest", "notes": "contagem de campo"},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["manual_count"] == 3
    assert updated.json()["label"] == "with_pest"
