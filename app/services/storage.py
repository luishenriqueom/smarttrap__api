import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def captures_root() -> Path:
    root = settings.captures_dir
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def save_jpeg(device_code: str, capture_id: uuid.UUID, captured_at: datetime, content: bytes) -> str:
    relative = Path(device_code) / f"{captured_at:%Y}" / f"{captured_at:%m}" / f"{capture_id}.jpg"
    path = captures_root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return relative.as_posix()


def resolve_capture(relative: str) -> Path:
    root = captures_root()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return path


def delete_capture_file(relative: str) -> None:
    path = resolve_capture(relative)
    path.unlink(missing_ok=True)
