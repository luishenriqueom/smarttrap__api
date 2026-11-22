from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    role: str
    is_demo: bool
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    recorded_at: datetime
    received_at: datetime
    pest_count: int
    confidence: float | None
    battery_v: float | None
    rssi: float | None
    snr: float | None


class DeviceOut(BaseModel):
    id: UUID
    code: str
    name: str
    location: str | None
    owner_id: UUID
    owner_name: str
    last_seen_at: datetime | None
    is_online: bool
    created_at: datetime
    last_metric: MetricOut | None
    capture_count: int
    frame_size: str
    jpeg_quality: int
    sleep_seconds: int
    model_id: UUID | None


class DeviceCreate(BaseModel):
    code: str
    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    owner_id: UUID | None = None
    frame_size: str | None = None
    jpeg_quality: int | None = None
    sleep_seconds: int | None = None


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    owner_id: UUID | None = None
    frame_size: str | None = None
    jpeg_quality: int | None = None
    sleep_seconds: int | None = None
    model_id: UUID | None = None


class FrameConfigOut(BaseModel):
    frame_size: str
    width: int
    height: int
    jpeg_quality: int
    sleep_seconds: int


class CaptureOut(BaseModel):
    id: UUID
    device_id: UUID
    device_name: str
    device_code: str
    captured_at: datetime
    received_at: datetime
    size_bytes: int
    frame_size: str | None
    jpeg_quality: int | None
    width: int | None
    height: int | None
    manual_count: int | None
    label: str
    notes: str | None


class CaptureUpdate(BaseModel):
    manual_count: int | None = Field(default=None, ge=0)
    label: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CaptureIds(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


class CaptureDiscardResult(BaseModel):
    discarded: int


class CaptureRestoreResult(BaseModel):
    restored: int


class CaptureImportResult(BaseModel):
    imported: int
    skipped: int


class DevicePage(BaseModel):
    items: list[DeviceOut]
    total: int
    limit: int
    offset: int


class CapturePage(BaseModel):
    items: list[CaptureOut]
    total: int
    limit: int
    offset: int


class MetricPage(BaseModel):
    items: list[MetricOut]
    total: int
    limit: int
    offset: int


class MetricIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    device_code: str
    recorded_at: datetime
    pest_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    battery_v: float | None = Field(default=None, ge=0, le=100)
    rssi: float | None = None
    snr: float | None = None
    firmware_version: int | None = Field(default=None, ge=0, le=65535)


class IngestOut(BaseModel):
    id: UUID


class SeriesPoint(BaseModel):
    device_id: UUID
    device_name: str
    bucket: datetime
    pest_count: int
    battery_v: float | None


class FirmwareOut(BaseModel):
    target: str
    version: int
    sha256: str
    size_bytes: int
    created_at: datetime
    update: bool | None = None


class FirmwarePublishOut(BaseModel):
    items: list[FirmwareOut]


class SpeciesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    position: int


class SpeciesCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class AnnotationOut(BaseModel):
    id: UUID
    capture_id: UUID
    species_id: UUID
    species_name: str
    x: int
    y: int
    width: int
    height: int
    source: str
    confidence: float | None


class AnnotationCreate(BaseModel):
    species_id: UUID
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class AnnotationUpdate(AnnotationCreate):
    pass


class ModelOut(BaseModel):
    id: UUID
    status: str
    sha256: str | None
    class_labels: list[str]
    input_size: int
    window: int
    stride: int
    error: str | None
    created_at: datetime


class ModelMetaOut(BaseModel):
    sha256: str
    window: int
    stride: int
    classes: list[str]
    threshold: float = 0.6
