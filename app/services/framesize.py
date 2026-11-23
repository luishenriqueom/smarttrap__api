from fastapi import HTTPException

FRAME_SIZES: dict[str, tuple[int, int]] = {
    "qqvga": (160, 120),
    "qvga": (320, 240),
    "vga": (640, 480),
    "svga": (800, 600),
    "xga": (1024, 768),
    "sxga": (1280, 1024),
    "uxga": (1600, 1200),
}
DEFAULT_FRAME_SIZE = "svga"
DEFAULT_JPEG_QUALITY = 12
MIN_JPEG_QUALITY = 4
MAX_JPEG_QUALITY = 63
DEFAULT_SLEEP_SECONDS = 300
DEFAULT_OPERATING_MODE = "collect"
OPERATING_MODES = {"collect", "infer"}
MIN_SLEEP_SECONDS = 60
MAX_SLEEP_SECONDS = 86400
_SOF = {0xC0, 0xC1, 0xC2, 0xC3}


def require_frame_size(value: str) -> str:
    token = value.strip().lower()
    if token not in FRAME_SIZES:
        raise HTTPException(status_code=422, detail="Resolução inválida")
    return token


def require_sleep_seconds(value: int) -> int:
    if value < MIN_SLEEP_SECONDS or value > MAX_SLEEP_SECONDS:
        raise HTTPException(status_code=422, detail="O intervalo de sono deve ficar entre 1 minuto e 24 horas")
    return value


def require_operating_mode(value: str) -> str:
    token = value.strip().lower()
    if token not in OPERATING_MODES:
        raise HTTPException(status_code=422, detail="Modo inválido")
    return token


def require_jpeg_quality(value: int) -> int:
    if value < MIN_JPEG_QUALITY or value > MAX_JPEG_QUALITY:
        raise HTTPException(
            status_code=422,
            detail="A qualidade JPEG deve ficar entre 4 e 63. Um número menor deixa o arquivo maior e mais nítido.",
        )
    return value


def recorded_quality(reported: str | None) -> int | None:
    if reported is None or reported.strip() == "":
        return None
    try:
        value = int(reported.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Qualidade JPEG inválida") from exc
    return require_jpeg_quality(value)


def jpeg_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 4 or content[:2] != b"\xff\xd8":
        return None
    index = 2
    limit = len(content)
    while index + 3 < limit:
        if content[index] != 0xFF:
            return None
        while index < limit and content[index] == 0xFF:
            index += 1
        if index >= limit:
            return None
        marker = content[index]
        index += 1
        if marker in (0xD8, 0xD9, 0xDA) or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            if marker in (0xD9, 0xDA):
                return None
            continue
        if index + 2 > limit:
            return None
        length = int.from_bytes(content[index : index + 2], "big")
        if length < 2 or index + length > limit:
            return None
        if marker in _SOF and length >= 7:
            height = int.from_bytes(content[index + 3 : index + 5], "big")
            width = int.from_bytes(content[index + 5 : index + 7], "big")
            if width > 0 and height > 0:
                return width, height
            return None
        index += length
    return None


def recorded_size(content: bytes, reported: str | None) -> tuple[str | None, int | None, int | None]:
    token = None
    if reported is not None and reported.strip() != "":
        token = require_frame_size(reported)
    parsed = jpeg_dimensions(content)
    if parsed is not None:
        return token, parsed[0], parsed[1]
    if token is None:
        return None, None, None
    width, height = FRAME_SIZES[token]
    return token, width, height
