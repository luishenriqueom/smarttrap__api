from tests.helpers import GATEWAY, JPEG, login


def test_rejects_invalid_api_key(client):
    response = client.post(
        "/api/v1/ingest/metrics",
        json={"device_code": "trap-01", "recorded_at": "2026-11-10T14:22:00Z", "pest_count": 1},
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


def test_accepts_jpeg_and_minimal_metric_under_superadmin(client):
    image = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-01", "captured_at": "2026-11-10T14:00:00Z"},
        files={"image": ("cap.jpg", JPEG, "application/octet-stream")},
        headers=GATEWAY,
    )
    assert image.status_code == 201, image.text

    metric = client.post(
        "/api/v1/ingest/metrics",
        json={"device_code": "trap-01", "recorded_at": "2026-11-10T14:22:00Z", "pest_count": 12},
        headers=GATEWAY,
    )
    assert metric.status_code == 201, metric.text

    missing = client.post(
        "/api/v1/ingest/metrics",
        json={"device_code": "trap-01", "recorded_at": "2026-11-10T14:22:00Z"},
        headers=GATEWAY,
    )
    assert missing.status_code == 422

    admin = login(client, "admin@smarttrap.local", "admin123")
    me = client.get("/api/v1/auth/me", headers=admin).json()
    devices = client.get("/api/v1/devices", headers=admin).json()
    created = next(item for item in devices["items"] if item["code"] == "trap-01")
    assert created["owner_id"] == me["id"]
    assert created["capture_count"] == 1
    assert created["last_metric"]["pest_count"] == 12
    assert created["is_online"] is True

    image_response = client.get(f"/api/v1/captures/{image.json()['id']}/image", headers=admin)
    assert image_response.status_code == 200
    assert image_response.content == JPEG
