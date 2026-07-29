"""
Centralized production security configuration.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


DEFAULT_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "https://ai-codebase-assistant-git-main-tirths-projects-9c208144.vercel.app",
]


def get_allowed_origins() -> List[str]:
    """
    Return safe CORS origins.

    Supports:
    - JSON array in CORS_ORIGINS
    - comma-separated values in CORS_ORIGINS
    - fallback defaults
    """
    raw = os.getenv("CORS_ORIGINS", "").strip()

    if raw and raw not in ("*", '["*"]', "[]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                result = [str(item).strip() for item in parsed if str(item).strip()]
                if result:
                    logger.info("Loaded CORS origins from JSON env: %s", result)
                    return result
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        split_values = [item.strip() for item in raw.split(",") if item.strip()]
        if split_values:
            logger.info("Loaded CORS origins from CSV env: %s", split_values)
            return split_values

    logger.info("Using default CORS origins: %s", DEFAULT_FRONTEND_ORIGINS)
    return DEFAULT_FRONTEND_ORIGINS


def get_security_config() -> dict:
    """Return consolidated security config."""
    environment = os.getenv("ENVIRONMENT", "development")
    is_production = environment == "production"

    return {
        "environment": environment,
        "is_production": is_production,
        "cors": {
            "allow_origins": get_allowed_origins(),
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "X-Request-ID",
                "Accept",
                "Origin",
            ],
            "expose_headers": [
                "X-Request-ID",
                "X-Response-Time",
            ],
            "max_age": 3600,
        },
        "rate_limiting": {
            "enabled": is_production,
            "default_requests_per_minute": 60,
            "auth_requests_per_minute": 10,
            "ai_requests_per_minute": 20,
        },
    }
