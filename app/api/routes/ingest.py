import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.deps import get_gateway
from app.db.models import Capture, Firmware, Gateway, Metric
from app.db.session import get_db
from app.schemas import FirmwareOut, IngestOut, MetricIn
from app.services.capture_events import capture_broker, capture_event
from app.services.devices import as_utc, get_or_create_device, normalize_code, parse_iso_datetime
from app.services.firmware import needs_update, require_target, resolve_firmware
from app.services.storage import MAX_IMAGE_BYTES, delete_capture_file, save_jpeg

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _touch(gateway: Gateway, device, moment: datetime) -> None:
    gateway.last_seen_at = moment
    device.last_seen_at = moment


@router.post("/images", response_model=IngestOut, status_code=201)
async def ingest_image(
    device_code: str = Form(),
    captured_at: str = Form(),
    image: UploadFile = File(),
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

    device = get_or_create_device(db, code)
    now = datetime.now(timezone.utc)
    capture_id = uuid.uuid4()
    relative = save_jpeg(code, capture_id, taken_at, content)
    capture = Capture(
        id=capture_id,
        device_id=device.id,
        captured_at=taken_at,
        received_at=now,
        file_path=relative,
        size_bytes=len(content),
        label="unlabeled",
    )
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
