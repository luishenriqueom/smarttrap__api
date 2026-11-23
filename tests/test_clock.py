from datetime import datetime, timedelta, timezone

from tests.helpers import GATEWAY, JPEG, login, login_demo


def _device(client, headers, code):
    devices = client.get("/api/v1/devices", headers=headers).json()
    return next(item for item in devices["items"] if item["code"] == code)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _unix(moment: datetime) -> int:
    return int(moment.timestamp())


def test_contacts_store_the_trap_clock_and_a_sync_command_reaches_wifi_and_lora(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    now = datetime.now(timezone.utc)
    behind = _unix(now - timedelta(hours=2))

    config = client.get(
        "/api/v1/ingest/config",
        params={"device_code": "trap-clock", "device_time": behind},
        headers=GATEWAY,
    )
    assert config.status_code == 200, config.text
    assert "set_time" not in config.json()

    stored = _device(client, admin, "trap-clock")
    assert stored["clock_sync_requested"] is False
    assert stored["last_clock_received_at"] is not None
    reported = _parse(stored["last_clock_at"])
    assert abs(reported - datetime.fromtimestamp(behind, timezone.utc)) < timedelta(seconds=2)

    unset = client.get(
        "/api/v1/ingest/config",
        params={"device_code": "trap-clock", "device_time": 0},
        headers=GATEWAY,
    )
    assert unset.status_code == 200, unset.text
    cleared = _device(client, admin, "trap-clock")
    assert cleared["last_clock_at"] is None
    assert cleared["last_clock_received_at"] is not None

    image = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-clock", "captured_at": "2026-11-23T03:00:00Z", "device_time": str(behind)},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert image.status_code == 201, image.text
    assert _device(client, admin, "trap-clock")["last_clock_at"] is not None

    kept = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-clock", "captured_at": "2026-11-23T03:05:00Z"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert kept.status_code == 201, kept.text
    assert _device(client, admin, "trap-clock")["last_clock_at"] is not None

    requested = client.post(f"/api/v1/devices/{stored['id']}/clock-sync", headers=admin)
    assert requested.status_code == 200, requested.text
    assert requested.json()["clock_sync_requested"] is True

    denied = client.post(f"/api/v1/devices/{stored['id']}/clock-sync", headers=login_demo(client))
    assert denied.status_code == 403

    armed = client.get("/api/v1/ingest/config", params={"device_code": "trap-clock"}, headers=GATEWAY)
    assert armed.status_code == 200, armed.text
    assert abs(armed.json()["set_time"] - _unix(datetime.now(timezone.utc))) < 10

    pending = client.get("/api/v1/ingest/clock-sync", headers=GATEWAY)
    assert pending.status_code == 200, pending.text
    assert pending.json() == {"items": [{"device_code": "trap-clock"}]}
    assert client.get("/api/v1/ingest/clock-sync").status_code == 401

    still_wrong = client.post(
        "/api/v1/ingest/metrics",
        json={
            "device_code": "trap-clock",
            "recorded_at": "2026-11-23T03:10:00Z",
            "pest_count": 1,
            "device_time": behind,
        },
        headers=GATEWAY,
    )
    assert still_wrong.status_code == 201, still_wrong.text
    assert _device(client, admin, "trap-clock")["clock_sync_requested"] is True

    synced = _unix(datetime.now(timezone.utc))
    clock = client.post(
        "/api/v1/ingest/clock",
        json={"device_code": "trap-clock", "device_time": synced},
        headers=GATEWAY,
    )
    assert clock.status_code == 204, clock.text
    done = _device(client, admin, "trap-clock")
    assert done["clock_sync_requested"] is False
    assert abs(_parse(done["last_clock_at"]) - datetime.fromtimestamp(synced, timezone.utc)) < timedelta(seconds=2)

    quiet = client.get("/api/v1/ingest/config", params={"device_code": "trap-clock"}, headers=GATEWAY)
    assert "set_time" not in quiet.json()
    assert client.get("/api/v1/ingest/clock-sync", headers=GATEWAY).json() == {"items": []}
