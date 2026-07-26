from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse


class SlidingWindowLimiter:
    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.RLock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            remaining = max(0, self.requests - len(events))
            if len(events) >= self.requests:
                return False, 0
            events.append(now)
            return True, remaining - 1


def install_security_middleware(
    app,
    *,
    api_key_hashes: set[str],
    rate_limit_requests: int,
    rate_limit_window_seconds: int,
    signed_request_validator: Callable[[Request], bool] | None = None,
) -> None:
    limiter = SlidingWindowLimiter(rate_limit_requests, rate_limit_window_seconds)

    @app.middleware("http")
    async def security(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or secrets.token_hex(12)
        client = request.client.host if request.client else "unknown"
        allowed, remaining = limiter.allow(client)
        if not allowed:
            response: Response = JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMITED", "message": "Request rate limit exceeded.", "recoverable": True}},
            )
            response.headers["Retry-After"] = str(rate_limit_window_seconds)
        elif api_key_hashes and request.url.path not in {"/healthz", "/readyz"} and not (signed_request_validator and signed_request_validator(request)):
            supplied = request.headers.get("x-api-key", "")
            digest = hashlib.sha256(supplied.encode()).hexdigest()
            if not supplied or not any(secrets.compare_digest(digest, expected) for expected in api_key_hashes):
                response = JSONResponse(
                    status_code=401,
                    content={"error": {"code": "AUTH_REQUIRED", "message": "A valid API key is required.", "recoverable": False}},
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response
