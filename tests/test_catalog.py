from app.db.models import TrainedModel
from app.db.session import SessionLocal
from app.services.training import models_root
from tests.helpers import login


def test_species_can_be_renamed_and_removed(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post("/api/v1/species", json={"name": "mosca"}, headers=admin)
    assert created.status_code == 201, created.text
    species_id = created.json()["id"]

    renamed = client.patch(f"/api/v1/species/{species_id}", json={"name": "mosca-da-fruta"}, headers=admin)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "mosca-da-fruta"

    conflict = client.post("/api/v1/species", json={"name": "Mosca-da-fruta"}, headers=admin)
    assert conflict.status_code == 409

    removed = client.delete(f"/api/v1/species/{species_id}", headers=admin)
    assert removed.status_code == 204
    listed = client.get("/api/v1/species", headers=admin)
    assert listed.json() == []


def test_device_coordinates_are_saved_as_a_pair(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    created = client.post(
        "/api/v1/devices",
        json={"code": "geo-1", "name": "Geo", "latitude": -5.05, "longitude": -42.8},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    assert created.json()["latitude"] == -5.05
    assert created.json()["longitude"] == -42.8

    missing = client.post(
        "/api/v1/devices",
        json={"code": "geo-2", "name": "Geo 2", "latitude": -5.05},
        headers=admin,
    )
    assert missing.status_code == 422

    cleared = client.patch(
        f"/api/v1/devices/{created.json()['id']}",
        json={"latitude": None, "longitude": None},
        headers=admin,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["latitude"] is None
    assert cleared.json()["longitude"] is None


def test_training_rejects_an_inverted_period(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    response = client.post(
        "/api/v1/models/train",
        json={"images_from": "2026-11-10T00:00:00Z", "images_to": "2026-11-01T00:00:00Z"},
        headers=admin,
    )
    assert response.status_code == 422
    assert "período" in response.json()["detail"]


def test_model_can_be_deleted_unless_it_is_training_or_assigned(client):
    admin = login(client, "admin@smarttrap.local", "admin123")
    session = SessionLocal()
    ready = TrainedModel(status="ready", class_labels=["mosca"], sha256="abc", file_path="pending.tflite")
    training = TrainedModel(status="training", class_labels=[])
    session.add(ready)
    session.add(training)
    session.commit()
    ready_id = ready.id
    training_id = training.id
    target = models_root() / f"{ready_id}.tflite"
    target.write_bytes(b"model")
    ready.file_path = f"{ready_id}.tflite"
    session.commit()
    session.close()

    blocked = client.delete(f"/api/v1/models/{training_id}", headers=admin)
    assert blocked.status_code == 409

    removed = client.delete(f"/api/v1/models/{ready_id}", headers=admin)
    assert removed.status_code == 204, removed.text
    assert not target.exists()

    device = client.post("/api/v1/devices", json={"code": "geo-model", "name": "Com modelo"}, headers=admin)
    assert device.status_code == 201, device.text
    session = SessionLocal()
    assigned = TrainedModel(status="ready", class_labels=["mosca"])
    session.add(assigned)
    session.commit()
    assigned_id = str(assigned.id)
    session.close()
    linked = client.patch(f"/api/v1/devices/{device.json()['id']}", json={"model_id": assigned_id}, headers=admin)
    assert linked.status_code == 200, linked.text
    refused = client.delete(f"/api/v1/models/{assigned_id}", headers=admin)
    assert refused.status_code == 409
