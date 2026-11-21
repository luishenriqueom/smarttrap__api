WINDOW = 96
STRIDE = 64


def window_origins(length: int, window: int = WINDOW, stride: int = STRIDE) -> list[int]:
    if length <= 0:
        return []
    if length <= window:
        return [0]
    last = length - window
    origins = list(range(0, last, stride))
    if origins[-1] != last:
        origins.append(last)
    return origins


def clip_box(x: int, y: int, width: int, height: int, origin_x: int, origin_y: int, window: int = WINDOW) -> tuple[int, int, int, int] | None:
    left = max(x, origin_x)
    top = max(y, origin_y)
    right = min(x + width, origin_x + window)
    bottom = min(y + height, origin_y + window)
    if right - left < 1 or bottom - top < 1:
        return None
    return left - origin_x, top - origin_y, right - left, bottom - top
