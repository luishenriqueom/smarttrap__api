import io
import json
import zipfile

from app.services.windows import clip_box, window_origins
from tests.helpers import GATEWAY, JPEG, login


def test_window_origins_cover_the_photo_without_a_gap():
    origins = window_origins(800)
    assert origins[0] == 0
    assert origins[-1] == 800 - 96
    assert all(origins[index + 1] - origins[index] <= 64 for index in range(len(origins) - 1))
    assert window_origins(1600)[-1] == 1600 - 96
    assert window_origins(50) == [0]


def test_clip_box_moves_into_the_window():
    assert clip_box(10, 10, 20, 20, 0, 0) == (10, 10, 20, 20)
    assert clip_box(90, 90, 20, 20, 64, 64) == (26, 26, 20, 20)
    assert clip_box(150, 150, 20, 20, 64, 64) == (86, 86, 10, 10)
    assert clip_box(0, 0, 10, 10, 64, 64) is None


def test_sleep_interval_is_configurable_and_defaults_to_five_minutes(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post("/api/v1/devices", json={"code": "trap-sono", "name": "Sono"}, headers=admin)
    assert created.status_code == 201, created.text
    assert created.json()["sleep_seconds"] == 300

    updated = client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"sleep_seconds": 600},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    config = client.get("/api/v1/ingest/config", params={"device_code": "trap-sono"}, headers=GATEWAY)
    assert config.json()["sleep_seconds"] == 600
    assert client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"sleep_seconds": 30},
        headers=admin,
    ).status_code == 422


def test_human_box_is_exported_and_device_box_arrives_with_the_photo(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    species = client.post("/api/v1/species", json={"name": "mosca"}, headers=admin)
    assert species.status_code == 201, species.text
    species_id = species.json()["id"]
    uploaded = client.post(
        "/api/v1/ingest/images",
        data={"device_code": "trap-01", "captured_at": "2026-11-02T14:22:03Z"},
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    capture_id = uploaded.json()["id"]
    marked = client.post(
        f"/api/v1/captures/{capture_id}/annotations",
        json={"species_id": species_id, "x": 4, "y": 6, "width": 12, "height": 10},
        headers=admin,
    )
    assert marked.status_code == 201, marked.text
    assert client.get(f"/api/v1/captures/{capture_id}", headers=admin).json()["label"] == "with_pest"

    exported = client.get(
        "/api/v1/captures/export",
        params={"from": "2026-11-01T00:00:00Z", "to": "2026-11-30T23:59:59Z"},
        headers=admin,
    )
    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    boxes = json.loads(archive.read("annotations.json"))
    saved = next(iter(boxes.values()))
    assert saved[0]["species"] == "mosca"
    assert saved[0]["source"] == "human"

    detected = client.post(
        "/api/v1/ingest/images",
        data={
            "device_code": "trap-01",
            "captured_at": "2026-11-02T15:00:00Z",
            "detections": json.dumps({"boxes": [{"species": "mosca", "x": 8, "y": 9, "width": 8, "height": 8, "confidence": 0.7}]}),
        },
        files={"image": ("cap.jpg", JPEG, "image/jpeg")},
        headers=GATEWAY,
    )
    assert detected.status_code == 201, detected.text
    listed = client.get(f"/api/v1/captures/{detected.json()['id']}/annotations", headers=admin)
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["source"] == "device"
    assert listed.json()[0]["species_name"] == "mosca"


def test_training_requires_edge_impulse_configuration(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    response = client.post("/api/v1/models/train", headers=admin)
    assert response.status_code == 422, response.text
