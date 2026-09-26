"""in-process token-bucket rate limiting.

v1 is SINGLE-WORKER only: buckets live in this process's memory. running more than one
uvicorn worker gives each worker its own buckets and silently multiplies the effective
limit. both Dockerfiles pin --workers 1 (dev relies on it implicitly no longer; prod
overrides the command but keeps the pin). a
distributed limiter (redis or equivalent) is deferred to v2. this matches plan.md's
"operational simplicity over horizontal scaling" decision for the MVP.

limits (per plan.md, tunable via settings):
  auth  10/min/ip    - login + callback (pre-auth, so keyed by client ip)
  chat  20/min/user  - POST /conversations/{id}/messages
  sync   1/min/user  - POST /profile/sync (AniList global cap is 90/min)

applied as FastAPI dependencies on the relevant routes, not as ASGI middleware: the
per-user limits need the authenticated user, which get_current_user already resolves
and FastAPI caches within a single request, so there's no duplicate session lookup.

note (accepted v1 debt, partially addressed): buckets idle for a full window are
evicted by a sweep that runs at most once per window (see _evict_idle), so memory
is bounded by the distinct ips/users active within the last minute. the remaining
debt is distribution, not growth: revisit with the v2 distributed limiter.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.dependencies import get_current_user
from app.models.db.user import User

_WINDOW_SECONDS = 60.0


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketLimiter:
    """fixed-rate token bucket keyed by an arbitrary string.

    `capacity` tokens refill linearly over _WINDOW_SECONDS; one request costs one token.
    there is no await between read and write, so the check-and-consume is atomic on the
    single-threaded event loop (no lock needed under the single-worker assumption).
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._last_sweep: float = 0.0

    def _evict_idle(self, now: float) -> None:
        """drop buckets untouched for a full window (at most one sweep per window).

        behavior-neutral: a bucket idle >= _WINDOW_SECONDS refills to capacity on
        its next touch anyway (refill caps at capacity), so recreating it then is
        identical to keeping it. this bounds memory to keys seen in the last minute.
        """
        if now - self._last_sweep < _WINDOW_SECONDS:
            return
        self._last_sweep = now
        for key in [k for k, b in self._buckets.items() if now - b.last_refill >= _WINDOW_SECONDS]:
            del self._buckets[key]

    def check(self, key: str, capacity: int) -> None:
        now = time.monotonic()
        self._evict_idle(now)
        refill_per_sec = capacity / _WINDOW_SECONDS

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(capacity), last_refill=now)
            self._buckets[key] = bucket
        else:
            elapsed = now - bucket.last_refill
            bucket.tokens = min(float(capacity), bucket.tokens + elapsed * refill_per_sec)
            bucket.last_refill = now

        if bucket.tokens < 1.0:
            retry_after = int((1.0 - bucket.tokens) / refill_per_sec) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.tokens -= 1.0


# process-wide bucket stores, one per limit class.
_auth_limiter = TokenBucketLimiter()
_chat_limiter = TokenBucketLimiter()
_sync_limiter = TokenBucketLimiter()


def _client_ip(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


async def rate_limit_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.rate_limit_enabled:
        return
    _auth_limiter.check(f"ip:{_client_ip(request)}", settings.rate_limit_auth_per_min)


async def rate_limit_chat(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.rate_limit_enabled:
        return
    _chat_limiter.check(f"user:{user.id}", settings.rate_limit_chat_per_min)


async def rate_limit_sync(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.rate_limit_enabled:
        return
    _sync_limiter.check(f"user:{user.id}", settings.rate_limit_sync_per_min)
