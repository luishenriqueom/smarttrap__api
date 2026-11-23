import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_gateway
from app.db.models import Capture, CaptureAnnotation, Device, Firmware, Gateway, Metric, Species, TrainedModel
from app.db.session import get_db
from app.schemas import ClockIn, ClockSyncList, ClockSyncItem, FirmwareOut, FrameConfigOut, IngestOut, MetricIn, ModelMetaOut
from app.services.capture_events import capture_broker, capture_event
from app.services.devices import (
    apply_reported_clock,
    as_utc,
    get_or_create_device,
    normalize_code,
    parse_device_time,
    parse_iso_datetime,
)
from app.services.firmware import needs_update, require_target, resolve_firmware
from app.services.framesize import FRAME_SIZES, recorded_quality, recorded_size
from app.services.storage import MAX_IMAGE_BYTES, delete_capture_file, save_jpeg
from app.services.training import models_root

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _touch(gateway: Gateway, device, moment: datetime) -> None:
    gateway.last_seen_at = moment
    device.last_seen_at = moment


@router.post("/images", response_model=IngestOut, status_code=201)
async def ingest_image(
    device_code: str = Form(),
    captured_at: str = Form(),
    image: UploadFile = File(),
    frame_size: str | None = Form(default=None),
    jpeg_quality: str | None = Form(default=None),
    detections: str | None = Form(default=None),
    device_time: str | None = Form(default=None),
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> IngestOut:
    code = normalize_code(device_code)
    taken_at = parse_iso_datetime(captured_at)
    content = await image.read(MAX_IMAGE_BYTES + 1)
    await image.close()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="A imagem excede 5 MB")
    if len(content) < 3 or content[:3] != b"\xff\xd8\xff":
        raise HTTPException(status_code=422, detail="O arquivo precisa ser um JPEG")
    token, width, height = recorded_size(content, frame_size)
    quality = recorded_quality(jpeg_quality)

    device = get_or_create_device(db, code)
    now = datetime.now(timezone.utc)
    apply_reported_clock(device, parse_device_time(device_time), now)
    capture_id = uuid.uuid4()
    relative = save_jpeg(code, capture_id, taken_at, content)
    capture = Capture(
        id=capture_id,
        device_id=device.id,
        captured_at=taken_at,
        received_at=now,
        file_path=relative,
        size_bytes=len(content),
        frame_size=token,
        jpeg_quality=quality,
        width=width,
        height=height,
        label="unlabeled",
    )
    _store_detections(db, capture, detections)
    _touch(gateway, device, now)
    db.add(capture)
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_capture_file(relative)
        raise
    db.refresh(capture)
    capture_broker.publish(capture_event(capture, device))
    return IngestOut(id=capture_id)


@router.post("/metrics", response_model=IngestOut, status_code=201)
def ingest_metric(
    body: MetricIn,
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> IngestOut:
    code = normalize_code(body.device_code)
    device = get_or_create_device(db, code)
    now = datetime.now(timezone.utc)
    apply_reported_clock(device, body.device_time, now)
    metric = Metric(
        device_id=device.id,
        recorded_at=as_utc(body.recorded_at),
        received_at=now,
        pest_count=body.pest_count,
        confidence=body.confidence,
        battery_v=body.battery_v,
        rssi=body.rssi,
        snr=body.snr,
        raw_payload=body.model_dump(mode="json"),
    )
    _touch(gateway, device, now)
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return IngestOut(id=metric.id)


@router.get("/config", response_model=FrameConfigOut, response_model_exclude_none=True)
def device_config(
    device_code: str = Query(min_length=1),
    device_time: int | None = Query(default=None, ge=0, le=0xFFFFFFFF),
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> FrameConfigOut:
    code = normalize_code(device_code)
    device = get_or_create_device(db, code)
    now = datetime.now(timezone.utc)
    apply_reported_clock(device, device_time, now)
    _touch(gateway, device, now)
    db.commit()
    width, height = FRAME_SIZES[device.frame_size]
    return FrameConfigOut(
        frame_size=device.frame_size,
        width=width,
        height=height,
        jpeg_quality=device.jpeg_quality,
        sleep_seconds=device.sleep_seconds,
        set_time=int(now.timestamp()) if device.clock_sync_requested else None,
    )


@router.post("/clock", status_code=204)
def ingest_clock(
    body: ClockIn,
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> Response:
    device = get_or_create_device(db, normalize_code(body.device_code))
    now = datetime.now(timezone.utc)
    apply_reported_clock(device, body.device_time, now)
    _touch(gateway, device, now)
    db.commit()
    return Response(status_code=204)


@router.get("/clock-sync", response_model=ClockSyncList)
def pending_clock_sync(
    db: Session = Depends(get_db),
    _gateway: Gateway = Depends(get_gateway),
) -> ClockSyncList:
    rows = db.scalars(select(Device).where(Device.clock_sync_requested.is_(True)).order_by(Device.code)).all()
    return ClockSyncList(items=[ClockSyncItem(device_code=row.code) for row in rows])


def _assigned_model(db: Session, device_code: str) -> tuple[object, TrainedModel]:
    code = normalize_code(device_code)
    device = get_or_create_device(db, code)
    if device.model_id is None:
        raise HTTPException(status_code=404, detail="Nenhum modelo atribuído")
    trained = db.get(TrainedModel, device.model_id)
    if trained is None or trained.status != "ready" or not trained.file_path or not trained.sha256:
        raise HTTPException(status_code=404, detail="Nenhum modelo pronto")
    return device, trained


@router.get("/models/current", response_model=ModelMetaOut)
def current_model_meta(
    device_code: str = Query(min_length=1),
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> ModelMetaOut:
    device, trained = _assigned_model(db, device_code)
    _touch(gateway, device, datetime.now(timezone.utc))
    db.commit()
    return ModelMetaOut(
        sha256=trained.sha256 or "",
        window=trained.window,
        stride=trained.stride,
        classes=list(trained.class_labels or []),
    )


@router.get("/models/current/file")
def current_model_file(
    device_code: str = Query(min_length=1),
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> FileResponse:
    device, trained = _assigned_model(db, device_code)
    path = (models_root() / (trained.file_path or "")).resolve()
    if not path.is_file() or not path.is_relative_to(models_root()):
        raise HTTPException(status_code=404, detail="Arquivo do modelo não encontrado")
    _touch(gateway, device, datetime.now(timezone.utc))
    db.commit()
    return FileResponse(path, media_type="application/octet-stream", filename="model.tflite")


def _store_detections(db: Session, capture: Capture, raw: str | None) -> None:
    if raw is None or raw.strip() == "":
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Detecções inválidas") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("boxes"), list):
        raise HTTPException(status_code=422, detail="Detecções inválidas")
    stored = 0
    for item in payload["boxes"]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("species", "")).strip()
        species = db.scalar(select(Species).where(Species.name == name))
        if species is None:
            continue
        try:
            box = CaptureAnnotation(
                capture_id=capture.id,
                species_id=species.id,
                x=int(item["x"]),
                y=int(item["y"]),
                width=int(item["width"]),
                height=int(item["height"]),
                source="device",
                confidence=None if item.get("confidence") is None else float(item["confidence"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Detecções inválidas") from exc
        if box.x < 0 or box.y < 0 or box.width < 1 or box.height < 1:
            continue
        db.add(box)
        stored += 1
    if stored:
        capture.label = "with_pest"


def _published(db: Session, target: str) -> Firmware:
    row = db.get(Firmware, require_target(target))
    if row is None:
        raise HTTPException(status_code=404, detail="Nenhum firmware publicado")
    return row


def _touch_gateway(db: Session, gateway: Gateway) -> None:
    gateway.last_seen_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/firmware/{target}/bin")
def download_firmware(
    target: str,
    current: int | None = Query(default=None, ge=0, le=65535),
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> Response:
    row = _published(db, target)
    _touch_gateway(db, gateway)
    if not needs_update(current, row.version):
        return Response(status_code=304)
    path = resolve_firmware(row.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo de firmware ausente")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
        headers={
            "x-MD5": row.md5,
            "X-Firmware-Version": str(row.version),
            "X-Firmware-Sha256": row.sha256,
            "Cache-Control": "no-store",
        },
    )


@router.get("/firmware/{target}", response_model=FirmwareOut)
def firmware_meta(
    target: str,
    current: int | None = Query(default=None, ge=0, le=65535),
    db: Session = Depends(get_db),
    gateway: Gateway = Depends(get_gateway),
) -> FirmwareOut:
    row = _published(db, target)
    _touch_gateway(db, gateway)
    return FirmwareOut(
        target=row.target,
        version=row.version,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
        update=needs_update(current, row.version),
    )
