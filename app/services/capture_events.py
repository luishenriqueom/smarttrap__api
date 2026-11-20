import queue
import threading
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.db.models import Capture, Device
from app.schemas import CaptureOut


class CaptureBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        events: queue.Queue = queue.Queue(maxsize=32)
        with self._lock:
            self._subscribers.append(events)
        return events

    def unsubscribe(self, events: queue.Queue) -> None:
        with self._lock:
            if events in self._subscribers:
                self._subscribers.remove(events)

    def publish(self, event: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for events in subscribers:
            try:
                events.put_nowait(event)
            except queue.Full:
                continue


capture_broker = CaptureBroker()


def capture_event(capture: Capture, device: Device) -> dict:
    payload = jsonable_encoder(
        CaptureOut(
            id=capture.id,
            device_id=capture.device_id,
            device_name=device.name,
            device_code=device.code,
            captured_at=capture.captured_at,
            received_at=capture.received_at,
            size_bytes=capture.size_bytes,
            manual_count=capture.manual_count,
            label=capture.label,
            notes=capture.notes,
        )
    )
    payload["owner_id"] = str(device.owner_id)
    return payload


def visible_to(role: str, user_id: UUID, event: dict) -> bool:
    if role == "superadmin":
        return True
    return event.get("owner_id") == str(user_id)
