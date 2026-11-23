import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Capture, Device, Metric, User
from app.services.framesize import require_operating_mode

CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ONLINE_WINDOW = timedelta(minutes=15)
CLOCK_EPOCH = 1_700_000_000
CLOCK_SYNC_TOLERANCE = timedelta(seconds=120)


def normalize_code(value: str) -> str:
    code = value.strip()
    if not CODE_RE.fullmatch(code):
        raise HTTPException(
            status_code=422,
            detail="O código da armadilha deve ter 1 a 64 caracteres (letras, números, _ ou -).",
        )
    return code


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data inválida. Use ISO-8601.") from exc
    return as_utc(parsed)


def apply_reported_mode(device: Device, raw: str | None) -> None:
    if raw is None or raw.strip() == "":
        return
    device.reported_mode = require_operating_mode(raw)


def apply_reported_clock(device: Device, unix_time: int | None, now: datetime) -> None:
    if unix_time is None:
        return
    device.last_clock_received_at = now
    if unix_time < CLOCK_EPOCH:
        device.last_clock_at = None
        return
    reported = datetime.fromtimestamp(unix_time, timezone.utc)
    device.last_clock_at = reported
    if device.clock_sync_requested and abs(now - reported) <= CLOCK_SYNC_TOLERANCE:
        device.clock_sync_requested = False


def parse_device_time(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip()
    if text == "":
        return None
    if not text.isdigit() or int(text) > 0xFFFFFFFF:
        raise HTTPException(status_code=422, detail="device_time inválido")
    return int(text)


def is_online(last_seen_at: datetime | None, now: datetime | None = None) -> bool:
    if last_seen_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current - as_utc(last_seen_at) <= ONLINE_WINDOW


def is_superadmin(user: User) -> bool:
    return user.role == "superadmin"


def visible_devices_query(user: User, owner_id: uuid.UUID | None = None):
    stmt = select(Device).options(joinedload(Device.owner)).order_by(Device.name)
    if is_superadmin(user):
        if owner_id is not None:
            stmt = stmt.where(Device.owner_id == owner_id)
        return stmt
    return stmt.where(Device.owner_id == user.id)


def get_visible_device(db: Session, user: User, device_id: uuid.UUID) -> Device:
    stmt = select(Device).options(joinedload(Device.owner)).where(Device.id == device_id)
    if not is_superadmin(user):
        stmt = stmt.where(Device.owner_id == user.id)
    device = db.scalar(stmt)
    if device is None:
        raise HTTPException(status_code=404, detail="Armadilha não encontrada")
    return device


def latest_metrics(db: Session, device_ids: list[uuid.UUID]) -> dict[uuid.UUID, Metric]:
    if not device_ids:
        return {}
    latest_time = (
        select(Metric.device_id, func.max(Metric.recorded_at).label("recorded_at"))
        .where(Metric.device_id.in_(device_ids))
        .group_by(Metric.device_id)
        .subquery()
    )
    rows = db.scalars(
        select(Metric).join(
            latest_time,
            (Metric.device_id == latest_time.c.device_id) & (Metric.recorded_at == latest_time.c.recorded_at),
        )
    ).all()
    return {row.device_id: row for row in rows}


def capture_counts(db: Session, device_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not device_ids:
        return {}
    rows = db.execute(
        select(Capture.device_id, func.count())
        .where(Capture.device_id.in_(device_ids), Capture.deleted_at.is_(None))
        .group_by(Capture.device_id)
    ).all()
    return {device_id: count for device_id, count in rows}


def get_or_create_device(db: Session, code: str) -> Device:
    device = db.scalar(select(Device).where(Device.code == code))
    if device is not None:
        return device
    admin = db.scalar(select(User).where(User.role == "superadmin").order_by(User.created_at))
    if admin is None:
        raise HTTPException(status_code=500, detail="SuperAdmin não encontrado")
    device = Device(code=code, name=code, owner_id=admin.id)
    db.add(device)
    db.flush()
    return device


def require_owner(db: Session, owner_id: uuid.UUID) -> User:
    owner = db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=422, detail="Dono da armadilha inválido")
    return owner
