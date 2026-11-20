import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Firmware

TARGETS = ("smarttrap", "heltec")
MAX_BYTES = {
    "smarttrap": 0x1E0000,
    "heltec": 0x3E0000,
}
MIN_BYTES = 1024


def firmware_root() -> Path:
    root = settings.firmware_dir
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def resolve_firmware(relative: str) -> Path:
    root = firmware_root()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Firmware não encontrado")
    return path


def require_target(target: str) -> str:
    if target not in TARGETS:
        raise HTTPException(status_code=404, detail="Firmware desconhecido")
    return target


class StoredFirmware:
    def __init__(self, target: str, version: int, sha256: str, md5: str, size_bytes: int, relative: str, temp: Path):
        self.target = target
        self.version = version
        self.sha256 = sha256
        self.md5 = md5
        self.size_bytes = size_bytes
        self.relative = relative
        self.temp = temp


async def stage_firmware(target: str, version: int, upload: UploadFile) -> StoredFirmware:
    require_target(target)
    if version < 1 or version > 65535:
        raise HTTPException(status_code=422, detail="A versão precisa estar entre 1 e 65535")

    first = await upload.read(1)
    if not first or first[0] != 0xE9:
        raise HTTPException(status_code=422, detail="O arquivo não parece um firmware ESP32")

    digest_sha = hashlib.sha256()
    digest_md5 = hashlib.md5()
    digest_sha.update(first)
    digest_md5.update(first)
    size = 1
    relative = f"{target}-{version}.bin"
    temp = firmware_root() / f".{relative}.part"
    try:
        with temp.open("wb") as handle:
            handle.write(first)
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES[target]:
                    raise HTTPException(status_code=413, detail="O firmware excede a partição OTA")
                digest_sha.update(chunk)
                digest_md5.update(chunk)
                handle.write(chunk)
    except HTTPException:
        temp.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size < MIN_BYTES:
        temp.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="O arquivo é pequeno demais para ser um firmware")

    return StoredFirmware(target, version, digest_sha.hexdigest(), digest_md5.hexdigest(), size, relative, temp)


def commit_firmware(db: Session, staged: list[StoredFirmware]) -> list[Firmware]:
    if not staged:
        raise HTTPException(status_code=422, detail="Envie ao menos um firmware")

    rows: list[Firmware] = []
    try:
        for item in staged:
            row = db.get(Firmware, item.target)
            now = datetime.now(timezone.utc)
            if row is None:
                row = Firmware(
                    target=item.target,
                    version=item.version,
                    sha256=item.sha256,
                    md5=item.md5,
                    size_bytes=item.size_bytes,
                    file_path=item.relative,
                    created_at=now,
                )
                db.add(row)
            else:
                row.version = item.version
                row.sha256 = item.sha256
                row.md5 = item.md5
                row.size_bytes = item.size_bytes
                row.file_path = item.relative
                row.created_at = now
            rows.append(row)
        db.commit()
        for row in rows:
            db.refresh(row)
    except Exception:
        db.rollback()
        for item in staged:
            item.temp.unlink(missing_ok=True)
        raise

    root = firmware_root()
    for item in staged:
        final = root / item.relative
        item.temp.replace(final)
        for leftover in root.glob(f"{item.target}-*.bin"):
            if leftover.name != item.relative:
                leftover.unlink(missing_ok=True)
    return rows


def needs_update(current: int | None, published: int) -> bool:
    if current is None:
        return True
    return published > current
