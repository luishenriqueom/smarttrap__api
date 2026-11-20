import hashlib

from tests.helpers import GATEWAY, login, login_demo

SMARTTRAP = b"\xe9" + b"\x11" * 2047
HELTEC = b"\xe9" + b"\x22" * 2047


def _publish(client, headers, **kwargs):
    data = {}
    files = {}
    if "smarttrap_version" in kwargs:
        data["smarttrap_version"] = str(kwargs["smarttrap_version"])
    if "heltec_version" in kwargs:
        data["heltec_version"] = str(kwargs["heltec_version"])
    if "smarttrap_bin" in kwargs:
        files["smarttrap_bin"] = ("smarttrap.bin", kwargs["smarttrap_bin"], "application/octet-stream")
    if "heltec_bin" in kwargs:
        files["heltec_bin"] = ("heltec.bin", kwargs["heltec_bin"], "application/octet-stream")
    return client.post("/api/v1/firmware", data=data, files=files, headers=headers)


def test_publishes_both_firmware_images_and_serves_the_newer_one(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = _publish(
        client,
        admin,
        smarttrap_version=2,
        smarttrap_bin=SMARTTRAP,
        heltec_version=1,
        heltec_bin=HELTEC,
    )
    assert created.status_code == 201, created.text
    items = {item["target"]: item for item in created.json()["items"]}
    assert items["smarttrap"]["version"] == 2
    assert items["smarttrap"]["sha256"] == hashlib.sha256(SMARTTRAP).hexdigest()
    assert items["heltec"]["size_bytes"] == len(HELTEC)

    listed = client.get("/api/v1/firmware", headers=admin)
    assert listed.status_code == 200
    assert {item["target"] for item in listed.json()} == {"smarttrap", "heltec"}

    meta = client.get("/api/v1/ingest/firmware/smarttrap?current=1", headers=GATEWAY)
    assert meta.status_code == 200, meta.text
    assert meta.json()["update"] is True
    assert meta.json()["version"] == 2

    same = client.get("/api/v1/ingest/firmware/smarttrap?current=2", headers=GATEWAY)
    assert same.json()["update"] is False
    newer = client.get("/api/v1/ingest/firmware/smarttrap?current=3", headers=GATEWAY)
    assert newer.json()["update"] is False

    binary = client.get("/api/v1/ingest/firmware/smarttrap/bin?current=1", headers=GATEWAY)
    assert binary.status_code == 200, binary.text
    assert binary.content == SMARTTRAP
    assert binary.headers["x-firmware-sha256"] == hashlib.sha256(SMARTTRAP).hexdigest()
    assert binary.headers["x-md5"] == hashlib.md5(SMARTTRAP).hexdigest()

    current = client.get("/api/v1/ingest/firmware/smarttrap/bin?current=2", headers=GATEWAY)
    assert current.status_code == 304
    ahead = client.get("/api/v1/ingest/firmware/heltec/bin?current=1", headers=GATEWAY)
    assert ahead.status_code == 304


def test_firmware_permissions_and_validation(client):
    demo = login_demo(client)
    rejected = _publish(client, demo, smarttrap_version=1, smarttrap_bin=SMARTTRAP)
    assert rejected.status_code == 403

    missing = client.get("/api/v1/ingest/firmware/smarttrap", headers=GATEWAY)
    assert missing.status_code == 404
    assert client.get("/api/v1/ingest/firmware/smarttrap/bin").status_code == 401
    assert client.get("/api/v1/ingest/firmware/outro", headers=GATEWAY).status_code == 404

    admin = login(client, "admin@smarttrap.local", "admin123")
    incomplete = _publish(client, admin, smarttrap_version=1)
    assert incomplete.status_code == 422
    empty = client.post("/api/v1/firmware", headers=admin)
    assert empty.status_code == 422
    fake = _publish(client, admin, smarttrap_version=1, smarttrap_bin=b"\x00" * 2048)
    assert fake.status_code == 422
    huge = _publish(client, admin, smarttrap_version=1, smarttrap_bin=b"\xe9" + b"\x00" * 0x1E0000)
    assert huge.status_code == 413

    metric = client.post(
        "/api/v1/ingest/metrics",
        json={
            "device_code": "trap-01",
            "recorded_at": "2026-11-10T14:22:00Z",
            "pest_count": 4,
            "confidence": 0.8,
            "firmware_version": 2,
        },
        headers=GATEWAY,
    )
    assert metric.status_code == 201, metric.text
