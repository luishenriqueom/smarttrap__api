from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_superadmin
from app.db.models import Firmware, User
from app.db.session import get_db
from app.schemas import FirmwareOut, FirmwarePublishOut
from app.services.firmware import commit_firmware, stage_firmware

router = APIRouter(prefix="/firmware", tags=["firmware"])


def _to_out(row: Firmware) -> FirmwareOut:
    return FirmwareOut(
        target=row.target,
        version=row.version,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


@router.get("", response_model=list[FirmwareOut])
def list_firmware(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
) -> list[FirmwareOut]:
    rows = db.scalars(select(Firmware).order_by(Firmware.target)).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=FirmwarePublishOut, status_code=201)
async def publish_firmware(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
    smarttrap_version: int | None = Form(default=None),
    heltec_version: int | None = Form(default=None),
    smarttrap_bin: UploadFile | None = File(default=None),
    heltec_bin: UploadFile | None = File(default=None),
) -> FirmwarePublishOut:
    staged = []
    pairs = (
        ("smarttrap", smarttrap_version, smarttrap_bin),
        ("heltec", heltec_version, heltec_bin),
    )
    provided = [(target, version, upload) for target, version, upload in pairs if version is not None or _has_file(upload)]
    if not provided:
        raise HTTPException(status_code=422, detail="Envie ao menos um firmware")
    try:
        for target, version, upload in provided:
            if version is None or upload is None or not _has_file(upload):
                raise HTTPException(status_code=422, detail=f"Envie a versão e o arquivo de {target} juntos")
            staged.append(await stage_firmware(target, version, upload))
        rows = commit_firmware(db, staged)
    except Exception:
        for item in staged:
            item.temp.unlink(missing_ok=True)
        raise
    return FirmwarePublishOut(items=[_to_out(row) for row in rows])


def _has_file(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)
