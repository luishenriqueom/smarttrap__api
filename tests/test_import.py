from tests.helpers import JPEG, login, login_demo


def test_import_assigns_photos_to_the_chosen_trap(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post("/api/v1/devices", json={"code": "trap-fotos", "name": "Fotos"}, headers=admin)
    assert created.status_code == 201, created.text
    device_id = created.json()["id"]

    response = client.post(
        "/api/v1/captures/import",
        data={
            "device_id": device_id,
            "captured_at": ["2026-08-01T12:00:00Z", "2026-08-01T12:01:00Z"],
        },
        files=[
            ("images", ("picture_2.jpg", JPEG, "image/jpeg")),
            ("images", ("notas.txt", b"oi", "text/plain")),
        ],
        headers=admin,
    )
    assert response.status_code == 201, response.text
    assert response.json() == {"imported": 1, "skipped": 1}

    listed = client.get("/api/v1/captures", params={"device_id": device_id}, headers=admin)
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["notes"] == "picture_2.jpg"
    assert item["device_code"] == "trap-fotos"
    assert item["label"] == "unlabeled"


def test_import_rejects_a_demo_account_and_another_users_trap(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post("/api/v1/devices", json={"code": "trap-fotos", "name": "Fotos"}, headers=admin)
    device_id = created.json()["id"]
    demo = login_demo(client)
    denied = client.post(
        "/api/v1/captures/import",
        data={"device_id": device_id, "captured_at": "2026-08-01T12:00:00Z"},
        files=[("images", ("picture_1.jpg", JPEG, "image/jpeg"))],
        headers=demo,
    )
    assert denied.status_code == 403

    common = login(client, "usuario@smarttrap.local", "usuario123")
    missing = client.post(
        "/api/v1/captures/import",
        data={"device_id": device_id, "captured_at": "2026-08-01T12:00:00Z"},
        files=[("images", ("picture_1.jpg", JPEG, "image/jpeg"))],
        headers=common,
    )
    assert missing.status_code == 404
