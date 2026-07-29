"""
Security middleware for production hardening.

Includes:
- Security headers middleware
- Request ID middleware
- Basic malicious URL/path sanitization middleware
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP-style security headers to every response."""

    def __init__(self, app: ASGIApp, environment: str = "production") -> None:
        super().__init__(app)
        self.environment = environment
        self.is_production = environment == "production"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to all responses."""
        response = await call_next(request)

        if self.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none';"
        )

        # Try to avoid leaking server tech where possible
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach request IDs and response timing to every request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - request.state.start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
        return response


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Block obviously malicious URL patterns before routing."""

    BLOCKED_PATTERNS = [
        "../",
        "..\\",
        "<script",
        "javascript:",
        "vbscript:",
        "%2e%2e",
        "%00",
        "etc/passwd",
        "win.ini",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        url_path = request.url.path.lower()
        query = str(request.url.query).lower()
        full_input = f"{url_path}?{query}"

        for pattern in self.BLOCKED_PATTERNS:
            if pattern in full_input:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Invalid request",
                        "request_id": getattr(request.state, "request_id", "unknown"),
                    },
                )

        return await call_next(request)
