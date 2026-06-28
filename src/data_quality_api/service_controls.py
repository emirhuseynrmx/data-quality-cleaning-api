from __future__ import annotations

from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from data_quality_api.settings import IDEMPOTENCY_CACHE_SIZE


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    identity_hash: str
    idempotency_key_present: bool


@dataclass(frozen=True)
class CachedResponse:
    status_code: int
    body: bytes
    media_type: str | None
    headers: dict[str, str]


class IdempotencyCache:
    def __init__(self, max_size: int = IDEMPOTENCY_CACHE_SIZE) -> None:
        self.max_size = max_size
        self._items: OrderedDict[str, CachedResponse] = OrderedDict()

    def get(self, key: str) -> CachedResponse | None:
        cached = self._items.get(key)
        if cached is None:
            return None
        self._items.move_to_end(key)
        return cached

    def set(self, key: str, response: CachedResponse) -> None:
        self._items[key] = response
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, identity: str, now: float | None = None) -> tuple[bool, int]:
        current = monotonic() if now is None else now
        events = self._events[identity]
        cutoff = current - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (current - events[0])))
            return False, retry_after
        events.append(current)
        return True, 0

    def clear(self) -> None:
        self._events.clear()


class AuditLog:
    def __init__(self, max_size: int = 500) -> None:
        self.max_size = max_size
        self._events: deque[AuditEvent] = deque(maxlen=max_size)

    def add(self, event: AuditEvent) -> None:
        self._events.append(event)

    def tail(self, limit: int = 50) -> list[AuditEvent]:
        return list(self._events)[-limit:]

    def clear(self) -> None:
        self._events.clear()


class AuditTailResponse(BaseModel):
    events: list[AuditEvent] = Field(default_factory=list)


def new_request_id() -> str:
    return uuid4().hex


def identity_hash(identity: str) -> str:
    return sha256(identity.encode("utf-8")).hexdigest()[:16]
