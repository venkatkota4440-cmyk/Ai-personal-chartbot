"""Fixed-window rate limiting.

The in-memory backend is fine for a single API process (local dev, tests).
Use RATE_LIMIT_BACKEND=redis whenever more than one API process runs, so the
limit is shared.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Record one attempt. Return seconds to wait if the limit is exceeded, else None."""

    def reset(self) -> None: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        with self._lock:
            started, count = self._windows.get(key, (now, 0))
            if now - started >= window_seconds:
                started, count = now, 0
            count += 1
            self._windows[key] = (started, count)
            if len(self._windows) > 10_000:
                self._evict(now, window_seconds)
        if count > limit:
            return max(1, int(window_seconds - (now - started)))
        return None

    def _evict(self, now: float, window_seconds: int) -> None:
        stale = [k for k, (s, _) in self._windows.items() if now - s >= window_seconds]
        for k in stale:
            del self._windows[k]

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        import redis  # imported lazily so the memory backend has no Redis dependency at runtime

        self._redis = redis.Redis.from_url(redis_url, socket_timeout=1)

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        redis_key = f"ratelimit:{key}"
        pipe = self._redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds, nx=True)
        pipe.ttl(redis_key)
        count, _, ttl = pipe.execute()  # type: ignore[no-untyped-call]
        if int(count) > limit:
            return max(1, int(ttl))
        return None

    def reset(self) -> None:
        for key in self._redis.scan_iter("ratelimit:*"):
            self._redis.delete(key)


_limiter: RateLimiter | None = None


def get_rate_limiter(settings: Settings) -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = (
            RedisRateLimiter(settings.redis_url) if settings.rate_limit_backend == "redis" else MemoryRateLimiter()
        )
    return _limiter


def enforce(limiter: RateLimiter, key: str, limit: int, window_seconds: int) -> None:
    retry_after = limiter.hit(key, limit, window_seconds)
    if retry_after is not None:
        raise AppError(
            ErrorCategory.RATE_LIMITED,
            "Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )
