"""ASGI middleware: request IDs, request size limits, CSRF, and security headers.

These are plain ASGI middleware (not BaseHTTPMiddleware) so they can stop a
request before its body is read and add headers to every response.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCategory, error_body
from app.core.logging import request_id_var
from app.core.security import CSRF_COOKIE, CSRF_HEADER, csrf_token_is_valid

logger = logging.getLogger("app.request")

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Reading a CSRF token must itself be exempt, otherwise no client could ever get one.
_CSRF_EXEMPT_PATHS = {"/api/auth/csrf"}

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cache-control", b"no-store"),
]


async def _send_json(
    send: Send, status: int, body: dict[str, object], extra_headers: list[tuple[bytes, bytes]]
) -> None:
    payload = json.dumps(body).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode()), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return bytes(value).decode("latin-1")
    return None


class RequestContextMiddleware:
    """Assigns a request ID, adds security headers, and logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        # Accept a client-supplied ID only if it looks like one of ours, to keep logs clean.
        request_id = incoming if incoming and len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                headers.extend(h for h in _SECURITY_HEADERS if h[0] not in existing)
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # path only: query strings may carry user data
                    "status": status_holder["status"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Rejects bodies over the limit, including chunked bodies without Content-Length."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _header(scope, b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_bytes):
            await self._reject(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        await _send_json(send, 413, error_body(ErrorCategory.PAYLOAD_TOO_LARGE, "Request body is too large"), [])


class CSRFMiddleware:
    """Signed double-submit CSRF check plus an Origin allowlist for state-changing requests.

    SameSite=Lax cookies already block most cross-site POSTs; this covers older
    browsers and same-site attackers (for example a compromised subdomain).
    """

    def __init__(self, app: ASGIApp, secret: str, allowed_origins: list[str]) -> None:
        self.app = app
        self.secret = secret
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _UNSAFE_METHODS
            or not scope["path"].startswith("/api/")
            or scope["path"] in _CSRF_EXEMPT_PATHS
        ):
            await self.app(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        if origin is not None and origin not in self.allowed_origins and not self._same_origin(scope, origin):
            await self._reject(send, "Request origin is not allowed")
            return

        cookies = SimpleCookie()
        cookie_header = _header(scope, b"cookie")
        if cookie_header:
            try:
                cookies.load(cookie_header)
            except Exception:  # malformed cookie header: treat as missing
                cookies = SimpleCookie()
        cookie_value = cookies[CSRF_COOKIE].value if CSRF_COOKIE in cookies else None
        header_value = _header(scope, CSRF_HEADER.lower().encode())
        if not csrf_token_is_valid(self.secret, cookie_value, header_value):
            await self._reject(send, "Missing or invalid CSRF token")
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _same_origin(scope: Scope, origin: str) -> bool:
        host = _header(scope, b"host")
        return host is not None and origin.split("://", 1)[-1] == host

    @staticmethod
    async def _reject(send: Send, message: str) -> None:
        await _send_json(send, 403, error_body(ErrorCategory.CSRF, message), [])
