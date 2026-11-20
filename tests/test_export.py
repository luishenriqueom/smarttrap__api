import io
import zipfile

from tests.helpers import GATEWAY, JPEG, login


def _upload(client, code: str, captured_at: str) -> None:
    response = client.post(
        "/api/v1/ingest/images",
        data={"device_code": code, "captured_at": captured_at},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert response.status_code == 201, response.text


def test_exports_zip_for_the_chosen_period(client):
    _upload(client, "trap-01", "2026-11-02T14:22:03Z")
    _upload(client, "trap-01", "2026-11-03T08:00:00Z")
    _upload(client, "trap-01", "2026-12-01T08:00:00Z")
    admin = login(client, "admin@smarttrap.local", "admin123")

    exported = client.get(
        "/api/v1/captures/export",
        params={"from": "2026-11-01T00:00:00Z", "to": "2026-11-30T23:59:59Z"},
        headers=admin,
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    names = archive.namelist()
    photos = [name for name in names if name.endswith(".jpg")]
    assert len(photos) == 2
    assert all(name.startswith("trap-01/2026-11-") for name in photos)
    assert "trap-01/2026-11-02T14-22-03Z_" in photos[0] or "trap-01/2026-11-02T14-22-03Z_" in photos[1]
    assert archive.read(photos[0]) == JPEG
    manifest = archive.read("manifest.csv").decode()
    assert "rotulo" in manifest
    assert "trap-01" in manifest

    empty = client.get(
        "/api/v1/captures/export",
        params={"from": "2020-01-01T00:00:00Z", "to": "2020-01-02T00:00:00Z"},
        headers=admin,
    )
    assert empty.status_code == 404
    backwards = client.get(
        "/api/v1/captures/export",
        params={"from": "2026-11-30T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        headers=admin,
    )
    assert backwards.status_code == 422


def test_export_hides_another_users_captures(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    common = login(client, "usuario@smarttrap.local", "usuario123")
    client.post("/api/v1/devices", json={"code": "trap-comum", "name": "Comum"}, headers=common)
    _upload(client, "trap-01", "2026-11-02T14:22:03Z")
    _upload(client, "trap-comum", "2026-11-02T15:00:00Z")

    exported = client.get(
        "/api/v1/captures/export",
        params={"from": "2026-11-01T00:00:00Z", "to": "2026-11-30T23:59:59Z"},
        headers=common,
    )
    assert exported.status_code == 200, exported.text
    names = zipfile.ZipFile(io.BytesIO(exported.content)).namelist()
    assert any(name.startswith("trap-comum/") for name in names)
    assert not any(name.startswith("trap-01/") for name in names)
    assert client.get("/api/v1/captures/export", headers=admin).status_code == 422
