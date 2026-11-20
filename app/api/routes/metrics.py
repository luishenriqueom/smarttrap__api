from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.models import Device, Metric, User
from app.db.session import get_db
from app.schemas import MetricOut, MetricPage, SeriesPoint
from app.services.devices import as_utc, get_visible_device, is_superadmin

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    resolved_end = as_utc(end) if end is not None else now
    resolved_start = as_utc(start) if start is not None else resolved_end - timedelta(days=7)
    if resolved_start > resolved_end:
        raise HTTPException(status_code=422, detail="O início do período é posterior ao fim")
    return resolved_start, resolved_end


@router.get("", response_model=MetricPage)
def list_metrics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_id: UUID | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MetricPage:
    if device_id is not None:
        get_visible_device(db, user, device_id)
    filters = _metric_filters(user, device_id, start, end)
    total = db.scalar(select(func.count()).select_from(Metric).join(Device).where(*filters)) or 0
    rows = db.scalars(
        select(Metric).join(Device).where(*filters).order_by(Metric.recorded_at.desc()).limit(limit).offset(offset)
    ).all()
    return MetricPage(
        items=[MetricOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/series", response_model=list[SeriesPoint])
def metric_series(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_id: UUID | None = None,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
) -> list[SeriesPoint]:
    resolved_start, resolved_end = _range(start, end)
    if device_id is not None:
        get_visible_device(db, user, device_id)
    device_filters = []
    if not is_superadmin(user):
        device_filters.append(Device.owner_id == user.id)
    if device_id is not None:
        device_filters.append(Device.id == device_id)
    devices = list(db.scalars(select(Device).where(*device_filters)).all())
    if not devices:
        return []
    names = {device.id: device.name for device in devices}
    rows = db.scalars(
        select(Metric)
        .where(
            Metric.device_id.in_(list(names)),
            Metric.recorded_at >= resolved_start,
            Metric.recorded_at <= resolved_end,
        )
        .order_by(Metric.recorded_at.asc())
    ).all()
    latest: dict[tuple[UUID, datetime], Metric] = {}
    for row in rows:
        moment = as_utc(row.recorded_at)
        if bucket == "hour":
            key_time = moment.replace(minute=0, second=0, microsecond=0)
        else:
            key_time = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        latest[(row.device_id, key_time)] = row
    points = [
        SeriesPoint(
            device_id=device_id,
            device_name=names[device_id],
            bucket=key_time,
            pest_count=row.pest_count,
            battery_v=row.battery_v,
        )
        for (device_id, key_time), row in latest.items()
    ]
    points.sort(key=lambda point: (point.bucket, point.device_name))
    return points


def _metric_filters(user: User, device_id: UUID | None, start: datetime | None, end: datetime | None) -> list:
    filters = []
    if not is_superadmin(user):
        filters.append(Device.owner_id == user.id)
    if device_id is not None:
        filters.append(Metric.device_id == device_id)
    if start is not None:
        filters.append(Metric.recorded_at >= as_utc(start))
    if end is not None:
        filters.append(Metric.recorded_at <= as_utc(end))
    return filters
