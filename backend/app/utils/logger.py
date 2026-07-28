"""
Structured logging configuration using structlog.
Provides JSON logging in production and pretty console logging in development.
"""

import logging
import sys
from typing import Any

import structlog


def add_app_context(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add application-level context to every log entry."""
    event_dict["app"] = "ai-codebase-assistant"
    event_dict["version"] = "2.0.0"
    return event_dict


def drop_color_message_key(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Remove the color_message key added by uvicorn."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(log_level: str = "INFO", environment: str = "development") -> None:
    """
    Configure structlog for the application.

    Development: Pretty colored console output.
    Production: JSON output for log aggregation.
    """
    is_production = environment == "production"

    # Set stdlib logging level
    log_level_int = logging.getLevelName(log_level.upper())

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level_int,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Build processor chain
    # NOTE: Do NOT use add_logger_name with PrintLoggerFactory
    # It requires BoundLogger from stdlib integration
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_app_context,
        drop_color_message_key,
    ]

    if is_production:
        processors: list[structlog.types.Processor] = shared_processors + [
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """
    Get a configured structlog logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module

    Returns:
        Bound structlog logger instance
    """
    return structlog.get_logger(name)
