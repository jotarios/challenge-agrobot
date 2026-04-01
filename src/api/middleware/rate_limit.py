"""Per-user rate limiter with memory eviction.

Keys by JWT user_id when authenticated, falls back to X-Forwarded-For
(for requests behind ALB/API Gateway), then client IP.
"""

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from src.shared.config import settings

_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/dashboard"}
_EVICT_INTERVAL = 300.0  # evict empty keys every 5 minutes


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._window = 60.0
        self._max_requests = settings.rate_limit_per_minute
        self._last_evict = time.time()

    def _get_client_key(self, request: Request) -> str:
        # Try JWT user_id from Authorization header (without full decode, just extract sub)
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                import jwt
                payload = jwt.decode(
                    auth[7:], settings.jwt_secret_key,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
                return f"user:{payload.get('sub', 'unknown')}"
            except Exception:
                pass

        # Behind ALB/API Gateway, use X-Forwarded-For
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        return f"ip:{request.client.host}" if request.client else "ip:unknown"

    def _evict_empty_keys(self):
        now = time.time()
        if now - self._last_evict < _EVICT_INTERVAL:
            return
        empty_keys = [k for k, v in self._requests.items() if not v]
        for k in empty_keys:
            del self._requests[k]
        self._last_evict = now

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        client_key = self._get_client_key(request)
        now = time.time()
        window_start = now - self._window

        # Clean old entries for this key
        self._requests[client_key] = [
            t for t in self._requests[client_key] if t > window_start
        ]

        if len(self._requests[client_key]) >= self._max_requests:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )

        self._requests[client_key].append(now)

        # Periodic eviction of empty keys
        self._evict_empty_keys()

        return await call_next(request)
