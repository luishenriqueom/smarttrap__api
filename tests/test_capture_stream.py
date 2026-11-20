from tests.helpers import GATEWAY, JPEG, login

from app.services.capture_events import capture_broker, visible_to


def test_image_ingest_publishes_capture_without_leaking_owner_to_other_users(client):
    events = capture_broker.subscribe()
    try:
        image = client.post(
            "/api/v1/ingest/images",
            data={"device_code": "trap-01", "captured_at": "2026-11-10T14:00:00Z"},
            files={"image": ("cap.jpg", JPEG, "application/octet-stream")},
            headers=GATEWAY,
        )
        assert image.status_code == 201, image.text
        event = events.get(timeout=2)
    finally:
        capture_broker.unsubscribe(events)

    assert event["id"] == image.json()["id"]
    assert event["device_code"] == "trap-01"
    assert event["label"] == "unlabeled"
    assert event["device_name"] == "trap-01"

    admin = login(client, "admin@smarttrap.local", "admin123")
    common = login(client, "usuario@smarttrap.local", "usuario123")
    admin_id = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    common_id = client.get("/api/v1/auth/me", headers=common).json()["id"]
    assert visible_to("superadmin", admin_id, event)
    assert not visible_to("common", common_id, event)
    assert visible_to("common", admin_id, event)


def test_capture_stream_requires_auth(client):
    response = client.get("/api/v1/captures/stream")
    assert response.status_code == 401
