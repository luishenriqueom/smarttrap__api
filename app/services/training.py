import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Capture, CaptureAnnotation, Device, Species, TrainedModel, User
from app.db.session import SessionLocal
from app.services.devices import is_superadmin
from app.services.storage import resolve_capture
from app.services.windows import WINDOW, clip_box, window_origins

INGEST_URL = "https://ingestion.edgeimpulse.com/api/training/files"
STUDIO = "https://studio.edgeimpulse.com/v1/api"
NEGATIVE_CAP_RATIO = 1


def models_root() -> Path:
    root = settings.models_dir
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def run_training(model_id) -> None:
    session = SessionLocal()
    try:
        _train(session, model_id)
    except Exception as exc:
        session.rollback()
        row = session.get(TrainedModel, model_id)
        if row is not None:
            row.status = "failed"
            row.error = str(exc)[:2000]
            session.commit()
    finally:
        session.close()


def _train(session: Session, model_id) -> None:
    row = session.get(TrainedModel, model_id)
    if row is None:
        return
    if not settings.ei_api_key or not settings.ei_project_id or not settings.ei_learn_id:
        row.status = "failed"
        row.error = "Edge Impulse não está configurado"
        session.commit()
        return
    species = list(session.scalars(select(Species).order_by(Species.position, Species.name)).all())
    if not species:
        row.status = "failed"
        row.error = "Cadastre ao menos uma espécie antes de treinar"
        session.commit()
        return
    labels = [item.name for item in species]
    row.class_labels = labels
    tiles = _tiles(session, {item.id: item.name for item in species})
    positives = [tile for tile in tiles if tile["boxes"]]
    if not positives:
        row.status = "failed"
        row.error = "Nenhuma praga marcada para treinar"
        session.commit()
        return
    negatives = [tile for tile in tiles if not tile["boxes"]]
    chosen = positives + negatives[: max(1, len(positives) * NEGATIVE_CAP_RATIO)]
    headers = {"x-api-key": settings.ei_api_key}
    with httpx.Client(timeout=120) as client:
        _studio(
            client,
            "POST",
            "",
            headers,
            json={"labelingMethod": "object_detection"},
        )
        for index, tile in enumerate(chosen):
            extra = {"x-bounding-boxes": json.dumps(tile["boxes"])} if tile["boxes"] else {"x-no-label": "1"}
            response = client.post(
                INGEST_URL,
                headers={**headers, **extra},
                files={"data": (f"tile_{index:05d}.jpg", tile["jpeg"], "image/jpeg")},
            )
            if response.status_code >= 300:
                raise RuntimeError(f"Falha ao enviar recorte: {response.status_code} {response.text[:240]}")
        train = _studio(
            client,
            "POST",
            f"/jobs/train/keras/{settings.ei_learn_id}",
            headers,
            json={"trainingCycles": 30, "learningRate": 0.001},
        )
        train_body = train.json()
        if not train_body.get("success", True):
            raise RuntimeError(train_body.get("error") or "O treino não iniciou")
        job_id = train_body.get("id")
        _wait_job(client, headers, job_id)
        build = _studio(
            client,
            "POST",
            "/jobs/build-ondevice-model",
            headers,
            params={"type": "zip"},
            json={"engine": "tflite", "modelType": "int8"},
        )
        build_body = build.json()
        if not build_body.get("success", True):
            raise RuntimeError(build_body.get("error") or "A exportação não iniciou")
        _wait_job(client, headers, build_body.get("id"))
        download = client.get(
            f"{STUDIO}/{settings.ei_project_id}/deployment/download",
            params={"type": "zip", "engine": "tflite", "modelType": "int8"},
            headers=headers,
        )
        download.raise_for_status()
        model_bytes = _tflite_from_zip(download.content)
    digest = hashlib.sha256(model_bytes).hexdigest()
    relative = f"{row.id}.tflite"
    target = models_root() / relative
    target.write_bytes(model_bytes)
    meta = models_root() / f"{row.id}.json"
    meta.write_text(
        json.dumps(
            {"sha256": digest, "window": WINDOW, "stride": 64, "classes": labels, "threshold": 0.6},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    row.file_path = relative
    row.sha256 = digest
    row.class_labels = labels
    row.status = "ready"
    row.error = None
    row.metrics = {"tiles": len(chosen), "positives": len(positives)}
    session.commit()


def _studio(client: httpx.Client, method: str, path: str, headers: dict, **kwargs) -> httpx.Response:
    response = client.request(
        method,
        f"{STUDIO}/{settings.ei_project_id}{path}",
        headers={**headers, "Content-Type": "application/json"},
        **kwargs,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "A chave do Edge Impulse não tem permissão para treinar. "
            "No projeto, abra Dashboard, Keys, Add new API key, escolha o papel Admin (full access) "
            "e substitua a EI_API_KEY. A chave atual envia fotos, mas não inicia o treino."
        )
    response.raise_for_status()
    return response


def _wait_job(client: httpx.Client, headers: dict, job_id) -> None:
    if job_id is None:
        raise RuntimeError("O Edge Impulse não devolveu o identificador do job")
    for _ in range(240):
        response = client.get(f"{STUDIO}/{settings.ei_project_id}/jobs/{job_id}/status", headers=headers)
        response.raise_for_status()
        body = response.json()
        job = body.get("job") or {}
        if job.get("finished"):
            if not job.get("finishedSuccessful", False):
                raise RuntimeError("O job do Edge Impulse falhou")
            return
        import time

        time.sleep(5)
    raise RuntimeError("O job do Edge Impulse excedeu o tempo de espera")


def _tflite_from_zip(content: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".tflite")]
        if not names:
            raise RuntimeError("O pacote do Edge Impulse não trouxe um .tflite")
        return archive.read(names[0])


def _tiles(session: Session, names: dict) -> list[dict]:
    rows = session.execute(
        select(Capture).where(Capture.deleted_at.is_(None), Capture.width.is_not(None), Capture.height.is_not(None))
    ).scalars()
    tiles = []
    for capture in rows:
        boxes = list(
            session.scalars(
                select(CaptureAnnotation).where(
                    CaptureAnnotation.capture_id == capture.id,
                    CaptureAnnotation.source == "human",
                )
            ).all()
        )
        if capture.label == "without_pest":
            boxes = []
        if not boxes and capture.label != "without_pest":
            continue
        path = resolve_capture(capture.file_path)
        if not path.is_file():
            continue
        image = Image.open(path).convert("RGB")
        for origin_y in window_origins(capture.height or 0):
            for origin_x in window_origins(capture.width or 0):
                translated = []
                for box in boxes:
                    clipped = clip_box(box.x, box.y, box.width, box.height, origin_x, origin_y)
                    if clipped is None:
                        continue
                    label = names.get(box.species_id, "")
                    if not label:
                        continue
                    translated.append(
                        {
                            "label": label,
                            "x": clipped[0],
                            "y": clipped[1],
                            "width": clipped[2],
                            "height": clipped[3],
                        }
                    )
                canvas = Image.new("RGB", (WINDOW, WINDOW))
                piece = image.crop((origin_x, origin_y, origin_x + WINDOW, origin_y + WINDOW))
                canvas.paste(piece, (0, 0))
                buffer = io.BytesIO()
                canvas.save(buffer, format="JPEG", quality=90)
                tiles.append({"jpeg": buffer.getvalue(), "boxes": translated})
    return tiles


def visible_training_count(session: Session, user: User) -> int:
    filters = [Capture.deleted_at.is_(None), CaptureAnnotation.source == "human"]
    if not is_superadmin(user):
        filters.append(Device.owner_id == user.id)
    return session.scalar(
        select(func.count()).select_from(CaptureAnnotation).join(Capture).join(Device).where(*filters)
    ) or 0
