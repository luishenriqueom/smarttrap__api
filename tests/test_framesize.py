import io
import zipfile

from tests.helpers import GATEWAY, JPEG, login


def _sof(width: int, height: int) -> bytes:
    return b"\xff\xd8\xff\xc0\x00\x0b\x08" + bytes((height >> 8, height & 0xFF, width >> 8, width & 0xFF, 1, 1, 0x11, 0)) + b"\xff\xd9"


def test_config_follows_the_device_and_defaults_to_svga(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post("/api/v1/devices", json={"code": "trap-res", "name": "Resolução"}, headers=admin)
    assert created.status_code == 201, created.text
    assert created.json()["frame_size"] == "svga"

    fresh = client.get("/api/v1/ingest/config", params={"device_code": "trap-nova"}, headers=GATEWAY)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json() == {"frame_size": "svga", "width": 800, "height": 600, "jpeg_quality": 12, "sleep_seconds": 300, "operating_mode": "collect"}

    updated = client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"frame_size": "qvga"},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["frame_size"] == "qvga"

    config = client.get("/api/v1/ingest/config", params={"device_code": "trap-res"}, headers=GATEWAY)
    assert config.status_code == 200, config.text
    assert config.json() == {"frame_size": "qvga", "width": 320, "height": 240, "jpeg_quality": 12, "sleep_seconds": 300, "operating_mode": "collect"}

    quality = client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"jpeg_quality": 20},
        headers=admin,
    )
    assert quality.status_code == 200, quality.text
    assert quality.json()["jpeg_quality"] == 20
    again = client.get("/api/v1/ingest/config", params={"device_code": "trap-res"}, headers=GATEWAY)
    assert again.json()["jpeg_quality"] == 20
    assert client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"jpeg_quality": 2},
        headers=admin,
    ).status_code == 422

    rejected = client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"frame_size": "4k"},
        headers=admin,
    )
    assert rejected.status_code == 422
    missing = client.get("/api/v1/ingest/config", params={"device_code": "trap-res"})
    assert missing.status_code == 401


def test_capture_records_the_resolution_that_arrived(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    plain = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-01", "captured_at": "2026-11-10T14:00:00Z", "frame_size": "vga", "jpeg_quality": "15"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert plain.status_code == 201, plain.text
    stored = client.get(f"/api/v1/captures/{plain.json()['id']}", headers=admin)
    assert stored.status_code == 200, stored.text
    assert stored.json()["frame_size"] == "vga"
    assert stored.json()["width"] == 640
    assert stored.json()["height"] == 480
    assert stored.json()["jpeg_quality"] == 15

    measured = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-01", "captured_at": "2026-11-10T15:00:00Z", "frame_size": "svga"},
        files={"image": ("cap.jpg", _sof(160, 120), "image/jpeg")},
        headers=GATEWAY,
    )
    assert measured.status_code == 201, measured.text
    body = client.get(f"/api/v1/captures/{measured.json()['id']}", headers=admin).json()
    assert body["frame_size"] == "svga"
    assert body["width"] == 160
    assert body["height"] == 120

    omitted = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-01", "captured_at": "2026-11-10T16:00:00Z"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert omitted.status_code == 201, omitted.text
    legacy = client.get(f"/api/v1/captures/{omitted.json()['id']}", headers=admin).json()
    assert legacy["frame_size"] is None
    assert legacy["width"] is None
    assert legacy["height"] is None
    assert legacy["jpeg_quality"] is None

    invalid = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-01", "captured_at": "2026-11-10T17:00:00Z", "frame_size": "nope"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert invalid.status_code == 422

    exported = client.get(
        "/api/v1/captures/export",
        params={"from": "2026-11-10T00:00:00Z", "to": "2026-11-10T23:59:59Z"},
        headers=admin,
    )
    assert exported.status_code == 200, exported.text
    manifest = zipfile.ZipFile(io.BytesIO(exported.content)).read("manifest.csv").decode()
    assert "resolucao" in manifest.splitlines()[0]
    assert "640x480" in manifest
    assert "160x120" in manifest
    assert "qualidade_jpeg" in manifest.splitlines()[0]
    assert ",15" in manifest
