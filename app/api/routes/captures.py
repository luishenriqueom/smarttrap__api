import csv
import io
import json
import queue
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import bearer_scheme, get_current_user, require_writer
from app.db.models import Capture, CaptureAnnotation, Device, Species, User
from app.db.session import SessionLocal, get_db
from app.schemas import (
    AnnotationCreate,
    AnnotationOut,
    CaptureDiscardResult,
    CaptureIds,
    CaptureImportResult,
    CaptureOut,
    CapturePage,
    CaptureRestoreResult,
    CaptureUpdate,
)
from app.services.capture_events import capture_broker, capture_event, visible_to
from app.services.devices import get_visible_device, is_superadmin, parse_iso_datetime
from app.services.framesize import jpeg_dimensions
from app.services.storage import MAX_IMAGE_BYTES, delete_capture_file, resolve_capture, save_jpeg

router = APIRouter(prefix="/captures", tags=["captures"])

LABELS = {"unlabeled", "with_pest", "without_pest"}
MAX_EXPORT = 2000


def _filters(user: User, device_id: UUID | None, start: datetime | None, end: datetime | None) -> list:
    filters = [Capture.deleted_at.is_(None)]
    if not is_superadmin(user):
        filters.append(Device.owner_id == user.id)
    if device_id is not None:
        filters.append(Capture.device_id == device_id)
    if start is not None:
        filters.append(Capture.captured_at >= start)
    if end is not None:
        filters.append(Capture.captured_at <= end)
    return filters


def _to_out(capture: Capture, device: Device) -> CaptureOut:
    return CaptureOut(
        id=capture.id,
        device_id=capture.device_id,
        device_name=device.name,
        device_code=device.code,
        captured_at=capture.captured_at,
        received_at=capture.received_at,
        size_bytes=capture.size_bytes,
        frame_size=capture.frame_size,
        jpeg_quality=capture.jpeg_quality,
        width=capture.width,
        height=capture.height,
        manual_count=capture.manual_count,
        label=capture.label,
        notes=capture.notes,
    )


@router.get("", response_model=CapturePage)
def list_captures(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_id: UUID | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CapturePage:
    filters = _filters(user, device_id, start, end)
    total = db.scalar(select(func.count()).select_from(Capture).join(Device).where(*filters)) or 0
    rows = db.execute(
        select(Capture, Device)
        .join(Device, Capture.device_id == Device.id)
        .where(*filters)
        .order_by(Capture.captured_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return CapturePage(
        items=[_to_out(capture, device) for capture, device in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export")
def export_captures(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_id: UUID | None = None,
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
) -> StreamingResponse:
    from fastapi import HTTPException

    if end < start:
        raise HTTPException(status_code=422, detail="O fim do período é anterior ao início")
    filters = _filters(user, device_id, start, end)
    total = db.scalar(select(func.count()).select_from(Capture).join(Device).where(*filters)) or 0
    if total == 0:
        raise HTTPException(status_code=404, detail="Nenhuma imagem neste período")
    if total > MAX_EXPORT:
        raise HTTPException(status_code=413, detail="O período tem imagens demais. Reduza o intervalo")
    rows = db.execute(
        select(Capture, Device)
        .join(Device, Capture.device_id == Device.id)
        .where(*filters)
        .order_by(Capture.captured_at.asc(), Capture.id.asc())
    ).all()

    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    written = 0
    with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_STORED) as archive:
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(
            ["arquivo", "codigo", "armadilha", "capturado_em", "rotulo", "contagem_manual", "notas", "resolucao", "qualidade_jpeg"]
        )
        for capture, device in rows:
            path = resolve_capture(capture.file_path)
            if not path.is_file():
                continue
            name = _archive_name(device.code, capture.captured_at, capture.id)
            archive.write(path, name)
            writer.writerow(
                [
                    name,
                    device.code,
                    device.name,
                    _utc(capture.captured_at).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    capture.label,
                    "" if capture.manual_count is None else capture.manual_count,
                    capture.notes or "",
                    "" if capture.width is None or capture.height is None else f"{capture.width}x{capture.height}",
                    "" if capture.jpeg_quality is None else capture.jpeg_quality,
                ]
            )
            written += 1
        if written == 0:
            raise HTTPException(status_code=404, detail="Nenhuma imagem neste período")
        archive.writestr("manifest.csv", manifest.getvalue())
        archive.writestr("annotations.json", json.dumps(_export_boxes(db, rows), ensure_ascii=False))
    spool.seek(0)
    filename = f"dataset_{_utc(start):%Y-%m-%d}_{_utc(end):%Y-%m-%d}.zip"

    def chunks():
        while True:
            block = spool.read(64 * 1024)
            if not block:
                break
            yield block

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/discard", response_model=CaptureDiscardResult)
def discard_captures(
    body: CaptureIds,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> CaptureDiscardResult:
    captures = _visible_active(db, user, body.ids)
    moment = datetime.now(timezone.utc)
    for capture in captures:
        capture.deleted_at = moment
    db.commit()
    return CaptureDiscardResult(discarded=len(captures))


@router.post("/restore", response_model=CaptureRestoreResult)
def restore_captures(
    body: CaptureIds,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> CaptureRestoreResult:
    captures = _visible_deleted(db, user, body.ids)
    for capture in captures:
        capture.deleted_at = None
    db.commit()
    return CaptureRestoreResult(restored=len(captures))


@router.post("/import", response_model=CaptureImportResult, status_code=201)
async def import_captures(
    device_id: UUID = Form(),
    images: list[UploadFile] = File(),
    captured_at: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> CaptureImportResult:
    if not images:
        raise HTTPException(status_code=422, detail="Escolha ao menos uma foto")
    if len(images) > 20:
        raise HTTPException(status_code=422, detail="Envie no máximo 20 fotos por vez")
    if captured_at and len(captured_at) != len(images):
        raise HTTPException(status_code=422, detail="Cada foto precisa da própria data")
    device = get_visible_device(db, user, device_id)
    now = datetime.now(timezone.utc)
    saved: list[str] = []
    created: list[Capture] = []
    skipped = 0
    try:
        for index, image in enumerate(images):
            content = await image.read(MAX_IMAGE_BYTES + 1)
            await image.close()
            filename = (image.filename or "").replace("\\", "/").split("/")[-1]
            if len(content) > MAX_IMAGE_BYTES or len(content) < 3 or content[:3] != b"\xff\xd8\xff":
                skipped += 1
                continue
            taken_at = parse_iso_datetime(captured_at[index]) if captured_at else now
            capture_id = uuid.uuid4()
            relative = save_jpeg(device.code, capture_id, taken_at, content)
            saved.append(relative)
            width, height = jpeg_dimensions(content) or (None, None)
            capture = Capture(
                id=capture_id,
                device_id=device.id,
                captured_at=taken_at,
                received_at=now,
                file_path=relative,
                size_bytes=len(content),
                width=width,
                height=height,
                label="unlabeled",
                notes=filename or None,
            )
            db.add(capture)
            created.append(capture)
        if not created:
            raise HTTPException(status_code=422, detail="Nenhuma das fotos é um JPEG")
        db.commit()
    except HTTPException:
        db.rollback()
        for relative in saved:
            delete_capture_file(relative)
        raise
    except Exception:
        db.rollback()
        for relative in saved:
            delete_capture_file(relative)
        raise
    for capture in created:
        db.refresh(capture)
        capture_broker.publish(capture_event(capture, device))
    return CaptureImportResult(imported=len(created), skipped=skipped)


@router.get("/stream")
def stream_captures(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> StreamingResponse:
    db = SessionLocal()
    try:
        user = get_current_user(credentials, db)
        viewer_id = user.id
        viewer_role = user.role
    finally:
        db.close()

    events = capture_broker.subscribe()

    def generate():
        try:
            yield ": ok\n\n"
            while True:
                try:
                    event = events.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                if not visible_to(viewer_role, viewer_id, event):
                    continue
                payload = {key: value for key, value in event.items() if key != "owner_id"}
                yield f"event: capture\ndata: {json.dumps(payload)}\n\n"
        finally:
            capture_broker.unsubscribe(events)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{capture_id}", response_model=CaptureOut)
def get_capture(
    capture_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CaptureOut:
    capture, device = _load(db, user, capture_id)
    return _to_out(capture, device)


@router.get("/{capture_id}/image")
def get_capture_image(
    capture_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    capture, _device = _load(db, user, capture_id)
    path = resolve_capture(capture.file_path)
    if not path.is_file():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{capture_id}/annotations", response_model=list[AnnotationOut])
def list_annotations(
    capture_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AnnotationOut]:
    capture, _device = _load(db, user, capture_id)
    return _annotation_out(db, capture.id)


@router.post("/{capture_id}/annotations", response_model=AnnotationOut, status_code=201)
def create_annotation(
    capture_id: UUID,
    body: AnnotationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> AnnotationOut:
    from fastapi import HTTPException

    capture, _device = _load(db, user, capture_id)
    species = db.get(Species, body.species_id)
    if species is None:
        raise HTTPException(status_code=422, detail="Espécie não encontrada")
    if capture.width is not None and body.x + body.width > capture.width:
        raise HTTPException(status_code=422, detail="A caixa passa da largura da foto")
    if capture.height is not None and body.y + body.height > capture.height:
        raise HTTPException(status_code=422, detail="A caixa passa da altura da foto")
    row = CaptureAnnotation(
        capture_id=capture.id,
        species_id=species.id,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
        source="human",
    )
    capture.label = "with_pest"
    db.add(row)
    db.commit()
    db.refresh(row)
    return _one_annotation(row, species)


@router.delete("/{capture_id}/annotations/{annotation_id}", status_code=204)
def delete_annotation(
    capture_id: UUID,
    annotation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> None:
    from fastapi import HTTPException

    capture, _device = _load(db, user, capture_id)
    row = db.get(CaptureAnnotation, annotation_id)
    if row is None or row.capture_id != capture.id or row.source != "human":
        raise HTTPException(status_code=404, detail="Marcação não encontrada")
    db.delete(row)
    db.flush()
    remaining = db.scalar(
        select(func.count()).select_from(CaptureAnnotation).where(
            CaptureAnnotation.capture_id == capture.id,
            CaptureAnnotation.source == "human",
        )
    )
    if remaining == 0 and capture.label == "with_pest":
        capture.label = "unlabeled"
    db.commit()


@router.patch("/{capture_id}", response_model=CaptureOut)
def update_capture(
    capture_id: UUID,
    body: CaptureUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> CaptureOut:
    capture, _device = _load(db, user, capture_id)
    changes = body.model_fields_set
    if "manual_count" in changes:
        capture.manual_count = body.manual_count
    if "label" in changes and body.label is not None:
        if body.label not in LABELS:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="Rótulo inválido")
        capture.label = body.label
    if "notes" in changes:
        capture.notes = body.notes.strip() if body.notes else None
    db.commit()
    db.refresh(capture)
    device = db.get(Device, capture.device_id)
    return _to_out(capture, device)


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _archive_name(device_code: str, captured_at: datetime, capture_id: UUID) -> str:
    code = re.sub(r"[^A-Za-z0-9_-]", "_", device_code).strip("_") or "armadilha"
    stamp = _utc(captured_at).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{code}/{stamp}_{capture_id.hex[:8]}.jpg"


def _export_boxes(db: Session, rows: list) -> dict:
    payload = {}
    for capture, device in rows:
        name = _archive_name(device.code, capture.captured_at, capture.id)
        payload[name] = [
            {
                "species": item.species_name,
                "x": item.x,
                "y": item.y,
                "width": item.width,
                "height": item.height,
                "source": item.source,
            }
            for item in _annotation_out(db, capture.id)
        ]
    return payload


def _annotation_out(db: Session, capture_id: UUID) -> list[AnnotationOut]:
    rows = db.execute(
        select(CaptureAnnotation, Species)
        .join(Species, CaptureAnnotation.species_id == Species.id)
        .where(CaptureAnnotation.capture_id == capture_id)
        .order_by(CaptureAnnotation.created_at.asc())
    ).all()
    return [_one_annotation(row, species) for row, species in rows]


def _one_annotation(row: CaptureAnnotation, species: Species) -> AnnotationOut:
    return AnnotationOut(
        id=row.id,
        capture_id=row.capture_id,
        species_id=species.id,
        species_name=species.name,
        x=row.x,
        y=row.y,
        width=row.width,
        height=row.height,
        source=row.source,
        confidence=row.confidence,
    )


def _owned(user: User, device: Device) -> bool:
    return is_superadmin(user) or device.owner_id == user.id


def _visible_active(db: Session, user: User, ids: list[UUID]) -> list[Capture]:
    return _visible_by_state(db, user, ids, deleted=False)


def _visible_deleted(db: Session, user: User, ids: list[UUID]) -> list[Capture]:
    return _visible_by_state(db, user, ids, deleted=True)


def _visible_by_state(db: Session, user: User, ids: list[UUID], deleted: bool) -> list[Capture]:
    from fastapi import HTTPException

    wanted = list(dict.fromkeys(ids))
    state = Capture.deleted_at.is_not(None) if deleted else Capture.deleted_at.is_(None)
    rows = db.execute(
        select(Capture, Device)
        .join(Device, Capture.device_id == Device.id)
        .where(Capture.id.in_(wanted), state)
    ).all()
    captures = [capture for capture, device in rows if _owned(user, device)]
    if len(captures) != len(wanted):
        raise HTTPException(status_code=404, detail="Captura não encontrada")
    return captures


def _load(db: Session, user: User, capture_id: UUID) -> tuple[Capture, Device]:
    from fastapi import HTTPException

    row = db.execute(
        select(Capture, Device)
        .join(Device, Capture.device_id == Device.id)
        .where(Capture.id == capture_id, Capture.deleted_at.is_(None))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Captura não encontrada")
    capture, device = row
    if not is_superadmin(user) and device.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Captura não encontrada")
    get_visible_device(db, user, device.id)
    return capture, device
