from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_writer
from app.db.models import Device, User
from app.db.session import get_db
from app.schemas import DeviceCreate, DeviceOut, DevicePage, DeviceUpdate, MetricOut
from app.services.devices import (
    capture_counts,
    get_visible_device,
    is_online,
    is_superadmin,
    latest_metrics,
    normalize_code,
    require_owner,
    visible_devices_query,
)

router = APIRouter(prefix="/devices", tags=["devices"])


def to_device_out(device: Device, last_metric, capture_count: int) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        code=device.code,
        name=device.name,
        location=device.location,
        owner_id=device.owner_id,
        owner_name=device.owner.name,
        last_seen_at=device.last_seen_at,
        is_online=is_online(device.last_seen_at),
        created_at=device.created_at,
        last_metric=MetricOut.model_validate(last_metric) if last_metric is not None else None,
        capture_count=capture_count,
    )


def present(db: Session, devices: list[Device]) -> list[DeviceOut]:
    ids = [device.id for device in devices]
    metrics = latest_metrics(db, ids)
    counts = capture_counts(db, ids)
    return [to_device_out(device, metrics.get(device.id), counts.get(device.id, 0)) for device in devices]


@router.get("", response_model=DevicePage)
def list_devices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    owner_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DevicePage:
    count_stmt = select(func.count()).select_from(Device)
    if is_superadmin(user):
        if owner_id is not None:
            count_stmt = count_stmt.where(Device.owner_id == owner_id)
    else:
        count_stmt = count_stmt.where(Device.owner_id == user.id)
    total = db.scalar(count_stmt) or 0
    stmt = visible_devices_query(user, owner_id)
    devices = list(db.scalars(stmt.limit(limit).offset(offset)).unique().all())
    return DevicePage(items=present(db, devices), total=total, limit=limit, offset=offset)


@router.post("", response_model=DeviceOut, status_code=201)
def create_device(
    body: DeviceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> DeviceOut:
    code = normalize_code(body.code)
    if db.scalar(select(Device.id).where(Device.code == code)) is not None:
        raise HTTPException(status_code=409, detail="Já existe uma armadilha com esse código")
    if body.owner_id is not None and not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Apenas o SuperAdmin altera o dono")
    owner_id = body.owner_id if body.owner_id is not None and is_superadmin(user) else user.id
    require_owner(db, owner_id)
    device = Device(code=code, name=body.name.strip(), location=_clean_location(body.location), owner_id=owner_id)
    db.add(device)
    db.commit()
    db.expire_all()
    loaded = get_visible_device(db, user, device.id)
    return present(db, [loaded])[0]


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeviceOut:
    device = get_visible_device(db, user, device_id)
    return present(db, [device])[0]


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: UUID,
    body: DeviceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> DeviceOut:
    device = get_visible_device(db, user, device_id)
    changes = body.model_fields_set
    if "owner_id" in changes:
        if not is_superadmin(user):
            raise HTTPException(status_code=403, detail="Apenas o SuperAdmin altera o dono")
        if body.owner_id is None:
            raise HTTPException(status_code=422, detail="Informe o dono da armadilha")
        require_owner(db, body.owner_id)
        device.owner_id = body.owner_id
    if "name" in changes and body.name is not None:
        device.name = body.name.strip()
    if "location" in changes:
        device.location = _clean_location(body.location)
    db.commit()
    db.expire_all()
    loaded = get_visible_device(db, user, device.id)
    return present(db, [loaded])[0]


def _clean_location(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
