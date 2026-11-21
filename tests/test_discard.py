import io
import zipfile

from tests.helpers import GATEWAY, JPEG, login, login_demo


def _upload(client, code: str, captured_at: str) -> str:
    response = client.post(
        "/api/v1/ingest/images",
        data={"device_code": code, "captured_at": captured_at},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_discarded_capture_stays_out_of_the_dataset_until_restored(client):
    keep = _upload(client, "trap-01", "2026-11-02T14:22:03Z")
    dropped = _upload(client, "trap-01", "2026-11-03T08:00:00Z")
    admin = login(client, "admin@smarttrap.local", "admin123")

    discarded = client.post("/api/v1/captures/discard", json={"ids": [dropped]}, headers=admin)
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["discarded"] == 1

    listed = client.get("/api/v1/captures", headers=admin)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [keep]
    assert client.get(f"/api/v1/captures/{dropped}", headers=admin).status_code == 404
    assert client.get(f"/api/v1/captures/{dropped}/image", headers=admin).status_code == 404

    device = next(item for item in client.get("/api/v1/devices", headers=admin).json()["items"] if item["code"] == "trap-01")
    assert device["capture_count"] == 1

    exported = client.get(
        "/api/v1/captures/export",
        params={"from": "2026-11-01T00:00:00Z", "to": "2026-11-30T23:59:59Z"},
        headers=admin,
    )
    photos = [name for name in zipfile.ZipFile(io.BytesIO(exported.content)).namelist() if name.endswith(".jpg")]
    assert len(photos) == 1
    assert "2026-11-02" in photos[0]

    restored = client.post("/api/v1/captures/restore", json={"ids": [dropped]}, headers=admin)
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"] == 1
    listed_again = client.get("/api/v1/captures", headers=admin)
    assert {item["id"] for item in listed_again.json()["items"]} == {keep, dropped}


def test_discard_rejects_a_capture_from_another_user(client):
    own = _upload(client, "trap-01", "2026-11-02T14:22:03Z")
    common = login(client, "usuario@smarttrap.local", "usuario123")
    client.post("/api/v1/devices", json={"code": "trap-comum", "name": "Comum"}, headers=common)
    foreign = _upload(client, "trap-comum", "2026-11-02T15:00:00Z")
    admin = login(client, "admin@smarttrap.local", "admin123")

    rejected = client.post("/api/v1/captures/discard", json={"ids": [own, foreign]}, headers=common)
    assert rejected.status_code == 404
    still_there = client.get("/api/v1/captures", headers=admin)
    assert {item["id"] for item in still_there.json()["items"]} == {own, foreign}


def test_demo_cannot_discard(client):
    capture_id = _upload(client, "trap-01", "2026-11-02T14:22:03Z")
    demo = login_demo(client)
    assert client.post("/api/v1/captures/discard", json={"ids": [capture_id]}, headers=demo).status_code == 403
