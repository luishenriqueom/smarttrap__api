from tests.helpers import GATEWAY, JPEG, login


def _device(client, headers, code):
    devices = client.get("/api/v1/devices", headers=headers).json()
    return next(item for item in devices["items"] if item["code"] == code)


def test_platform_sets_the_mode_and_the_trap_reports_the_one_it_is_running(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post("/api/v1/devices", json={"code": "trap-modo", "name": "Modo"}, headers=admin)
    assert created.status_code == 201, created.text
    assert created.json()["operating_mode"] == "collect"
    assert created.json()["reported_mode"] is None

    config = client.get(
        "/api/v1/ingest/config",
        params={"device_code": "trap-modo", "operating_mode": "collect"},
        headers=GATEWAY,
    )
    assert config.status_code == 200, config.text
    assert config.json()["operating_mode"] == "collect"
    assert _device(client, admin, "trap-modo")["reported_mode"] == "collect"

    updated = client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"operating_mode": "infer"},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["operating_mode"] == "infer"
    assert updated.json()["reported_mode"] == "collect"

    armed = client.get("/api/v1/ingest/config", params={"device_code": "trap-modo"}, headers=GATEWAY)
    assert armed.json()["operating_mode"] == "infer"
    assert client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"operating_mode": "outro"},
        headers=admin,
    ).status_code == 422

    image = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-modo", "captured_at": "2026-11-23T12:00:00Z", "operating_mode": "infer"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert image.status_code == 201, image.text
    assert _device(client, admin, "trap-modo")["reported_mode"] == "infer"

    metric = client.post(
        "/api/v1/ingest/metrics",
        json={"device_code": "trap-modo", "recorded_at": "2026-11-23T12:05:00Z", "pest_count": 0, "operating_mode": "collect"},
        headers=GATEWAY,
    )
    assert metric.status_code == 201, metric.text
    assert _device(client, admin, "trap-modo")["reported_mode"] == "collect"

    modes = client.get("/api/v1/ingest/modes", headers=GATEWAY)
    assert modes.status_code == 200, modes.text
    listed = next(item for item in modes.json()["items"] if item["device_code"] == "trap-modo")
    assert listed == {"device_code": "trap-modo", "operating_mode": "infer"}
    assert client.get("/api/v1/ingest/modes").status_code == 401
